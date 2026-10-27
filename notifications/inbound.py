"""Customer replies, from any provider's webhook or the simulator."""
import re

from django.db import transaction
from django.utils import timezone

from core.phones import normalize_phone
from .gateway import conversation_for
from .models import Message

STOP_WORDS = {'STOP', 'STOPALL', 'UNSUBSCRIBE', 'CANCEL', 'END', 'QUIT'}
WANTS_IT_WORDS = {'YES', 'HOLD', 'KEEP', 'NDIO'}
STOP_CONFIRMATION = "You won't get any more messages from us. Reply START if you change your mind."


def _first_word(body):
    match = re.match(r'\s*([A-Za-z]+)', body or '')
    return match.group(1).upper() if match else ''


def _find_customer(channel, from_address, shop=None):
    from customers.models import Customer
    # Real replies never reach a demo shop's sample customers; the simulator names its shop.
    customers = Customer.objects.filter(shop=shop) if shop else Customer.objects.filter(shop__is_demo=False)
    if channel == Message.EMAIL:
        matches = list(customers.filter(email__iexact=from_address)[:2])
    else:
        phone = normalize_phone(from_address)
        matches = list(customers.filter(phone_number=phone)[:2]) if phone else []
    # Only attach the reply when exactly one customer has this number or address.
    return matches[0] if len(matches) == 1 else None


@transaction.atomic
def receive(channel, from_address, body, to_address='', provider_message_id='', shop=None):
    """
    Record a customer's reply. Returns (message, auto_reply_text); the text is
    what the provider should answer immediately, if anything (STOP confirmation).
    """
    from intents.models import BlockedPurchaseIntent as Intent
    from intents.services import log_event, transition

    customer = _find_customer(channel, from_address, shop)
    clean_from = normalize_phone(from_address) or from_address
    if customer is None:
        message = Message.objects.create(direction=Message.INBOUND, channel=channel, from_address=clean_from,
                                         to_address=to_address, body=body, status=Message.RECEIVED,
                                         provider_message_id=provider_message_id)
        return message, ''

    conversation = conversation_for(customer)
    now = timezone.now()
    message = Message.objects.create(shop_id=customer.shop_id, conversation=conversation, direction=Message.INBOUND,
                                     channel=channel, from_address=clean_from, to_address=to_address, body=body,
                                     status=Message.RECEIVED, provider_message_id=provider_message_id)
    conversation.unread_count += 1
    conversation.last_message_at = conversation.last_inbound_at = now
    conversation.save(update_fields=['unread_count', 'last_message_at', 'last_inbound_at'])

    active = customer.intents.exclude(status__in=Intent.CLOSED_STATUSES)
    word = _first_word(body)
    if word in STOP_WORDS:
        customer.marketing_opt_in = False
        customer.save(update_fields=['marketing_opt_in'])
        for intent in active:
            log_event(intent, 'opted_out', note=f'Customer replied {word}; no more messages')
        return message, STOP_CONFIRMATION
    if word == 'START' and not customer.marketing_opt_in:
        customer.marketing_opt_in = True
        customer.save(update_fields=['marketing_opt_in'])

    for intent in active:
        if intent.status in (Intent.NOTIFIED, Intent.BACK_IN_STOCK):
            transition(intent, Intent.IN_CONVERSATION, note=f'Customer replied: {body[:120]}')
        else:
            log_event(intent, 'customer_replied', note=body[:120])
        if word in WANTS_IT_WORDS:
            log_event(intent, 'wants_it', note=f'Customer replied {word}')
    return message, ''
