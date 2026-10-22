from django.db import migrations


def normalize_existing_numbers(apps, schema_editor):
    from core.phones import normalize_phone

    Customer = apps.get_model('customers', 'Customer')
    taken = set(Customer.objects.values_list('phone_number', flat=True))
    for customer in Customer.objects.order_by('id'):
        normalized = normalize_phone(customer.phone_number)
        if not normalized or normalized == customer.phone_number:
            if not normalized:
                print(f"  customer {customer.id}: kept unreadable phone '{customer.phone_number}' as is")
            continue
        if normalized in taken:
            print(f"  customer {customer.id}: '{customer.phone_number}' is the same number as another customer "
                  f"({normalized}); left unchanged for manual merge")
            continue
        taken.discard(customer.phone_number)
        taken.add(normalized)
        customer.phone_number = normalized
        customer.save(update_fields=['phone_number'])


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0002_customer_marketing_opt_in'),
    ]

    operations = [
        migrations.RunPython(normalize_existing_numbers, migrations.RunPython.noop),
    ]
