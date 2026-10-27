"""Phase 3c: Conversations (chat and deal) and Floor mode."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import Membership, Shop, User
from customers.models import Customer
from intents import services
from intents.models import BlockedPurchaseIntent as Intent, Visit
from notifications.models import Conversation, Message
from products.models import Category, Product, ProductVariation


class ChatTestCase(TestCase):
    def setUp(self):
        self.shop = Shop.objects.create(name='Kimathi Street Store', payment_details='M-Pesa Till 123456.')
        self.users = {}
        for role in (Membership.OWNER, Membership.CASHIER):
            user = User.objects.create_user(role, password='pw12345!', first_name=role.title())
            Membership.objects.create(user=user, shop=self.shop, role=role)
            self.users[role] = user
        category = Category.objects.create(shop=self.shop, name='Running')
        self.product = Product.objects.create(shop=self.shop, category=category, name='Adidas Ultraboost', base_price=18700)
        self.grey42 = ProductVariation.objects.create(product=self.product, option1='42', option2='Grey', sku='AU-42-GRE')
        self.black42 = ProductVariation.objects.create(product=self.product, option1='42', option2='Black', sku='AU-42-BLA',
                                                       stock_quantity=2)
        self.jane = Customer.objects.create(shop=self.shop, first_name='Jane', last_name='Smith', phone_number='+254722345678')
        with self.captureOnCommitCallbacks(execute=True):
            self.intent = services.create_blocked_purchase_intent(self.jane, self.product, self.grey42, Intent.SIZE_MISSING,
                                                                  recorded_by=self.users['owner'])
        self.conversation = Conversation.objects.create(shop=self.shop, customer=self.jane, unread_count=1,
                                                        last_inbound_at=timezone.now() - timedelta(minutes=20),
                                                        last_message_at=timezone.now() - timedelta(minutes=20))
        Message.objects.create(shop=self.shop, conversation=self.conversation, direction=Message.INBOUND,
                               channel=Message.WHATSAPP, body='Can I pay a deposit on M-Pesa?', status=Message.RECEIVED)
        self.url = f'/notifications/c/{self.conversation.pk}/'

    def login(self, role='owner'):
        self.client.login(username=role, password='pw12345!')

    def post(self, data):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.url, data)


class InboxTests(ChatTestCase):
    def test_needs_reply_and_sent_tabs(self):
        self.login()
        rows = self.client.get('/notifications/?show=needs_reply').context['conversations']
        self.assertEqual([c.pk for c in rows], [self.conversation.pk])
        self.assertEqual(rows[0].main_item.pk, self.intent.pk)
        self.conversation.unread_count = 0
        self.conversation.save()
        self.assertEqual(self.client.get('/notifications/?show=needs_reply').context['conversations'], [])
        self.assertEqual(self.client.get('/notifications/?show=sent').status_code, 200)

    def test_opening_the_chat_marks_it_read(self):
        self.login('cashier')
        response = self.client.get(self.url)
        self.assertContains(response, 'Can I pay a deposit on M-Pesa?')
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.unread_count, 0)

    def test_another_shops_conversation_is_not_found(self):
        other = Shop.objects.create(name='Elsewhere')
        stranger = Customer.objects.create(shop=other, first_name='X', last_name='Y', phone_number='+254700000999')
        theirs = Conversation.objects.create(shop=other, customer=stranger)
        self.login()
        self.assertEqual(self.client.get(f'/notifications/c/{theirs.pk}/').status_code, 404)


class ReplyTests(ChatTestCase):
    def test_reply_inside_the_window_is_sent(self):
        self.login('cashier')
        self.post({'action': 'reply', 'body': 'Yes! Send it to our till.'})
        sent = Message.objects.get(conversation=self.conversation, direction=Message.OUTBOUND, template_key='')
        self.assertEqual((sent.body, sent.channel), ('Yes! Send it to our till.', Message.WHATSAPP))
        self.assertIn(sent.status, Message.SUCCESS_STATUSES)

    def test_whatsapp_free_text_is_refused_after_24_hours(self):
        self.conversation.last_inbound_at = timezone.now() - timedelta(hours=25)
        self.conversation.save()
        self.login()
        response = self.client.get(self.url)
        self.assertFalse(response.context['can_write'])
        self.assertContains(response, 'Send check-in message')
        self.post({'action': 'reply', 'body': 'Hello?'})
        self.assertFalse(Message.objects.filter(conversation=self.conversation, body='Hello?').exists())
        self.post({'action': 'check_in', 'intent': self.intent.pk})
        self.assertTrue(Message.objects.filter(conversation=self.conversation, template_key='check_in').exists())

    def test_quick_reply_without_javascript_sends_payment_details(self):
        self.login()
        self.post({'action': 'quick:payment', 'intent': self.intent.pk})
        sent = Message.objects.filter(conversation=self.conversation, direction=Message.OUTBOUND).latest('created_at')
        self.assertIn('M-Pesa Till 123456. Balance KSh 18,700', sent.body)


class DealTests(ChatTestCase):
    def test_deposit_reserves_and_paid_in_full_recovers(self):
        self.login('cashier')
        self.post({'action': 'deposit', 'intent': self.intent.pk, 'amount': '5000', 'method': 'mpesa', 'reference': 'QK7H2L9'})
        self.intent.refresh_from_db()
        self.assertEqual((self.intent.status, self.intent.amount_paid), (Intent.RESERVED, 5000))
        self.post({'action': 'paid', 'intent': self.intent.pk, 'method': 'cash'})
        self.intent.refresh_from_db()
        self.assertEqual((self.intent.status, self.intent.balance), (Intent.RECOVERED, 0))

    def test_bad_amounts_are_refused(self):
        self.login()
        for amount in ('', 'lots', '0', '99999'):
            self.post({'action': 'deposit', 'intent': self.intent.pk, 'amount': amount})
        self.intent.refresh_from_db()
        self.assertEqual((self.intent.status, self.intent.amount_paid), (Intent.OPEN, 0))

    def test_declined_is_closed_and_never_revenue(self):
        self.login()
        self.post({'action': 'decline', 'intent': self.intent.pk, 'reason': 'Bought elsewhere'})
        self.intent.refresh_from_db()
        self.assertEqual((self.intent.status, self.intent.closed_reason), (Intent.DECLINED, 'Bought elsewhere'))
        self.assertEqual(self.client.get(self.url).context['deals'], [])

    def test_change_item_to_another_option(self):
        self.login()
        self.post({'action': 'change', 'intent': self.intent.pk, 'variation': self.black42.pk})
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.variation, self.black42)

    def test_someone_elses_item_cannot_be_touched(self):
        peter = Customer.objects.create(shop=self.shop, first_name='Peter', last_name='K', phone_number='+254755345678')
        theirs = services.create_blocked_purchase_intent(peter, self.product, self.grey42, Intent.SIZE_MISSING)
        self.login()
        self.post({'action': 'decline', 'intent': theirs.pk})
        theirs.refresh_from_db()
        self.assertEqual(theirs.status, Intent.OPEN)


class FloorTests(ChatTestCase):
    def test_bought_is_one_tap(self):
        self.login('cashier')
        self.client.post('/floor/', {'action': 'bought'})
        self.assertEqual(Visit.objects.filter(shop=self.shop, outcome=Visit.BOUGHT).count(), 1)

    def test_saving_returns_to_where_you_started(self):
        self.login('cashier')
        page = self.client.get('/floor/', HTTP_REFERER='http://testserver/intents/?show=all').content.decode()
        self.assertNotIn('How did this visit end', page)
        self.assertIn('name="back" value="/intents/?show=all"', page)
        response = self.client.post('/floor/', {'product': self.product.pk, 'reason': Intent.OUT_OF_STOCK,
                                                'phone': '0712000999', 'then': 'done', 'back': '/intents/?show=all'})
        self.assertRedirects(response, '/intents/?show=all', fetch_redirect_response=False)
        # Another site, or Log missed sale itself, is never a place to return to.
        for bad in ('https://evil.example/x', '/floor/'):
            response = self.client.post('/floor/', {'action': 'bought', 'back': bad})
            self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)

    def test_didnt_buy_adds_the_customer_and_the_missed_sale(self):
        self.login('cashier')
        response = self.client.post('/floor/', {'product': self.product.pk, 'variation': self.grey42.pk,
                                                'reason': Intent.SIZE_MISSING, 'phone': '0712 345 678',
                                                'name': 'Mary Achieng', 'within': '4', 'then': 'done'})
        self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)  # no "How did this visit end?"
        mary = Customer.objects.get(shop=self.shop, phone_number='+254712345678')
        intent = mary.intents.get()
        self.assertEqual((mary.first_name, mary.last_name), ('Mary', 'Achieng'))
        self.assertEqual((intent.variation, intent.needed_by, intent.consent_given),
                         (self.grey42, timezone.localdate() + timedelta(days=4), False))

    def test_known_phone_reuses_the_customer_and_another_item_reuses_the_visit(self):
        self.login()
        response = self.client.post('/floor/', {'product': self.product.pk, 'reason': Intent.OUT_OF_STOCK,
                                                'phone': '0722 345 678', 'consent': 'yes', 'then': 'another'})
        intent = self.jane.intents.order_by('-pk').first()
        self.assertIn(f'customer={self.jane.pk}', response['Location'])
        self.assertIn(f'visit={intent.visit_id}', response['Location'])
        self.client.post('/floor/', {'product': self.product.pk, 'reason': Intent.COLOUR_MISSING, 'phone': '0722345678',
                                     'visit': intent.visit_id, 'consent': 'yes', 'then': 'done'})
        latest = self.jane.intents.order_by('-pk').first()
        self.assertEqual(latest.visit_id, intent.visit_id)
        self.assertEqual(Customer.objects.filter(shop=self.shop, phone_number='+254722345678').count(), 1)

    def test_missing_answers_keep_what_was_typed(self):
        self.login()
        before = Intent.objects.count()
        response = self.client.post('/floor/', {'product': self.product.pk, 'reason': '', 'phone': 'abc', 'name': 'Ali'},
                                    follow=True)
        self.assertEqual(Intent.objects.count(), before)
        self.assertContains(response, "Choose why they didn")
        self.assertEqual(response.context['form']['name'], 'Ali')

    def test_another_shops_product_is_refused(self):
        other = Shop.objects.create(name='Elsewhere')
        theirs = Product.objects.create(shop=other, category=Category.objects.create(shop=other, name='C'),
                                        name='Bag', base_price=100)
        self.login()
        before = Intent.objects.count()
        self.client.post('/floor/', {'product': theirs.pk, 'reason': Intent.OUT_OF_STOCK, 'phone': '0712000111'})
        self.assertEqual(Intent.objects.count(), before)

    def test_customer_lookup(self):
        self.login('cashier')
        self.assertEqual(self.client.get('/floor/customer/?phone=0722345678').json()['name'], 'Jane Smith')
        self.assertFalse(self.client.get('/floor/customer/?phone=0700000000').json()['found'])

    def test_pages_load(self):
        self.login('cashier')
        for url in ['/floor/', f'/floor/?customer={self.jane.pk}', '/notifications/?q=jane', self.url]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
