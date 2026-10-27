"""Phase 6: order suggestions, the Ask panel and smart quick replies. No AI service is involved."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import Membership, Shop, User
from analytics.selectors import get_to_order
from customers.models import Customer
from intents import services as intents
from intents.models import BlockedPurchaseIntent as Intent
from notifications import compose, inbound
from notifications.models import Conversation
from products.models import Category, Product, ProductType, ProductVariation
from products.services import receive_stock, record_till_sale
from . import ask


class AssistantCase(TestCase):
    def setUp(self):
        self.shop = Shop.objects.create(name='Kimathi Street Store', delivery_days=7)
        self.owner = User.objects.create_user('owner', password='pw12345!')
        Membership.objects.create(user=self.owner, shop=self.shop, role=Membership.OWNER)
        self.client.login(username='owner', password='pw12345!')
        shoes = ProductType.objects.get(shop=self.shop, name='Shoes')
        running = Category.objects.create(shop=self.shop, name='Running', product_type=shoes)
        self.boost = Product.objects.create(shop=self.shop, category=running, product_type=shoes,
                                            name='Adidas Ultraboost', base_price=18700)
        self.grey42 = ProductVariation.objects.create(product=self.boost, option1='42', option2='Grey', sku='AU-42-GRE')
        self.grey44 = ProductVariation.objects.create(product=self.boost, option1='44', option2='Grey', sku='AU-44-GRE')
        self.n = 0

    def customer(self, name='Jane'):
        self.n += 1
        return Customer.objects.create(shop=self.shop, first_name=name, phone_number=f'+2547110000{self.n:02d}')

    def waiting(self, variation, name='Jane', days_ago=0):
        intent = intents.create_blocked_purchase_intent(self.customer(name), self.boost, variation, Intent.SIZE_MISSING)
        if days_ago:
            Intent.objects.filter(pk=intent.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
        return intent

    def ask(self, question):
        return ask.answer(self.shop, question)


class SuggestionTests(AssistantCase):
    def row(self, variation):
        return next(r for r in get_to_order(self.shop) if r['variation_id'] == variation.pk)

    def test_waiting_customers_only_when_there_is_no_history(self):
        self.waiting(self.grey42)
        row = self.row(self.grey42)
        self.assertEqual((row['suggested'], row['why']), (1, '1 waiting → order 1'))

    def test_steady_demand_adds_the_customers_likely_to_ask_before_delivery(self):
        for i in range(14):  # 14 asked in 8 weeks, about 2 a week
            intent = self.waiting(self.grey42, f'C{i}', days_ago=7 + i * 3)
            Intent.objects.filter(pk=intent.pk).update(status=Intent.EXPIRED)
        self.waiting(self.grey42, 'Now')
        receive_stock(self.grey44.pk, 5)
        for _ in range(2):
            record_till_sale(self.grey44.pk, 1)
        row = self.row(self.grey42)
        self.assertEqual(row['suggested'], 3)  # 1 waiting + about 2 more in a week
        self.assertEqual(row['why'], '1 waiting + about 2 more in 7 days → order 3')

    def test_free_stock_and_orders_already_placed_are_taken_off(self):
        a = self.waiting(self.grey42, 'A')
        self.waiting(self.grey42, 'B')
        intents.mark_ordered([a])
        row = self.row(self.grey42)
        self.assertEqual(row['suggested'], 1)
        self.assertIn('1 already on order', row['why'])

    def test_to_order_page_and_whatsapp_list_use_the_suggestion(self):
        self.waiting(self.grey42)
        page = self.client.get('/intents/to-order/').content.decode()
        self.assertIn('Suggested order', page)
        self.assertIn('1 waiting → order 1', page)

    def test_delivery_time_is_a_setting(self):
        response = self.client.post('/settings/follow-ups/', {'follow_up_days': '2, 4, 7', 'expire_days_after_last_follow_up': 1,
                                                              'stock_hold_days': 8, 'reserve_pickup_days': 5, 'delivery_days': 14})
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.delivery_days, 14)
        response = self.client.post('/settings/follow-ups/', {'follow_up_days': '2', 'expire_days_after_last_follow_up': 1,
                                                              'stock_hold_days': 8, 'reserve_pickup_days': 5, 'delivery_days': 0})
        self.assertContains(response, 'between 1 and 90')


class AskTests(AssistantCase):
    def test_what_to_order(self):
        self.waiting(self.grey42)
        result = self.ask('What should I order this week?')
        self.assertIn('Adidas Ultraboost 42 / Grey: order 1', result['lines'][0]['text'])

    def test_who_is_waiting_for_a_size(self):
        self.waiting(self.grey42, 'Wanjiku')
        self.waiting(self.grey44, 'Otieno')
        result = self.ask("Who's waiting for size 42?")
        self.assertEqual(result['title'], '1 waiting for size/colour 42')
        self.assertTrue(result['lines'][0]['text'].startswith('Wanjiku: Adidas Ultraboost 42 / Grey'))
        result = self.ask('wanangoja adidas')
        self.assertEqual(len(result['lines']), 2)

    def test_recovered_and_money_waiting(self):
        intent = self.waiting(self.grey42)
        receive_stock(self.grey42.pk, 1)
        intent.refresh_from_db()
        intents.record_payment(intent, 18700, 'cash')
        self.waiting(self.grey44, 'Otieno')
        self.assertEqual(self.ask('How much did we recover this month?')['title'], 'KSh 18,700 recovered this month')
        self.assertEqual(self.ask('How much money is waiting?')['title'], 'KSh 18,700 waiting')

    def test_reasons_and_most_asked(self):
        self.waiting(self.grey42, 'A')
        self.waiting(self.grey42, 'B')
        self.assertEqual(self.ask("Why aren't people buying?")['lines'][0]['text'], 'Size missing')
        top = self.ask('Which items are asked for most?')['lines'][0]
        self.assertEqual((top['text'], top['sub']), ('Adidas Ultraboost 42 / Grey', 'asked 2 times'))

    def test_waiting_for_my_answer(self):
        intent = self.waiting(self.grey42, 'Wanjiku')
        with self.captureOnCommitCallbacks(execute=True):
            receive_stock(self.grey42.pk, 1)
            inbound.receive('whatsapp', intent.customer.phone_number, 'Can I pay half?')
        result = self.ask("Who's waiting for my answer?")
        self.assertEqual(result['lines'][0]['text'], 'Wanjiku (unread)')

    def test_reserved_and_stock(self):
        intent = self.waiting(self.grey42, 'Wanjiku')
        receive_stock(self.grey42.pk, 3)
        intent.refresh_from_db()
        intents.record_payment(intent, 5000, 'cash')
        self.assertIn('Wanjiku', self.ask("What's reserved?")['lines'][0]['text'])
        line = self.ask('How many Adidas 42 do we have?')['lines'][0]
        self.assertEqual(line['text'], 'Adidas Ultraboost 42 / Grey: 2 free')
        self.assertIn('1 put aside', line['sub'])

    def test_tell_me_about_a_customer(self):
        intent = self.waiting(self.grey42, 'Wanjiku')
        result = self.ask('Tell me about Wanjiku')
        self.assertIn(intent.customer.phone_number, result['title'])
        self.assertIn('Adidas Ultraboost 42 / Grey', result['lines'][0]['text'])
        self.assertIn('Wanjiku', self.ask(f'about {intent.customer.phone_number}')['title'])

    def test_how_are_we_doing_and_shop_link(self):
        self.assertEqual(self.ask('How are we doing this week?')['title'], 'This week')
        self.assertEqual(self.ask('What came in through the shop link?')['empty'],
                         'No requests through the shop link this month.')

    def test_unknown_questions_get_the_list_not_a_guess(self):
        result = self.ask('What is the weather in Nairobi?')
        self.assertFalse(result['understood'])
        self.assertEqual(len(result['examples']), 12)

    def test_panel_is_for_owners_and_managers(self):
        response = self.client.post('/dashboard/ask/', {'q': "Why aren't people buying?"})
        self.assertContains(response, 'ask-q')
        home = self.client.get('/dashboard/')
        self.assertContains(home, 'data-ask-open')
        self.assertContains(home, 'id="askPanel"')  # rendered on every page, not only when a message shows
        cashier = User.objects.create_user('cash', password='pw12345!')
        Membership.objects.create(user=cashier, shop=self.shop, role=Membership.CASHIER)
        self.client.login(username='cash', password='pw12345!')
        self.assertEqual(self.client.post('/dashboard/ask/', {'q': 'x'}).status_code, 403)
        self.assertNotContains(self.client.get('/dashboard/'), 'data-ask-open')

    def test_home_is_not_crowded(self):
        page = self.client.get('/dashboard/').content.decode()
        self.assertNotIn('ask-chip', page)  # examples load only when the panel opens


class QuickReplyTests(AssistantCase):
    def deal(self, message):
        intent = self.waiting(self.grey42, 'Wanjiku')
        with self.captureOnCommitCallbacks(execute=True):
            receive_stock(self.grey42.pk, 1)
            inbound.receive('whatsapp', intent.customer.phone_number, message)
        intent.refresh_from_db()
        return intent

    def test_words_point_to_the_right_reply(self):
        intent = self.deal('hi')
        cases = {'Naweza lipa nusu?': 'deposit', 'Can I pay half now': 'deposit', 'How do I pay?': 'payment',
                 'lipa na mpesa': 'payment', 'Nitakuja kesho': 'pickup', 'bei ni ngapi': 'price',
                 'Do you have another colour?': 'other', 'No, not now': 'thanks', 'sitaki': 'thanks',
                 'Sawa': 'payment', 'thanks!': ''}
        for text, key in cases.items():
            self.assertEqual(compose.suggest_quick_reply(text, intent), key, text)

    def test_suggested_reply_comes_first_and_is_filled_in(self):
        intent = self.deal('Can I pay half?')
        conversation = Conversation.objects.get(customer=intent.customer)
        page = self.client.get(f'/notifications/c/{conversation.pk}/').content.decode()
        self.assertLess(page.index('Suggested'), page.index('Send payment details'))
        self.assertIn("pay a deposit (for example KSh 9,300) and we&#x27;ll keep", page)

    def test_a_no_opens_close_as_declined(self):
        intent = self.deal('No thanks, sitaki')
        conversation = Conversation.objects.get(customer=intent.customer)
        page = self.client.get(f'/notifications/c/{conversation.pk}/').content.decode()
        self.assertIn('They seem to have said no', page)
        self.assertIn('Thank them', page)

    def test_no_suggestion_once_answered(self):
        intent = self.deal('Can I pay half?')
        conversation = Conversation.objects.get(customer=intent.customer)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f'/notifications/c/{conversation.pk}/', {'action': 'reply', 'body': 'Yes of course'})
        page = self.client.get(f'/notifications/c/{conversation.pk}/').content.decode()
        self.assertNotIn('suggested-tag', page)
