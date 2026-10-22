from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import BlockedPurchaseIntent as Intent, IntentEvent, Payment, Visit


class TransitionError(ValueError):
    pass


# Which status can follow which. Closed statuses (recovered, declined, expired) are final.
ALLOWED_TRANSITIONS = {
    Intent.OPEN: {Intent.ON_ORDER, Intent.BACK_IN_STOCK, Intent.NOTIFIED, Intent.IN_CONVERSATION,
                  Intent.RESERVED, Intent.RECOVERED, Intent.DECLINED, Intent.EXPIRED},
    Intent.ON_ORDER: {Intent.OPEN, Intent.BACK_IN_STOCK, Intent.IN_CONVERSATION, Intent.RESERVED,
                      Intent.RECOVERED, Intent.DECLINED, Intent.EXPIRED},
    Intent.BACK_IN_STOCK: {Intent.OPEN, Intent.NOTIFIED, Intent.IN_CONVERSATION, Intent.RESERVED,
                           Intent.RECOVERED, Intent.DECLINED, Intent.EXPIRED},
    Intent.NOTIFIED: {Intent.OPEN, Intent.IN_CONVERSATION, Intent.RESERVED, Intent.RECOVERED,
                      Intent.DECLINED, Intent.EXPIRED},
    Intent.IN_CONVERSATION: {Intent.OPEN, Intent.RESERVED, Intent.RECOVERED, Intent.DECLINED, Intent.EXPIRED},
    Intent.RESERVED: {Intent.IN_CONVERSATION, Intent.RECOVERED, Intent.DECLINED, Intent.EXPIRED},
    Intent.RECOVERED: set(),
    Intent.DECLINED: set(),
    Intent.EXPIRED: set(),
}


def allowed_next_statuses(intent):
    return ALLOWED_TRANSITIONS[intent.status]


def log_event(intent, kind, actor=None, note='', **data):
    return IntentEvent.objects.create(intent=intent, kind=kind, actor=actor, note=note, data=data)


@transaction.atomic
def transition(intent, to_status, actor=None, note='', **data):
    """The only way a missed sale changes status. Records the move in the timeline."""
    if to_status not in ALLOWED_TRANSITIONS[intent.status]:
        raise TransitionError(f'Cannot move from {intent.get_status_display()} to {dict(Intent.STATUS_CHOICES)[to_status]}.')
    from_status = intent.status
    intent.status = to_status
    update_fields = ['status', 'updated_at']
    if to_status in (Intent.DECLINED, Intent.EXPIRED) and note:
        intent.closed_reason = note[:200]
        update_fields.append('closed_reason')
    intent.save(update_fields=update_fields)

    if to_status in (Intent.OPEN, Intent.DECLINED, Intent.EXPIRED):
        _release_holds(intent)
    elif to_status == Intent.RECOVERED:
        _sell_held_units(intent, actor)

    IntentEvent.objects.create(intent=intent, kind='status', from_status=from_status, to_status=to_status,
                               note=note, data=data, actor=actor)
    return intent


# --- Capture ---------------------------------------------------------------

def create_blocked_purchase_intent(customer, product, variation, constraint_type, requested_quantity=1, estimated_value=None,
                                   notes="", recorded_by=None, visit=None, consent_given=True,
                                   preferred_channel=Intent.WHATSAPP, needed_by=None):
    if customer.shop_id != product.shop_id or (variation and variation.product_id != product.id):
        raise ValueError('Customer, product and variation must belong to the same shop and product.')
    if estimated_value is None:
        unit_price = variation.effective_price if variation else product.base_price
        estimated_value = unit_price * requested_quantity
    with transaction.atomic():
        if visit is None:
            visit = Visit.objects.create(shop_id=product.shop_id, customer=customer, outcome=Visit.DIDNT_BUY,
                                         recorded_by=recorded_by)
        intent = Intent.objects.create(
            shop_id=product.shop_id,
            visit=visit,
            customer=customer,
            product=product,
            variation=variation,
            constraint_type=constraint_type,
            requested_quantity=requested_quantity,
            estimated_value=estimated_value,
            notes=notes,
            recorded_by=recorded_by,
            consent_given=consent_given,
            preferred_channel=preferred_channel,
            needed_by=needed_by,
        )
        log_event(intent, 'created', actor=recorded_by, note=intent.get_constraint_type_display())
    return intent


def record_bought_visit(shop, recorded_by=None, customer=None):
    """A walk-in who bought. Counts towards walk-in conversion; nothing else to follow up."""
    return Visit.objects.create(shop=shop, customer=customer, outcome=Visit.BOUGHT, recorded_by=recorded_by)


# --- Stock ------------------------------------------------------------------

@transaction.atomic
def mark_ordered(intents, expected_at=None, actor=None):
    """The owner ordered the item. Waiting requests become On order."""
    moved = 0
    for intent in intents:
        if intent.status == Intent.OPEN:
            intent.expected_at = expected_at
            intent.save(update_fields=['expected_at', 'updated_at'])
            transition(intent, Intent.ON_ORDER, actor=actor, note='Ordered from supplier',
                       expected_at=expected_at.isoformat() if expected_at else None)
            moved += 1
    return moved


