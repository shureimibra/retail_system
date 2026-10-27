from datetime import date, timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import Membership, Shop, User
from analytics.selectors import get_dashboard_kpis, get_recovery_funnel, get_to_order
from customers.models import Customer
from intents import services
from intents.automation import process_due
from intents.models import BlockedPurchaseIntent as Intent
from notifications import inbound
from notifications.models import Message
from products.models import Category, Product, ProductType, ProductVariation, StockHold
from products.services import change_price, receive_stock


class AutomationTestCase(TestCase):
    def setUp(self):
        self.shop = Shop.objects.create(name='Kimathi Street Store')
        self.owner = User.objects.create_user('owner', password='pw12345!')
        Membership.objects.create(user=self.owner, shop=self.shop, role=Membership.OWNER)
        category = Category.objects.create(shop=self.shop, name='Running')
        shoes = ProductType.objects.get(shop=self.shop, name='Shoes')
        self.product = Product.objects.create(shop=self.shop, category=category, product_type=shoes,
                                              name='Nike Air Zoom', base_price=12500)
        self.black42 = ProductVariation.objects.create(product=self.product, option1='42', option2='Black', sku='NIKE-42-BLK')
        self.n = 0

    def customer(self, name):
        self.n += 1
        return Customer.objects.create(shop=self.shop, first_name=name, last_name='K', phone_number=f'+2547120000{self.n:02d}')

    def request(self, name, reason=Intent.SIZE_MISSING, **kwargs):
        return services.create_blocked_purchase_intent(self.customer(name), self.product, self.black42, reason,
                                                       recorded_by=self.owner, **kwargs)

    def run_due(self, days):
        with self.captureOnCommitCallbacks(execute=True):
            return process_due(now=timezone.now() + timedelta(days=days))

    def restock(self, qty):
        with self.captureOnCommitCallbacks(execute=True):
            receive_stock(self.black42.id, qty, recorded_by=self.owner)

    def reload(self, obj):
        obj.refresh_from_db()
        return obj

    def reminders(self, intent):
        return list(intent.messages.filter(template_key__startswith='reminder').values_list('template_key', flat=True))


class FollowUpTests(AutomationTestCase):
    def test_reminders_on_days_2_4_7_then_expiry(self):
        jane = self.request('Jane')
        self.restock(1)
        self.assertEqual(self.reload(jane).status, Intent.NOTIFIED)
        self.assertEqual(self.run_due(1)['follow_ups_sent'], 0)
        self.run_due(2)
        self.run_due(2)  # same day again: nothing new
        self.assertEqual(self.reminders(jane), ['reminder_1'])
        self.run_due(4)
        self.run_due(7)
        self.assertEqual(self.reminders(jane), ['reminder_1', 'reminder_2', 'reminder_3'])
        self.assertEqual(self.reload(jane).status, Intent.NOTIFIED)
        summary = self.run_due(8)
        self.assertEqual(summary['expired_no_reply'], 1)
        self.assertEqual(self.reload(jane).status, Intent.EXPIRED)
        self.assertEqual(jane.holds.get().status, StockHold.RELEASED)

    def test_a_reply_stops_the_reminders(self):
        jane = self.request('Jane')
        self.restock(1)
        inbound.receive('whatsapp', jane.customer.phone_number, 'Yes please')
        self.run_due(2)
        self.run_due(7)
        self.assertEqual(self.reminders(jane), [])
        self.assertEqual(self.reload(jane).status, Intent.IN_CONVERSATION)

    def test_quiet_customer_without_deposit_gives_the_unit_to_the_next(self):
        jane, john = self.request('Jane'), self.request('John')
        self.restock(1)
        inbound.receive('whatsapp', jane.customer.phone_number, 'Yes please')
        self.run_due(9)  # the 8-day hold has run out and Jane paid nothing
        self.assertEqual(self.reload(jane).status, Intent.EXPIRED)
        self.assertEqual(self.reload(john).status, Intent.NOTIFIED)

    def test_deposit_keeps_the_unit_past_the_hold(self):
        jane = self.request('Jane')
        self.restock(1)
        inbound.receive('whatsapp', jane.customer.phone_number, 'Yes please')
        with self.captureOnCommitCallbacks(execute=True):
            services.record_payment(self.reload(jane), 2000, 'mpesa', pickup_by=timezone.localdate() + timedelta(days=12))
        self.run_due(9)
        self.assertEqual(self.reload(jane).status, Intent.RESERVED)

    def test_expired_customers_unit_goes_to_the_next_in_line(self):
        jane, john = self.request('Jane'), self.request('John')
        self.restock(1)
        self.assertEqual((self.reload(jane).status, self.reload(john).status), (Intent.NOTIFIED, Intent.OPEN))
        for day in (2, 4, 7, 8):
            self.run_due(day)
        self.assertEqual(self.reload(jane).status, Intent.EXPIRED)
        self.assertEqual(self.reload(john).status, Intent.NOTIFIED)
        self.assertEqual(john.holds.get().status, StockHold.ACTIVE)


