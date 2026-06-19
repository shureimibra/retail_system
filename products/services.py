from .models import Category, Product, ProductVariation
from intents.models import BlockedPurchaseIntent
from notifications.services import SMSService

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
    return ProductVariation.objects.create(
        product=product,
        size=size,
        color=color,
        stock_quantity=stock_quantity,
        sku=sku
    )

def update_product_stock(variation_id, quantity_change):
    variation = ProductVariation.objects.get(id=variation_id)
    old_stock = variation.stock_quantity
    variation.stock_quantity = max(0, variation.stock_quantity + quantity_change)
    variation.save()
    
    # If stock becomes available (was 0, now > 0), check for blocked intents
    if old_stock == 0 and variation.stock_quantity > 0:
        # Find pending or monitoring intents matching this variation
        intents = BlockedPurchaseIntent.objects.filter(
            variation=variation,
            status__in=['Pending', 'Monitoring']
        )
        for intent in intents:
            SMSService.send_restock_notification(intent.id)
            
    return variation
