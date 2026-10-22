from django.db import migrations

STATUS_MAP = {
    'Pending': 'open',
    'Monitoring': 'open',
    'Resolved': 'back_in_stock',
    'Customer Notified': 'notified',
    'Recovered': 'recovered',
    'Closed': 'declined',
}
REASON_MAP = {
    'Size unavailable': 'size_missing',
    'Color unavailable': 'colour_missing',
    'Out of stock': 'out_of_stock',
    'Price too high': 'price_too_high',
    'Budget mismatch': 'over_budget',
}


def forwards(apps, schema_editor):
    Intent = apps.get_model('intents', 'BlockedPurchaseIntent')
    IntentEvent = apps.get_model('intents', 'IntentEvent')
    for intent in Intent.objects.all():
        old_status = intent.status
        intent.status = STATUS_MAP.get(old_status, old_status)
        intent.constraint_type = REASON_MAP.get(intent.constraint_type, 'other')
        note = 'Carried over from the previous version.'
        if old_status == 'Recovered':
            note += ' Payment was not recorded at the time.'
        if old_status == 'Closed':
            intent.closed_reason = 'Closed before the upgrade'
        intent.save(update_fields=['status', 'constraint_type', 'closed_reason'])
        IntentEvent.objects.create(intent=intent, kind='migrated', from_status=old_status,
                                   to_status=intent.status, note=note)


def backwards(apps, schema_editor):
    Intent = apps.get_model('intents', 'BlockedPurchaseIntent')
    status_back = {'open': 'Pending', 'on_order': 'Monitoring', 'back_in_stock': 'Resolved', 'notified': 'Customer Notified',
                   'in_conversation': 'Customer Notified', 'reserved': 'Customer Notified', 'recovered': 'Recovered',
                   'declined': 'Closed', 'expired': 'Closed'}
    reason_back = {v: k for k, v in REASON_MAP.items()}
    for intent in Intent.objects.all():
        intent.status = status_back.get(intent.status, intent.status)
        intent.constraint_type = reason_back.get(intent.constraint_type, 'Out of stock')
        intent.save(update_fields=['status', 'constraint_type'])


class Migration(migrations.Migration):

    dependencies = [
        ('intents', '0007_lifecycle_visits_payments_events'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
