"""Phase 4: M-Pesa payment prompts (Daraja STK push) and Settings checks. No test reaches a real provider."""
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import Membership, Shop, User
from customers.models import Customer
from intents import services
from intents.models import BlockedPurchaseIntent as Intent
from notifications.models import Conversation
from payments.models import MpesaRequest
from payments import services as mpesa
from products.models import Category, Product, ProductVariation

MPESA_ON = dict(MPESA_ENV='sandbox', MPESA_CONSUMER_KEY='key', MPESA_CONSUMER_SECRET='secret',
                MPESA_CALLBACK_TOKEN='s3cret', SITE_URL='https://shop.example')


def http(payload, status=200):
    response = MagicMock(status_code=status, ok=status < 400)
    response.json.return_value = payload
    return response


def callback(checkout, code=0, amount=5000, receipt='QK7H2L9XYZ', desc='The service request is processed successfully.'):
    body = {'MerchantRequestID': 'm-1', 'CheckoutRequestID': checkout, 'ResultCode': code, 'ResultDesc': desc}
    if code == 0:
        body['CallbackMetadata'] = {'Item': [{'Name': 'Amount', 'Value': amount}, {'Name': 'MpesaReceiptNumber', 'Value': receipt},
                                             {'Name': 'PhoneNumber', 'Value': 254722345678}]}
    return {'Body': {'stkCallback': body}}


@override_settings(**MPESA_ON)
class MpesaTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.shop = Shop.objects.create(name='Kimathi Street Store')
        self.users = {}
        for role in (Membership.OWNER, Membership.CASHIER):
            user = User.objects.create_user(role, password='pw12345!', first_name=role.title())
            Membership.objects.create(user=user, shop=self.shop, role=role)
            self.users[role] = user
        category = Category.objects.create(shop=self.shop, name='Running')
        product = Product.objects.create(shop=self.shop, category=category, name='Adidas Ultraboost', base_price=18700)
        variation = ProductVariation.objects.create(product=product, option1='42', option2='Grey', sku='AU-42-GRE')
        self.jane = Customer.objects.create(shop=self.shop, first_name='Jane', last_name='Smith', phone_number='+254722345678')
        self.intent = services.create_blocked_purchase_intent(self.jane, product, variation, Intent.SIZE_MISSING)
        self.conversation = Conversation.objects.create(shop=self.shop, customer=self.jane, last_inbound_at=timezone.now())

    def start(self, amount=5000, checkout='ws_CO_1'):
        with patch('payments.daraja.requests.get', return_value=http({'access_token': 'tok', 'expires_in': '3599'})), \
                patch('payments.daraja.requests.post', return_value=http(
                    {'MerchantRequestID': 'm-1', 'CheckoutRequestID': checkout, 'ResponseCode': '0'})) as post:
            request = mpesa.request_payment(self.intent, amount, '0722 345 678', actor=self.users['cashier'])
        return request, post

    def call_back(self, payload, token='s3cret'):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(f'/payments/mpesa/callback/{token}/', payload, content_type='application/json')


class PromptTests(MpesaTestCase):
    def test_prompt_is_sent_to_the_customer(self):
        request, post = self.start()
        payload = post.call_args.kwargs['json']
        self.assertEqual((payload['PhoneNumber'], payload['Amount'], payload['BusinessShortCode']), ('254722345678', 5000, '174379'))
        self.assertEqual(payload['CallBackURL'], 'https://shop.example/payments/mpesa/callback/s3cret/')
        self.assertIn('sandbox.safaricom.co.ke', post.call_args.args[0])
        self.assertEqual((request.status, request.checkout_request_id), (MpesaRequest.PENDING, 'ws_CO_1'))
        # Nothing is recorded until Safaricom confirms.
        self.assertEqual(self.intent.payments.count(), 0)

    def test_refused_before_anything_is_sent(self):
        for amount, phone in ((0, '0722345678'), (99999, '0722345678'), ('lots', '0722345678'), (100, '+1 415 555 0100')):
            with self.subTest(amount=amount, phone=phone), patch('payments.daraja.requests.post') as post:
                with self.assertRaises(ValueError):
                    mpesa.request_payment(self.intent, amount, phone)
                post.assert_not_called()

    def test_needs_keys_and_a_public_address(self):
        with self.settings(MPESA_ENV='off'), self.assertRaises(ValueError):
            mpesa.request_payment(self.intent, 100, '0722345678')
        with self.settings(SITE_URL='http://localhost:8000'), patch('payments.daraja.requests.get',
                                                                     return_value=http({'access_token': 't'})):
            with self.assertRaises(ValueError):
                mpesa.request_payment(self.intent, 100, '0722345678')

    def test_one_prompt_at_a_time(self):
        self.start()
        with self.assertRaises(ValueError):
            self.start(checkout='ws_CO_2')


