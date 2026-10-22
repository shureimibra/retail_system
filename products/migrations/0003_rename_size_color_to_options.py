from django.db import migrations


class Migration(migrations.Migration):
    """Keep existing data: size becomes option 1 and colour option 2."""

    dependencies = [
        ('products', '0002_category_shop_product_shop'),
    ]

    operations = [
        migrations.RenameField('productvariation', 'size', 'option1'),
        migrations.RenameField('productvariation', 'color', 'option2'),
    ]
