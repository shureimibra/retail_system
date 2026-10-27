"""M-Pesa payment prompts: start one, and record the payment once Safaricom confirms it."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from core.phones import normalize_phone
from intents.models import BlockedPurchaseIntent as Intent, Payment
from intents.services import TransitionError, record_payment
from . import daraja
from .models import MpesaRequest

# Daraja result codes that mean the customer didn't pay (cancelled, timed out, wrong PIN, not enough money...).
CANCELLED_CODES = {'1032', '1037', '2001', '1001', '1019', '1025', '1'}
# How long to wait for Safaricom's callback before asking M-Pesa directly.
QUERY_AFTER = timedelta(seconds=30)


def mpesa_mode():
    """off, sandbox or production, plus whether the keys are in place."""
    mode = settings.MPESA_ENV if settings.MPESA_ENV in ('sandbox', 'production') else 'off'
    ready = mode != 'off' and bool(settings.MPESA_CONSUMER_KEY and settings.MPESA_CONSUMER_SECRET
                                   and settings.MPESA_CALLBACK_TOKEN)
    return mode, ready


def callback_url():
    if not settings.SITE_URL.startswith('https://'):
        raise ValueError("M-Pesa needs this site's public https address. Start the tunnel and set SITE_URL to it.")
    return settings.SITE_URL.rstrip('/') + reverse('payments:mpesa-callback', args=[settings.MPESA_CALLBACK_TOKEN])


def mpesa_phone(raw, region='KE'):
    number = normalize_phone(raw, region)
    if not number or not number.startswith('+254'):
        raise ValueError('M-Pesa needs a Kenyan phone number, for example 0712 345 678.')
    return number.lstrip('+')


def request_payment(intent, amount, phone, actor=None):
    """Send the M-Pesa PIN prompt for this item. Nothing is recorded until Safaricom confirms the payment."""
    mode, ready = mpesa_mode()
    if intent.shop.is_demo:
        raise ValueError('M-Pesa is off in the demo shop: record the payment by hand instead.')
    if not ready:
        raise ValueError('M-Pesa is not set up yet. See Settings → Payments.')
    if intent.is_closed:
        raise TransitionError('This item is already closed.')
    try:
        amount = Decimal(str(amount).replace(',', '').strip()).quantize(Decimal('1'))
    except (InvalidOperation, ValueError):
        raise ValueError('Enter the amount as a whole number of shillings.')
    if amount < 1:
        raise ValueError('The amount must be at least 1 shilling.')
    if amount > intent.balance:
        raise ValueError(f'That is more than the balance due ({intent.balance:,.0f}).')
    if intent.mpesa_requests.filter(status=MpesaRequest.PENDING, created_at__gte=timezone.now() - timedelta(minutes=2)).exists():
        raise ValueError('A payment prompt is already waiting on the customer\'s phone. Give them a minute.')
    phone = mpesa_phone(phone, intent.shop.phone_region)
    reply = daraja.stk_push(phone, amount, reference=f'RO{intent.pk}', description=intent.shop.name, callback_url=callback_url())
    return MpesaRequest.objects.create(
        shop=intent.shop, intent=intent, requested_by=actor, phone=phone, amount=amount,
        merchant_request_id=reply.get('MerchantRequestID', ''), checkout_request_id=reply['CheckoutRequestID'])


def _metadata(callback):
    items = callback.get('CallbackMetadata', {}).get('Item', [])
    return {item.get('Name'): item.get('Value') for item in items}


@transaction.atomic
def _settle(checkout_request_id, result_code, result_desc, amount=None, receipt=''):
    """Close a pending request exactly once, whichever arrives first: the callback or our query."""
    request = (MpesaRequest.objects.select_for_update(of=('self',)).select_related('intent')
               .filter(checkout_request_id=checkout_request_id).first())
    if request is None or not request.is_pending:
        return request  # unknown, or already settled (Safaricom can call back more than once)
    request.result_code, request.result_desc = str(result_code), str(result_desc)[:300]
    if str(result_code) != '0':
        request.status = MpesaRequest.CANCELLED if str(result_code) in CANCELLED_CODES else MpesaRequest.FAILED
        request.save()
        return request
    paid = Decimal(str(amount)) if amount is not None else request.amount
    request.receipt = str(receipt or '')[:30]
    if paid != request.amount:
        request.status = MpesaRequest.NEEDS_CHECK
        request.result_desc = f'M-Pesa reported {paid:,.0f}, but {request.amount:,.0f} was asked for. Check and record it by hand.'
        request.save()
        return request
    try:
        payment = record_payment(request.intent, paid, Payment.MPESA, reference=request.receipt or 'M-Pesa prompt',
                                 actor=request.requested_by)
    except (ValueError, TransitionError) as error:
        request.status = MpesaRequest.NEEDS_CHECK
        request.result_desc = f'Money received, but it could not be recorded: {error}'
        request.save()
        return request
    request.status, request.payment = MpesaRequest.PAID, payment
    request.save()
    return request


def handle_callback(payload):
    """Safaricom's report of how a prompt ended."""
    callback = (payload or {}).get('Body', {}).get('stkCallback', {})
    if not callback.get('CheckoutRequestID'):
        return None
    data = _metadata(callback)
    return _settle(callback['CheckoutRequestID'], callback.get('ResultCode', ''), callback.get('ResultDesc', ''),
                   amount=data.get('Amount'), receipt=data.get('MpesaReceiptNumber', ''))


def refresh(request):
    """If the callback is late (for example the tunnel was down), ask M-Pesa directly."""
    if not request.is_pending or timezone.now() - request.created_at < QUERY_AFTER:
        return request
    try:
        reply = daraja.stk_query(request.checkout_request_id)
    except daraja.DarajaError:
        return request
    if 'ResultCode' not in reply:  # still being processed
        return request
    return _settle(request.checkout_request_id, reply['ResultCode'], reply.get('ResultDesc', '')) or request
