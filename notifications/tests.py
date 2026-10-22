import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import Membership, Shop, User
from customers.models import Customer
from intents.models import BlockedPurchaseIntent as Intent
from intents.services import create_blocked_purchase_intent, record_payment
from notifications import gateway, inbound
from notifications.models import Conversation, Message
from products.models import Category, Product, ProductType, ProductVariation
from products.services import receive_stock

WHATSAPP_CLOUD = {'whatsapp': 'whatsapp_cloud', 'sms': 'simulator', 'email': 'simulator'}


def http_response(status=200, payload=None):
    response = MagicMock()
    response.ok = 200 <= status < 300
    response.status_code = status
    response.json.return_value = payload or {}
    response.text = json.dumps(payload or {})
    return response


class MessagingTestCase(TestCase):
    def setUp(self):
        self.shop = Shop.objects.create(name='Kimathi Street Store')
        self.owner = User.objects.create_user('owner', password='pw12345!')
        Membership.objects.create(user=self.owner, shop=self.shop, role=Membership.OWNER)
        category = Category.objects.create(shop=self.shop, name='Running')
        shoes = ProductType.objects.get(shop=self.shop, name='Shoes')
        self.product = Product.objects.create(shop=self.shop, category=category, product_type=shoes,
                                              name='Adidas Ultraboost', base_price=18700)
        self.variation = ProductVariation.objects.create(product=self.product, option1='42', option2='Grey', sku='ADI-42-GRY')
        self.jane = Customer.objects.create(shop=self.shop, first_name='Jane', last_name='Smith',
                                            phone_number='+254722345678', email='jane@example.com')

    def waiting(self, customer=None, **kwargs):
        return create_blocked_purchase_intent(customer or self.jane, self.product, self.variation,
                                              Intent.SIZE_MISSING, recorded_by=self.owner, **kwargs)

    def restock(self, qty=1):
        with self.captureOnCommitCallbacks(execute=True):
            receive_stock(self.variation.id, qty)

    def outbound(self):
        return Message.objects.filter(direction=Message.OUTBOUND)


class RestockMessageTests(MessagingTestCase):
    def test_restock_message_is_sent_and_request_is_notified(self):
        intent = self.waiting()
        self.restock()
        message = self.outbound().get()
        self.assertEqual((message.channel, message.status, message.provider, message.to_address),
                         ('whatsapp', 'delivered', 'simulator', '+254722345678'))
        self.assertIn('Adidas Ultraboost in 42 / Grey', message.body)
        self.assertIn('Kimathi Street Store', message.body)
        self.assertIn("We're holding one for you until", message.body)
        self.assertIn('STOP', message.body)
        intent.refresh_from_db()
        self.assertEqual(intent.status, Intent.NOTIFIED)
        self.assertEqual(message.conversation.customer, self.jane)

    def test_opted_out_customer_gets_nothing(self):
        self.jane.marketing_opt_in = False
        self.jane.save()
        intent = self.waiting()
        self.restock()
        message = self.outbound().get()
        self.assertEqual((message.status, message.error_detail), ('skipped', 'Customer opted out'))
        intent.refresh_from_db()
        self.assertEqual(intent.status, Intent.BACK_IN_STOCK)

    def test_no_consent_no_message(self):
        self.waiting(consent_given=False)
        self.restock()
        self.assertEqual(self.outbound().get().error_detail, 'Customer did not agree to be contacted')

    def test_unreadable_phone_falls_to_email(self):
        bob = Customer.objects.create(shop=self.shop, first_name='Bob', last_name='K', phone_number='12345', email='bob@example.com')
        self.waiting(customer=bob)
        self.restock()
        message = self.outbound().get()
        self.assertEqual((message.channel, message.to_address, message.status), ('email', 'bob@example.com', 'delivered'))

    def test_deposit_sends_a_receipt(self):
        intent = self.waiting()
        self.restock()
        intent.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            record_payment(intent, 5000, 'mpesa', reference='SJK4H7Q2LM')
        receipt = self.outbound().get(template_key='deposit_receipt')
        self.assertIn('KSh 5,000', receipt.body)
        self.assertIn('Balance KSh 13,700', receipt.body)


