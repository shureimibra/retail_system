import django.dispatch
from django.dispatch import receiver
from services.inventory_service import handle_stock_update

# Define custom signals
on_product_stock_update = django.dispatch.Signal()
on_variation_update = django.dispatch.Signal()

@receiver(on_variation_update)
def handle_variation_stock_change(sender, instance, **kwargs):
    """
    Signal handler called when a ProductVariation stock is updated.
    """
    handle_stock_update(instance)

@receiver(on_product_stock_update)
def handle_product_stock_change(sender, instance, **kwargs):
    """
    Signal handler called when a Product stock is updated.
    """
    handle_stock_update(instance)
