from django.db.models.signals import post_save
from django.dispatch import receiver
from products.models import ProductVariation
from intents.models import BlockedPurchaseIntent
from notifications.services import SMSService

@receiver(post_save, sender=ProductVariation)
def check_inventory_for_intents(sender, instance, created, **kwargs):
    """
    Inventory Monitoring Engine:
    DEACTIVATED: Stock monitoring and resolution is now explicitly handled in
    services/inventory_service.py to prevent "Signal Storm" race conditions.
    """
    pass


@receiver(post_save, sender=BlockedPurchaseIntent)
def send_notification_on_intent_resolve(sender, instance, created, **kwargs):
    """
    Trigger notification when a BlockedPurchaseIntent's status is manually updated to 'Resolved':
    DEACTIVATED: Restock notifications are handled out-of-band by Celery workers
    triggered from the service layer.
    """
    pass
