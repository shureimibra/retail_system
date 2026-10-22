from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from accounts.models import Membership, User, default_shop_id
from products.models import Category, Product, ProductVariation
from products.services import set_stock, adjust_stock
from customers.models import Customer
from customers.services import get_or_create_customer
from intents.models import BlockedPurchaseIntent
from intents.services import create_blocked_purchase_intent
from notifications.models import NotificationLog
from notifications.tasks import send_restock_notification_task
from analytics.selectors import get_dashboard_kpis, get_restock_recommendations


@override_settings(
    TWILIO_ACCOUNT_SID='',
    TWILIO_AUTH_TOKEN='',
    TWILIO_PHONE_NUMBER=''
)
class RPCMSTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='staff1', password='password123')
        self.category = Category.objects.create(name='Electronics')
        self.product = Product.objects.create(category=self.category, name='iPhone 15', base_price=1000.00)
        self.variation = ProductVariation.objects.create(product=self.product, option1='128GB', option2='Black', stock_quantity=0, sku='IPH15-128-BLK')
        self.customer = Customer.objects.create(first_name='Alex', last_name='Smith', phone_number='+254711222333')

    def _intent(self, customer=None, constraint_type='Out of stock', **kwargs):
        return create_blocked_purchase_intent(
            customer=customer or self.customer,
            product=self.product,
            variation=kwargs.pop('variation', self.variation),
            constraint_type=constraint_type,
            recorded_by=self.user,
            **kwargs
        )

    def test_service_create_blocked_purchase_intent(self):
        intent = self._intent(requested_quantity=2, notes='Urgent purchase')
        self.assertEqual(intent.customer, self.customer)
        self.assertEqual(intent.requested_quantity, 2)
        self.assertEqual(float(intent.estimated_value), 2000.00)
        self.assertEqual(intent.status, 'Pending')

    def test_get_or_create_customer_reuses_phone_and_updates_details(self):
        shop = self.product.shop
        cust = get_or_create_customer(shop, '+254700000000', 'Jane', 'Doe', 'jane@example.com')
        again = get_or_create_customer(shop, '0700 000 000', 'Jane Updated', '', None)
        self.assertEqual(again.id, cust.id)
        self.assertEqual(again.first_name, 'Jane Updated')
        self.assertEqual(again.last_name, 'Doe')
        self.assertEqual(again.email, 'jane@example.com')

    def test_restock_notifies_waiting_customer(self):
        intent = self._intent()
        with self.captureOnCommitCallbacks(execute=True):
            set_stock(self.variation.id, 5)
        notifications = NotificationLog.objects.filter(intent=intent)
        self.assertEqual(notifications.count(), 1)
        self.assertEqual(notifications.first().status, 'Sent')
        intent.refresh_from_db()
        self.assertEqual(intent.status, 'Customer Notified')

    def test_saving_a_variation_alone_sends_nothing(self):
        self._intent()
        self.variation.stock_quantity = 5
        self.variation.save()
        self.assertEqual(NotificationLog.objects.count(), 0)

    def test_stock_decrease_sends_nothing(self):
        self.variation.stock_quantity = 5
        self.variation.save()
        self._intent()
        with self.captureOnCommitCallbacks(execute=True):
            adjust_stock(self.variation.id, -1)
        self.assertEqual(NotificationLog.objects.count(), 0)

    def test_restock_does_not_resolve_price_or_budget_reasons(self):
        price = self._intent(constraint_type='Price too high')
        budget = self._intent(constraint_type='Budget mismatch')
        with self.captureOnCommitCallbacks(execute=True):
            set_stock(self.variation.id, 5)
        price.refresh_from_db()
        budget.refresh_from_db()
        self.assertEqual(price.status, 'Pending')
        self.assertEqual(budget.status, 'Pending')
        self.assertEqual(NotificationLog.objects.count(), 0)

    def test_restock_resolves_product_level_intents(self):
        intent = self._intent(variation=None)
        with self.captureOnCommitCallbacks(execute=True):
            set_stock(self.variation.id, 3)
        intent.refresh_from_db()
        self.assertEqual(intent.status, 'Customer Notified')

    def test_duplicate_notification_prevention(self):
        intent = self._intent()
        self.assertTrue(send_restock_notification_task(intent.id))
        self.assertFalse(send_restock_notification_task(intent.id))
        self.assertEqual(NotificationLog.objects.filter(intent=intent).count(), 1)

    def test_analytics_selectors(self):
        for i in range(4):
            cust = Customer.objects.create(first_name=f'Cust{i}', last_name='Test', phone_number=f'+25471100000{i}')
            self._intent(customer=cust)
        kpis = get_dashboard_kpis(self.product.shop)
        self.assertEqual(kpis['total_blocked_purchases'], 4)
        self.assertEqual(kpis['active_intents'], 4)
        self.assertEqual(kpis['estimated_lost_revenue'], 4000.00)
        recommendations = get_restock_recommendations(self.product.shop, threshold=4)
        self.assertEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0]['product_name'], 'iPhone 15')
        self.assertEqual(recommendations[0]['blocked_count'], 4)

    def test_notification_failed_status_invalid_phone(self):
        invalid_cust = Customer.objects.create(first_name='John', last_name='Doe', phone_number='12345')
        intent = self._intent(customer=invalid_cust)
        with self.captureOnCommitCallbacks(execute=True):
            set_stock(self.variation.id, 5)
        logs = NotificationLog.objects.filter(intent=intent)
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().status, 'Failed')
        intent.refresh_from_db()
        self.assertEqual(intent.status, 'Resolved')


