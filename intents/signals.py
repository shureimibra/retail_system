from django.db.models.signals import post_save
from django.dispatch import receiver
from products.models import ProductVariation
from intents.models import BlockedPurchaseIntent
from notifications.services import SMSService

@receiver(post_save, sender=ProductVariation)
def check_inventory_for_intents(sender, instance, created, **kwargs):
    """
    Inventory Monitoring Engine:
    When a product variation is saved (e.g., restocked), check if it resolves
    any Pending or Monitoring intents.
    """
    if instance.stock_quantity > 0:
        # Find pending intents for this variation
        matching_intents = BlockedPurchaseIntent.objects.filter(
            variation=instance,
            status__in=['Pending', 'Monitoring']
        )
        
        for intent in matching_intents:
            # Update status to Resolved (this will trigger send_notification_on_intent_resolve)
            intent.status = 'Resolved'
            intent.save()


@receiver(post_save, sender=BlockedPurchaseIntent)
def send_notification_on_intent_resolve(sender, instance, created, **kwargs):
    """
    Trigger WhatsApp notification when a BlockedPurchaseIntent's status is manually updated to 'Resolved'
    (e.g., from the admin panel or intent update views).
    """
    if instance.status == 'Resolved':
        # Prevent duplicate notifications if one was already successfully sent
        from notifications.models import NotificationLog
        if not NotificationLog.objects.filter(intent=instance, status='Sent').exists():
            SMSService.send_restock_notification(instance.id)
