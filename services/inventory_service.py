from products.models import Product, ProductVariation
from services.intent_service import resolve_blocked_intents_for_product, resolve_blocked_intents_for_variation

def update_stock(variation_id, new_quantity):
    """
    Updates the stock quantity of a variation and returns it.
    """
    variation = ProductVariation.objects.get(id=variation_id)
    variation.stock_quantity = max(0, new_quantity)
    variation.save()
    return variation

def handle_stock_update(product_or_variation):
    """
    Determines if stock has become available and processes matching intents.
    """
    if isinstance(product_or_variation, ProductVariation):
        if product_or_variation.stock_quantity > 0:
            resolve_blocked_intents_for_variation(product_or_variation)
    elif isinstance(product_or_variation, Product):
        # Check if any variation has stock
        if ProductVariation.objects.filter(product=product_or_variation, stock_quantity__gt=0).exists():
            resolve_blocked_intents_for_product(product_or_variation)
