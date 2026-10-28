import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta
import producer,publisher as p

class AnnualTests(unittest.TestCase):
 def test_final_october_week_is_present_at_all_three_times(self):
  rows=p.load_schedule();last=rows[-21:]
  self.assertEqual(len(last),21)
  self.assertEqual({x['due'][11:16] for x in last},{'08:30','13:00','20:00'})
  self.assertEqual(last[0]['due'][:10],'2027-10-14')
  self.assertEqual(last[-1]['due'],'2027-10-20T20:00:00+07:00')
 def test_added_slots_require_matching_app_export_and_source_credit(self):
  rows=p.load_schedule();approval=json.loads((p.ROOT/'approval.json').read_text())
  row=next(x for x in rows if x['id'].startswith('YEAR-'));row['media'][1]['source_url']='https://www.youtube.com/watch?v=WRONGSOURCE'
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);raw=(json.dumps(rows,ensure_ascii=False,indent=2)+'\n').encode();(root/'schedule.json').write_bytes(raw)
   approval['schedule_sha256']=hashlib.sha256(raw).hexdigest();(root/'approval.json').write_text(json.dumps(approval))
   with self.assertRaisesRegex(RuntimeError,'source credit'):p.load_schedule(root)
 def test_annual_slots_have_screen_recording_then_app_export(self):
  rows=[x for x in p.load_schedule() if x['id'].startswith('YEAR-')]
  self.assertEqual(len(rows),549)
  for row in rows:
   self.assertEqual([x['type'] for x in row['media']],['VIDEO','VIDEO'])
   self.assertNotEqual(row['media'][0]['sha256'],row['media'][1]['sha256'])
   self.assertEqual(row['media'][0]['kind'],'owner_screen_recording')
   self.assertEqual(row['media'][1]['kind'],'verified_pixora_render')
 def test_annual_app_pairs_are_protected_from_podcast_refresh(self):
  rows=p.load_schedule();at=datetime.fromisoformat('2027-04-21T00:00:00+07:00')
  with tempfile.TemporaryDirectory() as tmp:
   ledger=p.Ledger(Path(tmp));targets=producer.targets(rows,ledger,at,7)
   self.assertEqual(targets,[])
 def test_search_phrase_does_not_misclassify_unrelated_content(self):
  self.assertEqual(producer.source_category({'title':'DAN UFO TURUN DI INDONESIA','channel':'Deddy Corbuzier'}),'other')
  self.assertEqual(producer.source_category({'title':'Obrolan dr. Tirta','channel':'Raditya Dika'}),'tirta')
  self.assertEqual(producer.source_category({'title':'Anggaran APBN dan Purbaya','channel':'CURHAT BANG Denny Sumargo'}),'politics')
 def test_higher_bitrate_english_dub_cannot_replace_original_indonesian(self):
  english={'format_id':'140-0','language':'en-US','abr':160,'ext':'m4a','format_note':'English auto dubbed','language_preference':-1}
  original={'format_id':'140-1','language':'id','abr':129,'ext':'m4a','format_note':'Indonesian original (default)','language_preference':10}
  self.assertEqual(producer.original_audio({'language':'id'},[english,original])['format_id'],'140-1')
  with self.assertRaises(RuntimeError):producer.original_audio({'language':'id'},[english])
 def test_new_source_popularity_floor_requires_one_hundred_thousand_observed_views(self):
  info={'upload_date':'20270420','duration':1800,'view_count':99999,'title':'Diskusi kebijakan publik'}
  due=datetime.fromisoformat('2027-04-22T20:00:00+07:00')
  self.assertFalse(producer.policy(info,due,100000))
  info['view_count']=100000
  self.assertTrue(producer.policy(info,due,100000))

if __name__=='__main__':unittest.main()
