from intents.models import BlockedPurchaseIntent
from django.utils.dateparse import parse_date

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
