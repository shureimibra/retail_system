from .models import BlockedPurchaseIntent

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
