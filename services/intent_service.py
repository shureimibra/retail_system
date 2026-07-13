from intents.models import BlockedPurchaseIntent
from products.models import ProductVariation
from services.notification_service import send_resolution_notification

def create_blocked_purchase_intent(customer, product, variation, constraint_type, requested_quantity=1, estimated_value=None, notes="", recorded_by=None):
    """
    Creates a new BlockedPurchaseIntent. Auto-calculates estimated lost value based on base price if blank.
    """
    if estimated_value is None:
        estimated_value = product.base_price * requested_quantity
        
    return BlockedPurchaseIntent.objects.create(
        customer=customer,
        product=product,
        variation=variation,
        constraint_type=constraint_type,
        requested_quantity=requested_quantity,
        estimated_value=estimated_value,
        notes=notes,
        recorded_by=recorded_by
    )

def resolve_blocked_intents_for_variation(variation):
    """
    Resolves all pending or monitoring blocked purchase intents linked to a specific variation.
    """
    intents = BlockedPurchaseIntent.objects.filter(
        variation=variation,
        status__in=['Pending', 'Monitoring']
    )
    resolved_count = 0
    for intent in intents:
        intent.status = 'Resolved'
        intent.save()
        send_resolution_notification(intent)
        resolved_count += 1
    return resolved_count

def resolve_blocked_intents_for_product(product):
    """
    Resolves product-level intents (no specific variation) if any variation is back in stock.
    Also checks variation-specific intents.
    """
    intents = BlockedPurchaseIntent.objects.filter(
        product=product,
        status__in=['Pending', 'Monitoring']
    )
    resolved_count = 0
    
    # Check if there is any stock available across variations
    has_stock = ProductVariation.objects.filter(product=product, stock_quantity__gt=0).exists()
    
    for intent in intents:
        if intent.variation:
            # If specific variation is back in stock, resolve it
            if intent.variation.stock_quantity > 0:
                intent.status = 'Resolved'
                intent.save()
                send_resolution_notification(intent)
                resolved_count += 1
        else:
            # If product-wide intent and at least one variation is in stock, resolve it
            if has_stock:
                intent.status = 'Resolved'
                intent.save()
                send_resolution_notification(intent)
                resolved_count += 1
                
    return resolved_count
