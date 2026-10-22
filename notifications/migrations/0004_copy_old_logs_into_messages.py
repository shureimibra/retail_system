from django.db import migrations


def copy_logs(apps, schema_editor):
    NotificationLog = apps.get_model('notifications', 'NotificationLog')
    InboundSMSLog = apps.get_model('notifications', 'InboundSMSLog')
    Conversation = apps.get_model('notifications', 'Conversation')
    Message = apps.get_model('notifications', 'Message')

    def conversation(customer):
        return Conversation.objects.get_or_create(shop_id=customer.shop_id, customer=customer)[0]

    for log in NotificationLog.objects.select_related('intent__customer').order_by('id'):
        customer = log.intent.customer
        message = Message.objects.create(
            shop_id=log.intent.shop_id, conversation=conversation(customer), intent=log.intent, direction='out',
            channel='whatsapp', to_address=customer.phone_number, body=log.message,
            template_key='restock_alert', status='sent' if log.status == 'Sent' else 'failed', provider='legacy',
            attempts=1, sent_at=log.sent_at)
        Message.objects.filter(pk=message.pk).update(created_at=log.sent_at)

    for log in InboundSMSLog.objects.select_related('customer').order_by('id'):
        channel = 'whatsapp' if log.from_number.startswith('whatsapp:') else 'sms'
        conv = conversation(log.customer) if log.customer else None
        message = Message.objects.create(
            shop_id=log.customer.shop_id if log.customer else None or Message._meta.get_field('shop').get_default(),
            conversation=conv, direction='in', channel=channel, from_address=log.from_number,
            to_address=log.to_number, body=log.body, status='received', provider='legacy')
        Message.objects.filter(pk=message.pk).update(created_at=log.received_at)
        if conv:
            Conversation.objects.filter(pk=conv.pk).update(last_inbound_at=log.received_at, last_message_at=log.received_at)


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0003_conversations_and_messages'),
    ]

    operations = [
        migrations.RunPython(copy_logs, migrations.RunPython.noop),
    ]
