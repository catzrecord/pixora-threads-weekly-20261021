"""Six-month owner-authorized campaign, using Meta's official Threads API."""
import argparse, hashlib, json, os, re, ssl, subprocess, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parent
API_BASE='https://graph.threads.net/v1.0/'
CAMPAIGN_START=datetime.fromisoformat('2026-10-21T00:00:00+07:00')
CAMPAIGN_END=datetime.fromisoformat('2027-04-21T00:00:00+07:00')
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
  url=('https://graph.threads.net/' if path=='refresh_access_token' else API_BASE)+path.lstrip('/');body=None
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
 if len(posts)!=546 or approval['account']!='1fatherx' or approval['start']!='2026-10-21' or approval['end']!='2027-04-20':raise RuntimeError('Unexpected campaign scope')
 expected={(CAMPAIGN_START+timedelta(days=d)).date().isoformat()+'T'+t+':00+07:00' for d in range(182) for t in ('08:30','13:00','20:00')}
 if {p['due'] for p in posts}!=expected or len({p['id'] for p in posts})!=546:raise RuntimeError('Missing or duplicate campaign slot')
 if posts!=sorted(posts,key=lambda p:p['due']):raise RuntimeError('Schedule is not chronological')
 demo_policy=approval.get('owner_screen_recording_revision')
 for p in posts:
  expected=['IMAGE','VIDEO']
  if demo_policy and p['id'] not in demo_policy['preserved_job_ids']:
   expected+=['VIDEO']
   demo=p['media'][-1]
   if demo.get('kind')!='owner_screen_recording' or demo.get('sha256') not in demo_policy['recording_sha256']:raise RuntimeError('Owned screen recording missing or changed')
   if demo['sha256']==p['media'][1]['sha256']:raise RuntimeError('Duplicate primary and screen recording video')
  if len(p['text'])>500 or [x['type'] for x in p['media']]!=expected:raise RuntimeError('Invalid carousel')
  if re.search(r'pixora|indo\s*photo',p['text'],re.I) or 'komen mau' not in p['text'].lower():raise RuntimeError('Caption violates approved sales voice')
  if not CAMPAIGN_START<=datetime.fromisoformat(p['due'])<CAMPAIGN_END:raise RuntimeError('Date outside approved campaign')
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
 if not CAMPAIGN_START<=at<CAMPAIGN_END:
  return {'state':'outside_approved_campaign','published_by_this_run':0}
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

def wait_for_due(posts,ledger,target_due,clock=now,sleep=time.sleep,report=print):
 """Arm exactly one approved slot before its deadline; never publish while waiting."""
 matching=[post for post in posts if post['due']==target_due]
 if len(matching)!=1:raise RuntimeError('Armed time must match exactly one approved slot')
 post=matching[0];due=datetime.fromisoformat(target_due);at=clock()
 if ledger.get(post['id'])['state'] in ('published','publishing','needs_reconciliation','missed'):
  return {'state':'already_recorded','post_id':post['id'],'published_by_this_run':0}
 if (due-at).total_seconds()>10800:raise RuntimeError('Cannot arm a slot more than three hours early')
 if (at-due).total_seconds()>1800:
  return {'state':'target_too_late','post_id':post['id'],'published_by_this_run':0}
 report(json.dumps({'state':'armed','post_id':post['id'],'due':target_due,
  'wait_seconds':max(0,int((due-at).total_seconds())),'published_by_this_run':0}),flush=True)
 while clock()<due:sleep(min(30,max(0,(due-clock()).total_seconds())))
 return {'state':'due','post_id':post['id'],'published_by_this_run':0}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['dry-run','check','preflight','due','wait-due','maintain'],default='dry-run')
 parser.add_argument('--due',default='')
 args=parser.parse_args();posts=load_schedule()
 if args.mode=='dry-run':
  print(json.dumps({'state':'dry_run','posts':len(posts),'next_due':posts[0]['due'],'network_requests':0}));return
 if args.mode in ('due','wait-due') and os.environ.get('PUBLISH_ENABLED')!='true':
  print(json.dumps({'state':'inactive','published_by_this_run':0}));return
 if args.mode in ('due','wait-due') and not CAMPAIGN_START<=now()<CAMPAIGN_END:
  print(json.dumps({'state':'outside_approved_campaign','published_by_this_run':0}));return
 if args.mode=='wait-due':
  result=wait_for_due(posts,Ledger(),args.due)
  if result['state']!='due':print(json.dumps(result));return
  # Timers can start well before publication. Read the latest receipts, approved
  # media and renewed credential after the wait, under the workflow's one lock.
  if os.environ.get('PERSIST_GIT')=='1':
   subprocess.run(['git','pull','--ff-only','origin','main'],cwd=ROOT,check=True,capture_output=True)
  posts=[post for post in load_schedule() if post['due']==args.due]
  if len(posts)!=1:raise RuntimeError('Armed slot is no longer approved')
 from credentials import load_token, maintain
 if args.mode=='maintain':
  if not CAMPAIGN_START<=now()<CAMPAIGN_END:
   print(json.dumps({'state':'outside_approved_campaign','published_by_this_run':0}));return
  print(json.dumps(maintain(ROOT)));return
 token=load_token(ROOT)
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
