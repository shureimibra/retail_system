from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth
from intents.models import BlockedPurchaseIntent, IntentEvent, Payment, Visit
from products.models import Product, ProductVariation
from customers.models import Customer
import datetime

from django.utils import timezone
from django.utils.dateparse import parse_date

def _filter_intents(shop, start_date=None, end_date=None, status=None):
    qs = BlockedPurchaseIntent.objects.filter(shop=shop)
    if start_date:
        d = parse_date(start_date) if isinstance(start_date, str) else start_date
        if d:
            qs = qs.filter(created_at__date__gte=d)
    if end_date:
        d = parse_date(end_date) if isinstance(end_date, str) else end_date
        if d:
            qs = qs.filter(created_at__date__lte=d)
    if status:
        qs = qs.filter(status=status)
    return qs

def get_dashboard_kpis(shop, start_date=None, end_date=None, status=None):
    base_qs = _filter_intents(shop, start_date, end_date, status)
    
    total_products = Product.objects.filter(shop=shop).count()
    total_customers = Customer.objects.filter(shop=shop).count()
    total_intents = base_qs.count()
    active_intents = base_qs.filter(status__in=BlockedPurchaseIntent.WAITING_STATUSES).count()
    recovered_intents = base_qs.filter(status=BlockedPurchaseIntent.RECOVERED).count()
    
    # Value of every missed sale that hasn't been paid for (still waiting, or lost)
    lost_revenue = base_qs.exclude(status=BlockedPurchaseIntent.RECOVERED).aggregate(
        total=Sum('estimated_value')
    )['total'] or 0.00
    
    # Recovered revenue counts only sales that were paid in full
    recovered_revenue = base_qs.filter(status=BlockedPurchaseIntent.RECOVERED).aggregate(
        total=Sum('estimated_value')
    )['total'] or 0.00
    
    waiting_demand = base_qs.filter(status__in=BlockedPurchaseIntent.WAITING_STATUSES).aggregate(
        total=Sum('estimated_value'))['total'] or 0
    deposits_held = Payment.objects.filter(intent__in=base_qs.filter(status=BlockedPurchaseIntent.RESERVED)).aggregate(
        total=Sum('amount'))['total'] or 0
    closed = base_qs.filter(status__in=BlockedPurchaseIntent.CLOSED_STATUSES).count()

    visits = Visit.objects.filter(shop=shop)
    if start_date:
        d = parse_date(start_date) if isinstance(start_date, str) else start_date
        if d:
            visits = visits.filter(created_at__date__gte=d)
    if end_date:
        d = parse_date(end_date) if isinstance(end_date, str) else end_date
        if d:
            visits = visits.filter(created_at__date__lte=d)
    total_visits = visits.count()
    bought_visits = visits.filter(outcome=Visit.BOUGHT).count()

    return {
        'total_products': total_products,
        'total_customers': total_customers,
        'total_blocked_purchases': total_intents,
        'active_intents': active_intents,
        'recovered_sales': recovered_intents,
        'estimated_lost_revenue': float(lost_revenue),
        'recovered_revenue': float(recovered_revenue),
        'waiting_demand': float(waiting_demand),
        'in_conversation': base_qs.filter(status=BlockedPurchaseIntent.IN_CONVERSATION).count(),
        'reserved': base_qs.filter(status=BlockedPurchaseIntent.RESERVED).count(),
        'deposits_held': float(deposits_held),
        # Recovered out of everything that has finished (recovered, declined or expired).
        'recovery_rate': round(100 * recovered_intents / closed, 1) if closed else None,
        # Walk-ins who bought, out of all recorded visits.
        'walk_in_conversion': round(100 * bought_visits / total_visits, 1) if total_visits else None,
    }


def get_recovery_funnel(shop, start_date=None, end_date=None, status=None):
    """How far the period's missed sales got. Every number is counted, none is estimated."""
    base_qs = _filter_intents(shop, start_date, end_date, status)
    logged = base_qs.count()
    told = base_qs.filter(notified_at__isnull=False).count()
    replied = base_qs.filter(Q(status__in=[BlockedPurchaseIntent.IN_CONVERSATION, BlockedPurchaseIntent.RESERVED,
                                           BlockedPurchaseIntent.RECOVERED])
                             | Q(events__to_status=BlockedPurchaseIntent.IN_CONVERSATION)).distinct().count()
    recovered = base_qs.filter(status=BlockedPurchaseIntent.RECOVERED).count()

    def step(label, count):
        return {'label': label, 'count': count, 'percent': round(100 * count / logged) if logged else 0}

    return [step('Missed sales logged', logged), step('Customer told it was ready', told),
            step('Customer replied', replied), step('Paid in full', recovered)]


