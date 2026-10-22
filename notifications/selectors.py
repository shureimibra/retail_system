"""Reads for Conversations: the inbox, one chat, and the deal beside it."""
from django.db.models import OuterRef, Q, Subquery
from django.utils import timezone

from intents.models import BlockedPurchaseIntent as Intent
from .gateway import WHATSAPP_WINDOW
from .models import Conversation, Message

# Which open item a conversation is "about" when a customer has several: the one furthest along.
STAGE_ORDER = [Intent.RESERVED, Intent.IN_CONVERSATION, Intent.NOTIFIED, Intent.BACK_IN_STOCK, Intent.ON_ORDER, Intent.OPEN]
DEAL_STEPS = [(Intent.NOTIFIED, 'Notified'), (Intent.IN_CONVERSATION, 'Talking'), (Intent.RESERVED, 'Reserved'),
              (Intent.RECOVERED, 'Paid')]


def inbox(shop, show='all', q='', limit=None):
    last = Message.objects.filter(conversation=OuterRef('pk')).order_by('-created_at')
    conversations = (Conversation.objects.filter(shop=shop, messages__isnull=False).distinct()
                     .select_related('customer')
                     .annotate(last_body=Subquery(last.values('body')[:1]),
                               last_direction=Subquery(last.values('direction')[:1]),
                               last_status=Subquery(last.values('status')[:1]))
                     .order_by('-unread_count', '-last_message_at'))
    if show == 'needs_reply':
        conversations = conversations.filter(unread_count__gt=0)
    q = (q or '').strip()
    if q:
        conversations = conversations.filter(Q(customer__first_name__icontains=q) | Q(customer__last_name__icontains=q)
                                             | Q(customer__phone_number__icontains=q))
    conversations = list(conversations[:limit] if limit else conversations)
    _attach_main_item(conversations)
    return conversations


def _attach_main_item(conversations):
    customer_ids = [c.customer_id for c in conversations]
    open_items = {}
    for intent in (Intent.objects.filter(customer_id__in=customer_ids).exclude(status__in=Intent.CLOSED_STATUSES)
                   .only('id', 'customer_id', 'status')):
        current = open_items.get(intent.customer_id)
        if current is None or STAGE_ORDER.index(intent.status) < STAGE_ORDER.index(current.status):
            open_items[intent.customer_id] = intent
    for conversation in conversations:
        conversation.main_item = open_items.get(conversation.customer_id)


def reply_window(conversation, now=None):
    """Hours left to send free text on WhatsApp (0 when closed)."""
    if not conversation.last_inbound_at:
        return 0
    left = conversation.last_inbound_at + WHATSAPP_WINDOW - (now or timezone.now())
    return max(0, int(left.total_seconds() // 3600)) if left.total_seconds() > 0 else 0


def chat(conversation):
    return list(conversation.messages.select_related('intent__product', 'intent__variation').order_by('created_at'))


def deals(conversation):
    """The customer's open items, furthest along first, with what the deal panel shows for each."""
    from products.models import StockHold
    shop = conversation.shop
    items = list(Intent.objects.filter(customer=conversation.customer).exclude(status__in=Intent.CLOSED_STATUSES)
                 .select_related('product', 'variation', 'recorded_by').prefetch_related('payments', 'holds'))
    items.sort(key=lambda i: (STAGE_ORDER.index(i.status), -i.pk))
    schedule = shop.follow_up_schedule
    for intent in items:
        reached = [s for s, _ in DEAL_STEPS].index(intent.status) if intent.status in [s for s, _ in DEAL_STEPS] else -1
        intent.steps = [(label, 'done' if i < reached else 'now' if i == reached else '') for i, (_, label) in enumerate(DEAL_STEPS)]
        hold = next((h for h in intent.holds.all() if h.status == StockHold.ACTIVE), None)
        intent.held_until = timezone.localtime(hold.expires_at).date() if hold else None
        intent.paid = intent.amount_paid
        intent.owed = intent.balance
        if intent.status == Intent.NOTIFIED and schedule:
            intent.follow_up_state = f'{intent.follow_ups_sent} of {len(schedule)} reminders sent'
        elif intent.status in (Intent.IN_CONVERSATION, Intent.RESERVED):
            intent.follow_up_state = 'Paused, they replied'
        else:
            intent.follow_up_state = ''
        intent.other_options = [v for v in intent.product.variations.prefetch_related('holds').all()
                                if v.pk != intent.variation_id]
    return items
