import copy,json,tempfile,unittest
from pathlib import Path
import publisher as p
from test_publisher import FakeAPI

class VideoOnlyTests(unittest.TestCase):
 def setUp(self):
  self.rows=json.loads((p.ROOT/'schedule.json').read_text())
  self.approval=json.loads((p.ROOT/'approval.json').read_text())
  self.row=next(x for x in self.rows if p.is_video_only(x,self.approval))
 def validate_changed(self,change):
  rows=copy.deepcopy(self.rows);row=next(x for x in rows if x['id']==self.row['id']);change(row)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p.save(root/'schedule.json',rows)
   approval=copy.deepcopy(self.approval);approval['schedule_sha256']=p.checksum((root/'schedule.json').read_bytes());p.save(root/'approval.json',approval)
   return p.load_schedule(root)
 def test_every_remaining_slot_has_only_video_and_a_matching_export(self):
  rows=p.load_schedule();future=[x for x in rows if p.is_video_only(x,self.approval)]
  self.assertEqual(len(future),1071)
  for row in future:p.validate_demo_pair(row,self.approval['video_only_revision'])
 def test_restored_image_is_rejected_even_with_new_schedule_hash(self):
  with self.assertRaisesRegex(RuntimeError,'Video-only'):
   self.validate_changed(lambda row:row['media'][0].update(type='IMAGE'))
 def test_unrelated_export_is_rejected(self):
  with self.assertRaisesRegex(RuntimeError,'approved pair'):
   self.validate_changed(lambda row:row['media'][1].update(sha256='0'*64))
 def test_swapping_demo_and_export_is_rejected(self):
  with self.assertRaisesRegex(RuntimeError,'genuine application'):
   self.validate_changed(lambda row:row['media'].reverse())
 def test_missing_source_credit_is_rejected(self):
  with self.assertRaisesRegex(RuntimeError,'source credit'):
   self.validate_changed(lambda row:row.update(text='Gw ada tools, komen mau.'))
 def test_paired_videos_publish_as_two_video_children(self):
  with tempfile.TemporaryDirectory() as tmp:
   api=FakeAPI();ledger=p.Ledger(Path(tmp))
   self.assertEqual(p.publish(self.row,api,ledger,verify=lambda _:None,sleep=lambda _:None),'published')
   creates=[x[2] for x in api.calls if x[1]=='123/threads']
   self.assertEqual([x['media_type'] for x in creates],['VIDEO','VIDEO','CAROUSEL'])
   self.assertEqual(creates[0]['video_url'],self.row['media'][0]['url'])
   self.assertEqual(creates[1]['video_url'],self.row['media'][1]['url'])

if __name__=='__main__':unittest.main()
