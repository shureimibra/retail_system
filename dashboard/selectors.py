"""Reads for Home. Each function feeds one widget; only the widgets on the person's layout are computed."""
from datetime import timedelta

from django.db.models import Count, Sum
from django.urls import reverse
from django.utils import timezone

from analytics.selectors import get_to_order
from intents.models import BlockedPurchaseIntent as Intent, IntentEvent, Payment, Visit
from notifications.models import Conversation, Message


def _day(d):
    """Fri 24 Oct"""
    return f'{d.strftime("%a")} {d.day} {d.strftime("%b")}'


def _short(amount):
    """12500 → 12.5k, 1200000 → 1.2M: fits a narrow chart column without cutting digits."""
    for size, suffix in ((1_000_000, 'M'), (1_000, 'k')):
        if amount >= size:
            return f'{amount / size:.1f}'.rstrip('0').rstrip('.') + suffix
    return f'{amount:.0f}'


def _in_period(qs, field, period):
    if period['start']:
        qs = qs.filter(**{f'{field}__date__gte': period['start']})
    if period['end']:
        qs = qs.filter(**{f'{field}__date__lte': period['end']})
    return qs


def recovered_in(shop, start=None, end=None):
    """Money and count of missed sales paid in full between two dates (by the day they were paid)."""
    events = IntentEvent.objects.filter(intent__shop=shop, kind='status', to_status=Intent.RECOVERED,
                                        intent__status=Intent.RECOVERED)
    if start:
        events = events.filter(created_at__date__gte=start)
    if end:
        events = events.filter(created_at__date__lte=end)
    intents = Intent.objects.filter(id__in=events.values('intent_id'))
    totals = intents.aggregate(money=Sum('estimated_value'), count=Count('id'))
    return float(totals['money'] or 0), totals['count']


def key_numbers(shop, period):
    today = timezone.localdate()
    waiting = Intent.objects.filter(shop=shop, status__in=Intent.WAITING_STATUSES)
    reserved = Intent.objects.filter(shop=shop, status=Intent.RESERVED)
    hour_ago = timezone.now() - timedelta(hours=1)
    money, count = recovered_in(shop, period['start'], period['end'])
    change = None
    if period['start'] and period['end']:
        length = (period['end'] - period['start']).days + 1
        before, _ = recovered_in(shop, period['start'] - timedelta(days=length), period['start'] - timedelta(days=1))
        if before:
            change = round(100 * (money - before) / before)
    return {
        'waiting_money': float(waiting.aggregate(total=Sum('estimated_value'))['total'] or 0),
        'waiting_customers': waiting.values('customer_id').distinct().count(),
        'due_this_week': waiting.filter(needed_by__lte=today + timedelta(days=7)).count(),
        'in_conversation': Intent.objects.filter(shop=shop, status=Intent.IN_CONVERSATION).count(),
        'unanswered': Conversation.objects.filter(shop=shop, unread_count__gt=0, last_inbound_at__lt=hour_ago).count(),
        'reserved': reserved.count(),
        'deposits': float(Payment.objects.filter(intent__in=reserved).aggregate(total=Sum('amount'))['total'] or 0),
        'recovered_money': money,
        'recovered_count': count,
        'recovered_change': change,
    }


