"""
Work that happens on a schedule rather than when someone clicks: follow-ups,
expiry and message retries. process_due() runs every 15 minutes (Celery beat),
or by hand with `python manage.py process_due`.
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from notifications.gateway import queue_message, retry_due_messages
from .models import BlockedPurchaseIntent as Intent
from .services import log_event, transition


def process_due(now=None):
    now = now or timezone.now()
    # Lapsed holds go first: the expiries below hand freed units to the next customer,
    # and those brand-new holds must not be mistaken for lapsed ones in the same run.
    holds_returned = _return_lapsed_holds(now)
    summary = {
        'follow_ups_sent': _send_follow_ups(now),
        'expired_no_reply': _expire_unanswered(now),
        'expired_not_collected': _expire_uncollected(now),
        'expired_waiting': _expire_long_waits(now),
        'expired_quiet': _expire_quiet_conversations(now),
        'holds_returned': holds_returned,
    }
    summary['messages_retried'] = len(retry_due_messages())
    return summary


def _schedule(shop):
    """The shop's reminder days, and the day the request expires after the last one."""
    days = shop.follow_up_schedule
    return days, (days[-1] if days else 0) + shop.expire_days_after_last_follow_up


def _send_follow_ups(now):
    sent = 0
    for intent in Intent.objects.filter(status=Intent.NOTIFIED, notified_at__isnull=False).select_related('customer', 'shop'):
        days, _ = _schedule(intent.shop)
        if intent.follow_ups_sent >= len(days):
            continue
        if now >= intent.notified_at + timedelta(days=days[intent.follow_ups_sent]):
            with transaction.atomic():
                number = intent.follow_ups_sent + 1
                queue_message(intent, f'reminder_{min(number, 3)}')
                intent.follow_ups_sent = number
                intent.save(update_fields=['follow_ups_sent', 'updated_at'])
                log_event(intent, 'follow_up', note=f'Reminder {number} of {len(days)}')
            sent += 1
    return sent


def _expire_unanswered(now):
    expired = 0
    for intent in Intent.objects.filter(status=Intent.NOTIFIED, notified_at__isnull=False).select_related('shop'):
        days, expire_after = _schedule(intent.shop)
        if intent.follow_ups_sent >= len(days) and intent.notified_at <= now - timedelta(days=expire_after):
            transition(intent, Intent.EXPIRED, note=f'No reply after {len(days)} reminders')
            expired += 1
    return expired


def _expire_uncollected(now):
    """Reserved items not collected by the pickup date. With a deposit paid, staff decide instead."""
    today = timezone.localdate(now)
    expired = 0
    for intent in Intent.objects.filter(status=Intent.RESERVED, pickup_by__lt=today):
        if intent.payments.exists():
            if not intent.events.filter(kind='pickup_overdue').exists():
                log_event(intent, 'pickup_overdue', note='Deposit paid but not collected by the pickup date')
            continue
        transition(intent, Intent.EXPIRED, note='Not collected by the pickup date')
        expired += 1
    return expired


def _expire_long_waits(now):
    expired = 0
    for intent in Intent.objects.filter(status__in=Intent.WAITING_STATUSES, expires_at__lte=now):
        transition(intent, Intent.EXPIRED, note='Still waiting when the 30 days ran out')
        expired += 1
    return expired


def _expire_quiet_conversations(now):
    """
    The customer replied but paid nothing before their held unit's time ran out. Close it so
    the unit goes to the next customer waiting. A deposit always keeps the hold (Reserved).
    """
    from products.models import StockHold
    expired = 0
    quiet = (Intent.objects.filter(status=Intent.IN_CONVERSATION, payments__isnull=True,
                                   holds__status=StockHold.ACTIVE, holds__expires_at__lt=now).distinct())
    for intent in quiet:
        transition(intent, Intent.EXPIRED, note='No deposit before the held unit\'s time ran out; it went to the next customer')
        expired += 1
    return expired


def _return_lapsed_holds(now):
    """A unit was held but the customer could never be reached (message failed). Free it for the next customer."""
    from products.models import StockHold
    returned = 0
    lapsed = (StockHold.objects.filter(status=StockHold.ACTIVE, expires_at__lt=now,
                                       intent__status=Intent.BACK_IN_STOCK).select_related('intent'))
    for hold in lapsed:
        transition(hold.intent, Intent.OPEN, note='Hold ended before the customer could be reached')
        returned += 1
    return returned


def notify_price_drop(price_change):
    """A price went down: tell everyone waiting for a lower price on that item."""
    product, variation = price_change.product, price_change.variation
    waiting = Intent.objects.filter(product=product, status__in=Intent.WAITING_STATUSES,
                                    constraint_type__in=Intent.PRICE_DROP_REASONS, expires_at__gt=timezone.now())
    if variation is not None:
        waiting = waiting.filter(variation=variation) | waiting.filter(variation__isnull=True)
    notified = 0
    for intent in waiting:
        unit_price = intent.variation.effective_price if intent.variation else product.base_price
        intent.estimated_value = unit_price * intent.requested_quantity
        intent.save(update_fields=['estimated_value', 'updated_at'])
        log_event(intent, 'price_drop', note=f'{price_change.old_price} → {price_change.new_price}')
        queue_message(intent, 'price_drop')
        notified += 1
    return notified
