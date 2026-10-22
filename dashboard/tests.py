from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import Membership, Shop, User
from customers.models import Customer
from dashboard import selectors
from dashboard.widgets import DEFAULTS, KEYS, layout_for
from intents import services
from intents.models import BlockedPurchaseIntent as Intent
from notifications.models import Conversation, Message
from products.models import Category, Product, ProductVariation


class HomeTestCase(TestCase):
    def setUp(self):
        self.shop = Shop.objects.create(name='Kimathi Street Store')
        self.users = {}
        for role in (Membership.OWNER, Membership.MANAGER, Membership.CASHIER):
            user = User.objects.create_user(role, password='pw12345!', first_name=role.title())
            Membership.objects.create(user=user, shop=self.shop, role=role)
            self.users[role] = user
        category = Category.objects.create(shop=self.shop, name='Running')
        self.product = Product.objects.create(shop=self.shop, category=category, name='Nike Air Zoom', base_price=12500)
        self.black42 = ProductVariation.objects.create(product=self.product, option1='42', option2='Black', sku='NIKE-42-BLK')
        self.n = 0
        self.all_time = {'start': None, 'end': None}

    def login(self, role):
        self.client.login(username=role, password='pw12345!')

    def customer(self, name):
        self.n += 1
        return Customer.objects.create(shop=self.shop, first_name=name, last_name='K', phone_number=f'+2547120000{self.n:02d}')

    def request(self, name, reason=Intent.SIZE_MISSING, **kwargs):
        with self.captureOnCommitCallbacks(execute=True):
            return services.create_blocked_purchase_intent(self.customer(name), self.product, self.black42, reason,
                                                           recorded_by=self.users['owner'], **kwargs)


class LayoutTests(HomeTestCase):
    def test_defaults_per_role(self):
        self.assertEqual(layout_for(self.shop, Membership.OWNER), KEYS)
        self.assertEqual(layout_for(self.shop, Membership.CASHIER), ['needs_you', 'key_numbers'])

    def test_saved_layout_drops_unknown_widgets(self):
        self.shop.home_layout = {'cashier': ['reasons', 'made_up', 'needs_you']}
        self.assertEqual(layout_for(self.shop, Membership.CASHIER), ['reasons', 'needs_you'])
        self.assertEqual(layout_for(self.shop, Membership.MANAGER), DEFAULTS[Membership.MANAGER])

    def test_cashier_home_shows_only_their_widgets(self):
        self.login('cashier')
        response = self.client.get('/dashboard/')
        self.assertContains(response, 'Needs you now')
        self.assertNotContains(response, 'Recovered per week')
        self.assertNotContains(response, 'Why people didn')

    def test_owner_home_shows_every_widget_and_any_period(self):
        self.login('owner')
        for query in ['', '?period=7d', '?period=custom&start_date=275760-04-25']:
            response = self.client.get('/dashboard/' + query)
            for title in ('Needs you now', 'Recovered per week', 'To order today', 'Walk-in conversion'):
                self.assertContains(response, title)


class HomeLayoutSettingsTests(HomeTestCase):
    url = '/settings/home-layout/'

    def test_only_the_owner_can_change_it(self):
        for role in ('manager', 'cashier'):
            self.login(role)
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(self.client.post(self.url, {'role': 'cashier', 'show': ['reasons']}).status_code, 403)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.home_layout, {})

    def test_save_move_and_reset(self):
        self.login('owner')
        self.client.post(self.url, {'role': 'cashier', 'order': KEYS, 'show': ['key_numbers', 'reasons']})
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.home_layout['cashier'], ['key_numbers', 'reasons'])

        self.client.post(self.url, {'role': 'cashier', 'order': ['key_numbers', 'reasons'], 'show': ['key_numbers', 'reasons'],
                                    'move': 'reasons:up'})
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.home_layout['cashier'], ['reasons', 'key_numbers'])

        self.client.post(self.url, {'role': 'cashier', 'action': 'reset'})
        self.shop.refresh_from_db()
        self.assertNotIn('cashier', self.shop.home_layout)

    def test_cashier_sees_the_saved_layout(self):
        self.shop.home_layout = {'cashier': ['reasons']}
        self.shop.save()
        self.login('cashier')
        response = self.client.get('/dashboard/')
        self.assertContains(response, 'Why people didn')
        self.assertNotContains(response, 'Needs you now')


