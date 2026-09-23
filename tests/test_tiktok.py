import copy
import unittest
from unittest.mock import Mock

from publish_tiktok import (Buffer, CHANNEL_ID, PublishError, approved_reels,
                            fingerprint, post_input, publish_one, validate)

REEL = {"id": "characzone-reel-05", "approved": True, "published": True,
        "video_url": "https://raw.githubusercontent.com/canakard1000/characzone-auto-reels/main/characzone-reel-05.mp4",
        "caption": "캐릭존 #가챠머신"}


class Ledger:
    def __init__(self, entry=None):
        self.entry = entry or {}
        self.history = []

    def get(self, _):
        return self.entry.copy()

    def save(self, _, entry):
        self.entry = entry.copy()
        self.history.append(entry.copy())


def client(status="sent"):
    c = Mock()
    c.create.return_value = "post1"
    c.post.return_value = {"id": "post1", "channelId": CHANNEL_ID, "text": REEL["caption"],
                           "status": status, "schedulingType": "automatic", "externalLink": "https://www.tiktok.com/@jinwoo.jang5/video/1"}
    c.safe.side_effect = str
    return c


class TikTokTests(unittest.TestCase):
    def test_only_due_true_approvals_ignore_instagram_published(self):
        items = [REEL, {**REEL, "id": "false", "approved": "true"},
                 {**REEL, "id": "rejected", "rejected": True},
                 {**REEL, "id": "future", "scheduled_for": "2099-01-01T00:00:00Z"}]
        self.assertEqual(approved_reels({"reels": items}), [REEL])

    def test_limits_and_external_urls(self):
        for changes in [{"caption": "x" * 2201}, {"caption": "#1 #2 #3 #4 #5 #6"},
                        {"video_url": "https://example.com/a.mp4"}, {"tiktok_is_ai_generated": "false"}]:
            with self.subTest(changes=changes), self.assertRaises(PublishError):
                validate({**REEL, **changes})

    def test_explicit_auto_mode_and_label(self):
        data = post_input({**REEL, "tiktok_is_ai_generated": True})
        self.assertEqual((data["mode"], data["schedulingType"]), ("shareNow", "automatic"))
        self.assertTrue(data["metadata"]["tiktok"]["isAiGenerated"])
        self.assertNotEqual(fingerprint(REEL), fingerprint({**REEL, "tiktok_is_ai_generated": True}))

    def test_persist_before_create_and_no_repeat(self):
        ledger, c = Ledger(), client()
        c.create.side_effect = lambda _: "post1" if ledger.entry["phase"] == "creating" else self.fail()
        self.assertEqual(publish_one(REEL, c, ledger), "published")
        self.assertEqual([e["phase"] for e in ledger.history], ["creating", "submitted", "published"])
        self.assertEqual(publish_one(REEL, c, ledger), "already_published")
        c.create.assert_called_once()

    def test_storage_failure_prevents_send(self):
        ledger, c = Ledger(), client()
        ledger.save = Mock(side_effect=PublishError("push failed"))
        with self.assertRaises(PublishError):
            publish_one(REEL, c, ledger)
        c.create.assert_not_called()

    def test_unknown_create_ack_never_retried(self):
        ledger, c = Ledger(), client()
        c.create.side_effect = PublishError("timeout")
        for _ in range(2):
            with self.assertRaises(PublishError):
                publish_one(REEL, c, ledger)
        c.create.assert_called_once()
        self.assertEqual(ledger.entry["phase"], "creating")

    def test_resume_same_post_without_create(self):
        ledger, c = Ledger(), client("sending")
        self.assertEqual(publish_one(REEL, c, ledger, polls=1), "submitted")
        self.assertNotEqual(ledger.entry["phase"], "published")
        c.post.return_value["status"] = "sent"
        self.assertEqual(publish_one(REEL, c, ledger), "published")
        c.create.assert_called_once()

    def test_notification_is_not_published(self):
        ledger, c = Ledger(), client()
        c.post.return_value["schedulingType"] = "notification"
        with self.assertRaises(PublishError):
            publish_one(REEL, c, ledger)
        self.assertEqual(ledger.entry["phase"], "needs_review")

    def test_error_stops_instead_of_recreating(self):
        ledger, c = Ledger(), client("error")
        for _ in range(2):
            with self.assertRaises(PublishError):
                publish_one(REEL, c, ledger)
        c.create.assert_called_once()
        self.assertEqual(ledger.entry["phase"], "failed")

    def test_approval_revoked_and_duplicate_stop_before_send(self):
        for cause in ["approval", "duplicate"]:
            ledger, c = Ledger(), client()
            check = Mock()
            if cause == "approval":
                check.side_effect = PublishError("revoked")
            else:
                c.check_duplicate.side_effect = PublishError("existing")
            with self.assertRaises(PublishError):
                publish_one(REEL, c, ledger, check)
            c.create.assert_not_called()
            self.assertFalse(ledger.history)

    def test_modified_submission_stops(self):
        ledger, c = Ledger(), client("sending")
        publish_one(REEL, c, ledger, polls=1)
        with self.assertRaises(PublishError):
            publish_one({**REEL, "caption": "changed"}, c, ledger)
        c.create.assert_called_once()

    def test_wrong_account_and_reminders_stop(self):
        account = {"id": CHANNEL_ID, "name": "jinwoo.jang5", "service": "tiktok",
                   "organizationId": "org1", "isDisconnected": False, "isLocked": False,
                   "metadata": {"defaultToReminders": False}}
        for changes in [{"name": "wrong"}, {"isDisconnected": True},
                        {"metadata": {"defaultToReminders": True}}]:
            c = Buffer("test-token")
            c.api = Mock(return_value={"channel": {**account, **changes}})
            with self.assertRaises(PublishError):
                c.preflight()

    def test_existing_initial_caption_blocks_duplicate(self):
        c = Buffer("test-token")
        c.list_posts = Mock(return_value={"edges": [{"node": {"id": "existing", "text": REEL["caption"], "assets": []}}],
                                         "pageInfo": {"hasNextPage": False}})
        with self.assertRaises(PublishError):
            c.check_duplicate(REEL)

    def test_wrong_returned_channel_cannot_count_as_published(self):
        c, ledger = client(), Ledger()
        c.post.return_value["channelId"] = "wrong"
        with self.assertRaises(PublishError):
            publish_one(REEL, c, ledger)
        self.assertNotEqual(ledger.entry["phase"], "published")


if __name__ == "__main__":
    unittest.main()
