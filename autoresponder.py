"""Reply once to new comments on the owner's posts using the official API."""
import argparse,json,os,subprocess
from datetime import datetime,timezone
from pathlib import Path
from secrets import choice
import publisher as p

ROOT=Path(__file__).resolve().parent
FIELDS='id,text,timestamp,username,is_reply_owned_by_me,replied_to,hide_status'
class RequestBudget(Exception):pass

class BudgetAPI:
 def __init__(self,api,limit):self.api=api;self.limit=limit;self.calls=0
 def call(self,*args,**kwargs):
  if self.calls>=self.limit:raise RequestBudget('Per-run API budget reached')
  self.calls+=1;return self.api.call(*args,**kwargs)

class ReplyLedger:
 def __init__(self,root=ROOT):
  self.root=root;self.path=root/'auto-reply-state.json'
  self.data=json.loads(self.path.read_text()) if self.path.exists() else {'jobs':{},'scan_offset':0}
 def save(self):
  p.save(self.path,self.data)
  if os.environ.get('PERSIST_GIT')!='1':return
  commands=[['git','config','user.name','threads-replies[bot]'],['git','config','user.email','threads-replies@users.noreply.github.com'],['git','add',self.path.name],['git','commit','-m','Record automatic comment reply state']]
  for cmd in commands:subprocess.run(cmd,cwd=self.root,check=True,capture_output=True)
  for attempt in range(3):
   result=subprocess.run(['git','push','origin','HEAD:main'],cwd=self.root,capture_output=True)
   if result.returncode==0:return
   subprocess.run(['git','fetch','origin','main'],cwd=self.root,check=True,capture_output=True)
   subprocess.run(['git','rebase','origin/main'],cwd=self.root,check=True,capture_output=True)
  raise RuntimeError('Reply ledger could not be persisted; publication stopped')
 def update(self,cid,**changes):
  item=dict(self.data['jobs'].get(cid,{}));item.update(changes,updated_at=p.stamp());self.data['jobs'][cid]=item;self.save()
 def offset(self,value):
  if self.data.get('scan_offset')!=value:self.data['scan_offset']=value;self.save()

def config(root=ROOT):
 value=json.loads((root/'auto-reply-config.json').read_text())
 if value.get('account')!='1fatherx' or value.get('reply_mode')!='public_comment_reply':raise RuntimeError('Unexpected reply account or mode')
 templates=value.get('reply_templates')
 if not isinstance(templates,list) or not templates or not all(isinstance(x,str) and 1<=len(x)<=500 for x in templates):raise RuntimeError('Invalid reply templates')
 if len(set(templates))!=len(templates):raise RuntimeError('Duplicate reply templates')
 datetime.fromisoformat(value['starts_at'])
 return value

def pages(api,path,fields,max_pages=30):
 cursor=None
 for _ in range(max_pages):
  args={'fields':fields,'limit':100}
  if cursor:args['after']=cursor
  result=api.call('GET',path,**args);yield result.get('data',[])
  paging=result.get('paging',{})
  if not paging.get('next'):return
  cursor=paging.get('cursors',{}).get('after')
  if not cursor:raise RuntimeError('API pagination cursor unavailable')
 raise RuntimeError('Pagination limit reached; stop rather than silently omit comments')

def roots(api,cfg):
 items=[]
 for page in pages(api,'me/threads','id,is_reply,has_replies',cfg['max_root_pages']):
  items.extend(x['id'] for x in page if x.get('is_reply') is False and x.get('has_replies') is True)
 return items

def conversation(api,root,cfg):
 items=[]
 for page in pages(api,str(root)+'/conversation',FIELDS):
  items.extend(page)
  # Inspect all pages for consistency; APIs can change their default ordering.
 return items

def owned(comment,account):
 return comment.get('is_reply_owned_by_me') is True or str(comment.get('username') or '').lower().lstrip('@')==account

def candidates(items,cfg):
 cutoff=datetime.fromisoformat(cfg['starts_at']);account=cfg['account']
 answered={str(x['replied_to']['id']):x for x in items if owned(x,account) and isinstance(x.get('replied_to'),dict) and x['replied_to'].get('id')}
 result=[]
 for x in items:
  if owned(x,account) or not x.get('id') or not x.get('timestamp'):continue
  if datetime.fromisoformat(x['timestamp'])<=cutoff:continue
  if str(x.get('hide_status') or 'NOT_HUSHED').upper() not in ('NOT_HUSHED','UNHUSHED'):continue
  result.append(x)
 return sorted(result,key=lambda x:x['timestamp']),answered

