import unittest
from unittest.mock import Mock
import requests
from refresh_threads_token import refresh, PublishError

class RefreshTests(unittest.TestCase):
    def test_existing_token_renewal(self):
        req = Mock(return_value=Mock(ok=True, json=lambda: {"access_token": "test-secret", "expires_in": 5184000}))
        self.assertEqual(refresh("test-secret", req), 5184000)
        self.assertNotIn("test-secret", req.call_args.args[0])
        self.assertNotIn("access_token", req.call_args.kwargs["params"])

    def test_rotated_token_not_silently_discarded(self):
        req = Mock(return_value=Mock(ok=True, json=lambda: {"access_token": "different-secret", "expires_in": 5184000}))
        with self.assertRaises(PublishError) as err:
            refresh("test-secret", req)
        self.assertNotIn("different-secret", str(err.exception))
        self.assertIn("replacement", str(err.exception))

    def test_error_body_not_exposed(self):
        req = Mock(return_value=Mock(ok=False, status_code=400, json=lambda: {"error": {"code": 190, "message": "test-secret"}}))
        with self.assertRaises(PublishError) as err:
            refresh("test-secret", req)
        self.assertNotIn("test-secret", str(err.exception))

    def test_transport_error_not_exposed(self):
        req = Mock(side_effect=requests.RequestException("test-secret"))
        with self.assertRaises(PublishError) as err:
            refresh("test-secret", req)
        self.assertNotIn("test-secret", str(err.exception))

    def test_invalid_expiry_rejected(self):
        for expiry in [None, 0, -1, True, "5184000"]:
            req = Mock(return_value=Mock(ok=True, json=lambda: {"access_token": "test-secret", "expires_in": expiry}))
            with self.assertRaises(PublishError):
                refresh("test-secret", req)

if __name__ == '__main__':
    unittest.main()
