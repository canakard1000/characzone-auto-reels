"""Read-only Ownerclan supplier-order report. Does not read unplaced market orders."""
import json
import os
import sys
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

ENDPOINT = 'https://api.ownerclan.com/v1/graphql'


class MonitorError(Exception):
    pass


def post(url, payload, headers=None):
    request = urllib.request.Request(url, json.dumps(payload).encode(),
                                    {'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except Exception:
        # URLs can contain Telegram tokens; never print exception strings.
        raise MonitorError('서비스 요청 실패: 인증·통신 상태 확인 필요') from None


def query_orders(token):
    orders, cursor, seen = [], None, set()
    for _ in range(100):
        after = ', after: ' + json.dumps(cursor) if cursor else ''
        query = ('query { allOrders(first: 100' + after + ') { '
                 'pageInfo { hasNextPage endCursor } edges { node { '
                 'key status note createdAt updatedAt products { itemKey quantity '
                 'trackingNumber shippingCompanyName shippedDate } } } } }')
        result = post(ENDPOINT, {'query': query}, {'Authorization': 'Bearer ' + token})
        if result.get('errors'):
            raise MonitorError('오너클랜 API 조회 오류: 주문 없음으로 판단하지 않음')
        try:
            connection = result['data']['allOrders']
            rows, page = connection['edges'], connection['pageInfo']
            if not isinstance(rows, list) or not isinstance(page['hasNextPage'], bool):
                raise ValueError()
            for row in rows:
                node = row['node']
                if not node.get('key') or not isinstance(node.get('products'), list):
                    raise ValueError()
                if node['key'] in seen:
                    raise ValueError()
                seen.add(node['key'])
                orders.append(node)
        except (KeyError, TypeError, ValueError):
            raise MonitorError('오너클랜 응답 형식 오류: 결과 미확인') from None
        if not page['hasNextPage']:
            return orders
        next_cursor = page.get('endCursor')
        if not next_cursor or next_cursor == cursor:
            raise MonitorError('페이지 조회 중단: 전체 주문 확인 실패')
        cursor = next_cursor
    raise MonitorError('조회 한도 초과: 전체 주문 확인 실패')


def report(orders):
    lines = ['[오너클랜 발주·송장 점검]',
             datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M KST'),
             '주의: 쇼핑몰의 미발주 새 주문은 이 조회에 포함되지 않습니다.',
             f'최근 90일 발주 내역: {len(orders)}건']
    if not orders:
        lines.append('오너클랜 발주 내역 없음. 쇼핑몰 새 주문 없음이라는 뜻은 아닙니다.')
    for order in orders:
        lines.append(f"발주 {order['key']} / 상태 {order.get('status', '미확인')}")
        for product in order['products']:
            line = f"상품 {product.get('itemKey', '미확인')} × {product.get('quantity', '?')}"
            tracking = product.get('trackingNumber')
            if tracking:
                line += f" / {product.get('shippingCompanyName') or '택배사 미확인'} / 송장 {tracking}"
            else:
                line += ' / 송장 미등록'
            lines.append(line)
    return '\n'.join(lines)


def send_telegram(message):
    token, chat = os.environ.get('TELEGRAM_BOT_TOKEN'), os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat:
        raise MonitorError('텔레그램 연결 설정 누락')
    # Do not retry ambiguous sends; avoid duplicate messages.
    for start in range(0, len(message), 3500):
        result = post('https://api.telegram.org/bot' + token + '/sendMessage',
                      {'chat_id': chat, 'text': message[start:start + 3500]})
        if result.get('ok') is not True or not result.get('result', {}).get('message_id'):
            raise MonitorError('텔레그램 전송 확인 실패')


def main():
    try:
        token = os.environ.get('OWNERCLAN_JWT')
        if not token:
            raise MonitorError('OWNERCLAN_JWT 설정 누락: 조회를 실행하지 못함')
        message = report(query_orders(token))
    except MonitorError as error:
        message = '[오너클랜 점검 실패]\n' + str(error) + '\n주문·송장 현황은 미확인입니다. 직접 확인이 필요합니다.'
        try:
            send_telegram(message)
        except MonitorError:
            print('조회 및 오류 알림 실패. 연결 설정 확인 필요.', file=sys.stderr)
        return 1
    try:
        send_telegram(message)
    except MonitorError:
        print('보고 전송 실패. 확인 필요.', file=sys.stderr)
        return 1
    print('공급사 발주 조회 및 Telegram message_id 확인 완료. 쇼핑몰 새 주문 조회는 미연결.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
