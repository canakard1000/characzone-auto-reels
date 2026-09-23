import copy
import unittest
from unittest.mock import Mock, patch

from publish_threads import Threads, PublishError, approved_reels, fingerprint, publish_one, validate

REEL = {"id": "characzone-reel-05", "approved": True, "published": True,
        "instagram_media_id": "existing-instagram-id", "caption": "캐릭존 가챠머신 창업",
        "video_url": "https://raw.githubusercontent.com/canakard1000/characzone-auto-reels/main/characzone-reel-05.mp4"}


class Ledger:
    def __init__(self, entry=None):
        self.entry = entry or {}
        self.writes = []

    def get(self, reel_id):
        return copy.deepcopy(self.entry)

    def save(self, reel_id, entry):
        self.entry = copy.deepcopy(entry)
        self.writes.append(copy.deepcopy(entry))


def client():
    c = Mock()
    c.create.return_value = "container-1"
    c.status.return_value = "FINISHED"
    c.publish.return_value = "media-1"
    return c


class PublishingTests(unittest.TestCase):
    def test_instagram_published_reel_still_eligible_and_manifest_untouched(self):
        reel = copy.deepcopy(REEL)
        self.assertEqual(approved_reels({"reels": [reel]}), [reel])
        ledger, c = Ledger(), client()
        self.assertEqual(publish_one(reel, c, ledger), "published")
        self.assertEqual(reel, REEL)
        self.assertEqual([x["phase"] for x in ledger.writes], ["creating", "processing", "publishing", "published"])

    def test_unapproved_and_string_true_excluded(self):
        self.assertEqual(approved_reels({"reels": [{**REEL, "approved": "true"}]}), [])
        self.assertEqual(approved_reels({"reels": [{**REEL, "approved": False}]}), [])

    def test_future_or_rejected_reels_excluded(self):
        for changes in [{"scheduled_for": "2099-01-01T00:00:00+00:00"}, {"rejected": True}]:
            self.assertEqual(approved_reels({"reels": [{**REEL, **changes}]}), [])
        self.assertEqual(approved_reels({"reels": [{**REEL, "scheduled_for": "2020-01-01T00:00:00Z"}]} )[0]["id"], REEL["id"])

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(PublishError):
            approved_reels({"reels": [REEL, REEL]})

    def test_repeat_does_not_send_again(self):
        c, ledger = client(), Ledger()
        publish_one(REEL, c, ledger)
        self.assertEqual(publish_one(REEL, c, ledger), "already_published")
        c.create.assert_called_once()
        c.publish.assert_called_once()

    def test_state_write_failure_prevents_upload(self):
        c, ledger = client(), Ledger()
        ledger.save = Mock(side_effect=PublishError("push failed"))
        with self.assertRaises(PublishError):
            publish_one(REEL, c, ledger)
        c.create.assert_not_called()
        c.publish.assert_not_called()

    def test_lost_create_acknowledgement_does_not_reupload(self):
        c, ledger = client(), Ledger()
        c.create.side_effect = PublishError("timeout")
        with self.assertRaises(PublishError):
            publish_one(REEL, c, ledger)
        with self.assertRaises(PublishError):
            publish_one(REEL, c, ledger)
        c.create.assert_called_once()

    def test_lost_publish_acknowledgement_reconciles(self):
        c, ledger = client(), Ledger()
        c.publish.side_effect = PublishError("timeout")
        with self.assertRaises(PublishError):
            publish_one(REEL, c, ledger)
        c.status.return_value = "PUBLISHED"
        self.assertEqual(publish_one(REEL, c, ledger), "published_reconciled")
        c.publish.assert_called_once()

    def test_uncertain_publish_never_blindly_resends(self):
        c = client()
        ledger = Ledger({"phase": "publishing", "fingerprint": fingerprint(REEL), "container_id": "c"})
        with self.assertRaises(PublishError):
            publish_one(REEL, c, ledger)
        c.create.assert_not_called()
        c.publish.assert_not_called()

    def test_processing_timeout_resumes_existing_container(self):
        c, ledger = client(), Ledger()
        c.status.return_value = "IN_PROGRESS"
        self.assertEqual(publish_one(REEL, c, ledger, sleep=lambda _: None), "processing")
        c.status.return_value = "FINISHED"
        publish_one(REEL, c, ledger)
        c.create.assert_called_once()

    def test_changed_content_blocks_resume(self):
        ledger = Ledger({"phase": "processing", "fingerprint": "different", "container_id": "c"})
        with self.assertRaises(PublishError):
            publish_one(REEL, client(), ledger)

    def test_expired_container_is_not_recreated(self):
        c, ledger = client(), Ledger()
        c.status.return_value = "EXPIRED"
        for _ in range(2):
            with self.assertRaises(PublishError):
                publish_one(REEL, c, ledger)
        c.create.assert_called_once()
        c.publish.assert_not_called()

    def test_revoked_approval_stops_publish(self):
        c = client()
        with self.assertRaises(PublishError):
            publish_one(REEL, c, Ledger(), check_approval=Mock(side_effect=PublishError("revoked")))
        c.publish.assert_not_called()

    def test_bad_url_and_long_caption_rejected(self):
        for changes in [{"video_url": "http://localhost/secret"}, {"caption": "a" * 501}]:
            with self.assertRaises(PublishError):
                validate({**REEL, **changes})

    def test_wrong_account_prevents_post(self):
        c = Threads("secret", "expected-id")
        c.api = Mock(return_value={"id": "expected-id", "username": "wrong_account"})
        with self.assertRaises(PublishError):
            c.preflight()

    def test_account_id_resolved_only_for_expected_username(self):
        c = Threads("secret", "")
        c.api = Mock(side_effect=[{"id": "verified-id", "username": "gacha_m2026"},
            {"data": [{"quota_usage": 0, "config": {"quota_total": 250}}]}])
        c.preflight()
        self.assertEqual(c.user_id, "verified-id")

    def test_configured_id_mismatch_rejected(self):
        c = Threads("secret", "different-id")
        c.api = Mock(return_value={"id": "verified-id", "username": "gacha_m2026"})
        with self.assertRaises(PublishError):
            c.preflight()

    def test_missing_publish_permission_rejected(self):
        c = Threads("secret", "expected-id")
        c.api = Mock(side_effect=[{"id": "expected-id", "username": "gacha_m2026"}, {"data": []}])
        with self.assertRaises(PublishError):
            c.preflight()

    @patch("publish_threads.requests.request")
    def test_api_error_never_leaks_raw_response(self, request):
        request.return_value.ok = False
        request.return_value.status_code = 400
        request.return_value.json.return_value = {"error": {"code": 190, "message": "secret-token"}}
        with self.assertRaises(PublishError) as caught:
            Threads("secret-token", "id").status("c")
        self.assertNotIn("secret-token", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
