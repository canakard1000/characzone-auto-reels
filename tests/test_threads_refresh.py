import copy
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import requests
from publish_threads import PublishError
from refresh_threads_token import refresh, renew
from threads_token_store import TokenStore, current_token, seal, unseal


class MemoryStore:
    root_secret = 'test-root-not-a-real-token'

    def __init__(self, state=None):
        self.state = state or {}
        self.history = []

    def read(self):
        return copy.deepcopy(self.state)

    def save(self, state):
        self.state = copy.deepcopy(state)
        self.history.append(copy.deepcopy(state))


class RenewalTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 24, tzinfo=timezone.utc)
        self.validate = Mock()
        self.api = Mock(return_value=('rotated-test-token', 5184000))

    def active(self, age, remaining=50):
        return {'access_token': 'active-test-token',
                'refreshed_at': (self.now-timedelta(days=age)).isoformat(),
                'expires_at': (self.now+timedelta(days=remaining)).isoformat()}

    def test_rotated_token_is_saved_before_validation_then_promoted(self):
        store = MemoryStore()
        def validate(token):
            if token == 'rotated-test-token':
                self.assertEqual(store.state['pending']['access_token'], token)
        result, active = renew(store, validate, self.api, self.now)
        self.assertEqual(result, 'renewed')
        self.assertEqual(store.state['active'], active)
        self.assertNotIn('pending', store.state)
        self.assertEqual(len(store.history), 2)

    def test_pending_survives_validation_error_and_recovers_without_refresh(self):
        store = MemoryStore({'active': self.active(8)})
        self.validate.side_effect = [None, PublishError('temporary failure')]
        with self.assertRaises(PublishError):
            renew(store, self.validate, self.api, self.now)
        self.assertEqual(store.state['active']['access_token'], 'active-test-token')
        self.assertIn('pending', store.state)
        renew(store, Mock(), self.api, self.now)
        self.api.assert_called_once()
        self.assertEqual(store.state['active']['access_token'], 'rotated-test-token')

    def test_daily_check_does_not_rotate_fresh_token(self):
        for age in (0, 1, 6):
            with self.subTest(age=age):
                result, _ = renew(MemoryStore({'active': self.active(age)}), self.validate, self.api, self.now)
                self.assertEqual(result, 'checked')
        self.api.assert_not_called()

    def test_weekly_or_near_expiry_renews(self):
        for age, remaining in ((7, 50), (2, 13)):
            with self.subTest(age=age):
                result, _ = renew(MemoryStore({'active': self.active(age, remaining)}), self.validate, self.api, self.now)
                self.assertEqual(result, 'renewed')

    def test_save_failure_never_reports_success(self):
        store = MemoryStore()
        store.save = Mock(side_effect=OSError('push failed'))
        with self.assertRaises(OSError):
            renew(store, self.validate, self.api, self.now)
        self.assertNotIn('active', store.state)

    def test_refresh_accepts_rotated_credential_and_official_query_format(self):
        request = Mock(return_value=Mock(ok=True, json=lambda: {'access_token': 'new-test-token', 'expires_in': 5184000}))
        self.assertEqual(refresh('old-test-token', request), ('new-test-token', 5184000))
        self.assertEqual(request.call_args.kwargs['params'], {'access_token':'old-test-token','grant_type':'th_refresh_token'})

    def test_refresh_errors_never_echo_credentials_or_response(self):
        request = Mock(return_value=Mock(ok=False, status_code=400, json=lambda: {'error': {'code':190,'message':'private-token'}}))
        with self.assertRaises(PublishError) as error:
            refresh('private-token', request)
        self.assertNotIn('private-token', str(error.exception))
        request.side_effect = requests.RequestException('https://example/?access_token=private-token')
        with self.assertRaises(PublishError) as error:
            refresh('private-token', request)
        self.assertNotIn('private-token', str(error.exception))

    def test_invalid_expiry_rejected(self):
        for expiry in (None, 0, -1, True, '5184000'):
            request = Mock(return_value=Mock(ok=True, json=lambda: {'access_token':'new-test-token','expires_in':expiry}))
            with self.assertRaises(PublishError):
                refresh('old-test-token', request)


@unittest.skipUnless(importlib.util.find_spec('cryptography'), 'Threads-only encryption dependency')
class EncryptionTests(unittest.TestCase):
    def test_roundtrip_randomized_and_no_plaintext(self):
        state = {'active': {'access_token':'test-sensitive-token'}}
        first = seal(state, 'test-root-key')
        self.assertNotIn('test-sensitive-token', json.dumps(first))
        self.assertEqual(unseal(first, 'test-root-key'), state)
        self.assertNotEqual(first, seal(state, 'test-root-key'))

    def test_wrong_key_and_tampering_fail_closed(self):
        envelope = seal({'active': {}}, 'test-root-key')
        with self.assertRaises(Exception):
            unseal(envelope, 'wrong-key')
        envelope['ciphertext'] = 'AAAA' + envelope['ciphertext'][4:]
        with self.assertRaises(Exception):
            unseal(envelope, 'test-root-key')

    def test_publisher_uses_active_and_blocks_pending_or_corrupt_state(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TokenStore(directory, 'test-root-key')
            self.assertEqual(current_token(directory, 'test-root-key'), 'test-root-key')
            store.path.write_text(json.dumps(seal({'active': {'access_token':'latest-test-token'}}, store.root_secret)))
            self.assertEqual(current_token(directory, store.root_secret), 'latest-test-token')
            store.path.write_text(json.dumps(seal({'pending':{'access_token':'unverified-test-token'}}, store.root_secret)))
            with self.assertRaises(ValueError):
                current_token(directory, store.root_secret)
            store.path.write_text('corrupt')
            with self.assertRaises(ValueError):
                current_token(directory, store.root_secret)
        with self.assertRaises(ValueError):
            current_token(directory, 'test-root-key')
