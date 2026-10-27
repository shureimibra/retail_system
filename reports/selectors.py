from collections import OrderedDict

from django.db.models import Case, Count, F, Sum, Value, When
from django.db.models.functions import TruncMonth
from django.utils.dateparse import parse_date

from intents.models import BlockedPurchaseIntent, IntentEvent


def get_report_data(shop, start_date_str=None, end_date_str=None, status=None):
    qs = BlockedPurchaseIntent.objects.filter(shop=shop).select_related('customer', 'product', 'variation', 'recorded_by')

    if start_date_str:
        start_date = parse_date(start_date_str)
        if start_date:
            qs = qs.filter(created_at__date__gte=start_date)

    if end_date_str:
        end_date = parse_date(end_date_str)
        if end_date:
            qs = qs.filter(created_at__date__lte=end_date)

    if status:
        qs = qs.filter(status=status)

    return qs.order_by('-created_at')


def recovered_by_month(shop, start=None, end=None):
    """Sales paid in full, by the month they were paid. Declined and expired never count."""
    events = IntentEvent.objects.filter(intent__shop=shop, kind='status', to_status=BlockedPurchaseIntent.RECOVERED,
                                        intent__status=BlockedPurchaseIntent.RECOVERED)
    if start:
        events = events.filter(created_at__date__gte=start)
    if end:
        events = events.filter(created_at__date__lte=end)
    months = OrderedDict()
    for event in (events.annotate(month=TruncMonth('created_at')).select_related('intent')
                  .order_by('month', 'intent_id')):
        row = months.setdefault(event.month, {'month': event.month, 'count': 0, 'money': 0.0, 'ids': set()})
        if event.intent_id in row['ids']:
            continue
        row['ids'].add(event.intent_id)
        row['count'] += 1
        row['money'] += float(event.intent.estimated_value or 0)
    return [{k: v for k, v in row.items() if k != 'ids'} for row in months.values()]


def demand_by_item(shop, start=None, end=None):
    """Missed sales per item, option and reason in the period: what customers asked for and why they left."""
    qs = BlockedPurchaseIntent.objects.filter(shop=shop)
    if start:
        qs = qs.filter(created_at__date__gte=start)
    if end:
        qs = qs.filter(created_at__date__lte=end)
    reasons = dict(BlockedPurchaseIntent.CONSTRAINT_CHOICES)
    qs = qs.annotate(reason=Case(When(constraint_type=BlockedPurchaseIntent.OVER_BUDGET, then=Value(BlockedPurchaseIntent.PRICE_TOO_HIGH)),
                                 default=F('constraint_type')))
    rows = (qs.values('product__name', 'variation__option1', 'variation__option2', 'variation__option3', 'reason')
            .annotate(count=Count('id'), money=Sum('estimated_value'))
            .order_by('-count', 'product__name'))
    return [{'product': r['product__name'],
             'option': ' / '.join(v for v in (r['variation__option1'], r['variation__option2'], r['variation__option3']) if v)
                       or 'Any option',
             'reason': reasons.get(r['reason'], r['reason']),
             'count': r['count'], 'money': float(r['money'] or 0)} for r in rows]
