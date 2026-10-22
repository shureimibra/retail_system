from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from accounts.models import default_shop_id
from customers.models import Customer
from products.models import Product, ProductVariation


def get_default_expiry():
    return timezone.now() + timedelta(days=30)


class Visit(models.Model):
    """One customer visit to the shop. Groups the items they couldn't buy, or records that they bought."""
    BOUGHT = 'bought'
    DIDNT_BUY = 'didnt_buy'
    OUTCOME_CHOICES = [
        (BOUGHT, 'Bought'),
        (DIDNT_BUY, "Didn't buy"),
    ]

    shop = models.ForeignKey('accounts.Shop', on_delete=models.CASCADE, default=default_shop_id, related_name='visits')
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='visits')
    outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES, default=DIDNT_BUY)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class BlockedPurchaseIntent(models.Model):
    """A missed sale: a customer wanted something the shop couldn't sell them."""

    # Lifecycle. Only intents.services.transition() changes status.
    OPEN = 'open'
    ON_ORDER = 'on_order'
    BACK_IN_STOCK = 'back_in_stock'
    NOTIFIED = 'notified'
    IN_CONVERSATION = 'in_conversation'
    RESERVED = 'reserved'
    RECOVERED = 'recovered'
    DECLINED = 'declined'
    EXPIRED = 'expired'
    STATUS_CHOICES = [
        (OPEN, 'Open'),
        (ON_ORDER, 'On order'),
        (BACK_IN_STOCK, 'Back in stock'),
        (NOTIFIED, 'Notified'),
        (IN_CONVERSATION, 'In conversation'),
        (RESERVED, 'Reserved'),
        (RECOVERED, 'Recovered'),
        (DECLINED, 'Declined'),
        (EXPIRED, 'Expired'),
    ]
    WAITING_STATUSES = [OPEN, ON_ORDER]
    CLOSED_STATUSES = [RECOVERED, DECLINED, EXPIRED]

    # Why they didn't buy, and what can fix it.
    SIZE_MISSING = 'size_missing'
    COLOUR_MISSING = 'colour_missing'
    OUT_OF_STOCK = 'out_of_stock'
    PRICE_TOO_HIGH = 'price_too_high'
    OVER_BUDGET = 'over_budget'
    OTHER = 'other'
    CONSTRAINT_CHOICES = [
        (SIZE_MISSING, 'Size missing'),
        (COLOUR_MISSING, 'Colour missing'),
        (OUT_OF_STOCK, 'Out of stock'),
        (PRICE_TOO_HIGH, 'Price too high'),
        (OVER_BUDGET, 'Over budget'),
        (OTHER, 'Something else'),
    ]
    RESTOCK_REASONS = [SIZE_MISSING, COLOUR_MISSING, OUT_OF_STOCK]
    PRICE_DROP_REASONS = [PRICE_TOO_HIGH, OVER_BUDGET]

    WHATSAPP = 'whatsapp'
    SMS = 'sms'
    EMAIL = 'email'
    CHANNEL_CHOICES = [(WHATSAPP, 'WhatsApp'), (SMS, 'SMS'), (EMAIL, 'Email')]

    shop = models.ForeignKey('accounts.Shop', on_delete=models.CASCADE, default=default_shop_id, related_name='intents')
    visit = models.ForeignKey(Visit, on_delete=models.SET_NULL, null=True, blank=True, related_name='intents')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='intents')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='intents')
    variation = models.ForeignKey(ProductVariation, on_delete=models.SET_NULL, null=True, blank=True, related_name='intents')

    constraint_type = models.CharField('reason', max_length=50, choices=CONSTRAINT_CHOICES)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default=OPEN)

    requested_quantity = models.PositiveIntegerField(default=1)
    estimated_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    consent_given = models.BooleanField(default=True, help_text='Customer agreed to be contacted about this item.')
    preferred_channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=WHATSAPP)
    needed_by = models.DateField(null=True, blank=True)
    expected_at = models.DateField(null=True, blank=True, help_text='When the ordered stock should arrive.')
    pickup_by = models.DateField(null=True, blank=True, help_text='Reserved items are held until this date.')
    closed_reason = models.CharField(max_length=200, blank=True)

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(default=get_default_expiry)

    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"Intent for {self.product.name} by {self.customer.phone_number} - {self.status}"

    @property
    def is_closed(self):
        return self.status in self.CLOSED_STATUSES

    @property
    def amount_due(self):
        return self.estimated_value or 0

    @property
    def amount_paid(self):
        return sum(self.payments.values_list('amount', flat=True), 0)

    @property
    def balance(self):
        return max(0, self.amount_due - self.amount_paid)


class IntentEvent(models.Model):
    """One line in a missed sale's timeline: what happened, when, and who did it."""
    intent = models.ForeignKey(BlockedPurchaseIntent, on_delete=models.CASCADE, related_name='events')
    kind = models.CharField(max_length=40)
    from_status = models.CharField(max_length=50, blank=True)
    to_status = models.CharField(max_length=50, blank=True)
    note = models.CharField(max_length=300, blank=True)
    data = models.JSONField(default=dict, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']


class Payment(models.Model):
    MPESA = 'mpesa'
    CASH = 'cash'
    CARD = 'card'
    BANK = 'bank'
    METHOD_CHOICES = [(MPESA, 'M-Pesa'), (CASH, 'Cash'), (CARD, 'Card'), (BANK, 'Bank')]

    intent = models.ForeignKey(BlockedPurchaseIntent, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    reference = models.CharField(max_length=60, blank=True, help_text='For example the M-Pesa code.')
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
