"""Refresh the next seven days with credited, clean public-source practice clips.

Every calendar slot already has verified real fallback media. Failure to obtain a
fresh source preserves that media and never claims a new clip was produced.
"""
import argparse, hashlib, json, os, re, subprocess, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
import publisher as p

ROOT=Path(__file__).resolve().parent
CHANNELS=['HASCreative','VINDES','radityadika','AgakLaenOfficial','HelmyYahyaBicara','CXOMedia','curhatbang','corbuzier','MaknaTalks','DanielManantaNetwork','MenjadiManusia','kasisolusi','tuah_kreasi','TSMediaID']
REPO='catzrecord/pixora-threads-weekly-20261021'
RELEASE='rolling-practice-media'
CREDIT='\n\nCuplikan sumber buat latihan: '
EXCLUDE=re.compile(r'battle dance|dance battle|bakudansa|games agak laen|bunuh|pemerkosa|pelecehan|gantung diri',re.I)

class Quiet:
 def debug(self,*args):pass
 def info(self,*args):pass
 def warning(self,*args):pass
 def error(self,*args):pass

def policy(info,due):
 try:age=(due.date()-datetime.strptime(info.get('upload_date',''),'%Y%m%d').date()).days
 except ValueError:return False
 return 0<=age<=21 and (info.get('duration') or 0)>=1200 and (info.get('view_count') or 0)>=10000 and info.get('live_status') not in ('is_live','is_upcoming') and not EXCLUDE.search(info.get('title',''))

def targets(posts,ledger,at,horizon=7):
 return [x for x in posts if x['due'][11:16]=='20:00' and x['due'][:10]>='2026-10-28'
  and at+timedelta(hours=24)<datetime.fromisoformat(x['due'])<=at+timedelta(days=horizon)
  and ledger.get(x['id'])['state']=='pending' and x['media'][1]['kind']!='podcast_practice_source']

def options():
 return dict(quiet=True,no_warnings=True,skip_download=True,socket_timeout=15,retries=0,extractor_retries=0,logger=Quiet())

def discover(at,used):
 from yt_dlp import YoutubeDL
 offset=at.toordinal()%len(CHANNELS);channels=(CHANNELS+CHANNELS)[offset:offset+4]
 ids=[];lists=[]
 for channel in channels:
  try:
   with YoutubeDL({**options(),'extract_flat':True,'playlistend':8}) as dl:
    listing=dl.extract_info('https://www.youtube.com/@'+channel+'/videos',download=False)
   group=[]
   for x in listing.get('entries') or []:
    vid=x.get('id','')
    if re.fullmatch(r'[A-Za-z0-9_-]{11}',vid) and vid not in used:group.append(vid)
   lists.append(group)
  except Exception:continue
 for rank in range(8):
  for group in lists:
   if rank<len(group) and group[rank] not in ids:ids.append(group[rank])
 return ids[:16]

def extract(vid):
 from yt_dlp import YoutubeDL
 with YoutubeDL(options()) as dl:return dl.extract_info('https://www.youtube.com/watch?v='+vid,download=False)

