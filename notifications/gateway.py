"""
The only place messages are sent from. Everything else calls queue_message()
or send_reply(); delivery happens after the database commit, in a Celery task
(run inline in development).
"""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.phones import normalize_phone
from .compose import compose, template_params
from .models import Conversation, Message
from .providers import provider_for

CHANNEL_ORDER = [Message.WHATSAPP, Message.SMS, Message.EMAIL]
# Messages that should only ever reach a customer once per request.
ONCE_PER_REQUEST = {'restock_alert', 'price_drop', 'deposit_receipt', 'reminder_1', 'reminder_2', 'reminder_3'}
WHATSAPP_WINDOW = timedelta(hours=24)


def conversation_for(customer):
    conversation, _ = Conversation.objects.get_or_create(shop_id=customer.shop_id, customer=customer)
    return conversation


def address_for(customer, channel):
    if channel == Message.EMAIL:
        return customer.email or ''
    return normalize_phone(customer.phone_number) or ''


def _pick_channel(customer, preferred, exclude=()):
    order = [preferred] + [c for c in CHANNEL_ORDER if c != preferred]
    for channel in order:
        if channel not in exclude and address_for(customer, channel):
            return channel
    return None


def _photo_url(intent):
    variation = intent.variation
    photo = variation.photo if variation else intent.product.image
    return settings.SITE_URL.rstrip('/') + photo.url if photo else ''


def _queue(message):
    from .tasks import deliver_message
    transaction.on_commit(lambda: deliver_message.delay(message.id))
    return message


def queue_message(intent, template_key, channel=None):
    """Write a customer message about a missed sale and send it after commit."""
    customer = intent.customer
    channel = channel or _pick_channel(customer, intent.preferred_channel) or intent.preferred_channel
    message = Message.objects.create(
        shop_id=intent.shop_id, conversation=conversation_for(customer), intent=intent,
        direction=Message.OUTBOUND, channel=channel, to_address=address_for(customer, channel),
        body=compose(template_key, intent), template_key=template_key,
        media_url=_photo_url(intent) if template_key in ('restock_alert', 'price_drop') else '',
        template_params=template_params(template_key, intent),
    )
    Conversation.objects.filter(pk=message.conversation_id).update(last_message_at=message.created_at)
    return _queue(message)


def send_reply(conversation, body, channel=None):
    """A staff reply in the inbox. Goes out on the channel the customer last used."""
    last_in = conversation.messages.filter(direction=Message.INBOUND).order_by('-created_at').first()
    channel = channel or (last_in.channel if last_in else Message.WHATSAPP)
    message = Message.objects.create(
        shop_id=conversation.shop_id, conversation=conversation, direction=Message.OUTBOUND, channel=channel,
        to_address=address_for(conversation.customer, channel), body=body,
    )
    conversation.last_message_at = timezone.now()
    conversation.save(update_fields=['last_message_at'])
    return _queue(message)


def _reason_not_to_send(message):
    customer = message.conversation.customer if message.conversation else None
    if customer is None:
        return 'No customer for this message'
    if not customer.marketing_opt_in:
        return 'Customer opted out'
    if message.intent and not message.intent.consent_given:
        return 'Customer did not agree to be contacted'
    if not message.to_address:
        return f'No {message.get_channel_display()} address for this customer'
    if message.template_key in ONCE_PER_REQUEST and message.intent and Message.objects.filter(
            intent=message.intent, template_key=message.template_key,
            status__in=Message.SUCCESS_STATUSES).exclude(pk=message.pk).exists():
        return 'Already sent'
    if message.channel == Message.WHATSAPP and not message.template_key:
        last_in = message.conversation.last_inbound_at
        if not last_in or timezone.now() - last_in > WHATSAPP_WINDOW:
            return 'WhatsApp only allows free-text replies within 24 hours of the customer\'s last message'
    return ''


def deliver(message_id):
    """Send one queued (or retry-due) message. Returns the message."""
    with transaction.atomic():
        message = Message.objects.select_for_update(of=('self',)).select_related('conversation__customer', 'intent').get(pk=message_id)
        if message.status not in (Message.QUEUED, Message.FAILED):
            return message
        reason = _reason_not_to_send(message)
        if reason:
            message.status = Message.SKIPPED
            message.error_detail = reason
            message.next_attempt_at = None
            message.save(update_fields=['status', 'error_detail', 'next_attempt_at'])
            return message

    provider = provider_for(message.channel)
    result = provider.send(message)
    now = timezone.now()
    message.attempts += 1
    message.provider = provider.name
    if result.ok:
        message.status = result.status
        message.provider_message_id = result.provider_message_id
        message.sent_at = now
        message.delivered_at = now if result.status == Message.DELIVERED else None
        message.error_code = message.error_detail = ''
        message.next_attempt_at = None
    else:
        message.status = Message.FAILED
        message.error_code, message.error_detail = result.error_code, result.error_detail
        retry = not result.permanent and message.attempts < settings.MESSAGE_MAX_ATTEMPTS
        message.next_attempt_at = now + timedelta(minutes=5 * 2 ** message.attempts) if retry else None
    message.save()

    if result.ok:
        _after_success(message)
    elif result.permanent:
        fall_back(message)
    return message


def _after_success(message):
    from intents.models import BlockedPurchaseIntent as Intent
    from intents.services import log_event, transition
    intent = message.intent
    if intent is None:
        return
    intent.refresh_from_db()
    if message.template_key == 'restock_alert' and intent.status in (Intent.OPEN, Intent.BACK_IN_STOCK):
        transition(intent, Intent.NOTIFIED, note=f'Restock message sent by {message.get_channel_display()}')
    elif message.template_key == 'price_drop' and intent.status in Intent.WAITING_STATUSES:
        transition(intent, Intent.NOTIFIED, note=f'Price-drop message sent by {message.get_channel_display()}')
    else:
        log_event(intent, 'message_sent', note=f'{message.get_channel_display()}: {message.body[:120]}')


def fall_back(message):
    """The channel can't reach this customer (for example not on WhatsApp). Try the next one."""
    if message.intent is None or not message.template_key:
        return None
    tried = set(Message.objects.filter(intent=message.intent, template_key=message.template_key)
                .values_list('channel', flat=True))
    channel = _pick_channel(message.conversation.customer, message.channel, exclude=tried)
    if channel is None:
        return None
    return queue_message(message.intent, message.template_key, channel=channel)


def update_delivery_status(provider_message_id, status, error_code='', error_detail='', permanent=False):
    """A provider told us what happened to a message we sent."""
    message = Message.objects.filter(provider_message_id=provider_message_id, direction=Message.OUTBOUND).first()
    if message is None:
        return None
    now = timezone.now()
    if status == Message.DELIVERED and message.status in (Message.SENT, Message.QUEUED):
        message.status, message.delivered_at = Message.DELIVERED, now
    elif status == Message.READ:
        message.status, message.read_at = Message.READ, now
        message.delivered_at = message.delivered_at or now
    elif status == Message.FAILED:
        message.status, message.error_code, message.error_detail = Message.FAILED, error_code, error_detail[:300]
    message.save()
    if status == Message.FAILED and permanent:
        fall_back(message)
    return message


def retry_due_messages():
    """Re-send messages that failed for a temporary reason and are due another try."""
    due = Message.objects.filter(status=Message.FAILED, next_attempt_at__lte=timezone.now()).values_list('id', flat=True)
    return [deliver(message_id) for message_id in list(due)]
