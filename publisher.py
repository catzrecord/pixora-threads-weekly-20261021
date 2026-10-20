"""One-week approved campaign dispatcher, using only Meta's official Threads API."""
import argparse, hashlib, json, os, ssl, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parent
API_BASE='https://graph.threads.net/v1.0/'
# The system CA bundle is needed by this Mac's standalone Python installation.
TLS=ssl.create_default_context(cafile='/etc/ssl/cert.pem') if sys.platform=='darwin' else ssl.create_default_context()

def now():return datetime.now(timezone.utc)
def stamp():return now().isoformat()
def checksum(data):return hashlib.sha256(data).hexdigest()
def save(path,value):
 temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temp.replace(path)

class API:
 def __init__(self,token):self.token=token
 def call(self,method,path,**params):
  url=API_BASE+path.lstrip('/');body=None
  if method=='GET' and params:url+='?'+urlencode(params)
  elif method=='POST':body=urlencode(params).encode()
  request=Request(url,data=body,method=method,headers={
   'Authorization':'Bearer '+self.token,'Content-Type':'application/x-www-form-urlencoded',
   'User-Agent':'PIXORA-Weekly-Threads-Publisher/1.0'})
  try:
   with urlopen(request,timeout=60,context=TLS) as response:return json.load(response)
  except HTTPError as error:
   try:message=json.loads(error.read()).get('error',{}).get('message','Request rejected')
   except Exception:message='Request rejected'
   raise RuntimeError(f'Threads API HTTP {error.code}: '+message.replace(self.token,'[redacted]')) from None
  except (URLError,TimeoutError):raise RuntimeError('Threads API network response unavailable') from None

def load_schedule(root=ROOT):
 raw=(root/'schedule.json').read_bytes();approval=json.loads((root/'approval.json').read_text())
 if checksum(raw)!=approval['schedule_sha256']:raise RuntimeError('Approved schedule changed')
 posts=json.loads(raw)
 if len(posts)!=21 or approval['account']!='1fatherx':raise RuntimeError('Unexpected campaign scope')
 for p in posts:
  if len(p['text'])>500 or [x['type'] for x in p['media']]!=['IMAGE','VIDEO']:raise RuntimeError('Invalid carousel')
  if not '2026-10-21'<=p['due'][:10]<='2026-10-27':raise RuntimeError('Date outside approved week')
 return posts

class Ledger:
 def __init__(self,root=ROOT):
  self.root=root;self.path=root/'state.json'
  self.data=json.loads(self.path.read_text()) if self.path.exists() else {'jobs':{}}
 def get(self,pid):return self.data['jobs'].get(pid,{'state':'pending','children':[]})
 def update(self,pid,**changes):
  record=dict(self.get(pid));record.update(changes,updated_at=stamp())
  self.data['jobs'][pid]=record;save(self.path,self.data)
  if os.environ.get('PERSIST_GIT')=='1':
   # Persist before publish: if push fails, no publication request is sent.
   for cmd in [
    ['git','config','user.name','pixora-weekly-publisher[bot]'],
    ['git','config','user.email','pixora-weekly-publisher@users.noreply.github.com'],
    ['git','add','state.json'],
    ['git','commit','-m',f'Record {pid} {record["state"]}'],
    ['git','push','origin','HEAD:main'],
   ]:subprocess.run(cmd,cwd=self.root,check=True,capture_output=True)
  return record

def identity(api):
 me=api.call('GET','me',fields='id,username')
 if me.get('username','').lower().lstrip('@')!='1fatherx':raise RuntimeError('API account is not @1fatherx')
 quota=api.call('GET',str(me['id'])+'/threads_publishing_limit',fields='quota_usage,config')
 rows=quota.get('data',[])
 if not rows:raise RuntimeError('Publishing quota unavailable')
 config=rows[0].get('config',{});limit=config.get('quota_total')
 if limit is None or rows[0].get('quota_usage',0)>=int(limit):raise RuntimeError('Publishing quota unavailable or exhausted')
 return me

def verify_asset(item):
 parsed=urlparse(item['url'])
 if parsed.scheme!='https' or parsed.hostname!='github.com':raise RuntimeError('Unexpected approved media host')
 req=Request(item['url'],headers={'User-Agent':'PIXORA-Weekly-Media-Check/1.0'})
 h=hashlib.sha256();size=0;first=b''
 with urlopen(req,timeout=90,context=TLS) as response:
  mime=response.headers.get('Content-Type','').split(';')[0]
  expected='image/' if item['type']=='IMAGE' else 'video/'
  # Release CDN downloads can use a generic binary MIME despite correct media bytes.
  if not mime.startswith(expected) and mime!='application/octet-stream':raise RuntimeError('Hosted media has wrong MIME type')
  for block in iter(lambda:response.read(1024*1024),b''):
   if not first:first=block[:16]
   size+=len(block)
   if size>item['bytes']:raise RuntimeError('Hosted media exceeds approved size')
   h.update(block)
 if size!=item['bytes'] or h.hexdigest()!=item['sha256']:raise RuntimeError('Hosted media differs from approved file')
 if item['type']=='IMAGE' and not (first.startswith(b'\x89PNG\r\n\x1a\n') or first.startswith(b'\xff\xd8\xff')):
  raise RuntimeError('Hosted image format is invalid')
 if item['type']=='VIDEO' and first[4:8]!=b'ftyp':raise RuntimeError('Hosted video is not MP4')

