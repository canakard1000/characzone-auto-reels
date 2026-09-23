import json, tempfile, unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
import generate_daily_reels as generator
import publish_reel

class GenerationTests(unittest.TestCase):
    def test_schedule_converts_kst_to_utc(self):
        self.assertEqual(generator.schedule(date(2026,9,24),"am").isoformat(),"2026-09-24T00:00:00+00:00")
        self.assertEqual(generator.schedule(date(2026,9,24),"pm").isoformat(),"2026-09-24T07:00:00+00:00")
    def test_required_wording(self):
        text=" ".join(generator.HOOKS+generator.COPY)
        self.assertNotIn("가챠샵",text); self.assertIn("가챠머신 창업",text)
    def test_only_approved_machine_photos_are_selected(self):
        self.assertEqual(generator.APPROVED_SOURCE_NAMES,{"22188.jpg","22196.jpg","22201.jpg","22203.jpg","22220.jpg","22221.jpg","22243.jpg"})
    def test_future_reel_is_not_published(self):
        payload={"reels":[{"id":"future","approved":True,"published":False,"scheduled_for":"2999-01-01T00:00:00+00:00"}]}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"approved.json"; p.write_text(json.dumps(payload))
            with patch.object(publish_reel,"MANIFEST",p), self.assertRaises(SystemExit) as result: publish_reel.load_approved_reel()
            self.assertEqual(result.exception.code,0)
if __name__=="__main__": unittest.main()
