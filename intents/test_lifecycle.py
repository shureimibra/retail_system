from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import Membership, Shop, User
from analytics.selectors import get_dashboard_kpis
from customers.models import Customer
from intents import services
from intents.models import BlockedPurchaseIntent as Intent, Visit
from notifications.models import Message
from products.models import Category, Product, ProductType, ProductVariation, StockHold, StockMovement
from products.services import receive_stock


class LifecycleTestCase(TestCase):
    def setUp(self):
        self.shop = Shop.objects.create(name='Kimathi Street Store')
        self.owner = User.objects.create_user('owner', password='pw12345!')
        Membership.objects.create(user=self.owner, shop=self.shop, role=Membership.OWNER)
        category = Category.objects.create(shop=self.shop, name='Running')
        shoes = ProductType.objects.get(shop=self.shop, name='Shoes')
        self.product = Product.objects.create(shop=self.shop, category=category, product_type=shoes,
                                              name='Adidas Ultraboost', base_price=18700)
        self.grey42 = ProductVariation.objects.create(product=self.product, option1='42', option2='Grey', sku='ADI-UB-42-GRY')
        self.brown42 = ProductVariation.objects.create(product=self.product, option1='42', option2='Brown', sku='ADI-UB-42-BRN')
        self.jane = Customer.objects.create(shop=self.shop, first_name='Jane', last_name='Smith', phone_number='+254722345678')

    def intent(self, variation=None, reason=Intent.SIZE_MISSING, customer=None):
        return services.create_blocked_purchase_intent(customer or self.jane, self.product, variation or self.grey42,
                                                       reason, recorded_by=self.owner)

    def restock(self, variation, qty):
        with self.captureOnCommitCallbacks(execute=True):
            receive_stock(variation.id, qty, recorded_by=self.owner)

    def reload(self, obj):
        obj.refresh_from_db()
        return obj


class TransitionRuleTests(LifecycleTestCase):
    def test_new_request_is_open_with_a_visit_and_a_timeline(self):
        intent = self.intent()
        self.assertEqual(intent.status, Intent.OPEN)
        self.assertEqual(intent.visit.outcome, Visit.DIDNT_BUY)
        self.assertEqual(list(intent.events.values_list('kind', flat=True)), ['created'])

    def test_allowed_move_is_recorded(self):
        intent = self.intent()
        services.transition(intent, Intent.IN_CONVERSATION, actor=self.owner, note='Customer called')
        event = intent.events.last()
        self.assertEqual((event.from_status, event.to_status, event.note, event.actor), ('open', 'in_conversation', 'Customer called', self.owner))

    def test_disallowed_move_is_refused(self):
        intent = self.intent()
        services.transition(intent, Intent.RESERVED)
        with self.assertRaises(services.TransitionError):
            services.transition(intent, Intent.NOTIFIED)

    def test_closed_is_final(self):
        for final in (Intent.RECOVERED, Intent.DECLINED, Intent.EXPIRED):
            intent = self.intent()
            services.transition(intent, final)
            with self.assertRaises(services.TransitionError):
                services.transition(intent, Intent.OPEN)

    def test_every_status_has_rules(self):
        self.assertEqual(set(services.ALLOWED_TRANSITIONS), {code for code, _ in Intent.STATUS_CHOICES})

    def test_bought_visit_is_counted_without_a_request(self):
        visit = services.record_bought_visit(self.shop, recorded_by=self.owner)
        self.assertEqual(visit.outcome, Visit.BOUGHT)
        self.assertFalse(visit.intents.exists())


class OrderAndRestockTests(LifecycleTestCase):
    def test_mark_ordered(self):
        intent = self.intent()
        services.mark_ordered([intent], expected_at=date(2026, 10, 30), actor=self.owner)
        self.reload(intent)
        self.assertEqual((intent.status, intent.expected_at), (Intent.ON_ORDER, date(2026, 10, 30)))

    def test_restock_after_ordering_notifies(self):
        intent = self.intent()
        services.mark_ordered([intent])
        self.restock(self.grey42, 1)
        self.assertEqual(self.reload(intent).status, Intent.NOTIFIED)
        self.assertEqual(list(intent.events.values_list('to_status', flat=True)),
                         ['', 'on_order', 'back_in_stock', 'notified'])

    def test_failed_message_leaves_it_back_in_stock(self):
        bad = Customer.objects.create(shop=self.shop, first_name='X', last_name='Y', phone_number='12345')
        intent = self.intent(customer=bad)
        self.restock(self.grey42, 1)
        self.assertEqual(self.reload(intent).status, Intent.BACK_IN_STOCK)
        self.assertEqual(Message.objects.filter(direction='out').get().status, 'skipped')


