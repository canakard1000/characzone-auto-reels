import unittest

from sync_telegram_approvals import latest_pending


class TelegramApprovalTests(unittest.TestCase):
    def test_plain_approval_selects_upcoming_reels_in_schedule_order(self):
        reels = [
            {
                "id": "pm",
                "scheduled_for": "2099-01-01T07:00:00+00:00",
                "telegram_notified": True,
                "approved": False,
                "rejected": False,
                "published": False,
            },
            {
                "id": "am",
                "scheduled_for": "2099-01-01T00:00:00+00:00",
                "telegram_notified": True,
                "approved": False,
                "rejected": False,
                "published": False,
            },
        ]

        self.assertEqual(latest_pending(reels)["id"], "am")
        reels[1]["approved"] = True
        self.assertEqual(latest_pending(reels)["id"], "pm")


if __name__ == "__main__":
    unittest.main()
