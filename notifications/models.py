from django.db import models
from intents.models import BlockedPurchaseIntent

class NotificationLog(models.Model):
    intent = models.ForeignKey(BlockedPurchaseIntent, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, default='Sent')
    
    def __str__(self):
        return f"Notification for {self.intent.id} at {self.sent_at}"


class InboundSMSLog(models.Model):
    from_number = models.CharField(max_length=30)
    to_number = models.CharField(max_length=30)
    body = models.TextField()
    received_at = models.DateTimeField(auto_now_add=True)
    customer = models.ForeignKey(
        'customers.Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inbound_messages'
    )

    def __str__(self):
        return f"Reply from {self.from_number} at {self.received_at}"