class PaymentTests(LifecycleTestCase):
    def setUp(self):
        super().setUp()
        self.request = self.intent()
        self.restock(self.grey42, 1)
        self.reload(self.request)

    def test_deposit_reserves_and_keeps_the_unit(self):
        services.record_payment(self.request, 5000, 'mpesa', reference='SJK4H7Q2LM', actor=self.owner)
        self.reload(self.request)
        self.assertEqual(self.request.status, Intent.RESERVED)
        self.assertEqual(self.request.pickup_by, timezone.localdate() + timedelta(days=5))
        self.assertEqual((self.request.amount_paid, self.request.balance), (5000, 13700))
        hold = self.request.holds.get()
        self.assertEqual(hold.status, StockHold.ACTIVE)
        self.assertGreaterEqual(hold.expires_at.date(), self.request.pickup_by)

    def test_paid_in_full_is_recovered_and_the_unit_is_sold(self):
        services.record_payment(self.request, 5000, 'mpesa', actor=self.owner)
        services.record_payment(self.request, 13700, 'cash', actor=self.owner)
        self.reload(self.request)
        self.assertEqual(self.request.status, Intent.RECOVERED)
        self.assertEqual(self.reload(self.grey42).stock_quantity, 0)
        self.assertEqual(self.request.holds.get().status, StockHold.SOLD)
        self.assertEqual(StockMovement.objects.filter(kind=StockMovement.SOLD).get().quantity_change, -1)

    def test_payment_rules(self):
        with self.assertRaises(ValueError):
            services.record_payment(self.request, 0, 'cash')
        with self.assertRaises(ValueError):
            services.record_payment(self.request, 18701, 'cash')
        services.decline(self.request, 'Bought elsewhere')
        with self.assertRaises(services.TransitionError):
            services.record_payment(self.request, 100, 'cash')

    def test_decline_releases_the_unit(self):
        services.decline(self.request, 'Bought elsewhere', actor=self.owner)
        self.reload(self.request)
        self.assertEqual((self.request.status, self.request.closed_reason), (Intent.DECLINED, 'Bought elsewhere'))
        self.assertEqual(self.request.holds.get().status, StockHold.RELEASED)
        self.assertEqual(self.reload(self.grey42).available_quantity, 1)

    def test_only_recovered_counts_as_revenue(self):
        services.record_payment(self.request, 5000, 'mpesa')
        self.assertEqual(get_dashboard_kpis(self.shop)['recovered_revenue'], 0)
        services.record_payment(self.request, 13700, 'mpesa')
        self.assertEqual(get_dashboard_kpis(self.shop)['recovered_revenue'], 18700)


class ChangeItemTests(LifecycleTestCase):
    def test_change_to_an_item_in_stock_moves_the_hold(self):
        intent = self.intent()
        self.restock(self.grey42, 1)
        receive_stock(self.brown42.id, 2)
        services.transition(self.reload(intent), Intent.IN_CONVERSATION)
        services.change_item(intent, self.brown42, actor=self.owner)
        self.reload(intent)
        self.assertEqual((intent.variation, intent.status), (self.brown42, Intent.IN_CONVERSATION))
        self.assertEqual(intent.holds.get(status=StockHold.ACTIVE).variation, self.brown42)
        self.assertEqual(self.reload(self.grey42).available_quantity, 1)
        self.assertEqual(intent.events.filter(kind='item_changed').get().data['new'], 'Adidas Ultraboost 42 / Brown')

    def test_change_to_an_item_not_in_stock_goes_back_to_open(self):
        intent = self.intent()
        self.restock(self.grey42, 1)
        services.change_item(self.reload(intent), self.brown42, actor=self.owner)
        self.assertEqual(self.reload(intent).status, Intent.OPEN)
        self.assertFalse(intent.holds.filter(status=StockHold.ACTIVE).exists())


