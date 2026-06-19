from .models import BlockedPurchaseIntent

def get_all_intents():
    return BlockedPurchaseIntent.objects.all().select_related('customer', 'product', 'variation', 'recorded_by').order_by('-created_at')

def get_intent_by_id(intent_id):
    try:
        return BlockedPurchaseIntent.objects.select_related('customer', 'product', 'variation', 'recorded_by').get(id=intent_id)
    except BlockedPurchaseIntent.DoesNotExist:
        return None

def get_similar_blocked_purchase_intents(intent):
    """Find other blocked intents for the same product and variation/color/size"""
    qs = BlockedPurchaseIntent.objects.filter(product=intent.product).exclude(id=intent.id)
    if intent.variation:
        qs = qs.filter(variation=intent.variation)
    return qs.select_related('customer')

def filter_blocked_purchase_intents(customer_id=None, product_id=None, constraint_type=None, status=None):
    qs = BlockedPurchaseIntent.objects.all().select_related('customer', 'product', 'variation', 'recorded_by')
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    if product_id:
        qs = qs.filter(product_id=product_id)
    if constraint_type:
        qs = qs.filter(constraint_type=constraint_type)
    if status:
        qs = qs.filter(status=status)
    return qs.order_by('-created_at')
