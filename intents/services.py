from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import BlockedPurchaseIntent

ACTIVE_STATUSES = ['Pending', 'Monitoring']

# Reasons a restock can fix. Price and budget reasons wait for a price drop instead.
RESTOCK_CONSTRAINTS = ['Size unavailable', 'Color unavailable', 'Out of stock']


def create_blocked_purchase_intent(customer, product, variation, constraint_type, requested_quantity=1, estimated_value=None, notes="", recorded_by=None):
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


def update_intent_status(intent_id, status, user=None):
    intent = BlockedPurchaseIntent.objects.get(id=intent_id)
    intent.status = status
    intent.save()
    return intent


def resolve_intents_for_variation(variation):
    """
    Mark active, unexpired restock-type intents for this variation (and
    product-level intents for its product) as Resolved, and queue one restock
    notification per intent once the transaction commits.
    """
    from notifications.tasks import send_restock_notification_task

    intents = list(
        BlockedPurchaseIntent.objects.filter(
            product=variation.product,
            status__in=ACTIVE_STATUSES,
            constraint_type__in=RESTOCK_CONSTRAINTS,
            expires_at__gt=timezone.now(),
        ).filter(Q(variation=variation) | Q(variation__isnull=True))
    )
    for intent in intents:
        intent.status = 'Resolved'
        intent.save(update_fields=['status', 'updated_at'])
        transaction.on_commit(lambda intent_id=intent.id: send_restock_notification_task.delay(intent_id))
    return len(intents)
