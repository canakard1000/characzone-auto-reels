import unittest
from unittest.mock import patch
import monitor


class MonitorTests(unittest.TestCase):
    def test_authentication_is_not_logged_or_persisted(self):
        with patch.dict(monitor.os.environ, {'OWNERCLAN_USERNAME': 'fake-user',
                        'OWNERCLAN_PASSWORD': 'fake-pass'}, clear=True):
            with patch.object(monitor, 'post', return_value='header.payload.signature') as p:
                self.assertEqual(monitor.get_token(), 'header.payload.signature')
                self.assertEqual(p.call_args.args[0], monitor.AUTH_ENDPOINT)

    def test_authentication_unknown_schema_fails(self):
        with patch.dict(monitor.os.environ, {'OWNERCLAN_USERNAME': 'fake-user',
                        'OWNERCLAN_PASSWORD': 'fake-pass'}, clear=True):
            with patch.object(monitor, 'post', return_value={'unknown': 'value'}):
                with self.assertRaises(monitor.MonitorError):
                    monitor.get_token()

    def test_errors_are_not_empty_orders(self):
        with patch.object(monitor, 'post', return_value={'errors': [{'message': 'bad'}]}):
            with self.assertRaises(monitor.MonitorError):
                monitor.query_orders('fake')

    def test_pagination(self):
        def page(key, more, cursor):
            return {'data': {'allOrders': {'edges': [{'node': {'key': key, 'products': []}}],
                     'pageInfo': {'hasNextPage': more, 'endCursor': cursor}}}}
        with patch.object(monitor, 'post', side_effect=[page('a', True, 'x'), page('b', False, 'y')]) as p:
            self.assertEqual([x['key'] for x in monitor.query_orders('fake')], ['a', 'b'])
            self.assertIn('after: "x"', p.call_args.args[1]['query'])

    def test_missing_order_data_fails(self):
        with patch.object(monitor, 'post', return_value={'data': {'allOrders': None}}):
            with self.assertRaises(monitor.MonitorError):
                monitor.query_orders('fake')

    def test_scope_is_explicit(self):
        self.assertIn('미발주 새 주문', monitor.report([]))
        self.assertIn('쇼핑몰 새 주문 없음이라는 뜻은 아닙니다', monitor.report([]))

    def test_tracking_and_quantity_reported(self):
        result = monitor.report([{'key': 'a', 'status': 'SHIPPED', 'products': [
            {'itemKey': 'p', 'quantity': 6, 'trackingNumber': '123', 'shippingCompanyName': '택배'}]}])
        self.assertIn('× 6', result)
        self.assertIn('송장 123', result)

    def test_telegram_requires_ack(self):
        with patch.dict(monitor.os.environ, {'TELEGRAM_BOT_TOKEN': 'fake', 'TELEGRAM_CHAT_ID': '1'}):
            with patch.object(monitor, 'post', return_value={'ok': False}):
                with self.assertRaises(monitor.MonitorError):
                    monitor.send_telegram('hello')


if __name__ == '__main__':
    unittest.main()
