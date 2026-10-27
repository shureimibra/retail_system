from django.conf import settings
from django.db import models


class MpesaRequest(models.Model):
    """One "pay with M-Pesa" prompt sent to a customer's phone (Daraja STK push), and how it ended."""
    PENDING = 'pending'
    PAID = 'paid'
    CANCELLED = 'cancelled'
    FAILED = 'failed'
    NEEDS_CHECK = 'needs_check'
    STATUS_CHOICES = [
        (PENDING, 'Waiting for the customer'),
        (PAID, 'Paid'),
        (CANCELLED, 'Cancelled by the customer'),
        (FAILED, 'Failed'),
        (NEEDS_CHECK, 'Paid, but needs checking'),
    ]

    shop = models.ForeignKey('accounts.Shop', on_delete=models.CASCADE, related_name='mpesa_requests')
    intent = models.ForeignKey('intents.BlockedPurchaseIntent', on_delete=models.CASCADE, related_name='mpesa_requests')
    payment = models.OneToOneField('intents.Payment', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='mpesa_request')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    phone = models.CharField(max_length=15, help_text='2547XXXXXXXX, as M-Pesa expects it.')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    merchant_request_id = models.CharField(max_length=60, blank=True)
    checkout_request_id = models.CharField(max_length=60, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    result_code = models.CharField(max_length=20, blank=True)
    result_desc = models.CharField(max_length=300, blank=True)
    receipt = models.CharField(max_length=30, blank=True, help_text='The M-Pesa code, e.g. QK7H2L9XYZ.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.phone} {self.amount} ({self.get_status_display()})'

    @property
    def is_pending(self):
        return self.status == self.PENDING
