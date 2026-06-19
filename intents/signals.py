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
            # Update status to Resolved or trigger notification
            intent.status = 'Resolved'
            intent.save()
            # Trigger SMS notification
            SMSService.send_restock_notification(intent.id)
