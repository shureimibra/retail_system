"""
What should happen next for a missed sale, in one line, and where to do it. Used by Waiting and the
item page, so staff never have to guess (or change a status by hand): statuses move only through
real actions (order, receive stock, a reply, a payment, declined), most of them automatic.
"""
from django.urls import reverse

from .models import BlockedPurchaseIntent as Intent


def _day(d):
    return f'{d.strftime("%a")} {d.day} {d.strftime("%b")}'


def next_step(intent, manager=True):
    """{'text', 'action', 'url'}; action/url are empty when nothing needs doing yet."""
    customer = intent.customer.first_name or intent.customer.phone_number
    conversation = intent.customer.conversations.first()
    chat = reverse('notifications:conversation', args=[conversation.pk]) if conversation else reverse('customers:detail', args=[intent.customer_id])
    product = reverse('products:detail', args=[intent.product_id])
    status = intent.status

    if status == Intent.OPEN:
        if intent.constraint_type in Intent.PRICE_DROP_REASONS:
            return {'text': 'Waiting for a lower price. They are messaged when you lower it.',
                    'action': 'Change price' if manager else '', 'url': product if manager else ''}
        if intent.constraint_type == Intent.OTHER:
            return {'text': 'Follow up with them yourself (see the note).', 'action': 'Call or message', 'url': chat}
        if manager:
            return {'text': 'Order it from your supplier.', 'action': 'To order', 'url': reverse('intents:to_order')}
        return {'text': 'Waiting for the owner or a manager to order it.', 'action': '', 'url': ''}
    if status == Intent.ON_ORDER:
        due = f' (due {_day(intent.expected_at)})' if intent.expected_at else ''
        receive = f'{product}?receive={intent.variation_id}#receive' if intent.variation_id else f'{product}#receive'
        return {'text': f'Ordered{due}. When it arrives, receive the stock: they are messaged automatically.',
                'action': 'Receive stock' if manager else '', 'url': receive if manager else ''}
    if status == Intent.BACK_IN_STOCK:
        if not intent.consent_given or not intent.customer.marketing_opt_in:
            return {'text': f"A unit is held, but {customer} didn't agree to messages. Call them.",
                    'action': 'Call', 'url': chat}
        return {'text': f'A unit is held. The message to {customer} is going out; if it fails, call them.',
                'action': 'Open chat', 'url': chat}
    if status == Intent.NOTIFIED:
        return {'text': f'{customer} was told. Waiting for their reply; reminders go out automatically.',
                'action': 'Open chat', 'url': chat}
    if status == Intent.IN_CONVERSATION:
        return {'text': f'{customer} replied. Answer them and take a deposit or full payment.',
                'action': 'Reply', 'url': chat}
    if status == Intent.RESERVED:
        pickup = f' by {_day(intent.pickup_by)}' if intent.pickup_by else ''
        return {'text': f'Reserved. Collect the balance when they pick it up{pickup}.', 'action': 'Open deal', 'url': chat}
    return {'text': '', 'action': '', 'url': ''}
