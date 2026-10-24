"""
The only code that talks to Safaricom Daraja. Sandbox by default (free, test money);
MPESA_ENV=production switches to the live API once the shop's Till or Paybill is approved.
"""
import base64
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.core.cache import cache

TIMEOUT_SECONDS = 20
HOSTS = {'sandbox': 'https://sandbox.safaricom.co.ke', 'production': 'https://api.safaricom.co.ke'}


class DarajaError(Exception):
    """Daraja refused or couldn't be reached. The message is safe to show staff."""


def _host():
    return HOSTS.get(settings.MPESA_ENV, HOSTS['sandbox'])


def _token():
    key = f'daraja-token-{settings.MPESA_ENV}'
    token = cache.get(key)
    if token:
        return token
    try:
        response = requests.get(f'{_host()}/oauth/v1/generate?grant_type=client_credentials', timeout=TIMEOUT_SECONDS,
                                auth=(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET))
        data = response.json()
    except (requests.RequestException, ValueError):
        raise DarajaError("Couldn't reach M-Pesa. Check the internet connection and try again.")
    token = data.get('access_token')
    if not token:
        raise DarajaError('M-Pesa refused the app keys. Check MPESA_CONSUMER_KEY and MPESA_CONSUMER_SECRET.')
    cache.set(key, token, max(60, int(data.get('expires_in', 3599)) - 60))
    return token


def _password():
    stamp = datetime.now(ZoneInfo('Africa/Nairobi')).strftime('%Y%m%d%H%M%S')
    raw = f'{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{stamp}'
    return base64.b64encode(raw.encode()).decode(), stamp


def _post(path, payload):
    try:
        response = requests.post(f'{_host()}{path}', json=payload, timeout=TIMEOUT_SECONDS,
                                 headers={'Authorization': f'Bearer {_token()}'})
        return response.json()
    except (requests.RequestException, ValueError):
        raise DarajaError("Couldn't reach M-Pesa. Check the internet connection and try again.")


def stk_push(phone, amount, reference, description, callback_url):
    """Show the M-Pesa PIN prompt on the customer's phone. Returns Daraja's reply (CheckoutRequestID...)."""
    password, stamp = _password()
    data = _post('/mpesa/stkpush/v1/processrequest', {
        'BusinessShortCode': settings.MPESA_SHORTCODE, 'Password': password, 'Timestamp': stamp,
        'TransactionType': settings.MPESA_TRANSACTION_TYPE, 'Amount': int(amount),
        'PartyA': phone, 'PartyB': settings.MPESA_SHORTCODE, 'PhoneNumber': phone,
        'CallBackURL': callback_url, 'AccountReference': reference[:12], 'TransactionDesc': description[:13],
    })
    if str(data.get('ResponseCode')) != '0':
        raise DarajaError(data.get('errorMessage') or data.get('ResponseDescription') or 'M-Pesa refused the request.')
    return data


def stk_query(checkout_request_id):
    """Ask M-Pesa how a prompt ended, for when its callback never arrived. Returns Daraja's reply."""
    password, stamp = _password()
    return _post('/mpesa/stkpushquery/v1/query', {
        'BusinessShortCode': settings.MPESA_SHORTCODE, 'Password': password, 'Timestamp': stamp,
        'CheckoutRequestID': checkout_request_id,
    })