def answer(api,me,comment,root,cfg,ledger):
 cid=str(comment['id']);previous=ledger.data['jobs'].get(cid,{})
 if previous.get('state') in ('published','already_answered','publishing','needs_reconciliation','failed'):return previous.get('state')
 text=previous.get('reply_text') or choice(cfg['reply_templates'])
 container=str(api.call('POST',str(me['id'])+'/threads',media_type='TEXT',text=text,reply_to_id=cid,auto_publish_text='false')['id'])
 p.ready(api,container)
 if api.limit-api.calls<1:raise RequestBudget('Reserve the publish request before saving intent')
 # This durable intent must reach GitHub before any public publish request.
 ledger.update(cid,state='publishing',root_id=str(root),container_id=container,reply_text=text)
 try:
  result=api.call('POST',str(me['id'])+'/threads_publish',creation_id=container)
  reply_id=str(result['id'])
 except Exception:
  ledger.update(cid,state='needs_reconciliation',error='Publish response unavailable; do not retry blindly')
  return 'needs_reconciliation'
 ledger.update(cid,state='published',published_id=reply_id,published_at=p.stamp())
 return 'published'

def run(api,cfg,ledger,mode='scan',at=None):
 at=at or datetime.now(timezone.utc);budget=BudgetAPI(api,cfg['max_requests_per_run']);me=p.identity(budget)
 root_ids=roots(budget,cfg);start=int(ledger.data.get('scan_offset',0))%max(1,len(root_ids))
 ordered=root_ids[start:]+root_ids[:start];sent=0;eligible=0;scanned=0;limited=False
 today=at.date().isoformat();daily=sum(x.get('state')=='published' and x.get('published_at','').startswith(today) for x in ledger.data['jobs'].values())
 if mode=='check':
  if root_ids:budget.call('GET',str(root_ids[0])+'/conversation',fields=FIELDS,limit=1)
  else:
   sample=budget.call('GET','me/threads',fields='id',limit=1).get('data',[])
   if sample:budget.call('GET',str(sample[0]['id'])+'/replies',fields=FIELDS,limit=1)
  return {'state':'verified','username':me['username'],'reply_access_verified':True,'published_by_this_run':0}
 for index,rid in enumerate(ordered):
  try:
   items=conversation(budget,rid,cfg);comments,answered=candidates(items,cfg)
   for comment in comments:
    cid=str(comment['id']);state=ledger.data['jobs'].get(cid,{}).get('state')
    if cid in answered:
     if mode=='run' and state in ('publishing','needs_reconciliation'):
      existing=answered[cid];saved=ledger.data['jobs'][cid].get('reply_text')
      matches=existing.get('text')==saved if saved else existing.get('text') in cfg['reply_templates']
      ledger.update(cid,state='published' if matches else 'already_answered',published_id=str(existing['id']),reconciled=True,published_at=p.stamp())
     continue
    if state in ('published','already_answered','publishing','needs_reconciliation','failed'):continue
    eligible+=1
    if mode!='run':continue
    if sent>=cfg['max_replies_per_run'] or daily+sent>=cfg['max_replies_per_day']:limited=True;break
    if budget.limit-budget.calls<4:raise RequestBudget('Reserve API calls for a complete reply')
    outcome=answer(budget,me,comment,rid,cfg,ledger)
    sent+=int(outcome=='published')
   scanned+=1
   if limited:break
  except RequestBudget:limited=True;break
 if mode=='run' and root_ids:ledger.offset((start+scanned)%len(root_ids))
 return {'state':'active' if mode=='run' else 'dry_run','username':me['username'],'roots_with_replies':len(root_ids),'roots_scanned':scanned,'eligible_comments':eligible,'published_by_this_run':sent,'limited':limited,'api_requests':budget.calls}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['check','scan','run'],default='scan');args=parser.parse_args()
 cfg=config()
 if args.mode=='run' and os.environ.get('AUTO_REPLY_ENABLED')!='true':
  print(json.dumps({'state':'inactive','published_by_this_run':0}));return
 from credentials import load_token
 api=p.API(load_token(ROOT));result=run(api,cfg,ReplyLedger(),args.mode);print(json.dumps(result))

if __name__=='__main__':
 try:main()
 except Exception as error:
  print(json.dumps({'state':'reply_worker_stopped','error':str(error) if isinstance(error,RuntimeError) else type(error).__name__,'published_by_this_run':None,'publication_receipts':'auto-reply-state.json'}));raise SystemExit(1)
