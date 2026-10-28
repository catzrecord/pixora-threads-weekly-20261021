import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import autoresponder as a

CFG={'account':'1fatherx','reply_mode':'public_comment_reply','reply_templates':['DM gw ya kak.','DM gw. thanks'],'starts_at':'2026-10-28T15:00:00+00:00','max_replies_per_run':5,'max_replies_per_day':100,'max_requests_per_run':50,'max_root_pages':30}
def comment(cid='COMMENT',**changes):
 value={'id':cid,'timestamp':'2026-10-28T15:10:00+00:00','username':'visitor','is_reply_owned_by_me':False,'hide_status':'NOT_HUSHED'};value.update(changes);return value

class API:
 def __init__(self,comments=None,username='1fatherx',fail=False,deny=False):
  self.comments=comments if comments is not None else [comment()];self.username=username;self.calls=[];self.fail=fail;self.deny=deny;self.before_publish=None
 def call(self,method,path,**params):
  self.calls.append((method,path,params))
  if path=='me':return {'id':'OWNER','username':self.username}
  if path.endswith('threads_publishing_limit'):return {'data':[{'quota_usage':0,'config':{'quota_total':250}}]}
  if path=='me/threads':
   if self.deny:raise RuntimeError('Threads API HTTP 403: permission missing')
   return {'data':[{'id':'ROOT','is_reply':False,'has_replies':True},{'id':'OWN_REPLY','is_reply':True,'has_replies':True}]}
  if path=='ROOT/conversation':return {'data':self.comments}
  if path=='OWNER/threads':return {'id':'DRAFT'}
  if path=='DRAFT':return {'status':'FINISHED'}
  if path=='OWNER/threads_publish':
   if self.before_publish:self.before_publish()
   if self.fail:raise TimeoutError()
   return {'id':'PUBLISHED_REPLY'}
  raise AssertionError((method,path))

class AutoReplyTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.ledger=a.ReplyLedger(self.root);self.cfg=copy.deepcopy(CFG)
 def tearDown(self):self.tmp.cleanup()
 def test_exact_text_and_comment_target_with_durable_intent(self):
  api=API();api.before_publish=lambda:self.assertEqual(json.loads(self.ledger.path.read_text())['jobs']['COMMENT']['state'],'publishing')
  with patch.object(a,'choice',return_value='DM gw ya kak.'):out=a.run(api,self.cfg,self.ledger,'run')
  self.assertEqual(out['published_by_this_run'],1)
  created=next(x[2] for x in api.calls if x[1]=='OWNER/threads')
  self.assertEqual(created,{'media_type':'TEXT','text':'DM gw ya kak.','reply_to_id':'COMMENT','auto_publish_text':'false'})
  self.assertEqual(self.ledger.data['jobs']['COMMENT']['published_id'],'PUBLISHED_REPLY')
 def test_second_run_never_duplicates_a_reply(self):
  a.run(API(),self.cfg,self.ledger,'run');api=API();a.run(api,self.cfg,self.ledger,'run')
  self.assertFalse(any(x[0]=='POST' for x in api.calls))
 def test_old_comments_own_comments_and_hidden_comments_are_ignored(self):
  items=[comment('OLD',timestamp='2026-10-27T15:00:00+00:00'),comment('OWN',username='1fatherx'),comment('PRIVATE',username=None,is_reply_owned_by_me=True),comment('HIDDEN',hide_status='HIDDEN')]
  api=API(items);out=a.run(api,self.cfg,self.ledger,'run');self.assertEqual(out['published_by_this_run'],0)
  self.assertFalse(any(x[0]=='POST' for x in api.calls))
 def test_private_commenter_with_no_public_username_can_receive_reply(self):
  out=a.run(API([comment(username=None)]),self.cfg,self.ledger,'run');self.assertEqual(out['published_by_this_run'],1)
 def test_scan_never_posts_or_mutates_ledger(self):
  api=API();out=a.run(api,self.cfg,self.ledger,'scan');self.assertEqual(out['eligible_comments'],1);self.assertFalse(self.ledger.path.exists())
  self.assertFalse(any(x[0]=='POST' for x in api.calls))
 def test_wrong_account_stops_before_any_post(self):
  api=API(username='someone_else')
  with self.assertRaises(RuntimeError):a.run(api,self.cfg,self.ledger,'run')
  self.assertFalse(any(x[0]=='POST' for x in api.calls))
 def test_permission_denial_never_sends_a_message(self):
  api=API(deny=True)
  with self.assertRaisesRegex(RuntimeError,'403'):a.run(api,self.cfg,self.ledger,'run')
  self.assertFalse(any(x[0]=='POST' for x in api.calls))
 def test_ambiguous_publish_is_held_and_not_retried(self):
  a.run(API(fail=True),self.cfg,self.ledger,'run');self.assertEqual(self.ledger.data['jobs']['COMMENT']['state'],'needs_reconciliation')
  retry=API();a.run(retry,self.cfg,self.ledger,'run');self.assertFalse(any(x[0]=='POST' for x in retry.calls))
 def test_existing_owner_reply_prevents_extra_automatic_reply(self):
  items=[comment(),comment('OWNER_REPLY',username='1fatherx',replied_to={'id':'COMMENT'},text='Sudah gw jawab ya.')]
  api=API(items);a.run(api,self.cfg,self.ledger,'run');self.assertFalse(any(x[0]=='POST' for x in api.calls))
 def test_ambiguous_receipt_can_reconcile_from_the_visible_owner_reply(self):
  self.ledger.update('COMMENT',state='needs_reconciliation')
  items=[comment(),comment('FOUND',username='1fatherx',replied_to={'id':'COMMENT'},text=self.cfg['reply_templates'][0])]
  api=API(items);a.run(api,self.cfg,self.ledger,'run');self.assertEqual(self.ledger.data['jobs']['COMMENT']['state'],'published');self.assertEqual(self.ledger.data['jobs']['COMMENT']['published_id'],'FOUND')
  self.assertFalse(any(x[0]=='POST' for x in api.calls))
 def test_run_cap_and_api_budget_prevent_unbounded_sends(self):
  self.cfg['max_replies_per_run']=1;api=API([comment('A'),comment('B')]);out=a.run(api,self.cfg,self.ledger,'run');self.assertEqual(out['published_by_this_run'],1);self.assertTrue(out['limited'])
  self.cfg['max_requests_per_run']=4;api=API([comment('C')]);out=a.run(api,self.cfg,self.ledger,'run');self.assertEqual(out['published_by_this_run'],0);self.assertFalse(any(x[0]=='POST' for x in api.calls))
 def test_failed_receipt_persistence_stops_before_publication(self):
  api=API()
  with patch.object(self.ledger,'save',side_effect=RuntimeError('push failed')):
   with self.assertRaisesRegex(RuntimeError,'push failed'):a.run(api,self.cfg,self.ledger,'run')
  self.assertFalse(any(x[1]=='OWNER/threads_publish' for x in api.calls))
 def test_random_choice_uses_only_the_two_exact_owner_templates(self):
  for i,text in enumerate(['DM gw ya kak.','DM gw. thanks']):
   api=API([comment(str(i))])
   with patch.object(a,'choice',return_value=text) as pick:a.run(api,self.cfg,self.ledger,'run')
   pick.assert_called_once_with(self.cfg['reply_templates'])
   self.assertEqual(next(x[2]['text'] for x in api.calls if x[1]=='OWNER/threads'),text)
   self.assertEqual(self.ledger.data['jobs'][str(i)]['reply_text'],text)
 def test_saved_template_reconciles_after_the_template_list_changes(self):
  self.ledger.update('COMMENT',state='needs_reconciliation',reply_text='DM gw. thanks')
  self.cfg['reply_templates']=['Updated future template']
  api=API([comment(),comment('FOUND',username='1fatherx',replied_to={'id':'COMMENT'},text='DM gw. thanks')])
  a.run(api,self.cfg,self.ledger,'run');self.assertEqual(self.ledger.data['jobs']['COMMENT']['state'],'published')
  self.assertFalse(any(x[0]=='POST' for x in api.calls))

if __name__=='__main__':unittest.main()