def needs_you(shop, limit=8):
    """One row per thing someone should act on now, newest first."""
    today = timezone.localdate()
    rows = []
    for conv in (Conversation.objects.filter(shop=shop, unread_count__gt=0)
                 .select_related('customer').order_by('-last_inbound_at')[:limit]):
        last = conv.messages.filter(direction=Message.INBOUND).order_by('-created_at').first()
        rows.append({'kind': 'reply', 'badge': 'In conversation', 'badge_class': 'in_conversation',
                     'title': f'{conv.customer.first_name or conv.customer.phone_number} replied',
                     'sub': (last.body[:80] if last else ''), 'at': conv.last_inbound_at,
                     'action': 'Reply', 'url': reverse('notifications:conversation', args=[conv.pk])})

    due = (Intent.objects.filter(shop=shop, status=Intent.OPEN, needed_by__isnull=False,
                                 needed_by__lte=today + timedelta(days=2)))
    due_count = due.count()
    if due_count:
        first = due.order_by('needed_by').values_list('needed_by', flat=True).first()
        rows.append({'kind': 'promise', 'badge': 'Open', 'badge_class': 'open',
                     'title': f'{due_count} promise{"s" if due_count != 1 else ""} due by {_day(first)}',
                     'sub': 'Nothing ordered yet', 'at': None,
                     'action': 'View', 'url': reverse('intents:list') + '?show=stock'})

    for intent in (Intent.objects.filter(shop=shop, status=Intent.RESERVED, pickup_by__lt=today)
                   .select_related('customer', 'product', 'variation').order_by('pickup_by')[:limit]):
        rows.append({'kind': 'pickup', 'badge': 'Reserved', 'badge_class': 'reserved',
                     'title': f"{intent.customer.first_name}'s pickup is overdue",
                     'sub': f'{intent.product.name}{" · " + intent.variation.label if intent.variation else ""}'
                            f' · was due {_day(intent.pickup_by)}',
                     'at': None, 'action': 'Open', 'url': reverse('intents:update', args=[intent.pk])})

    week_ago = timezone.now() - timedelta(days=7)
    failed = (Message.objects.filter(shop=shop, direction=Message.OUTBOUND, status=Message.FAILED, created_at__gte=week_ago,
                                     intent__status__in=Intent.WAITING_STATUSES + [Intent.BACK_IN_STOCK, Intent.NOTIFIED])
              .select_related('conversation__customer').order_by('-created_at'))
    seen = set()
    for message in failed:
        customer = message.conversation.customer if message.conversation else None
        if customer is None or customer.pk in seen:
            continue
        seen.add(customer.pk)
        rows.append({'kind': 'failed', 'badge': 'Send failed', 'badge_class': 'failed',
                     'title': f"Couldn't reach {customer.first_name or customer.phone_number}",
                     'sub': f'{message.get_channel_display()}: {message.error_detail or message.get_status_display()}',
                     'at': message.created_at, 'action': 'Fix number', 'url': reverse('customers:update', args=[customer.pk])})
        if len(seen) >= limit:
            break

    far_past = timezone.now() - timedelta(days=3650)
    rows.sort(key=lambda r: r['at'] or far_past, reverse=True)
    return rows[:limit]


def reasons(shop, period):
    qs = _in_period(Intent.objects.filter(shop=shop), 'created_at', period)
    total = qs.count()
    labels = dict(Intent.CONSTRAINT_CHOICES)
    return [{'label': labels.get(r['constraint_type'], r['constraint_type']), 'count': r['count'],
             'percent': round(100 * r['count'] / total)}
            for r in qs.values('constraint_type').annotate(count=Count('id')).order_by('-count')]


def to_order_top(shop, limit=5):
    return [row for row in get_to_order(shop) if row['to_order'] > 0][:limit]


def recovered_weekly(shop, weeks=8):
    """Paid recoveries per week (Monday to Sunday), oldest first, ending this week."""
    today = timezone.localdate()
    this_monday = today - timedelta(days=today.weekday())
    rows = []
    for i in range(weeks - 1, -1, -1):
        start = this_monday - timedelta(weeks=i)
        money, count = recovered_in(shop, start, start + timedelta(days=6))
        rows.append({'label': f'{start.day} {start.strftime("%b")}', 'money': money, 'count': count})
    top = max((r['money'] for r in rows), default=0)
    for row in rows:
        row['percent'] = round(100 * row['money'] / top) if top else 0
        row['short'] = _short(row['money'])
    return rows


def conversion(shop, period, minimum=10):
    visits = _in_period(Visit.objects.filter(shop=shop), 'created_at', period)
    total = visits.count()
    bought = visits.filter(outcome=Visit.BOUGHT).count()
    return {'total': total, 'bought': bought, 'enough': total >= minimum,
            'percent': round(100 * bought / total) if total else 0, 'minimum': minimum}


BUILDERS = {
    'key_numbers': lambda shop, period: key_numbers(shop, period),
    'needs_you': lambda shop, period: needs_you(shop),
    'reasons': lambda shop, period: reasons(shop, period),
    'to_order': lambda shop, period: to_order_top(shop),
    'recovered_weekly': lambda shop, period: recovered_weekly(shop),
    'conversion': lambda shop, period: conversion(shop, period),
}