@override_settings(MESSAGING_PROVIDERS=WHATSAPP_CLOUD, WHATSAPP_TOKEN='t', WHATSAPP_PHONE_NUMBER_ID='123')
class WhatsAppCloudTests(MessagingTestCase):
    @patch('notifications.providers.requests.post')
    def test_template_send(self, post):
        post.return_value = http_response(200, {'messages': [{'id': 'wamid.1'}]})
        self.waiting()
        self.restock()
        message = self.outbound().get()
        self.assertEqual((message.status, message.provider_message_id), ('sent', 'wamid.1'))
        payload = post.call_args.kwargs['json']
        self.assertEqual((payload['to'], payload['type'], payload['template']['name']), ('254722345678', 'template', 'hello_world'))

    @patch('notifications.providers.requests.post')
    def test_not_on_whatsapp_falls_back_to_sms(self, post):
        post.return_value = http_response(400, {'error': {'code': 131026, 'message': 'Message undeliverable'}})
        intent = self.waiting()
        self.restock()
        whatsapp, sms = self.outbound().order_by('id')
        self.assertEqual((whatsapp.channel, whatsapp.status, whatsapp.error_code), ('whatsapp', 'failed', '131026'))
        self.assertIsNone(whatsapp.next_attempt_at)
        self.assertEqual((sms.channel, sms.status), ('sms', 'delivered'))
        intent.refresh_from_db()
        self.assertEqual(intent.status, Intent.NOTIFIED)

    @patch('notifications.providers.requests.post')
    def test_temporary_failure_is_retried_later(self, post):
        post.return_value = http_response(500, {'error': {'code': 2, 'message': 'Service unavailable'}})
        self.waiting()
        self.restock()
        message = self.outbound().get()
        self.assertEqual((message.status, message.attempts), ('failed', 1))
        self.assertIsNotNone(message.next_attempt_at)
        self.assertEqual(gateway.retry_due_messages(), [])  # not due yet

        post.return_value = http_response(200, {'messages': [{'id': 'wamid.2'}]})
        Message.objects.filter(pk=message.pk).update(next_attempt_at=timezone.now() - timedelta(minutes=1))
        gateway.retry_due_messages()
        message.refresh_from_db()
        self.assertEqual((message.status, message.attempts, message.provider_message_id), ('sent', 2, 'wamid.2'))


@override_settings(MESSAGING_PROVIDERS={'whatsapp': 'simulator', 'sms': 'africastalking', 'email': 'simulator'},
                   AFRICASTALKING_API_KEY='k', AFRICASTALKING_USERNAME='sandbox')
class AfricasTalkingTests(MessagingTestCase):
    @patch('notifications.providers.requests.post')
    def test_sms_through_sandbox(self, post):
        post.return_value = http_response(201, {'SMSMessageData': {'Recipients': [{'status': 'Success', 'messageId': 'ATXid_1'}]}})
        self.waiting(preferred_channel=Intent.SMS)
        self.restock()
        message = self.outbound().get()
        self.assertEqual((message.channel, message.status, message.provider_message_id), ('sms', 'sent', 'ATXid_1'))
        self.assertIn('api.sandbox.africastalking.com', post.call_args.args[0])


@override_settings(MESSAGING_PROVIDERS={'whatsapp': 'simulator', 'sms': 'twilio', 'email': 'simulator'},
                   TWILIO_ACCOUNT_SID='AC1', TWILIO_AUTH_TOKEN='tok', TWILIO_PHONE_NUMBER='+15555555555')
class TwilioSMSTests(MessagingTestCase):
    @patch('twilio.rest.Client')
    def test_sms_through_twilio(self, client):
        client.return_value.messages.create.return_value.sid = 'SM1'
        self.waiting(preferred_channel=Intent.SMS)
        self.restock()
        message = self.outbound().get()
        self.assertEqual((message.provider, message.provider_message_id), ('twilio', 'SM1'))
        kwargs = client.return_value.messages.create.call_args.kwargs
        self.assertEqual((kwargs['from_'], kwargs['to']), ('+15555555555', '+254722345678'))


