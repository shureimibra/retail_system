from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import BlockedPurchaseIntent

ACTIVE_STATUSES = ['Pending', 'Monitoring']

# Reasons a restock can fix. Price and budget reasons wait for a price drop instead.
RESTOCK_CONSTRAINTS = ['Size unavailable', 'Color unavailable', 'Out of stock']


def create_blocked_purchase_intent(customer, product, variation, constraint_type, requested_quantity=1, estimated_value=None, notes="", recorded_by=None):
    if customer.shop_id != product.shop_id or (variation and variation.product_id != product.id):
        raise ValueError('Customer, product and variation must belong to the same shop and product.')
    if estimated_value is None:
        estimated_value = product.base_price * requested_quantity

    return BlockedPurchaseIntent.objects.create(
        shop_id=product.shop_id,
        customer=customer,
        product=product,
        variation=variation,
        constraint_type=constraint_type,
        requested_quantity=requested_quantity,
        estimated_value=estimated_value,
        notes=notes,
        recorded_by=recorded_by
    )


def update_intent_status(intent_id, status, user=None):
    intent = BlockedPurchaseIntent.objects.get(id=intent_id)
    intent.status = status
    intent.save()
    return intent


def resolve_intents_for_variation(variation):
    """
    Stock arrived for this variation. Waiting customers (restock reasons only,
    not expired) are served oldest first: each gets one unit put aside, is
    marked Resolved, and is messaged once the transaction commits. Customers
    beyond the units available keep waiting.
    """
    from notifications.tasks import send_restock_notification_task
    from products.models import StockHold

    waiting = (BlockedPurchaseIntent.objects
               .filter(product=variation.product, status__in=ACTIVE_STATUSES,
                       constraint_type__in=RESTOCK_CONSTRAINTS, expires_at__gt=timezone.now())
               .filter(Q(variation=variation) | Q(variation__isnull=True))
               .exclude(holds__status=StockHold.ACTIVE)
               .order_by('created_at', 'id'))
    available = variation.available_quantity
    hold_until = timezone.now() + timedelta(days=settings.STOCK_HOLD_DAYS)
    served = 0
    for intent in waiting:
        if served >= available:
            break
        StockHold.objects.create(variation=variation, intent=intent, quantity=1, expires_at=hold_until)
        intent.status = 'Resolved'
        intent.save(update_fields=['status', 'updated_at'])
        transaction.on_commit(lambda intent_id=intent.id: send_restock_notification_task.delay(intent_id))
        served += 1
    return served
