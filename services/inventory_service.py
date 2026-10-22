import logging
from django.utils import timezone
from products.models import Product, ProductVariation
from intents.models import BlockedPurchaseIntent
from notifications.tasks import send_restock_notification_task

logger = logging.getLogger(__name__)

def update_stock(variation_id, new_quantity):
    """
    Updates the stock quantity of a variation, and triggers background
    resolution notifications if stock becomes available.
    """
    variation = ProductVariation.objects.get(id=variation_id)
    variation.stock_quantity = max(0, new_quantity)
    # Save the variation (signals should be bypassed or deactivated for notifications)
    variation.save()
    
    if variation.stock_quantity > 0:
        resolve_intents_for_variation_async(variation)
        
    return variation

def resolve_intents_for_variation_async(variation):
    """
    Finds active, non-expired intents matching the variation, marks them
    as Resolved, and dispatches Celery notification tasks.
    """
    now = timezone.now()
    # Exclude expired intents
    intents = BlockedPurchaseIntent.objects.filter(
        variation=variation,
        status__in=['Pending', 'Monitoring'],
        expires_at__gt=now
    )
    resolved_count = 0
    for intent in intents:
        intent.status = 'Resolved'
        intent.save(update_fields=['status'])
        
        # Hand off notification dispatching to asynchronous background tasks
        send_restock_notification_task.delay(intent.id)
        resolved_count += 1
        
    logger.info(f"Scheduled notification tasks for {resolved_count} intents linked to variation {variation.id}")
    return resolved_count

def handle_stock_update(product_or_variation):
    """
    Explicit service endpoint to handle stock updates.
    """
    if isinstance(product_or_variation, ProductVariation):
        if product_or_variation.stock_quantity > 0:
            resolve_intents_for_variation_async(product_or_variation)
    elif isinstance(product_or_variation, Product):
        # Find all variations with stock
        if ProductVariation.objects.filter(product=product_or_variation, stock_quantity__gt=0).exists():
            resolve_intents_for_product_async(product_or_variation)

def resolve_intents_for_product_async(product):
    """
    Resolves product-level intents (no specific variation) asynchronously
    if any variation is back in stock.
    """
    now = timezone.now()
    has_stock = ProductVariation.objects.filter(product=product, stock_quantity__gt=0).exists()
    if not has_stock:
        return 0

    intents = BlockedPurchaseIntent.objects.filter(
        product=product,
        status__in=['Pending', 'Monitoring'],
        expires_at__gt=now
    )
    resolved_count = 0
    for intent in intents:
        if intent.variation:
            if intent.variation.stock_quantity > 0:
                intent.status = 'Resolved'
                intent.save(update_fields=['status'])
                send_restock_notification_task.delay(intent.id)
                resolved_count += 1
        else:
            intent.status = 'Resolved'
            intent.save(update_fields=['status'])
            send_restock_notification_task.delay(intent.id)
            resolved_count += 1
            
    return resolved_count