class ExpiryTests(AutomationTestCase):
    def test_reservation_without_deposit_expires_after_pickup_date(self):
        jane = self.request('Jane')
        self.restock(1)
        services.reserve(self.reload(jane), pickup_by=timezone.localdate() + timedelta(days=2))
        self.run_due(2)
        self.assertEqual(self.reload(jane).status, Intent.RESERVED)
        self.run_due(3)
        self.assertEqual(self.reload(jane).status, Intent.EXPIRED)

    def test_reservation_with_deposit_is_left_for_staff(self):
        jane = self.request('Jane')
        self.restock(1)
        with self.captureOnCommitCallbacks(execute=True):
            services.record_payment(self.reload(jane), 2000, 'mpesa', pickup_by=timezone.localdate() + timedelta(days=1))
        self.run_due(5)
        self.run_due(6)
        self.assertEqual(self.reload(jane).status, Intent.RESERVED)
        self.assertEqual(jane.events.filter(kind='pickup_overdue').count(), 1)

    def test_long_waits_expire_after_30_days(self):
        jane = self.request('Jane')
        self.assertEqual(self.run_due(29)['expired_waiting'], 0)
        self.assertEqual(self.run_due(31)['expired_waiting'], 1)
        self.assertEqual(self.reload(jane).status, Intent.EXPIRED)

    def test_hold_for_unreachable_customer_goes_back(self):
        nobody = Customer.objects.create(shop=self.shop, first_name='X', last_name='Y', phone_number='12345')
        lost = services.create_blocked_purchase_intent(nobody, self.product, self.black42, Intent.SIZE_MISSING)
        john = self.request('John')
        self.restock(1)
        self.assertEqual(self.reload(lost).status, Intent.BACK_IN_STOCK)
        self.assertEqual(self.run_due(9)['holds_returned'], 1)
        self.assertEqual(self.reload(lost).status, Intent.OPEN)
        self.assertEqual(self.reload(john).status, Intent.NOTIFIED)

    def test_management_command(self):
        out = StringIO()
        call_command('process_due', stdout=out)
        self.assertIn('follow ups sent: 0', out.getvalue())


class PriceDropTests(AutomationTestCase):
    def test_price_cut_notifies_price_reasons_only(self):
        pricey = self.request('Mary', reason=Intent.PRICE_TOO_HIGH)
        budget = self.request('Ali', reason=Intent.OVER_BUDGET)
        size = self.request('Jane')
        with self.captureOnCommitCallbacks(execute=True):
            change_price(self.product, 9900, changed_by=self.owner)
        self.assertEqual([self.reload(i).status for i in (pricey, budget, size)],
                         [Intent.NOTIFIED, Intent.NOTIFIED, Intent.OPEN])
        message = pricey.messages.get(template_key='price_drop')
        self.assertIn('now KSh 9,900 (was KSh 12,500)', message.body)
        self.assertEqual(float(self.reload(pricey).estimated_value), 9900)

    def test_price_rise_notifies_nobody(self):
        pricey = self.request('Mary', reason=Intent.PRICE_TOO_HIGH)
        with self.captureOnCommitCallbacks(execute=True):
            change_price(self.product, 13000)
        self.assertEqual(self.reload(pricey).status, Intent.OPEN)
        self.assertFalse(Message.objects.exists())