def get_to_order(shop):
    """The morning list: items customers are waiting for, most money first, then the earliest need."""
    rows = {}
    waiting = (BlockedPurchaseIntent.objects
               .filter(shop=shop, status__in=BlockedPurchaseIntent.WAITING_STATUSES,
                       constraint_type__in=BlockedPurchaseIntent.RESTOCK_REASONS)
               .select_related('product', 'variation', 'customer')
               .prefetch_related('variation__holds')
               .order_by('created_at'))
    for intent in waiting:
        key = (intent.product_id, intent.variation_id)
        row = rows.setdefault(key, {
            'key': f'{intent.product_id}-{intent.variation_id or 0}',
            'product_id': intent.product_id, 'product_name': intent.product.name,
            'supplier': intent.product.supplier,
            'variation_id': intent.variation_id,
            'variation_label': intent.variation.label if intent.variation else 'Any size or colour',
            'sku': intent.variation.sku if intent.variation else '',
            'available': intent.variation.available_quantity if intent.variation else None,
            'waiting': 0, 'on_order': 0, 'money_waiting': 0, 'needed_by': None, 'expected_at': None,
            'customers': [], 'initials': [], 'open_ids': [],
        })
        row['waiting'] += intent.requested_quantity
        if intent.status == BlockedPurchaseIntent.ON_ORDER:
            row['on_order'] += intent.requested_quantity
            if intent.expected_at and (row['expected_at'] is None or intent.expected_at < row['expected_at']):
                row['expected_at'] = intent.expected_at
        else:
            row['open_ids'].append(intent.id)
        row['money_waiting'] += float(intent.estimated_value or 0)
        if intent.needed_by and (row['needed_by'] is None or intent.needed_by < row['needed_by']):
            row['needed_by'] = intent.needed_by
        customer = intent.customer
        row['customers'].append(customer.first_name or customer.phone_number)
        row['initials'].append(((customer.first_name or '')[:1] + (customer.last_name or '')[:1]).upper()
                               or customer.phone_number[-2:])
    for row in rows.values():
        row['to_order'] = max(0, row['waiting'] - (row['available'] or 0) - row['on_order'])
    _add_suggestions(shop, rows.values())
    far = datetime.date.max
    return sorted(rows.values(), key=lambda r: (-r['money_waiting'], r['needed_by'] or far, r['product_name']))

DEMAND_WEEKS = 8


def _add_suggestions(shop, rows):
    """
    How many to order: customers waiting now, plus the customers likely to ask (or buy at the till) before the
    delivery arrives, judged from the last 8 weeks, minus free stock and what's already on order. Advice only.
    """
    from products.models import StockMovement
    since = timezone.now() - datetime.timedelta(weeks=DEMAND_WEEKS)
    ids = [r['variation_id'] for r in rows if r['variation_id']]
    asked = dict(BlockedPurchaseIntent.objects.filter(shop=shop, variation_id__in=ids, created_at__gte=since)
                 .exclude(constraint_type__in=BlockedPurchaseIntent.PRICE_DROP_REASONS)
                 .values('variation_id').annotate(n=Count('id')).values_list('variation_id', 'n'))
    sold = dict(StockMovement.objects.filter(variation_id__in=ids, kind=StockMovement.TILL_SALE, created_at__gte=since)
                .values('variation_id').annotate(n=Sum('quantity_change')).values_list('variation_id', 'n'))
    days = shop.delivery_days or 7
    for row in rows:
        free, on_order = row['available'] or 0, row['on_order']
        expected = 0
        if row['variation_id']:
            per_week = (asked.get(row['variation_id'], 0) + abs(sold.get(row['variation_id']) or 0)) / DEMAND_WEEKS
            expected = round(per_week * days / 7)
        row['expected'] = expected
        row['suggested'] = max(0, row['waiting'] + expected - free - on_order)
        parts = [f"{row['waiting']} waiting"]
        if expected:
            parts.append(f'about {expected} more in {days} days')
        why = ' + '.join(parts)
        if free:
            why += f', {free} free in stock'
        if on_order:
            why += f', {on_order} already on order'
        row['why'] = f"{why} → order {row['suggested']}"


def get_constraint_distribution(shop, start_date=None, end_date=None, status=None):
    base_qs = _filter_intents(shop, start_date, end_date, status)
    labels = dict(BlockedPurchaseIntent.CONSTRAINT_CHOICES)
    rows = base_qs.values('constraint_type').annotate(count=Count('id')).order_by('-count')
    return [{'constraint_type': labels.get(r['constraint_type'], r['constraint_type']), 'count': r['count']} for r in rows]

def get_top_blocked_products(shop, limit=5, start_date=None, end_date=None, status=None):
    base_qs = _filter_intents(shop, start_date, end_date, status)
    return list(base_qs.values('product__name')
                .annotate(count=Count('id'), total_value=Sum('estimated_value'))
                .order_by('-count')[:limit])

def get_monthly_intent_trends(shop, start_date=None, end_date=None, status=None):
    base_qs = _filter_intents(shop, start_date, end_date, status)
    # Group by month and count
    trends = (base_qs
              .annotate(month=TruncMonth('created_at'))
              .values('month')
              .annotate(count=Count('id'), recovered=Count('id', filter=Q(status=BlockedPurchaseIntent.RECOVERED)))
              .order_by('month'))
    
    result = []
    for t in trends:
        month_str = t['month'].strftime('%b %Y') if t['month'] else 'Unknown'
        result.append({
            'month': month_str,
            'count': t['count'],
            'recovered': t['recovered']
        })
    return result

def get_restock_recommendations(shop, threshold=4, start_date=None, end_date=None, status=None):
    """
    If a product variation (or product) appears more than `threshold` times
    in missed sales that are still waiting for stock, recommend restocking.
    """
    base_qs = _filter_intents(shop, start_date, end_date, status)
    # Group by product variation
    variations = (base_qs
                  .filter(status__in=BlockedPurchaseIntent.WAITING_STATUSES)
                  .values('variation_id', 'product__name', 'variation__option1', 'variation__option2')
                  .annotate(blocked_count=Count('id'))
                  .filter(blocked_count__gte=threshold)
                  .order_by('-blocked_count'))
    
    recommendations = []
    for var in variations:
        if var['variation_id']:
            # Check current stock
            try:
                pv = ProductVariation.objects.get(id=var['variation_id'])
                stock = pv.stock_quantity
            except ProductVariation.DoesNotExist:
                stock = 0
            
            recommendations.append({
                'variation_id': var['variation_id'],
                'product_name': var['product__name'],
                'size': var['variation__option1'] or 'N/A',
                'color': var['variation__option2'] or 'N/A',
                'blocked_count': var['blocked_count'],
                'current_stock': stock,
                'status': 'RECOMMENDED FOR RESTOCK'
            })
    return recommendations
