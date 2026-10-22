from django.db import migrations


def date_existing(apps, schema_editor):
    """Records notified before follow-ups existed: give them a date, and no surprise reminders."""
    Intent = apps.get_model('intents', 'BlockedPurchaseIntent')
    for intent in Intent.objects.filter(status='notified', notified_at__isnull=True):
        intent.notified_at = intent.updated_at
        intent.follow_ups_sent = 3
        intent.save(update_fields=['notified_at', 'follow_ups_sent'])


class Migration(migrations.Migration):

    dependencies = [
        ('intents', '0009_follow_up_tracking'),
    ]

    operations = [
        migrations.RunPython(date_existing, migrations.RunPython.noop),
    ]