def render(info,directory):
 # Use original aspect ratio and original audio. No overlays, crop, speed changes or music.
 formats=info.get('formats') or []
 vs=[x for x in formats if x.get('protocol')=='https' and 0<(x.get('height') or 0)<=720 and x.get('vcodec','none')!='none' and x.get('acodec')=='none']
 audio=[x for x in formats if x.get('protocol')=='https' and x.get('vcodec')=='none' and x.get('acodec','none')!='none']
 vs.sort(key=lambda x:((x.get('height') or 0),x.get('vcodec','').startswith('avc1')),reverse=True)
 audio.sort(key=lambda x:(x.get('ext')=='m4a',x.get('abr') or 0),reverse=True)
 if not vs or not audio:raise RuntimeError('Public source streams unavailable')
 low=180;high=info['duration']-210
 chapters=[x for x in info.get('chapters') or [] if low<=x.get('start_time',0)<=high and not re.search(r'intro|sponsor|iklan|outro|opening|closing',x.get('title',''),re.I)]
 heat=[x for x in info.get('heatmap') or [] if low<=x.get('start_time',0)<=high]
 if chapters:start=chapters[len(chapters)//3]['start_time'];method='Public source chapter boundary'
 elif heat:start=max(low,min(high,max(heat,key=lambda x:x.get('value',0))['start_time']-12));method='Public source replay peak'
 else:raise RuntimeError('No source chapter or replay peak; keep reviewed fallback')
 # Require source captions to check this excerpt, instead of guessing its subject.
 tracks=info.get('subtitles') or {};tracks=tracks if 'id' in tracks else info.get('automatic_captions') or {}
 keys=[k for k in tracks if k in ('id','id-orig')]+[k for k in tracks if k.endswith('-orig')]
 segments=[]
 for key in keys:
  choices=[x for x in tracks[key] if x.get('ext')=='json3']
  if not choices:continue
  result=subprocess.run(['curl','-fLsS','--max-time','25',choices[0]['url']],capture_output=True,timeout=30)
  if result.returncode:continue
  try:data=json.loads(result.stdout)
  except ValueError:continue
  segments=[{'start':e.get('tStartMs',0)/1000,'end':(e.get('tStartMs',0)+e.get('dDurationMs',0))/1000,'text':''.join(s.get('utf8','') for s in e.get('segs',[]))} for e in data.get('events',[]) if e.get('segs')]
  if segments:break
 excerpt=[x for x in segments if x['end']>=start and x['start']<=start+90]
 if not excerpt or EXCLUDE.search(' '.join(x['text'] for x in excerpt)):raise RuntimeError('Source transcript review unavailable or unsuitable')
 near=[x for x in excerpt if abs(x['start']-start)<10 and x['start']>=low]
 if near:start=min(near,key=lambda x:abs(x['start']-start))['start']
 out=directory/'clip.mp4';cmd=['ffmpeg','-nostdin','-y','-v','error','-threads','2']
 headers=''.join(k+': '+str(v)+'\r\n' for k,v in info.get('http_headers',{}).items() if k.lower() in ('user-agent','referer','accept-language'))
 for f in [vs[0],audio[0]]:cmd+=['-rw_timeout','30000000','-headers',headers,'-ss',str(start),'-i',f['url']]
 cmd+=['-t','90','-map','0:v:0','-map','1:a:0','-c:v','libx264','-threads','2','-preset','fast','-crf','20','-pix_fmt','yuv420p','-r','25','-fps_mode','cfr','-c:a','aac','-b:a','160k','-ar','48000','-movflags','+faststart',str(out)]
 result=subprocess.run(cmd,capture_output=True,timeout=420)
 if result.returncode:raise RuntimeError('Source download or render failed')
 probe=json.loads(subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(out)],capture_output=True,check=True).stdout)
 v=next(x for x in probe['streams'] if x['codec_type']=='video');a=next(x for x in probe['streams'] if x['codec_type']=='audio')
 if v['codec_name']!='h264' or a['codec_name']!='aac' or abs(float(v['duration'])-90)>.3 or abs(float(a['duration'])-90)>.3 or int(v.get('nb_frames',0))<2160:raise RuntimeError('Source media stream validation failed')
 decoded=subprocess.run(['ffmpeg','-nostdin','-v','error','-threads','2','-i',str(out),'-f','null','-'],capture_output=True,timeout=180)
 if decoded.returncode or decoded.stderr.strip():raise RuntimeError('Source media decode failed')
 digest=hashlib.sha256(out.read_bytes()).hexdigest();final=directory/(digest+'.mp4');out.rename(final)
 return final,{'video_id':info['id'],'source_url':'https://www.youtube.com/watch?v='+info['id'],
  'title':info.get('title'),'channel':info.get('channel'),'source_upload_date':info.get('upload_date'),
  'views_observed':info.get('view_count'),'observed_at':p.stamp(),'start_seconds':start,'end_seconds':start+90,
  'selection_method':method+'; checked against original-language captions','transcript_excerpt':excerpt,
  'duration_seconds':float(probe['format']['duration']),'full_decode_verified':True,'original_frame_and_audio':True,
  'added_elements':False,'crop_or_reframe':False,'is_app_export':False,'sha256':digest,'bytes':final.stat().st_size}