class RecordMissedSaleFlowTests(TestCase):
    """
    Regression guard for the shop's core flow: a customer doesn't buy, and the
    owner records what they wanted (product, size, colour, reason, phone).
    This must keep working through every phase.
    """

    def setUp(self):
        self.owner = User.objects.create_user('owner', password='pw12345!')
        Membership.objects.create(user=self.owner, shop_id=default_shop_id(), role=Membership.OWNER)
        cat = Category.objects.create(name='Footwear')
        self.shoe = Product.objects.create(category=cat, name='Nike Air Zoom', description='Running', base_price=12500)
        self.variation = ProductVariation.objects.create(product=self.shoe, option1='42', option2='Black', stock_quantity=0, sku='NIKE-AZ-42-BLK')
        self.customer = Customer.objects.create(first_name='John', last_name='Doe', phone_number='+254712345678', email='john@example.com')
        self.client.login(username='owner', password='pw12345!')

    def test_owner_records_missed_sale_from_the_form(self):
        self.assertEqual(self.client.get(reverse('intents:create')).status_code, 200)
        response = self.client.post(reverse('intents:create'), {
            'customer': self.customer.id, 'product': self.shoe.id, 'variation': self.variation.id,
            'constraint_type': 'Size unavailable', 'requested_quantity': 1, 'estimated_value': '',
            'notes': 'Wanted 42 in black',
        })
        self.assertRedirects(response, reverse('intents:list'))
        intent = BlockedPurchaseIntent.objects.get()
        self.assertEqual((intent.variation.size, intent.variation.color), ('42', 'Black'))
        self.assertEqual(intent.constraint_type, 'Size unavailable')
        self.assertEqual(intent.customer.phone_number, '+254712345678')
        self.assertEqual(float(intent.estimated_value), 12500.00)
        self.assertEqual(intent.status, 'Pending')
        self.assertEqual(intent.recorded_by, self.owner)
        self.assertContains(self.client.get(reverse('intents:list')), 'Nike Air Zoom')

    def test_create_form_cannot_set_status_by_hand(self):
        self.client.post(reverse('intents:create'), {
            'customer': self.customer.id, 'product': self.shoe.id, 'variation': self.variation.id,
            'constraint_type': 'Size unavailable', 'requested_quantity': 1, 'status': 'Recovered',
        })
        self.assertEqual(BlockedPurchaseIntent.objects.get().status, 'Pending')

    def test_owner_records_missed_sale_from_the_quick_record_api(self):
        response = self.client.post('/api/intents/', {
            'customer': self.customer.id, 'product': self.shoe.id, 'variation': self.variation.id,
            'constraint_type': 'Color unavailable', 'requested_quantity': 1,
        }, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        intent = BlockedPurchaseIntent.objects.get()
        self.assertEqual(response.data['id'], intent.id)
        self.assertEqual(response.data['status'], 'Pending')

    def test_quick_restock_api_notifies_waiting_customer(self):
        self.client.post('/api/intents/', {
            'customer': self.customer.id, 'product': self.shoe.id, 'variation': self.variation.id,
            'constraint_type': 'Size unavailable', 'requested_quantity': 1,
        }, content_type='application/json')
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(f'/api/variations/{self.variation.id}/', {'stock_quantity': 10}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['stock_quantity'], 10)
        self.assertEqual(NotificationLog.objects.count(), 1)


class RPCMSAPITestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='admin', password='adminpassword')
        self.client.login(username='admin', password='adminpassword')
        self.category = Category.objects.create(name='Electronics')
        self.product = Product.objects.create(category=self.category, name='iPhone 15', base_price=1000.00)
        self.customer = Customer.objects.create(first_name='Alex', last_name='Smith', phone_number='+254711222333')

    def test_api_health_check(self):
        self.client.logout()
        response = self.client.get(reverse('api-health'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'status': 'ok'})

    def test_api_products_list(self):
        response = self.client.get(reverse('api-product-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_api_customers_list(self):
        response = self.client.get(reverse('api-customer-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_api_dashboard_stats(self):
        response = self.client.get(reverse('api-dashboard'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('kpis', response.data)
        self.assertIn('recommendations', response.data)
