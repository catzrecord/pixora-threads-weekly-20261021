"""Authenticated encrypted token state; the encryption key stays in Actions secrets."""
import json, os, subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

def cipher():
 key=os.environ.get('THREADS_TOKEN_VAULT_KEY','')
 if not key:raise RuntimeError('Threads credential vault key is not configured')
 return Fernet(key.encode())

def read(root):
 try:data=json.loads(cipher().decrypt((root/'token.enc').read_bytes()))
 except (InvalidToken,ValueError):raise RuntimeError('Threads credential vault authentication failed') from None
 if data.get('username')!='1fatherx':raise RuntimeError('Unexpected credential vault account')
 return data

def write(root,data):
 path=root/'token.enc';temp=root/'token.enc.tmp'
 temp.write_bytes(cipher().encrypt(json.dumps(data).encode()));temp.replace(path)

def load_token(root,at=None):
 data=read(root);at=at or datetime.now(timezone.utc)
 if datetime.fromisoformat(data['expires_at'])<=at:raise RuntimeError('Threads access expired; owner reauthorization required')
 return data['access_token']

def maintain(root,at=None,api_factory=None,persist=None):
 from publisher import API,identity
 at=at or datetime.now(timezone.utc);data=read(root)
 issued=datetime.fromisoformat(data['refreshed_at']);expires=datetime.fromisoformat(data['expires_at'])
 if expires<=at:raise RuntimeError('Expired token cannot be refreshed; owner reauthorization required')
 if at-issued<timedelta(days=20) and expires-at>timedelta(days=20):
  return {'state':'credential_healthy','expires_at':data['expires_at'],'published_by_this_run':0}
 if at-issued<timedelta(hours=24):raise RuntimeError('Token is too young to refresh')
 factory=api_factory or API
 api=factory(data['access_token']);identity(api)
 response=api.call('GET','refresh_access_token',grant_type='th_refresh_token')
 token=response.get('access_token');seconds=response.get('expires_in')
 if not isinstance(token,str) or not token or not isinstance(seconds,int) or seconds<86400:raise RuntimeError('Refresh returned invalid credential metadata')
 identity(factory(token))
 updated={**data,'access_token':token,'refreshed_at':at.isoformat(),
  'expires_at':(at+timedelta(seconds=seconds)).isoformat(),'expires_in':seconds}
 write(root,updated)
 if persist:persist()
 elif os.environ.get('PERSIST_GIT')=='1':
  for cmd in [
   ['git','config','user.name','threads-campaign[bot]'],
   ['git','config','user.email','threads-campaign@users.noreply.github.com'],
   ['git','add','token.enc'],['git','commit','-m','Renew encrypted Threads credential'],
   ['git','push','origin','HEAD:main']]:subprocess.run(cmd,cwd=root,check=True,capture_output=True)
 return {'state':'credential_refreshed','expires_at':updated['expires_at'],'published_by_this_run':0}
