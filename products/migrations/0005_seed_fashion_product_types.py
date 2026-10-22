from django.db import migrations

CATEGORY_HINTS = [
    ('Shoes', ('shoe', 'foot', 'sneaker', 'boot', 'sandal')),
    ('Clothing', ('cloth', 'apparel', 'wear', 'shirt', 'dress', 'jean', 'trouser')),
    ('Bags', ('bag', 'backpack', 'purse', 'handbag')),
    ('Accessories', ('accessor', 'watch', 'belt', 'jewel', 'cap', 'hat')),
]


def seed_types_and_assign(apps, schema_editor):
    from products.models import FASHION_PRODUCT_TYPES

    Shop = apps.get_model('accounts', 'Shop')
    ProductType = apps.get_model('products', 'ProductType')
    Product = apps.get_model('products', 'Product')
    for shop in Shop.objects.all():
        types = {}
        for name, o1, v1, o2, v2, o3, v3 in FASHION_PRODUCT_TYPES:
            types[name], _ = ProductType.objects.get_or_create(
                shop=shop, name=name,
                defaults=dict(option1_name=o1, option1_values=v1, option2_name=o2,
                              option2_values=v2, option3_name=o3, option3_values=v3))
        for product in Product.objects.filter(shop=shop, product_type__isnull=True).select_related('category'):
            category = product.category.name.lower()
            type_name = next((t for t, hints in CATEGORY_HINTS if any(h in category for h in hints)), 'Other')
            product.product_type = types[type_name]
            product.save(update_fields=['product_type'])


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0004_catalog_types_photos_stock'),
    ]

    operations = [
        migrations.RunPython(seed_types_and_assign, migrations.RunPython.noop),
    ]