class NeedsYouTests(HomeTestCase):
    def kinds(self):
        return [row['kind'] for row in selectors.needs_you(self.shop)]

    def test_nothing_to_do(self):
        self.assertEqual(self.kinds(), [])

    def test_unread_reply(self):
        intent = self.request('Jane')
        conversation = Conversation.objects.create(shop=self.shop, customer=intent.customer, unread_count=1,
                                                   last_inbound_at=timezone.now())
        Message.objects.create(shop=self.shop, conversation=conversation, direction=Message.INBOUND,
                               channel=Message.WHATSAPP, body='Can I pay a deposit?', status=Message.RECEIVED)
        rows = selectors.needs_you(self.shop)
        self.assertEqual(rows[0]['kind'], 'reply')
        self.assertIn('Can I pay a deposit?', rows[0]['sub'])

    def test_promise_due_and_nothing_ordered(self):
        self.request('Mary', needed_by=timezone.localdate() + timedelta(days=1))
        self.request('Peter', needed_by=timezone.localdate() + timedelta(days=20))
        promise = [r for r in selectors.needs_you(self.shop) if r['kind'] == 'promise']
        self.assertEqual(len(promise), 1)
        self.assertTrue(promise[0]['title'].startswith('1 promise due by'))

    def test_overdue_pickup(self):
        intent = self.request('Ali')
        services.reserve(intent, pickup_by=timezone.localdate() - timedelta(days=1))
        self.assertIn('pickup', self.kinds())

    def test_failed_message_points_to_fixing_the_number(self):
        intent = self.request('Robert')
        conversation = Conversation.objects.create(shop=self.shop, customer=intent.customer)
        Message.objects.create(shop=self.shop, conversation=conversation, intent=intent, direction=Message.OUTBOUND,
                               channel=Message.WHATSAPP, body='Back in stock', status=Message.FAILED,
                               error_detail='Not on WhatsApp')
        row = next(r for r in selectors.needs_you(self.shop) if r['kind'] == 'failed')
        self.assertEqual(row['action'], 'Fix number')
        self.assertIn('Not on WhatsApp', row['sub'])


class RecoveredTests(HomeTestCase):
    def test_only_paid_in_full_counts(self):
        paid = self.request('Jane')
        services.record_payment(paid, 12500, 'cash', actor=self.users['owner'])
        deposit = self.request('Mary')
        with self.captureOnCommitCallbacks(execute=True):
            services.record_payment(deposit, 2000, 'mpesa', actor=self.users['owner'])
        declined = self.request('Peter')
        services.decline(declined, 'Bought elsewhere')

        numbers = selectors.key_numbers(self.shop, self.all_time)
        self.assertEqual((numbers['recovered_money'], numbers['recovered_count']), (12500.0, 1))
        self.assertEqual((numbers['reserved'], numbers['deposits']), (1, 2000.0))
        self.assertEqual(sum(week['money'] for week in selectors.recovered_weekly(self.shop)), 12500.0)

    def test_waiting_demand_counts_customers_once(self):
        customer = self.customer('Jane')
        for _ in range(2):
            services.create_blocked_purchase_intent(customer, self.product, self.black42, Intent.SIZE_MISSING,
                                                    recorded_by=self.users['owner'])
        numbers = selectors.key_numbers(self.shop, self.all_time)
        self.assertEqual(numbers['waiting_customers'], 1)
        self.assertEqual(numbers['waiting_money'], 25000.0)

    def test_conversion_waits_for_enough_visits(self):
        self.request('Jane')
        services.record_bought_visit(self.shop)
        conversion = selectors.conversion(self.shop, self.all_time)
        self.assertEqual((conversion['total'], conversion['bought'], conversion['enough']), (2, 1, False))


class ReportsTests(HomeTestCase):
    def test_cashiers_cannot_open_reports_or_downloads(self):
        self.login('cashier')
        for url in ['/reports/', '/reports/csv/', '/reports/pdf/', '/reports/csv/recovered/', '/reports/csv/to-order/']:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_summary_downloads(self):
        paid = self.request('Jane')
        services.record_payment(paid, 12500, 'cash', actor=self.users['owner'])
        declined = self.request('Peter', reason=Intent.COLOUR_MISSING)
        services.decline(declined)
        self.request('Mary')
        self.login('manager')

        recovered = self.client.get('/reports/csv/recovered/?period=30d').content.decode()
        self.assertIn('Paid in full', recovered)
        self.assertIn(',1,12500.00', recovered)

        demand = self.client.get('/reports/csv/demand/').content.decode()
        self.assertIn('Nike Air Zoom,42 / Black,Size missing,2', demand)
        self.assertIn('Colour missing,1', demand)

        to_order = self.client.get('/reports/csv/to-order/').content.decode()
        self.assertIn('NIKE-42-BLK,1,1', to_order)
        self.assertEqual(self.client.get('/reports/csv/nonsense/').status_code, 404)

    def test_reports_page_shows_the_three_reports(self):
        self.login('owner')
        response = self.client.get('/reports/?period=month')
        for title in ('Recovered money by month', 'Missed sales by item and reason', 'To-order list'):
            self.assertContains(response, title)


class NavigationTests(HomeTestCase):
    def test_menu_names_and_role(self):
        self.login('owner')
        response = self.client.get('/dashboard/')
        self.assertContains(response, '>Waiting<')
        self.assertContains(response, '>Conversations<')
        self.assertContains(response, 'href="/reports/"')
        self.client.logout()
        self.login('cashier')
        self.assertNotContains(self.client.get('/dashboard/'), 'href="/reports/"')

    def test_status_filter_on_waiting(self):
        intent = self.request('Ali')
        services.reserve(intent)
        self.request('Mary')
        self.login('owner')
        response = self.client.get('/intents/?status=reserved')
        self.assertEqual(response.context['item_count'], 1)
        self.assertContains(response, '<option value="reserved" selected>')
