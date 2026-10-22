"""The words of each customer message. Kept short: they're read on a phone."""
from django.utils import timezone

CURRENCY_LABELS = {'KES': 'KSh'}


def money(shop, amount):
    label = CURRENCY_LABELS.get(shop.currency, shop.currency)
    return f'{label} {amount:,.0f}'


def _day(value):
    return value.strftime('%a %d %b').replace(' 0', ' ') if value else ''


def item_name(intent):
    if intent.variation and intent.variation.label:
        return f'{intent.product.name} in {intent.variation.label}'
    return intent.product.name


def _hold_until(intent):
    from products.models import StockHold
    hold = intent.holds.filter(status=StockHold.ACTIVE).order_by('-expires_at').first()
    return timezone.localtime(hold.expires_at).date() if hold else None


def restock_alert(intent):
    name = intent.customer.first_name or 'there'
    held = _hold_until(intent)
    holding = f" We're holding one for you until {_day(held)}." if held else ''
    return (f"Hi {name}, the {item_name(intent)} you asked about on {_day(timezone.localtime(intent.created_at).date())} "
            f"is back at {intent.shop.name}.{holding} Reply YES to keep it, or STOP to opt out.")


def deposit_receipt(intent):
    name = intent.customer.first_name or 'there'
    paid = money(intent.shop, intent.amount_paid)
    balance = money(intent.shop, intent.balance)
    pickup = f' Please pick it up by {_day(intent.pickup_by)}.' if intent.pickup_by else ''
    return f"Thank you {name}. We received {paid} for the {item_name(intent)}. Balance {balance}.{pickup}"


def price_drop(intent):
    name = intent.customer.first_name or 'there'
    change = intent.product.price_changes.order_by('-created_at').first()
    was = f' (was {money(intent.shop, change.old_price)})' if change else ''
    unit = intent.variation.effective_price if intent.variation else intent.product.base_price
    return (f"Good news {name}: the {item_name(intent)} is now {money(intent.shop, unit)}{was} at {intent.shop.name}. "
            f"Reply YES to reserve it, or STOP to opt out.")


def reminder_1(intent):
    name = intent.customer.first_name or 'there'
    return (f"Hi {name}, a reminder that the {item_name(intent)} is waiting for you at {intent.shop.name}. "
            f"Reply YES to keep it, or STOP to opt out.")


def reminder_2(intent):
    name = intent.customer.first_name or 'there'
    held = _hold_until(intent)
    until = f' until {_day(held)}' if held else ''
    return f"Hi {name}, we're still holding the {item_name(intent)} for you{until}. Reply YES to keep it, or STOP to opt out."


def reminder_3(intent):
    name = intent.customer.first_name or 'there'
    return (f"Last call, {name}: we can hold the {item_name(intent)} until tomorrow, then it goes back on sale. "
            f"Reply YES to keep it.")


TEMPLATES = {
    'restock_alert': restock_alert,
    'price_drop': price_drop,
    'deposit_receipt': deposit_receipt,
    'reminder_1': reminder_1,
    'reminder_2': reminder_2,
    'reminder_3': reminder_3,
}


def compose(template_key, intent):
    return TEMPLATES[template_key](intent)
