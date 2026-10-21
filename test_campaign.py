import json, os, sys, tempfile, types, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from cryptography.fernet import Fernet
import credentials as c
import producer
import publisher as p

class RefreshAPI:
 def __init__(self,token):self.token=token
 def call(self,method,path,**params):
  if path=='me':return {'id':'123','username':'1fatherx'}
  if 'publishing_limit' in path:return {'data':[{'quota_usage':0,'config':{'quota_total':250}}]}
  if path=='refresh_access_token':return {'access_token':'NEW_TEST_TOKEN','expires_in':5184000}
  raise AssertionError(path)

class CampaignTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  self.env=patch.dict(os.environ,{'THREADS_TOKEN_VAULT_KEY':Fernet.generate_key().decode()});self.env.start()
  self.at=datetime(2026,11,15,tzinfo=timezone.utc)
  c.write(self.root,{'access_token':'OLD_TEST_TOKEN','username':'1fatherx','refreshed_at':(self.at-timedelta(days=25)).isoformat(),'expires_at':(self.at+timedelta(days=35)).isoformat()})
 def tearDown(self):self.env.stop();self.temp.cleanup()
 def test_vault_never_stores_plain_token(self):
  self.assertNotIn(b'OLD_TEST_TOKEN',(self.root/'token.enc').read_bytes());self.assertEqual(c.load_token(self.root,self.at),'OLD_TEST_TOKEN')
 def test_vault_tamper_fails_closed(self):
  raw=bytearray((self.root/'token.enc').read_bytes());raw[len(raw)//2]^=1;(self.root/'token.enc').write_bytes(raw)
  with self.assertRaises(RuntimeError):c.load_token(self.root,self.at)
 def test_refresh_is_saved_encrypted_before_reporting_success(self):
  saved=[];r=c.maintain(self.root,self.at,RefreshAPI,lambda:saved.append(c.read(self.root)['access_token']))
  self.assertEqual(r['state'],'credential_refreshed');self.assertEqual(saved,['NEW_TEST_TOKEN'])
  self.assertNotIn(b'NEW_TEST_TOKEN',(self.root/'token.enc').read_bytes())
  self.assertEqual(datetime.fromisoformat(c.read(self.root)['expires_at']),self.at+timedelta(days=60))
 def test_recent_token_does_not_hit_refresh_api(self):
  d=c.read(self.root);d['refreshed_at']=(self.at-timedelta(hours=1)).isoformat();c.write(self.root,d)
  def never(_):raise AssertionError('Network should not be used')
  self.assertEqual(c.maintain(self.root,self.at,never)['state'],'credential_healthy')
 def test_expired_credential_requires_reauthorization(self):
  with self.assertRaises(RuntimeError):c.maintain(self.root,self.at+timedelta(days=40),RefreshAPI)
 def test_refresh_persistence_failure_is_not_success(self):
  def fail():raise RuntimeError('push failed')
  with self.assertRaises(RuntimeError):c.maintain(self.root,self.at,RefreshAPI,fail)
 def test_source_age_checked_at_posting_time(self):
  info={'upload_date':'20261021','duration':1800,'view_count':11000,'title':'Obrolan kreator'}
  self.assertTrue(producer.policy(info,datetime.fromisoformat('2026-11-10T20:00:00+07:00')))
  self.assertFalse(producer.policy(info,datetime.fromisoformat('2026-11-12T20:00:00+07:00')))
 def test_discovery_interleaves_channels_before_source_attempt_limit(self):
  class Listing:
   def __init__(self,options):pass
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def extract_info(self,url,download=False):
    handle=url.split('@')[1].split('/')[0];index=producer.CHANNELS.index(handle)
    return {'entries':[{'id':f'{index:02}{rank:09}'} for rank in range(8)]}
  with patch.dict(sys.modules,{'yt_dlp':types.SimpleNamespace(YoutubeDL=Listing)}):
   candidates=producer.discover(self.at,set())
  self.assertEqual(len(candidates),16)
  self.assertEqual(len({vid[:2] for vid in candidates[:4]}),4)
 def test_producer_preserves_approved_week_published_and_near_due(self):
  rows=p.load_schedule();ledger=p.Ledger(self.root);at=datetime.fromisoformat('2026-11-03T09:00:00+00:00')
  eligible=producer.targets(rows,ledger,at,14);self.assertTrue(eligible)
  first=eligible[0];ledger.update(first['id'],state='published')
  self.assertNotIn(first['id'],[x['id'] for x in producer.targets(rows,ledger,at,14)])
  self.assertTrue(all(x['due'][:10]>='2026-10-28' and x['media'][1]['kind']!='podcast_practice_source' for x in eligible))

if __name__=='__main__':unittest.main()