@override_settings(MESSAGING_PROVIDERS={'whatsapp': 'simulator', 'sms': 'simulator', 'email': 'email'})
class EmailTests(MessagingTestCase):
    def test_email_goes_through_django_mail(self):
        self.waiting(preferred_channel=Intent.EMAIL)
        self.restock()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['jane@example.com'])
        self.assertIn('Adidas Ultraboost', mail.outbox[0].body)


class InboundAndReplyTests(MessagingTestCase):
    def setUp(self):
        super().setUp()
        self.intent = self.waiting()
        self.restock()
        self.intent.refresh_from_db()

    def test_reply_moves_request_into_conversation(self):
        message, auto_reply = inbound.receive('whatsapp', 'whatsapp:+254722345678', 'Yes!! Can I pay a deposit?')
        self.assertEqual(auto_reply, '')
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, Intent.IN_CONVERSATION)
        self.assertTrue(self.intent.events.filter(kind='wants_it').exists())
        conversation = message.conversation
        self.assertEqual((conversation.unread_count, conversation.customer), (1, self.jane))

    def test_stop_opts_out_on_every_channel(self):
        _, auto_reply = inbound.receive('sms', '0722 345 678', 'stop please')
        self.assertIn("won't get any more messages", auto_reply)
        self.jane.refresh_from_db()
        self.assertFalse(self.jane.marketing_opt_in)
        conversation = Conversation.objects.get(customer=self.jane)
        with self.captureOnCommitCallbacks(execute=True):
            reply = gateway.send_reply(conversation, 'Are you still interested?', channel='sms')
        reply.refresh_from_db()
        self.assertEqual((reply.status, reply.error_detail), ('skipped', 'Customer opted out'))
        inbound.receive('sms', '+254722345678', 'START')
        self.jane.refresh_from_db()
        self.assertTrue(self.jane.marketing_opt_in)

    def test_whatsapp_free_text_only_within_24_hours(self):
        conversation = Conversation.objects.get(customer=self.jane)
        with self.captureOnCommitCallbacks(execute=True):
            early = gateway.send_reply(conversation, 'Hello?', channel='whatsapp')
        early.refresh_from_db()
        self.assertEqual(early.status, 'skipped')
        inbound.receive('whatsapp', '+254722345678', 'Hi, is it still there?')
        with self.captureOnCommitCallbacks(execute=True):
            reply = gateway.send_reply(conversation, 'Yes, we are holding it for you.')
        reply.refresh_from_db()
        self.assertEqual((reply.channel, reply.status), ('whatsapp', 'delivered'))

    def test_unknown_sender_is_kept_without_a_customer(self):
        message, _ = inbound.receive('sms', '+254700999999', 'Who is this?')
        self.assertIsNone(message.conversation)


