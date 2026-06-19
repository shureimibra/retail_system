from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import NotificationLog

@receiver(post_save, sender=NotificationLog)
def update_intent_status_on_notification(sender, instance, created, **kwargs):
    """
    Update BlockedPurchaseIntent status to 'Customer Notified' when a notification is successfully sent.
    """
    if instance.status == 'Sent':
        intent = instance.intent
        if intent.status != 'Customer Notified':
            intent.status = 'Customer Notified'
            intent.save(update_fields=['status'])