class NumbersTests(AutomationTestCase):
    def test_to_order_list(self):
        for name in ('A', 'B', 'C'):
            self.request(name, needed_by=date(2026, 10, 30 if name != 'B' else 24))
        services.mark_ordered([Intent.objects.first()])
        receive_stock(self.black42.id, 1)
        row = get_to_order(self.shop)[0]
        self.assertEqual((row['product_name'], row['variation_label'], row['waiting']), ('Nike Air Zoom', '42 / Black', 2))
        self.assertEqual((row['to_order'], row['money_waiting'], row['needed_by']), (2, 25000.0, date(2026, 10, 24)))

    def test_to_order_api_is_per_shop(self):
        self.request('A')
        self.client.login(username='owner', password='pw12345!')
        self.assertEqual(len(self.client.get('/api/to-order/').json()), 1)
        self.assertEqual(len(self.client.get('/api/v1/to-order/').json()), 1)
        self.assertEqual(self.client.get('/api/v1/intents/').status_code, 200)

    def test_funnel_and_kpis_count_real_records(self):
        a, b, c = self.request('A'), self.request('B'), self.request('C')
        services.record_bought_visit(self.shop)
        self.restock(2)
        inbound.receive('sms', a.customer.phone_number, 'Yes')
        services.record_payment(self.reload(a), 12500, 'cash')
        services.decline(self.reload(b), 'Too late')
        funnel = {s['label']: (s['count'], s['percent']) for s in get_recovery_funnel(self.shop)}
        self.assertEqual(funnel, {'Missed sales logged': (3, 100), 'Customer told it was ready': (2, 67),
                                  'Customer replied': (1, 33), 'Paid in full': (1, 33)})
        kpis = get_dashboard_kpis(self.shop)
        self.assertEqual((kpis['recovery_rate'], kpis['walk_in_conversion']), (50.0, 25.0))
        self.assertEqual(kpis['recovered_revenue'], 12500)


class DesignNoteStoryTest(AutomationTestCase):
    """
    The Phase 1 'done when' story: capture, to-order, mark ordered, receive 4 of
    6, messages out, a reply, a deposit, paid; plus a decline, an expiry after
    day 7, and a price-too-high request notified on a price cut.
    """

    def test_story(self):
        names = ['Jane', 'John', 'Robert', 'Mary', 'Peter', 'Amina']
        waiting = [self.request(name, needed_by=date(2026, 10, 31)) for name in names]
        pricey = self.request('Ali', reason=Intent.PRICE_TOO_HIGH)

        self.assertEqual(get_to_order(self.shop)[0]['to_order'], 6)
        services.mark_ordered(waiting, expected_at=date(2026, 10, 30), actor=self.owner)
        self.restock(4)
        self.assertEqual([self.reload(i).status for i in waiting], [Intent.NOTIFIED] * 4 + [Intent.ON_ORDER] * 2)
        self.assertEqual(Message.objects.filter(template_key='restock_alert', status='delivered').count(), 4)

        jane, john, robert = waiting[0], waiting[1], waiting[2]
        inbound.receive('whatsapp', jane.customer.phone_number, 'Yes!! Can I pay a deposit on M-Pesa?')
        with self.captureOnCommitCallbacks(execute=True):
            services.record_payment(self.reload(jane), 5000, 'mpesa', reference='SJK4H7Q2LM')
        self.assertEqual(self.reload(jane).status, Intent.RESERVED)
        services.record_payment(jane, 7500, 'cash')
        self.assertEqual(self.reload(jane).status, Intent.RECOVERED)

        with self.captureOnCommitCallbacks(execute=True):
            services.decline(self.reload(john), 'Bought elsewhere')
        self.assertEqual(self.reload(waiting[4]).status, Intent.NOTIFIED)  # John's pair went to Peter

        for day in (2, 4, 7, 8):
            self.run_due(day)
        self.assertEqual(self.reload(robert).status, Intent.EXPIRED)
        self.assertEqual(len(self.reminders(robert)), 3)

        with self.captureOnCommitCallbacks(execute=True):
            change_price(self.product, 9900, changed_by=self.owner)
        self.assertEqual(self.reload(pricey).status, Intent.NOTIFIED)

        kpis = get_dashboard_kpis(self.shop)
        self.assertEqual((kpis['recovered_sales'], kpis['recovered_revenue']), (1, 12500))
        self.assertEqual(self.reload(self.black42).stock_quantity, 3)
