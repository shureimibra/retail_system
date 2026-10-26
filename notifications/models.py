from django.db import models

from accounts.models import default_shop_id


class Conversation(models.Model):
    """Everything sent to and received from one customer, on any channel."""
    shop = models.ForeignKey('accounts.Shop', on_delete=models.CASCADE, default=default_shop_id, related_name='conversations')
    customer = models.ForeignKey('customers.Customer', on_delete=models.CASCADE, related_name='conversations')
    unread_count = models.PositiveIntegerField(default=0)
    last_message_at = models.DateTimeField(null=True, blank=True)
    last_inbound_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-last_message_at']
        constraints = [
            models.UniqueConstraint(fields=['shop', 'customer'], name='one_conversation_per_customer'),
        ]

    def __str__(self):
        return f'Conversation with {self.customer}'


class Message(models.Model):
    OUTBOUND = 'out'
    INBOUND = 'in'
    DIRECTION_CHOICES = [(OUTBOUND, 'Sent'), (INBOUND, 'Received')]

    WHATSAPP = 'whatsapp'
    SMS = 'sms'
    EMAIL = 'email'
    CHANNEL_CHOICES = [(WHATSAPP, 'WhatsApp'), (SMS, 'SMS'), (EMAIL, 'Email')]

    QUEUED = 'queued'
    SENT = 'sent'
    DELIVERED = 'delivered'
    READ = 'read'
    FAILED = 'failed'
    SKIPPED = 'skipped'
    RECEIVED = 'received'
    STATUS_CHOICES = [
        (QUEUED, 'Queued'),
        (SENT, 'Sent'),
        (DELIVERED, 'Delivered'),
        (READ, 'Read'),
        (FAILED, 'Send failed'),
        (SKIPPED, 'Not sent'),
        (RECEIVED, 'Received'),
    ]
    SUCCESS_STATUSES = [SENT, DELIVERED, READ]

    shop = models.ForeignKey('accounts.Shop', on_delete=models.CASCADE, default=default_shop_id, related_name='messages')
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, null=True, blank=True, related_name='messages')
    intent = models.ForeignKey('intents.BlockedPurchaseIntent', on_delete=models.SET_NULL, null=True, blank=True, related_name='messages')
    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    to_address = models.CharField(max_length=254, blank=True)
    from_address = models.CharField(max_length=254, blank=True)
    body = models.TextField()
    template_key = models.CharField(max_length=40, blank=True, help_text='Which message this is, e.g. restock_alert.')
    media_url = models.URLField(max_length=500, blank=True)
    alert_dismissed = models.BooleanField(default=False, help_text='Staff hid this failure from Home → Needs you now.')
    template_params = models.JSONField(default=list, blank=True,
                                       help_text='Values for the approved WhatsApp template, in order.')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=QUEUED)
    provider = models.CharField(max_length=30, blank=True)
    provider_message_id = models.CharField(max_length=120, blank=True, db_index=True)
    error_code = models.CharField(max_length=40, blank=True)
    error_detail = models.CharField(max_length=300, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at', 'id']

    def __str__(self):
        return f'{self.get_direction_display()} {self.get_channel_display()} {self.to_address or self.from_address}'

    @property
    def succeeded(self):
        return self.status in self.SUCCESS_STATUSES