class WebhookTests(MessagingTestCase):
    def setUp(self):
        super().setUp()
        self.waiting()
        self.restock()

    def test_twilio_reply_and_stop_answer(self):
        response = self.client.post('/notifications/webhook/', {'From': '+254722345678', 'To': '+1', 'Body': 'STOP', 'MessageSid': 'SM9'})
        self.assertEqual(response.status_code, 200)
        self.assertIn("won't get any more messages", response.content.decode())
        self.assertEqual(Message.objects.get(direction='in').provider_message_id, 'SM9')

    @override_settings(TWILIO_AUTH_TOKEN='secret')
    def test_twilio_requires_a_valid_signature_when_configured(self):
        response = self.client.post('/notifications/webhook/', {'From': '+254722345678', 'Body': 'Hi'})
        self.assertEqual(response.status_code, 403)

    @override_settings(WHATSAPP_VERIFY_TOKEN='verify-me')
    def test_whatsapp_verification_handshake(self):
        url = '/notifications/webhooks/whatsapp/'
        ok = self.client.get(url, {'hub.mode': 'subscribe', 'hub.verify_token': 'verify-me', 'hub.challenge': '42'})
        self.assertEqual((ok.status_code, ok.content), (200, b'42'))
        self.assertEqual(self.client.get(url, {'hub.mode': 'subscribe', 'hub.verify_token': 'nope'}).status_code, 403)

    @override_settings(WHATSAPP_APP_SECRET='app-secret')
    def test_whatsapp_messages_and_statuses_with_signature(self):
        sent = Message.objects.get(direction='out')
        Message.objects.filter(pk=sent.pk).update(provider_message_id='wamid.X', status='sent')
        body = json.dumps({'entry': [{'changes': [{'value': {
            'messages': [{'from': '254722345678', 'id': 'wamid.IN', 'type': 'text', 'text': {'body': 'Hold it for me'}}],
            'statuses': [{'id': 'wamid.X', 'status': 'read'}],
        }}]}]}).encode()
        signature = 'sha256=' + hmac.new(b'app-secret', body, hashlib.sha256).hexdigest()
        url = '/notifications/webhooks/whatsapp/'
        self.assertEqual(self.client.post(url, body, content_type='application/json',
                                          HTTP_X_HUB_SIGNATURE_256='sha256=bad').status_code, 403)
        response = self.client.post(url, body, content_type='application/json', HTTP_X_HUB_SIGNATURE_256=signature)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Message.objects.get(direction='in').body, 'Hold it for me')
        sent.refresh_from_db()
        self.assertEqual(sent.status, 'read')

    @override_settings(AFRICASTALKING_WEBHOOK_TOKEN='tok123')
    def test_africastalking_reply_and_delivery_report(self):
        self.assertEqual(self.client.post('/notifications/webhooks/africastalking/wrong/', {'from': '+254722345678', 'text': 'Hi'}).status_code, 403)
        sent = Message.objects.get(direction='out')
        Message.objects.filter(pk=sent.pk).update(provider_message_id='ATX1', status='sent')
        self.client.post('/notifications/webhooks/africastalking/tok123/', {'id': 'ATX1', 'status': 'Success'})
        self.client.post('/notifications/webhooks/africastalking/tok123/', {'from': '+254722345678', 'to': '22384', 'text': 'Yes', 'id': 'in1'})
        sent.refresh_from_db()
        self.assertEqual(sent.status, 'delivered')
        self.assertEqual(Message.objects.get(direction='in').body, 'Yes')


class SimulatorAndInboxTests(MessagingTestCase):
    def setUp(self):
        super().setUp()
        self.intent = self.waiting()
        self.restock()
        self.client.login(username='owner', password='pw12345!')

    def test_simulator_shows_messages_and_replies_as_customer(self):
        page = self.client.get('/notifications/simulator/')
        self.assertContains(page, 'Adidas Ultraboost in 42 / Grey')
        self.client.post('/notifications/simulator/', {'from': '+254722345678', 'channel': 'whatsapp', 'body': 'YES'})
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, Intent.IN_CONVERSATION)

    @override_settings(SIMULATOR_ENABLED=False)
    def test_simulator_is_off_when_disabled(self):
        self.assertEqual(self.client.get('/notifications/simulator/').status_code, 404)

    def test_inbox_api(self):
        inbound.receive('whatsapp', '+254722345678', 'Can I pay a deposit?')
        conversations = self.client.get('/api/conversations/').json()
        self.assertEqual(len(conversations), 1)
        self.assertEqual(conversations[0]['unread_count'], 1)
        url = f"/api/conversations/{conversations[0]['id']}/"
        with self.captureOnCommitCallbacks(execute=True):
            messages = self.client.post(url + 'messages/', {'body': 'Yes, send to Till 123456'}, content_type='application/json').json()
        self.assertEqual(messages[-1]['body'], 'Yes, send to Till 123456')
        self.assertEqual(self.client.post(url + 'read/').json()['unread_count'], 0)

    def test_inbox_is_per_shop(self):
        other = Shop.objects.create(name='Other')
        stranger = User.objects.create_user('stranger', password='pw12345!')
        Membership.objects.create(user=stranger, shop=other, role=Membership.OWNER)
        self.client.login(username='stranger', password='pw12345!')
        self.assertEqual(self.client.get('/api/conversations/').json(), [])