def host(path):
 exists=subprocess.run(['gh','release','view',RELEASE,'--repo',REPO],capture_output=True)
 if exists.returncode:subprocess.run(['gh','release','create',RELEASE,'--repo',REPO,'--title','Rolling source-practice media','--notes','Credited public-source practice excerpts. Original frame and audio; no tool-output claim.'],check=True,capture_output=True)
 subprocess.run(['gh','release','upload',RELEASE,str(path),'--repo',REPO],check=True,capture_output=True)
 return f'https://github.com/{REPO}/releases/download/{RELEASE}/{path.name}'

def persist():
 for cmd in [['git','config','user.name','threads-campaign[bot]'],['git','config','user.email','threads-campaign@users.noreply.github.com'],
  ['git','add','schedule.json','approval.json','production.json'],['git','commit','-m','Refresh upcoming credited practice media'],['git','push','origin','HEAD:main']]:
  subprocess.run(cmd,cwd=ROOT,check=True,capture_output=True)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--horizon',type=int,default=7);parser.add_argument('--max-new',type=int,default=2);parser.add_argument('--check',action='store_true');args=parser.parse_args()
 at=p.now();posts=p.load_schedule();pending=targets(posts,p.Ledger(),at,args.horizon)
 report={'checked_at':at.isoformat(),'eligible_slots':len(pending),'new_clips':0,'fallback_preserved':True,'published_by_this_run':0}
 if args.check or not pending:report['state']='buffer_ready' if not pending else 'fallback_ready';print(json.dumps(report));return
 if not p.CAMPAIGN_START<=at<p.CAMPAIGN_END:print(json.dumps({'state':'outside_approved_campaign'}));return
 history_path=ROOT/'production.json';history=json.loads(history_path.read_text()) if history_path.exists() else {'clips':[],'runs':[]}
 used={x['video_id'] for x in history['clips']}
 for post in posts:
  match=re.search(r'youtube\.com/watch\?v=([\w-]{11})',post['text'])
  if match:used.add(match.group(1))
 candidates=discover(at,used);attempts=0;report['candidates_discovered']=len(candidates);failures={}
 for post in pending[:min(2,max(0,args.max_new))]:
  for vid in list(candidates):
   if attempts>=8:break
   candidates.remove(vid);attempts+=1;stage='metadata_unavailable'
   try:
    info=extract(vid)
    if not policy(info,datetime.fromisoformat(post['due'])):
     failures['ineligible_source']=failures.get('ineligible_source',0)+1;continue
    stage='source_render_or_host_unavailable'
    with tempfile.TemporaryDirectory(prefix='threads-source-') as tmp:
     path,record=render(info,Path(tmp));url=host(path)
     item={'type':'VIDEO','url':url,'sha256':record['sha256'],'bytes':record['bytes'],
      'alt_text':'Cuplikan sumber podcast untuk latihan clipping; frame dan audio asli','kind':'podcast_practice_source'}
     p.verify_asset(item)
    base=post['text'].split(CREDIT)[0];text=base+CREDIT+record['source_url']
    if len(text)>500:raise RuntimeError('Credited caption exceeds limit')
    post['text']=text;post['media'][1]=item;record['post_id']=post['id'];history['clips'].append(record)
    report['new_clips']+=1;break
   except Exception:
    # Public-source failure details can contain signed URLs. Never print them.
    failures[stage]=failures.get(stage,0)+1;continue
 report.update(state='updated' if report['new_clips'] else 'fallback_retained',source_attempts=attempts,failure_counts=failures)
 history['runs']=(history['runs']+[report])[-210:]
 if report['new_clips']:
  p.save(ROOT/'schedule.json',posts);approval=json.loads((ROOT/'approval.json').read_text());approval['schedule_sha256']=p.checksum((ROOT/'schedule.json').read_bytes());approval['media_refreshed_at']=at.isoformat();p.save(ROOT/'approval.json',approval)
 p.save(history_path,history)
 if os.environ.get('PERSIST_GIT')=='1':persist()
 print(json.dumps(report))

if __name__=='__main__':
 try:main()
 except Exception as e:
  print(json.dumps({'state':'producer_error','error':type(e).__name__,'fallback_preserved':True}));raise SystemExit(1)