def resolve_intents_for_variation(variation):
    """
    Stock arrived for this variation. Waiting customers (restock reasons only,
    not expired) are served oldest first: each gets one unit put aside, moves
    to Back in stock, and is messaged once the transaction commits. Customers
    beyond the units available keep waiting.
    """
    from notifications.tasks import send_restock_notification_task
    from products.models import StockHold

    waiting = (Intent.objects
               .filter(product=variation.product, status__in=Intent.WAITING_STATUSES,
                       constraint_type__in=Intent.RESTOCK_REASONS, expires_at__gt=timezone.now())
               .filter(Q(variation=variation) | Q(variation__isnull=True))
               .exclude(holds__status=StockHold.ACTIVE)
               .order_by('created_at', 'id'))
    available = variation.available_quantity
    served = 0
    for intent in waiting:
        if served >= available:
            break
        _hold_unit(intent, variation)
        transition(intent, Intent.BACK_IN_STOCK, note='Stock arrived; one unit put aside', variation=variation.label)
        transaction.on_commit(lambda intent_id=intent.id: send_restock_notification_task.delay(intent_id))
        served += 1
    return served


def _hold_unit(intent, variation):
    from products.models import StockHold
    return StockHold.objects.create(variation=variation, intent=intent, quantity=1,
                                    expires_at=timezone.now() + timedelta(days=settings.STOCK_HOLD_DAYS))


def _release_holds(intent):
    from products.models import StockHold
    intent.holds.filter(status=StockHold.ACTIVE).update(status=StockHold.RELEASED)


def _sell_held_units(intent, actor):
    from products.models import ProductVariation, StockHold, StockMovement
    for hold in intent.holds.filter(status=StockHold.ACTIVE):
        variation = ProductVariation.objects.select_for_update().get(pk=hold.variation_id)
        sold = min(hold.quantity, variation.stock_quantity)
        variation.stock_quantity -= sold
        variation.save(update_fields=['stock_quantity'])
        StockMovement.objects.create(variation=variation, kind=StockMovement.SOLD, quantity_change=-sold,
                                     stock_after=variation.stock_quantity, recorded_by=actor,
                                     reference=f'Missed sale #{intent.id}')
        hold.status = StockHold.SOLD
        hold.save(update_fields=['status'])


# --- Customer agreed: reserve and pay ------------------------------------------

def _default_pickup_by():
    return timezone.localdate() + timedelta(days=settings.RESERVE_PICKUP_DAYS)


def _keep_hold_until(intent, pickup_by):
    from products.models import StockHold
    until = timezone.make_aware(datetime.combine(pickup_by, time(23, 59)))
    intent.holds.filter(status=StockHold.ACTIVE, expires_at__lt=until).update(expires_at=until)


@transaction.atomic
def reserve(intent, pickup_by=None, actor=None, note=''):
    """Customer agreed to come for it (with or without a deposit)."""
    intent.pickup_by = pickup_by or _default_pickup_by()
    intent.save(update_fields=['pickup_by', 'updated_at'])
    _keep_hold_until(intent, intent.pickup_by)
    if intent.status != Intent.RESERVED:
        transition(intent, Intent.RESERVED, actor=actor, note=note or 'Customer will pick it up',
                   pickup_by=intent.pickup_by.isoformat())
    return intent


@transaction.atomic
def record_payment(intent, amount, method, reference='', actor=None, pickup_by=None):
    """
    Record money received for a missed sale. A part payment is a deposit and
    reserves the item; once the full amount is paid the sale is Recovered.
    """
    amount = Decimal(str(amount))
    if intent.is_closed:
        raise TransitionError('This missed sale is already closed.')
    if amount <= 0:
        raise ValueError('Payment must be more than zero.')
    if amount > intent.balance:
        raise ValueError(f'Payment is more than the balance due ({intent.balance}).')
    payment = Payment.objects.create(intent=intent, amount=amount, method=method, reference=reference, recorded_by=actor)
    log_event(intent, 'payment', actor=actor, note=f'{payment.get_method_display()} {amount}',
              amount=str(amount), method=method, reference=reference)
    if intent.balance == 0:
        transition(intent, Intent.RECOVERED, actor=actor, note='Paid in full')
    else:
        reserve(intent, pickup_by=pickup_by, actor=actor, note='Deposit paid')
    return payment


def decline(intent, reason='', actor=None):
    """Customer said no. Closed, never counted as revenue."""
    return transition(intent, Intent.DECLINED, actor=actor, note=reason or 'Customer declined')


@transaction.atomic
def change_item(intent, new_variation, actor=None):
    """The customer wants a different size, colour or product. History keeps the original."""
    from notifications.tasks import send_restock_notification_task

    from products.models import ProductVariation

    if intent.is_closed:
        raise TransitionError('This missed sale is already closed.')
    # Use the current stock, not whatever the caller's copy says.
    new_variation = ProductVariation.objects.select_for_update().select_related('product').get(pk=new_variation.pk)
    if new_variation.product.shop_id != intent.shop_id:
        raise ValueError('The new item must belong to the same shop.')
    old_label = f'{intent.product.name} {intent.variation.label if intent.variation else ""}'.strip()
    _release_holds(intent)
    intent.product = new_variation.product
    intent.variation = new_variation
    intent.estimated_value = new_variation.effective_price * intent.requested_quantity
    intent.save(update_fields=['product', 'variation', 'estimated_value', 'updated_at'])
    new_label = f'{new_variation.product.name} {new_variation.label}'.strip()
    log_event(intent, 'item_changed', actor=actor, note=f'{old_label} → {new_label}', old=old_label, new=new_label)

    if new_variation.available_quantity > 0:
        _hold_unit(intent, new_variation)
        if intent.status in Intent.WAITING_STATUSES:
            transition(intent, Intent.BACK_IN_STOCK, actor=actor, note='New item is in stock; one unit put aside')
            transaction.on_commit(lambda intent_id=intent.id: send_restock_notification_task.delay(intent_id))
    elif intent.status not in Intent.WAITING_STATUSES:
        transition(intent, Intent.OPEN, actor=actor, note='New item is not in stock yet')
    return intent
