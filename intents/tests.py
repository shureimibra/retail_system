from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from accounts.models import User
from products.models import Category, Product, ProductVariation
from customers.models import Customer
from intents.models import BlockedPurchaseIntent
from notifications.models import NotificationLog
from services.intent_service import create_blocked_purchase_intent, resolve_blocked_intents_for_variation
from services.customer_service import create_customer
from services.notification_service import send_resolution_notification
from analytics.selectors import get_dashboard_kpis, get_restock_recommendations

@override_settings(
    TWILIO_ACCOUNT_SID='',
    TWILIO_AUTH_TOKEN='',
    TWILIO_PHONE_NUMBER=''
)
class RPCMSTestCase(TestCase):
    def setUp(self):
        # Create standard User
        self.user = User.objects.create_user(username='staff1', password='password123')
        
        # Create Categories & Products
        self.category = Category.objects.create(name='Electronics')
        self.product = Product.objects.create(category=self.category, name='iPhone 15', base_price=1000.00)
        self.variation = ProductVariation.objects.create(product=self.product, size='128GB', color='Black', stock_quantity=0, sku='IPH15-128-BLK')
        
        # Create Customer
        self.customer = Customer.objects.create(first_name='Alex', last_name='Smith', phone_number='+254711222333')

    def test_service_create_blocked_purchase_intent(self):
        # Test creation of intent with auto-calculated estimated value
        intent = create_blocked_purchase_intent(
            customer=self.customer,
            product=self.product,
            variation=self.variation,
            constraint_type='Out of stock',
            requested_quantity=2,
            notes='Urgent purchase',
            recorded_by=self.user
        )
        
        self.assertEqual(intent.customer, self.customer)
        self.assertEqual(intent.product, self.product)
        self.assertEqual(intent.requested_quantity, 2)
        # 1000.00 * 2 = 2000.00
        self.assertEqual(float(intent.estimated_value), 2000.00)
        self.assertEqual(intent.status, 'Pending')

    def test_customer_creation_service(self):
        # Test create or get logic in customer_service
        cust = create_customer('Jane', 'Doe', '+254700000000', 'jane@example.com')
        self.assertEqual(cust.first_name, 'Jane')
        self.assertEqual(cust.phone_number, '+254700000000')

        # Create again with same phone, should update details
        cust_updated = create_customer('Jane Updated', 'Doe', '+254700000000', 'jane.up@example.com')
        self.assertEqual(cust_updated.id, cust.id)
        self.assertEqual(cust_updated.first_name, 'Jane Updated')

    def test_stock_trigger_signal_and_resolution(self):
        # Create a pending intent for the out of stock variation
        intent = create_blocked_purchase_intent(
            customer=self.customer,
            product=self.product,
            variation=self.variation,
            constraint_type='Out of stock',
            recorded_by=self.user
        )
        
        # Update stock quantity of variation from 0 to 5.
        # This will fire the on_variation_update signal, triggering inventory_service,
        # which will resolve the intent and trigger notification_service.
        self.variation.stock_quantity = 5
        self.variation.save() 
        
        # Check that NotificationLog was created
        notifications = NotificationLog.objects.filter(intent=intent)
        self.assertEqual(notifications.count(), 1)
        self.assertEqual(notifications.first().status, 'Sent')
        
        # Check that intent status was updated to "Customer Notified" by the notification service
        intent.refresh_from_db()
        self.assertEqual(intent.status, 'Customer Notified')

    def test_duplicate_notification_prevention(self):
        # Create a pending intent
        intent = create_blocked_purchase_intent(
            customer=self.customer,
            product=self.product,
            variation=self.variation,
            constraint_type='Out of stock',
            recorded_by=self.user
        )
        
        # Send first notification
        log1 = send_resolution_notification(intent)
        self.assertIsNotNone(log1)
        
        # Attempt to send second notification for the same intent
        log2 = send_resolution_notification(intent)
        self.assertIsNone(log2) # Duplicate check should prevent creation of new logs
        
        # Ensure only 1 log entry exists
        self.assertEqual(NotificationLog.objects.filter(intent=intent).count(), 1)

    def test_analytics_selectors(self):
        # Create blocked intents to trigger restock recommendation threshold (>=4)
        for i in range(4):
            cust = Customer.objects.create(first_name=f'Cust{i}', last_name='Test', phone_number=f'+25471100000{i}')
            create_blocked_purchase_intent(
                customer=cust,
                product=self.product,
                variation=self.variation,
                constraint_type='Out of stock',
                recorded_by=self.user
            )
            
        kpis = get_dashboard_kpis()
        self.assertEqual(kpis['total_blocked_purchases'], 4)
        self.assertEqual(kpis['active_intents'], 4)
        self.assertEqual(kpis['estimated_lost_revenue'], 4000.00)
        
        recommendations = get_restock_recommendations(threshold=4)
        self.assertEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0]['product_name'], 'iPhone 15')
        self.assertEqual(recommendations[0]['blocked_count'], 4)

    def test_notification_failed_status_invalid_phone(self):
        # Create customer with invalid phone format (no + prefix)
        invalid_cust = Customer.objects.create(
            first_name='John', last_name='Doe', phone_number='0711222333'
        )
        # Create pending intent
        intent = create_blocked_purchase_intent(
            customer=invalid_cust,
            product=self.product,
            variation=self.variation,
            constraint_type='Out of stock',
            recorded_by=self.user
        )
        
        # Trigger resolution (which sends notification)
        self.variation.stock_quantity = 5
        self.variation.save()
        
        # Verify that NotificationLog exists with status 'Failed'
        logs = NotificationLog.objects.filter(intent=intent)
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().status, 'Failed')
        
        # Since it failed, the intent status should remain 'Resolved' (not Customer Notified)
        intent.refresh_from_db()
        self.assertEqual(intent.status, 'Resolved')

    def test_notification_log_signal_updates_intent_status(self):
        # Create pending intent
        intent = create_blocked_purchase_intent(
            customer=self.customer,
            product=self.product,
            variation=self.variation,
            constraint_type='Out of stock',
            recorded_by=self.user
        )
        
        # Manually create a NotificationLog with status='Sent'
        NotificationLog.objects.create(
            intent=intent,
            message="Manual message",
            status='Sent'
        )
        
        # Verify that the intent status was automatically updated to 'Customer Notified' by the signal
        intent.refresh_from_db()
        self.assertEqual(intent.status, 'Customer Notified')



class RPCMSAPITestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='admin', password='adminpassword')
        self.client.login(username='admin', password='adminpassword')
        
        # Category, Product, Customer for API tests
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
