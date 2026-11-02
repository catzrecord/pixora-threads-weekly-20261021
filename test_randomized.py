import copy,json,tempfile,unittest
from pathlib import Path
import publisher as p

class RandomizedTests(unittest.TestCase):
 def setUp(self):
  self.rows=json.loads((p.ROOT/'schedule.json').read_text());self.approval=json.loads((p.ROOT/'approval.json').read_text());cut='2026-11-02T13:00:00+07:00'
  self.approval['randomized_schedule_revision']={'from_due':cut,'windows_wib':[['08:00','09:50'],['13:00','15:00'],['20:00','21:45']],'preserved_job_times':{x['id']:x['due'] for x in self.rows if x['due']<cut}}
  self.row=next(x for x in self.rows if x['due']>=cut)
 def validate(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p.save(root/'schedule.json',self.rows);self.approval['schedule_sha256']=p.checksum((root/'schedule.json').read_bytes());p.save(root/'approval.json',self.approval);return p.load_schedule(root)
 def test_new_minute_with_three_daily_posts_is_accepted(self):
  self.row['due']='2026-11-02T14:37:00+07:00';self.validate()
 def test_outside_window_is_rejected_even_with_approved_hash(self):
  self.row['due']='2026-11-02T17:37:00+07:00'
  with self.assertRaisesRegex(RuntimeError,'outside approved window'):self.validate()
 def test_moving_one_post_to_another_day_is_rejected(self):
  self.row['due']='2026-11-03T14:37:00+07:00';self.rows.sort(key=lambda x:x['due'])
  with self.assertRaisesRegex(RuntimeError,'three posts'):self.validate()
 def test_historical_due_cannot_change(self):
  self.rows[0]['due']='2026-10-21T08:31:00+07:00'
  with self.assertRaisesRegex(RuntimeError,'Historical publication time changed'):self.validate()
 def test_only_explicitly_approved_pairs_allow_result_first(self):
  pair=next(x for x in self.approval['video_only_revision']['pairs'] if x['id']==self.row['app_demo_pair_id']);pair['allow_result_first']=True
  self.row['media'].sort(key=lambda x:0 if x['kind']=='verified_pixora_render' else 1);self.validate();pair['allow_result_first']=False
  with self.assertRaisesRegex(RuntimeError,'approved order'):self.validate()
 def test_duplicate_recording_cannot_pass_as_reversed_pair(self):
  pair=next(x for x in self.approval['video_only_revision']['pairs'] if x['id']==self.row['app_demo_pair_id']);pair['allow_result_first']=True
  self.row['media']=[copy.deepcopy(self.row['media'][0])]*2
  with self.assertRaisesRegex(RuntimeError,'approved order'):self.validate()
 def test_wrong_hash_in_reversed_pair_is_rejected(self):
  pair=next(x for x in self.approval['video_only_revision']['pairs'] if x['id']==self.row['app_demo_pair_id']);pair['allow_result_first']=True
  self.row['media'].sort(key=lambda x:0 if x['kind']=='verified_pixora_render' else 1);self.row['media'][0]['sha256']='0'*64
  with self.assertRaisesRegex(RuntimeError,'approved pair'):self.validate()
