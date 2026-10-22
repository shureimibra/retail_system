from django.db.models import Count, Min, Sum

from intents.models import BlockedPurchaseIntent as Intent
from .models import Category, Product, ProductVariation


def get_all_categories(shop):
    return Category.objects.filter(shop=shop).order_by('name')


def get_all_products(shop):
    return Product.objects.filter(shop=shop).select_related('category').order_by('name')


def get_product_variations(product_id):
    return ProductVariation.objects.filter(product_id=product_id).order_by('option1', 'option2', 'option3')


def _ordered(values, suggested):
    """Option values in the order the product type suggests (36, 37, 38 / XS, S, M), then the rest A to Z."""
    position = {v: i for i, v in enumerate(suggested)}
    return sorted(values, key=lambda v: (position.get(v, len(position)), v))


def product_detail(product):
    """Everything the product page shows: the option grid with stock and waiting counts, and who is waiting."""
    variations = list(product.variations.prefetch_related('holds').order_by('option1', 'option2', 'option3'))
    waiting = Intent.objects.filter(product=product, status__in=Intent.WAITING_STATUSES)
    for_stock = waiting.filter(constraint_type__in=Intent.RESTOCK_REASONS)
    for_price = waiting.filter(constraint_type__in=Intent.PRICE_DROP_REASONS)
    waiting_by_variation = dict(for_stock.values_list('variation_id').annotate(n=Count('id')))
    for v in variations:
        v.waiting = waiting_by_variation.get(v.id, 0)

    options = product.product_type.options if product.product_type else [('Size', []), ('Colour', [])]
    names = [name for name, _ in options] + ['', '', '']
    suggested = [values for _, values in options] + [[], [], []]
    grid = None
    uses_option3 = any(v.option3 for v in variations)
    if variations and not uses_option3 and any(v.option2 for v in variations) and any(v.option1 for v in variations):
        cols = _ordered({v.option1 for v in variations if v.option1}, suggested[0])
        rows = _ordered({v.option2 for v in variations if v.option2}, suggested[1])
        cells = {(v.option2, v.option1): v for v in variations}
        grid = {'col_name': names[0], 'row_name': names[1], 'cols': cols,
                'rows': [(row, [cells.get((row, col)) for col in cols]) for row in rows]}

    stock_totals = for_stock.aggregate(customers=Count('customer', distinct=True), money=Sum('estimated_value'),
                                       oldest=Min('needed_by'))
    photo_option = 'option2' if any(v.option2 for v in variations) else 'option1'
    photo_values = _ordered({getattr(v, photo_option) for v in variations if getattr(v, photo_option)},
                            suggested[1 if photo_option == 'option2' else 0])
    photos = {p.value: p for p in product.option_photos.all()}
    return {
        'variations': variations,
        'grid': grid,
        'option_names': [n for n in names[:3] if n],
        'type_options': [(name, values) for name, values in options],
        'total_stock': sum(v.stock_quantity for v in variations),
        'waiting_stock': {'count': for_stock.count(), 'customers': stock_totals['customers'],
                          'money': float(stock_totals['money'] or 0), 'oldest_need': stock_totals['oldest']},
        'waiting_price': {'count': for_price.count(), 'customers': for_price.values('customer').distinct().count()},
        'photo_label': names[1] if photo_option == 'option2' else names[0],
        'photos': [(value, photos.get(value)) for value in photo_values],
    }