class StoryTests(LifecycleTestCase):
    """The design note's story, as far as 1c goes (replies arrive in 1d)."""

    def test_six_waiting_four_arrive_one_pays(self):
        customers = [Customer.objects.create(shop=self.shop, first_name=f'C{i}', last_name='X',
                                             phone_number=f'+2547110000{i:02d}') for i in range(6)]
        requests = [self.intent(customer=c) for c in customers]
        services.mark_ordered(requests, expected_at=date(2026, 10, 30), actor=self.owner)
        self.restock(self.grey42, 4)
        statuses = [self.reload(r).status for r in requests]
        self.assertEqual(statuses, [Intent.NOTIFIED] * 4 + [Intent.ON_ORDER] * 2)
        self.assertEqual(Message.objects.filter(direction='out').count(), 4)

        first = requests[0]
        services.transition(first, Intent.IN_CONVERSATION, note='Wants to pay a deposit')
        services.record_payment(first, 5000, 'mpesa', reference='SJK4H7Q2LM')
        services.record_payment(self.reload(first), 13700, 'cash')
        services.decline(self.reload(requests[1]), 'Bought elsewhere')
        self.assertEqual(self.reload(first).status, Intent.RECOVERED)
        self.assertEqual(self.reload(self.grey42).stock_quantity, 3)
        self.assertEqual(self.grey42.available_quantity, 1)

        kpis = get_dashboard_kpis(self.shop)
        self.assertEqual((kpis['recovered_sales'], kpis['recovered_revenue']), (1, 18700))


class LifecycleApiTests(LifecycleTestCase):
    def setUp(self):
        super().setUp()
        self.request = self.intent()
        self.client.login(username='owner', password='pw12345!')
        self.url = f'/api/intents/{self.request.id}/'

    def post(self, path, data):
        return self.client.post(self.url + path, data, content_type='application/json')

    def test_status_cannot_be_written_directly(self):
        self.client.patch(self.url, {'status': 'recovered'}, content_type='application/json')
        self.assertEqual(self.reload(self.request).status, Intent.OPEN)

    def test_transition_action(self):
        response = self.post('transition/', {'status': 'in_conversation', 'note': 'Called back'})
        self.assertEqual((response.status_code, response.data['status_label']), (200, 'In conversation'))
        self.assertEqual(self.post('transition/', {'status': 'notified'}).status_code, 400)

    def test_payments_action(self):
        response = self.post('payments/', {'amount': '5000', 'method': 'mpesa', 'reference': 'SJK4H7Q2LM'})
        self.assertEqual((response.data['status'], response.data['balance']), ('reserved', 13700))
        self.assertEqual(self.post('payments/', {'amount': '999999', 'method': 'cash'}).status_code, 400)
        response = self.post('payments/', {'amount': '13700', 'method': 'cash'})
        self.assertEqual(response.data['status'], 'recovered')
        timeline = self.client.get(self.url + 'timeline/').json()
        self.assertEqual(len(timeline['payments']), 2)
        self.assertIn('recovered', [e['to_status'] for e in timeline['events']])

    def test_change_item_action(self):
        response = self.post('change-item/', {'variation': self.brown42.id})
        self.assertEqual(response.data['variation'], self.brown42.id)
        self.assertEqual(self.post('change-item/', {'variation': 999999}).status_code, 400)

    def test_mark_ordered_is_for_managers(self):
        response = self.post('mark-ordered/', {'expected_at': '2026-10-30'})
        self.assertEqual((response.status_code, response.data['status']), (200, 'on_order'))
        cashier = User.objects.create_user('cashier', password='pw12345!')
        Membership.objects.create(user=cashier, shop=self.shop, role=Membership.CASHIER)
        self.client.login(username='cashier', password='pw12345!')
        other = self.intent()
        r = self.client.post(f'/api/intents/{other.id}/mark-ordered/', {}, content_type='application/json')
        self.assertEqual(r.status_code, 403)

    def test_record_bought_visit(self):
        response = self.client.post('/api/visits/bought/')
        self.assertEqual((response.status_code, response.data['outcome']), (201, 'bought'))
        self.assertEqual(Visit.objects.filter(shop=self.shop, outcome=Visit.BOUGHT).count(), 1)


class EditPageTests(LifecycleTestCase):
    def test_edit_page_offers_only_allowed_statuses_and_records_the_change(self):
        intent = self.intent()
        services.transition(intent, Intent.RESERVED)
        self.client.login(username='owner', password='pw12345!')
        page = self.client.get(f'/intents/{intent.id}/update/')
        offered = [value for value, _ in page.context['form'].fields['status'].choices]
        self.assertEqual(set(offered), {'reserved', 'in_conversation', 'recovered', 'declined', 'expired'})
        self.client.post(f'/intents/{intent.id}/update/', {
            'customer': self.jane.id, 'product': self.product.id, 'variation': self.grey42.id,
            'constraint_type': 'size_missing', 'requested_quantity': 1, 'estimated_value': '18700',
            'status': 'declined', 'notes': ''})
        self.reload(intent)
        self.assertEqual(intent.status, Intent.DECLINED)
        self.assertEqual(intent.events.last().note, 'Changed on the edit page')
