from django.db import transaction

from .models import Category, Product, ProductVariation


def create_category(name, description=""):
    return Category.objects.create(name=name, description=description)


def create_product(category, name, description, base_price):
    return Product.objects.create(
        category=category,
        name=name,
        description=description,
        base_price=base_price
    )


def create_product_variation(product, size, color, stock_quantity, sku):
    variation = ProductVariation.objects.create(
        product=product,
        size=size,
        color=color,
        stock_quantity=stock_quantity,
        sku=sku
    )
    if variation.stock_quantity > 0:
        _notify_waiting_customers(variation)
    return variation


@transaction.atomic
def set_stock(variation_id, new_quantity):
    """Set a variation's stock. If stock went up, waiting customers are notified."""
    variation = ProductVariation.objects.select_for_update().get(id=variation_id)
    old_quantity = variation.stock_quantity
    variation.stock_quantity = max(0, new_quantity)
    variation.save(update_fields=['stock_quantity'])
    if variation.stock_quantity > old_quantity:
        _notify_waiting_customers(variation)
    return variation


@transaction.atomic
def adjust_stock(variation_id, quantity_change):
    """Add (or remove, if negative) stock without a read-then-write race."""
    variation = ProductVariation.objects.select_for_update().get(id=variation_id)
    return set_stock(variation.id, variation.stock_quantity + quantity_change)


def _notify_waiting_customers(variation):
    from intents.services import resolve_intents_for_variation
    return resolve_intents_for_variation(variation)
