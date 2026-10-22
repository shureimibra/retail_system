from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def icon(name, size=''):
    """An icon from the inline Lucide sprite: {% icon "house" %} or {% icon "plus" "sm" %}."""
    css = 'icon icon-sm' if size == 'sm' else 'icon'
    return format_html('<svg class="{}" aria-hidden="true" focusable="false"><use href="#i-{}"></use></svg>', css, name)


@register.inclusion_tag('ui/field.html')
def field(bound_field, help_text=None):
    """One form field: label, control, help and error, the same everywhere."""
    return {'field': bound_field, 'help': help_text if help_text is not None else bound_field.help_text}


@register.filter
def initials(user):
    name = (user.get_full_name() or user.get_username() or '?').split()
    return ''.join(part[0] for part in name[:2]).upper()


@register.filter
def money(value, shop=None):
    """KSh 12,500 style amounts (no decimals for whole shillings)."""
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        return value
    label = {'KES': 'KSh'}.get(getattr(shop, 'currency', 'KES'), getattr(shop, 'currency', 'KSh'))
    return f'{label} {amount:,.0f}' if amount == int(amount) else f'{label} {amount:,.2f}'


EVENT_LABELS = {'created': 'Logged', 'payment': 'Payment', 'item_changed': 'Item changed', 'message_sent': 'Message sent',
                'customer_replied': 'Customer replied', 'wants_it': 'Customer wants it', 'opted_out': 'Opted out',
                'follow_up': 'Reminder sent', 'price_drop': 'Price dropped', 'pickup_overdue': 'Pickup overdue',
                'migrated': 'Carried over'}


@register.filter
def event_label(event):
    """Readable title for a timeline event."""
    if event.kind == 'status':
        from intents.models import BlockedPurchaseIntent
        return dict(BlockedPurchaseIntent.STATUS_CHOICES).get(event.to_status, event.to_status)
    return EVENT_LABELS.get(event.kind, event.kind.replace('_', ' ').capitalize())
