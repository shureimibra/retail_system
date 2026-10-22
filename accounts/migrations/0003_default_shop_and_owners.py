from django.db import migrations


def create_default_shop(apps, schema_editor):
    Shop = apps.get_model('accounts', 'Shop')
    Membership = apps.get_model('accounts', 'Membership')
    User = apps.get_model('accounts', 'User')
    shop = Shop.objects.order_by('id').first() or Shop.objects.create(name='My Shop')
    for user in User.objects.all():
        Membership.objects.get_or_create(user=user, shop=shop, defaults={'role': 'owner'})


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_shop_and_membership'),
    ]

    operations = [
        migrations.RunPython(create_default_shop, migrations.RunPython.noop),
    ]