def ready(api,cid,sleep=time.sleep):
 for _ in range(12):
  status=api.call('GET',cid,fields='status,error_message').get('status')
  if status=='FINISHED':return
  if status in ('ERROR','EXPIRED'):raise RuntimeError('Media container '+status)
  sleep(15)
 raise RuntimeError('Media container still processing; resume same container')

def publish(post,api,ledger,verify=verify_asset,sleep=time.sleep):
 pid=post['id'];record=ledger.get(pid)
 if record['state'] in ('published','publishing','needs_reconciliation','missed'):return record['state']
 me=identity(api)
 for item in post['media']:verify(item)
 children=list(record.get('children',[]))
 for item in post['media'][len(children):]:
  params={'media_type':item['type'],'is_carousel_item':'true','alt_text':item['alt_text']}
  params['image_url' if item['type']=='IMAGE' else 'video_url']=item['url']
  cid=str(api.call('POST',str(me['id'])+'/threads',**params)['id'])
  children.append(cid)
  ledger.update(pid,state='children_created',children=children)
 for child in children:ready(api,child,sleep)
 record=ledger.get(pid);parent=record.get('container_id')
 if not parent:
  parent=str(api.call('POST',str(me['id'])+'/threads',media_type='CAROUSEL',
   children=','.join(children),text=post['text'])['id'])
  ledger.update(pid,state='container_created',container_id=parent,children=children)
 ready(api,parent,sleep)
 ledger.update(pid,state='publishing',container_id=parent)
 try:
  result=api.call('POST',str(me['id'])+'/threads_publish',creation_id=parent)
  published_id=str(result['id'])
 except Exception:
  ledger.update(pid,state='needs_reconciliation',error='Publish response unavailable; do not automatically retry')
  return 'needs_reconciliation'
 permalink=''
 try:permalink=api.call('GET',published_id,fields='id,permalink').get('permalink','')
 except Exception:pass
 ledger.update(pid,state='published',published_id=published_id,permalink=permalink)
 return 'published'

def dispatch(posts,api,ledger,at=None,enabled=False,verify=verify_asset,sleep=time.sleep):
 at=at or now()
 if not enabled:return {'state':'inactive','published_by_this_run':0}
 # Never publish outside this explicitly approved one-week experiment.
 if at.isoformat()<'2026-10-21T00:00:00+00:00' or at.isoformat()>='2026-10-28T00:00:00+00:00':
  return {'state':'outside_approved_week','published_by_this_run':0}
 for post in posts:
  age=(at-datetime.fromisoformat(post['due'])).total_seconds()
  record=ledger.get(post['id'])
  if age<0:continue
  if record['state'] in ('published','publishing','needs_reconciliation','missed'):continue
  if age>1800:
   ledger.update(post['id'],state='missed',error='More than 30 minutes late; no catch-up burst');continue
  state=publish(post,api,ledger,verify,sleep)
  return {'state':state,'post_id':post['id'],'published_by_this_run':int(state=='published')}
 return {'state':'no_due_post','published_by_this_run':0}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['dry-run','check','preflight','due'],default='dry-run')
 args=parser.parse_args();posts=load_schedule()
 if args.mode=='dry-run':
  print(json.dumps({'state':'dry_run','posts':len(posts),'next_due':posts[0]['due'],'network_requests':0}));return
 if args.mode=='due' and os.environ.get('PUBLISH_ENABLED')!='true':
  print(json.dumps({'state':'inactive','published_by_this_run':0}));return
 token=os.environ.get('THREADS_ACCESS_TOKEN','')
 if not token:raise RuntimeError('THREADS_ACCESS_TOKEN has not been configured')
 api=API(token)
 if args.mode in ('check','preflight'):
  me=identity(api)
  if args.mode=='preflight':
   for post in posts[:3]:
    for item in post['media']:verify_asset(item)
  print(json.dumps({'state':'verified','username':me['username'],'media_first_day_checked':args.mode=='preflight','published_by_this_run':0}));return
 result=dispatch(posts,api,Ledger(),enabled=os.environ.get('PUBLISH_ENABLED')=='true')
 print(json.dumps(result))

if __name__=='__main__':
 try:main()
 except Exception as e:
  # Avoid dumping request objects, environment variables or credentials.
  print(json.dumps({'state':'error','error':type(e).__name__,'message':str(e).replace(os.environ.get('THREADS_ACCESS_TOKEN') or '\0','[redacted]')}))
  raise SystemExit(1)