class CallbackTests(MpesaTestCase):
    def test_paid_deposit_records_itself_once(self):
        self.start()
        self.assertEqual(self.call_back(callback('ws_CO_1')).json()['ResultCode'], 0)
        self.call_back(callback('ws_CO_1'))  # Safaricom can send the same result twice
        self.intent.refresh_from_db()
        payment = self.intent.payments.get()
        self.assertEqual((payment.amount, payment.method, payment.reference), (5000, 'mpesa', 'QK7H2L9XYZ'))
        self.assertEqual(self.intent.status, Intent.RESERVED)
        self.assertEqual(MpesaRequest.objects.get().status, MpesaRequest.PAID)

    def test_paid_in_full_is_recovered(self):
        self.start(amount=18700)
        self.call_back(callback('ws_CO_1', amount=18700))
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, Intent.RECOVERED)

    def test_cancelled_records_nothing(self):
        self.start()
        self.call_back(callback('ws_CO_1', code=1032, desc='Request cancelled by user'))
        request = MpesaRequest.objects.get()
        self.assertEqual((request.status, request.result_desc), (MpesaRequest.CANCELLED, 'Request cancelled by user'))
        self.assertEqual(self.intent.payments.count(), 0)

    def test_wrong_token_or_amount_is_not_recorded(self):
        self.start()
        self.assertEqual(self.call_back(callback('ws_CO_1'), token='guess').status_code, 404)
        self.assertEqual(self.intent.payments.count(), 0)
        self.call_back(callback('ws_CO_1', amount=1))
        self.assertEqual(MpesaRequest.objects.get().status, MpesaRequest.NEEDS_CHECK)
        self.assertEqual(self.intent.payments.count(), 0)

    def test_unknown_or_broken_callbacks_are_ignored(self):
        self.assertEqual(self.call_back(callback('ws_CO_unknown')).json()['ResultCode'], 0)
        response = self.client.post('/payments/mpesa/callback/s3cret/', 'not json', content_type='application/json')
        self.assertEqual(response.status_code, 200)

    def test_late_callback_is_checked_with_a_query(self):
        request, _ = self.start()
        MpesaRequest.objects.filter(pk=request.pk).update(created_at=timezone.now() - timedelta(minutes=1))
        self.client.login(username='cashier', password='pw12345!')
        with patch('payments.daraja.requests.post', return_value=http({'ResultCode': '0', 'ResultDesc': 'processed'})), \
                self.captureOnCommitCallbacks(execute=True):
            data = self.client.get(f'/payments/mpesa/{request.pk}/status/').json()
        self.assertEqual(data['status'], MpesaRequest.PAID)
        self.assertEqual(self.intent.payments.get().amount, 5000)


class DealPanelTests(MpesaTestCase):
    def test_cashier_sends_a_prompt_from_the_conversation(self):
        self.client.login(username='cashier', password='pw12345!')
        url = f'/notifications/c/{self.conversation.pk}/'
        self.assertContains(self.client.get(url), 'Send payment prompt')
        with patch('payments.daraja.requests.get', return_value=http({'access_token': 'tok'})), \
                patch('payments.daraja.requests.post', return_value=http({'CheckoutRequestID': 'ws_CO_9', 'ResponseCode': '0'})):
            self.client.post(url, {'action': 'mpesa', 'intent': self.intent.pk, 'amount': '2000', 'phone': '0722345678'})
        self.assertEqual(MpesaRequest.objects.get().amount, 2000)
        self.assertContains(self.client.get(url), 'to enter their M-Pesa PIN')

    def test_daraja_refusal_is_shown_plainly(self):
        self.client.login(username='owner', password='pw12345!')
        with patch('payments.daraja.requests.get', return_value=http({'errorMessage': 'Invalid credentials'}, 400)):
            response = self.client.post(f'/notifications/c/{self.conversation.pk}/',
                                        {'action': 'mpesa', 'intent': self.intent.pk, 'amount': '2000', 'phone': '0722345678'},
                                        follow=True)
        self.assertContains(response, 'M-Pesa refused the app keys')
        self.assertFalse(MpesaRequest.objects.exists())

    def test_status_of_another_shops_prompt_is_hidden(self):
        request, _ = self.start()
        other = Shop.objects.create(name='Elsewhere')
        outsider = User.objects.create_user('outsider', password='pw12345!')
        Membership.objects.create(user=outsider, shop=other, role=Membership.OWNER)
        self.client.login(username='outsider', password='pw12345!')
        self.assertEqual(self.client.get(f'/payments/mpesa/{request.pk}/status/').status_code, 404)


class SettingsTests(MpesaTestCase):
    def test_payments_section_is_for_the_owner(self):
        self.client.login(username='cashier', password='pw12345!')
        self.assertEqual(self.client.get('/settings/payments/').status_code, 403)
        self.client.login(username='owner', password='pw12345!')
        self.assertContains(self.client.get('/settings/payments/'), 'Sandbox')
        self.client.post('/settings/payments/', {'payment_details': 'M-Pesa Till 123456'})
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.payment_details, 'M-Pesa Till 123456')

    @override_settings(MESSAGING_PROVIDERS={'whatsapp': 'whatsapp_cloud', 'sms': 'twilio', 'email': 'simulator'},
                       WHATSAPP_TOKEN='t', WHATSAPP_PHONE_NUMBER_ID='123', TWILIO_ACCOUNT_SID='',
                       TWILIO_AUTH_TOKEN='', TWILIO_PHONE_NUMBER='')
    def test_connections_and_test_message(self):
        self.client.login(username='owner', password='pw12345!')
        page = self.client.get('/settings/messaging/')
        self.assertContains(page, 'Connected')
        self.assertContains(page, 'Missing in .env: TWILIO_ACCOUNT_SID')
        self.assertNotContains(page, 'value="t"')
        with patch('notifications.providers.requests.post', return_value=http({'messages': [{'id': 'wamid.T'}]})) as post:
            response = self.client.post('/settings/messaging/', {'action': 'test', 'channel': 'whatsapp', 'to': '0722345678'},
                                        follow=True)
        self.assertEqual(post.call_args.kwargs['json']['template']['name'], 'hello_world')
        self.assertContains(response, 'Sent to +254722345678 through Meta WhatsApp Cloud API')
