import unittest, tempfile
from datetime import datetime, timedelta
from pathlib import Path
from test_publisher import post
import publisher as p

class ClockTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.ledger=p.Ledger(Path(self.temp.name))
 def tearDown(self):self.temp.cleanup()
 def test_arming_waits_for_exact_time_without_publishing(self):
  current=[datetime.fromisoformat('2026-10-21T01:00:00+00:00')]
  waits=[];reports=[]
  def sleep(seconds):waits.append(seconds);current[0]+=timedelta(seconds=seconds)
  result=p.wait_for_due([post()],self.ledger,post()['due'],clock=lambda:current[0],sleep=sleep,
   report=lambda value,**kwargs:reports.append(value))
  self.assertEqual(result['state'],'due');self.assertEqual(sum(waits),1800)
  self.assertEqual(current[0],datetime.fromisoformat(post()['due']))
  self.assertEqual(self.ledger.get(post()['id'])['state'],'pending')
  self.assertIn('"state": "armed"',reports[0])
 def test_unknown_slot_cannot_be_armed(self):
  with self.assertRaises(RuntimeError):p.wait_for_due([post()],self.ledger,'2026-10-21T08:31:00+07:00')
 def test_excessively_early_trigger_is_rejected(self):
  with self.assertRaises(RuntimeError):
   p.wait_for_due([post()],self.ledger,post()['due'],clock=lambda:datetime.fromisoformat('2026-10-20T21:00:00+00:00'))
 def test_arming_published_slot_exits_without_sleep(self):
  self.ledger.update(post()['id'],state='published',published_id='old')
  result=p.wait_for_due([post()],self.ledger,post()['due'],sleep=lambda _:self.fail('must not wait'))
  self.assertEqual(result['state'],'already_recorded')
 def test_late_trigger_does_not_create_a_catch_up(self):
  result=p.wait_for_due([post()],self.ledger,post()['due'],clock=lambda:datetime.fromisoformat('2026-10-21T03:00:00+00:00'))
  self.assertEqual(result['state'],'target_too_late')
  self.assertEqual(self.ledger.get(post()['id'])['state'],'pending')

if __name__=='__main__':unittest.main()
