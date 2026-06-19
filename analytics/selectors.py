from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth
from intents.models import BlockedPurchaseIntent
from products.models import Product, ProductVariation
from customers.models import Customer
import datetime

from django.utils.dateparse import parse_date

def _filter_intents(start_date=None, end_date=None, status=None):
    qs = BlockedPurchaseIntent.objects.all()
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

def get_dashboard_kpis(start_date=None, end_date=None, status=None):
    base_qs = _filter_intents(start_date, end_date, status)
    
    total_products = Product.objects.filter(active=True).count() if hasattr(Product, 'active') else Product.objects.count()
    total_customers = Customer.objects.count()
    total_intents = base_qs.count()
    active_intents = base_qs.filter(status__in=['Pending', 'Monitoring']).count()
    recovered_intents = base_qs.filter(status__in=['Resolved', 'Customer Notified', 'Recovered']).count()
    
    # Lost revenue is estimated value of intents that are Pending, Monitoring or Closed (unrecovered)
    lost_revenue = base_qs.exclude(status__in=['Resolved', 'Customer Notified', 'Recovered']).aggregate(
        total=Sum('estimated_value')
    )['total'] or 0.00
    
    # Recovered revenue is estimated value of recovered intents
    recovered_revenue = base_qs.filter(status__in=['Resolved', 'Customer Notified', 'Recovered']).aggregate(
        total=Sum('estimated_value')
    )['total'] or 0.00
    
    return {
        'total_products': total_products,
        'total_customers': total_customers,
        'total_blocked_purchases': total_intents,
        'active_intents': active_intents,
        'recovered_sales': recovered_intents,
        'estimated_lost_revenue': float(lost_revenue),
        'recovered_revenue': float(recovered_revenue),
    }

def get_constraint_distribution(start_date=None, end_date=None, status=None):
    base_qs = _filter_intents(start_date, end_date, status)
    return list(base_qs.values('constraint_type')
                .annotate(count=Count('id'))
                .order_by('-count'))

def get_top_blocked_products(limit=5, start_date=None, end_date=None, status=None):
    base_qs = _filter_intents(start_date, end_date, status)
    return list(base_qs.values('product__name')
                .annotate(count=Count('id'), total_value=Sum('estimated_value'))
                .order_by('-count')[:limit])

def get_monthly_intent_trends(start_date=None, end_date=None, status=None):
    base_qs = _filter_intents(start_date, end_date, status)
    # Group by month and count
    trends = (base_qs
              .annotate(month=TruncMonth('created_at'))
              .values('month')
              .annotate(count=Count('id'), recovered=Count('id', filter=Q(status__in=['Resolved', 'Customer Notified', 'Recovered'])))
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

def get_restock_recommendations(threshold=4, start_date=None, end_date=None, status=None):
    """
    If a product variation (or product) appears more than `threshold` times
    in blocked purchase intents with status Pending/Monitoring, recommend restocking.
    """
    base_qs = _filter_intents(start_date, end_date, status)
    # Group by product variation
    variations = (base_qs
                  .filter(status__in=['Pending', 'Monitoring'])
                  .values('variation_id', 'product__name', 'variation__size', 'variation__color')
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
                'size': var['variation__size'] or 'N/A',
                'color': var['variation__color'] or 'N/A',
                'blocked_count': var['blocked_count'],
                'current_stock': stock,
                'status': 'RECOMMENDED FOR RESTOCK'
            })
    return recommendations
