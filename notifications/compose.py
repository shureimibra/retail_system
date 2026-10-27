"""The words of each customer message. Kept short: they're read on a phone."""
import re
from datetime import timedelta

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


def check_in(intent):
    """The approved message used when WhatsApp's 24-hour reply window has closed."""
    name = intent.customer.first_name or 'there'
    return (f"Hi {name}, this is {intent.shop.name} about the {item_name(intent)}. "
            f"Reply to this message and we'll help you.")


# Quick replies staff can send (or edit first) inside an open conversation.
def quick_reply(key, intent):
    name = intent.customer.first_name or 'there'
    shop = intent.shop
    if key == 'payment':
        details = shop.payment_details.strip().rstrip('.') or 'Please ask us how to pay'
        return f"Hi {name}, you can pay for the {item_name(intent)} here: {details}. Balance {money(shop, intent.balance)}."
    if key == 'pickup':
        when = f' until {_day(intent.pickup_by)}' if intent.pickup_by else ''
        return f"Great, {name}. We're keeping the {item_name(intent)} for you{when}. See you at {shop.name}."
    if key == 'other':
        return f"Hi {name}, we also have the {intent.product.name} in other options. Would one of these work for you? "
    if key == 'deposit':
        hold = intent.pickup_by or timezone.localdate() + timedelta(days=shop.reserve_pickup_days)
        part = max(100, int(intent.balance / 2 // 100 * 100)) if intent.balance else 0
        example = f' (for example {money(shop, part)})' if part else ''
        return (f"Hi {name}, yes: pay a deposit{example} and we'll keep the {item_name(intent)} for you "
                f"until {_day(hold)}. Pay the rest when you collect it.")
    if key == 'price':
        unit = intent.variation.effective_price if intent.variation else intent.product.base_price
        return f"Hi {name}, the {item_name(intent)} is {money(shop, unit)}."
    if key == 'thanks':
        return f"No problem, {name}. Thank you for letting us know. We're here whenever you need anything."
    return ''


QUICK_REPLIES = [('payment', 'Send payment details'), ('deposit', 'Deposit'), ('pickup', 'Confirm pickup'),
                 ('price', 'Price'), ('other', 'Offer another option')]
THANKS = ('thanks', 'Thank them')

# Words in a customer's message that point to the right reply, in English and common Swahili/Sheng.
# Checked in this order; "no" first, so "no, I can't pay now" isn't taken as a payment question.
SUGGEST_RULES = [
    ('thanks', r"\b(no|nope|not now|not interested|sitaki|hapana|later|baadaye|i.?ll pass)\b"),
    ('deposit', r"deposit|\bhalf\b|\bpart\b|nusu|kidogo kidogo|lipa kidogo|installment"),
    ('payment', r"\bpay\b|payment|m-?pesa|\btill\b|paybill|\blipa\b|\bpesa\b|account|send money"),
    ('pickup', r"\bwhen\b|\bcome\b|pick ?up|collect|saturday|sunday|monday|tuesday|wednesday|thursday|friday|"
               r"\bkesho\b|\bleo\b|nikuje|nitakuja|open"),
    ('price', r"price|how much|discount|last price|cheaper|\bbei\b|punguza|ngapi|\bcost"),
    ('other', r"other size|another|different|colou?r|\brangi\b|\bsaizi\b|\bsize\b"),
    ('yes', r"\b(yes|yeah|yep|ok|okay|sawa|ndio|ndiyo|poa|i want|nataka|i.?ll take)\b"),
]


def suggest_quick_reply(text, intent):
    """The quick reply that best answers the customer's last message, or '' if nothing fits."""
    text = (text or '').lower()
    key = next((k for k, pattern in SUGGEST_RULES if re.search(pattern, text)), '')
    if key == 'yes':
        # They want it: how to pay, or if they've paid something already, when to come.
        key = 'pickup' if intent.amount_paid else 'payment'
    return key


def template_params(template_key, intent):
    """
    The values for an approved WhatsApp template, in order. The wording around them
    lives in docs/whatsapp-templates.md and must match what Meta approved.
    WhatsApp refuses empty values, so every part has a fallback.
    """
    shop = intent.shop
    name = intent.customer.first_name or 'there'
    item = item_name(intent)
    held = _hold_until(intent)
    if template_key == 'restock_alert':
        asked = _day(timezone.localtime(intent.created_at).date())
        return [name, item, asked, shop.name, _day(held) or 'the end of the week']
    if template_key == 'price_drop':
        change = intent.product.price_changes.order_by('-created_at').first()
        unit = intent.variation.effective_price if intent.variation else intent.product.base_price
        was = money(shop, change.old_price) if change else money(shop, unit)
        return [name, item, money(shop, unit), was, shop.name]
    if template_key == 'deposit_receipt':
        return [name, money(shop, intent.amount_paid), item, money(shop, intent.balance),
                _day(intent.pickup_by) or 'the agreed day']
    if template_key == 'reminder_1':
        return [name, item, shop.name]
    if template_key == 'reminder_2':
        return [name, item, _day(held) or 'the end of the week']
    if template_key == 'reminder_3':
        return [name, item]
    if template_key == 'check_in':
        return [name, shop.name, item]
    return []


TEMPLATES = {
    'restock_alert': restock_alert,
    'price_drop': price_drop,
    'deposit_receipt': deposit_receipt,
    'reminder_1': reminder_1,
    'reminder_2': reminder_2,
    'reminder_3': reminder_3,
    'check_in': check_in,
}


def compose(template_key, intent):
    return TEMPLATES[template_key](intent)
