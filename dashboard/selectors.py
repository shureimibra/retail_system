"""Reads for Home. Each function feeds one widget; only the widgets on the person's layout are computed."""
from datetime import timedelta

from django.db.models import Count, OuterRef, Subquery, Sum
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


def needs_you(shop):
    """
    Everything someone should act on now. Most valuable first: customers waiting for an answer,
    overdue pickups, promises due, then messages that couldn't be delivered; newest first within each.
    Nothing is cut off here; Home shows the first few and the rest on "Show all".
    """
    today = timezone.localdate()
    rows = []
    last = Message.objects.filter(conversation=OuterRef('pk')).order_by('-created_at', '-id')
    waiting = (Conversation.objects.filter(shop=shop)
               .annotate(last_direction=Subquery(last.values('direction')[:1]), last_body=Subquery(last.values('body')[:1]))
               .filter(last_direction=Message.INBOUND).select_related('customer'))
    for conv in waiting:
        who = conv.customer.first_name or conv.customer.phone_number
        rows.append({'kind': 'reply', 'priority': 0, 'badge': 'Waiting for you', 'badge_class': 'in_conversation',
                     'title': f'{who} is waiting for your answer' + (' (unread)' if conv.unread_count else ''),
                     'sub': (conv.last_body or '')[:100], 'at': conv.last_inbound_at,
                     'action': 'Reply', 'url': reverse('notifications:conversation', args=[conv.pk])})

    for intent in (Intent.objects.filter(shop=shop, status=Intent.RESERVED, pickup_by__lt=today)
                   .select_related('customer', 'product', 'variation')):
        rows.append({'kind': 'pickup', 'priority': 1, 'badge': 'Reserved', 'badge_class': 'reserved',
                     'title': f"{intent.customer.first_name or intent.customer.phone_number}'s pickup is overdue",
                     'sub': f'{intent.product.name}{" · " + intent.variation.label if intent.variation else ""}'
                            f' · was due {_day(intent.pickup_by)}',
                     'at': None, 'sort_day': intent.pickup_by,
                     'action': 'Open', 'url': reverse('intents:update', args=[intent.pk])})

    due = Intent.objects.filter(shop=shop, status=Intent.OPEN, needed_by__isnull=False,
                                needed_by__lte=today + timedelta(days=2))
    due_count = due.count()
    if due_count:
        first = due.order_by('needed_by').values_list('needed_by', flat=True).first()
        rows.append({'kind': 'promise', 'priority': 2, 'badge': 'Open', 'badge_class': 'open',
                     'title': f'{due_count} promise{"s" if due_count != 1 else ""} due by {_day(first)}',
                     'sub': 'Nothing ordered yet', 'at': None,
                     'action': 'To order', 'url': reverse('intents:to_order')})

    week_ago = timezone.now() - timedelta(days=7)
    failed = (Message.objects.filter(shop=shop, direction=Message.OUTBOUND, status=Message.FAILED, created_at__gte=week_ago,
                                     alert_dismissed=False,
                                     intent__status__in=Intent.WAITING_STATUSES + [Intent.BACK_IN_STOCK, Intent.NOTIFIED])
              .select_related('conversation__customer').order_by('-created_at'))
    seen = set()
    for message in failed:
        customer = message.conversation.customer if message.conversation else None
        if customer is None or customer.pk in seen:
            continue
        seen.add(customer.pk)
        if message.error_code == 'network':
            why = "Couldn't connect to the message service (internet problem). It will be tried again."
        else:
            why = message.error_detail or message.get_status_display()
        rows.append({'kind': 'failed', 'priority': 3, 'badge': 'Send failed', 'badge_class': 'failed',
                     'title': f"Couldn't reach {customer.first_name or customer.phone_number}",
                     'sub': f'{message.get_channel_display()}: {why}'[:160], 'at': message.created_at,
                     'action': 'Fix number', 'url': reverse('customers:update', args=[customer.pk]),
                     'dismiss_id': message.pk})

    far_past = timezone.now() - timedelta(days=3650)
    rows.sort(key=lambda r: r['at'] or far_past, reverse=True)
    rows.sort(key=lambda r: r['priority'])  # stable: newest first within each kind
    return rows


def reasons(shop, period):
    qs = _in_period(Intent.objects.filter(shop=shop), 'created_at', period)
    total = qs.count()
    labels = dict(Intent.CONSTRAINT_CHOICES)
    counts = {}
    for r in qs.values('constraint_type').annotate(count=Count('id')):
        label = labels.get(r['constraint_type'], r['constraint_type'])  # both price reasons share one label
        counts[label] = counts.get(label, 0) + r['count']
    return [{'label': label, 'count': count, 'percent': round(100 * count / total)}
            for label, count in sorted(counts.items(), key=lambda item: -item[1])]


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
