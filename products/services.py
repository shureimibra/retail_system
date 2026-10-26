from decimal import Decimal

from django.db import transaction

from .models import (FASHION_PRODUCT_TYPES, Category, PriceChange, Product, ProductType,
                     ProductVariation, StockMovement)


def seed_product_types(shop):
    """Give a shop the starter fashion product types (safe to run twice)."""
    for name, o1, v1, o2, v2, o3, v3 in FASHION_PRODUCT_TYPES:
        ProductType.objects.get_or_create(
            shop=shop, name=name,
            defaults=dict(option1_name=o1, option1_values=v1, option2_name=o2,
                          option2_values=v2, option3_name=o3, option3_values=v3))


def seed_product_types_for_new_shop(sender, instance, created, **kwargs):
    if created:
        seed_product_types(instance)


def create_category(name, description=""):
    return Category.objects.create(name=name, description=description)


def create_product(category, name, description, base_price, product_type=None):
    return Product.objects.create(
        shop=category.shop,
        category=category,
        product_type=product_type,
        name=name,
        description=description,
        base_price=base_price
    )


def create_product_variation(product, option1, option2, stock_quantity, sku, option3=None, recorded_by=None):
    variation = ProductVariation.objects.create(
        product=product, option1=option1, option2=option2, option3=option3, sku=sku,
    )
    if stock_quantity:
        receive_stock(variation.id, stock_quantity, recorded_by=recorded_by)
        variation.refresh_from_db()
    return variation


@transaction.atomic
def receive_stock(variation_id, quantity, recorded_by=None, reference=''):
    """A delivery arrived. Adds stock and puts units aside for waiting customers."""
    if quantity <= 0:
        raise ValueError('Received quantity must be more than zero.')
    variation = ProductVariation.objects.select_for_update().get(id=variation_id)
    return _apply_stock_change(variation, variation.stock_quantity + quantity,
                               StockMovement.RECEIVED, recorded_by, reference)


@transaction.atomic
def set_stock(variation_id, new_quantity, recorded_by=None, reference=''):
    """A stock count: set the quantity on hand. If it went up, waiting customers are notified."""
    variation = ProductVariation.objects.select_for_update().get(id=variation_id)
    return _apply_stock_change(variation, max(0, new_quantity), StockMovement.ADJUSTED, recorded_by, reference)


@transaction.atomic
def adjust_stock(variation_id, quantity_change, recorded_by=None, reference=''):
    """Add (or remove, if negative) stock without a read-then-write race."""
    variation = ProductVariation.objects.select_for_update().get(id=variation_id)
    return _apply_stock_change(variation, max(0, variation.stock_quantity + quantity_change),
                               StockMovement.ADJUSTED, recorded_by, reference)


def _apply_stock_change(variation, new_quantity, kind, recorded_by, reference):
    old_quantity = variation.stock_quantity
    if new_quantity == old_quantity:
        return variation
    variation.stock_quantity = new_quantity
    variation.save(update_fields=['stock_quantity'])
    StockMovement.objects.create(
        variation=variation, kind=kind, quantity_change=new_quantity - old_quantity,
        stock_after=new_quantity, reference=reference, recorded_by=recorded_by,
    )
    if new_quantity > old_quantity:
        from intents.services import resolve_intents_for_variation
        resolve_intents_for_variation(variation)
    return variation


@transaction.atomic
def change_price(product, new_price, changed_by=None, variation=None):
    """Change a product's price (or one variation's own price) and record it."""
    new_price = Decimal(str(new_price))
    if variation is not None:
        old_price = variation.effective_price
        variation.price = new_price
        variation.save(update_fields=['price'])
    else:
        old_price = product.base_price
        product.base_price = new_price
        product.save(update_fields=['base_price', 'updated_at'])
    if new_price == old_price:
        return None
    change = PriceChange.objects.create(product=product, variation=variation, old_price=old_price,
                                        new_price=new_price, changed_by=changed_by)
    if change.is_drop:
        from intents.automation import notify_price_drop
        notify_price_drop(change)
    return change


def suggest_sku(product, *values):
    """NAZ-42-BLA style: product initials, then each option (colours shortened). Made unique if taken."""
    parts = [''.join(w[0] for w in product.name.split()).upper()[:4] or 'P']
    for i, value in enumerate(v for v in values if v):
        value = value.replace(' ', '').upper()
        parts.append(value if i == 0 else value[:3])
    base = '-'.join(parts)[:90]
    sku, n = base, 2
    while ProductVariation.objects.filter(sku=sku).exists():
        sku, n = f'{base}-{n}', n + 1
    return sku


def set_option_photo(product, value, image):
    """The photo for every row with this option value (e.g. Black). Replaces any earlier one."""
    from .models import ProductOptionPhoto
    photo = ProductOptionPhoto.objects.filter(product=product, value=value).first() or ProductOptionPhoto(product=product, value=value)
    photo.image = image
    photo.save()
    return photo


MAX_NEW_OPTIONS = 200


def add_option_combinations(product, option_lists, recorded_by=None):
    """
    Every combination of the given sizes × colours (× third option), each with 0 in stock.
    Returns (added, already_listed). Existing combinations are left alone.
    """
    from itertools import product as combinations
    lists = [values or [None] for values in option_lists]
    if all(values == [None] for values in lists):
        return 0, 0
    existing = {tuple((v or '').lower() for v in combo)
                for combo in product.variations.values_list('option1', 'option2', 'option3')}
    added = skipped = 0
    for combo in list(combinations(*lists))[:MAX_NEW_OPTIONS]:
        key = tuple((v or '').lower() for v in combo)
        if key in existing:
            skipped += 1
            continue
        create_product_variation(product, combo[0], combo[1], 0, suggest_sku(product, *[v or '' for v in combo]),
                                 option3=combo[2], recorded_by=recorded_by)
        existing.add(key)
        added += 1
    return added, skipped
