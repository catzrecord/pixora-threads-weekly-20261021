import hashlib, io, json, tempfile, unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path
import publisher as p

class FakeAPI:
 def __init__(self,username='1fatherx',fail_publish=False):self.calls=[];self.username=username;self.fail_publish=fail_publish
 def call(self,method,path,**params):
  self.calls.append((method,path,params))
  if path=='me':return {'id':'123','username':self.username}
  if 'publishing_limit' in path:return {'data':[{'quota_usage':0,'config':{'quota_total':250}}]}
  if path.endswith('threads_publish'):
   if self.fail_publish:raise TimeoutError()
   return {'id':'PUBLISHED'}
  if path.endswith('/threads'):return {'id':'CONTAINER-'+str(len(self.calls))}
  if path=='PUBLISHED':return {'permalink':'https://www.threads.com/@1fatherx/post/test'}
  return {'status':'FINISHED'}

def post():return {'id':'TEST-01','due':'2026-10-21T08:30:00+07:00','text':'Approved caption',
 'media':[{'type':'IMAGE','url':'https://github.com/1.jpg','alt_text':'Product'},
          {'type':'VIDEO','url':'https://github.com/1.mp4','alt_text':'Demo'}]}

class Tests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.ledger=p.Ledger(self.root)
 def tearDown(self):self.temp.cleanup()
 def test_future_and_outside_week_never_call_api(self):
  for when in ['2026-10-20T01:30:00+00:00','2026-10-21T01:29:00+00:00','2026-10-28T01:30:00+00:00']:
   api=FakeAPI();p.dispatch([post()],api,self.ledger,at=datetime.fromisoformat(when),enabled=True)
   self.assertEqual(api.calls,[])
 def test_wrong_account_stops_before_creation(self):
  api=FakeAPI('other')
  with self.assertRaises(RuntimeError):p.publish(post(),api,self.ledger,verify=lambda _:None)
  self.assertFalse(any(x[0]=='POST' for x in api.calls))
 def test_two_media_and_exact_caption_in_one_carousel(self):
  api=FakeAPI();self.assertEqual(p.publish(post(),api,self.ledger,verify=lambda _:None),'published')
  creates=[x[2] for x in api.calls if x[1]=='123/threads']
  self.assertEqual([x['media_type'] for x in creates],['IMAGE','VIDEO','CAROUSEL'])
  self.assertEqual(creates[-1]['text'],post()['text'])
  self.assertEqual(len(creates[-1]['children'].split(',')),2)
 def test_ambiguous_publish_is_durable_and_not_retried(self):
  api=FakeAPI(fail_publish=True);self.assertEqual(p.publish(post(),api,self.ledger,verify=lambda _:None),'needs_reconciliation')
  retry=FakeAPI();self.assertEqual(p.publish(post(),retry,p.Ledger(self.root),verify=lambda _:None),'needs_reconciliation')
  self.assertEqual(retry.calls,[])
 def test_late_job_is_missed_without_api(self):
  api=FakeAPI();p.dispatch([post()],api,self.ledger,at=datetime.fromisoformat('2026-10-21T02:01:00+00:00'),enabled=True)
  self.assertEqual(self.ledger.get('TEST-01')['state'],'missed');self.assertEqual(api.calls,[])
 def test_hosted_hash_failure_stops_before_creation(self):
  def fail(_):raise RuntimeError('hash mismatch')
  api=FakeAPI()
  with self.assertRaises(RuntimeError):p.publish(post(),api,self.ledger,verify=fail)
  self.assertFalse(any(x[0]=='POST' for x in api.calls))
 def test_already_published_never_repeats(self):
  self.ledger.update('TEST-01',state='published',published_id='OLD');api=FakeAPI()
  self.assertEqual(p.publish(post(),api,self.ledger,verify=lambda _:None),'published');self.assertEqual(api.calls,[])
 def test_binary_cdn_mime_still_requires_exact_media_bytes(self):
  raw=b'\x89PNG\r\n\x1a\n'+b'approved-image';response=io.BytesIO(raw);response.headers={'Content-Type':'application/octet-stream'}
  item={'type':'IMAGE','url':'https://github.com/asset.png','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
  with patch.object(p,'urlopen',return_value=response):p.verify_asset(item)
  wrong=io.BytesIO(b'<html>not media</html>');wrong.headers={'Content-Type':'application/octet-stream'}
  with patch.object(p,'urlopen',return_value=wrong),self.assertRaises(RuntimeError):p.verify_asset(item)

if __name__=='__main__':unittest.main()
