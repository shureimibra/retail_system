from django.test import TestCase, override_settings
from unittest.mock import patch, MagicMock
from customers.models import Customer
from products.models import Category, Product, ProductVariation
from intents.models import BlockedPurchaseIntent
from notifications.models import NotificationLog
from notifications.tasks import send_restock_notification_task

class RestockNotificationTaskTestCase(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Electronics")
        self.product = Product.objects.create(
            category=self.category,
            name="Laptop",
            description="A high-end laptop",
            base_price=1000.00
        )
        self.variation = ProductVariation.objects.create(
            product=self.product,
            option1="15-inch",
            option2="Silver",
            stock_quantity=0,
            sku="LAPTOP-SLV-15"
        )
        self.customer = Customer.objects.create(
            first_name="Alice",
            last_name="Smith",
            email="alice@example.com",
            phone_number="+1234567890"
        )
        self.intent = BlockedPurchaseIntent.objects.create(
            customer=self.customer,
            product=self.product,
            variation=self.variation,
            status='open'
        )

    @override_settings(
        TWILIO_ACCOUNT_SID='',
        TWILIO_AUTH_TOKEN='',
        TWILIO_PHONE_NUMBER=''
    )
    def test_send_sms_simulation_fallback(self):
        """
        When Twilio settings are missing, the task should fall back to simulation mode.
        """
        success = send_restock_notification_task(self.intent.id)
        self.assertTrue(success)
        
        # Verify database record
        log = NotificationLog.objects.filter(intent=self.intent).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'Sent')
        self.assertIn("Hello Alice, the Laptop 15-inch / Silver you requested is now available.", log.message)
        
        # Verify status update
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, 'notified')

    @override_settings(
        TWILIO_ACCOUNT_SID='ACtesting',
        TWILIO_AUTH_TOKEN='test_token',
        TWILIO_PHONE_NUMBER='+15555555555'
    )
    @patch('notifications.tasks.Client')
    def test_send_sms_with_twilio_success(self, mock_twilio_client):
        """
        When Twilio settings are configured, the task should dispatch using the Twilio client.
        """
        # Set up mock client
        mock_instance = MagicMock()
        mock_twilio_client.return_value = mock_instance
        
        success = send_restock_notification_task(self.intent.id)
        self.assertTrue(success)
        
        # Check client was instantiated with correct keys
        mock_twilio_client.assert_called_once_with('ACtesting', 'test_token')
        
        # Check messages.create was called
        mock_instance.messages.create.assert_called_once_with(
            body="Hello Alice, the Laptop 15-inch / Silver you requested is now available. Reply STOP to opt out.",
            from_="whatsapp:+15555555555",
            to="whatsapp:+1234567890"
        )
        
        # Check DB log
        log = NotificationLog.objects.filter(intent=self.intent).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'Sent')

    @override_settings(
        TWILIO_ACCOUNT_SID='ACtesting',
        TWILIO_AUTH_TOKEN='test_token',
        TWILIO_PHONE_NUMBER='+15555555555'
    )
    @patch('notifications.tasks.Client')
    def test_send_sms_with_twilio_failure(self, mock_twilio_client):
        """
        When Twilio client raises an exception, the notification status is set to Failed.
        """
        # Set up mock client to raise exception
        mock_instance = MagicMock()
        mock_instance.messages.create.side_effect = Exception("Twilio API Error")
        mock_twilio_client.return_value = mock_instance
        
        success = send_restock_notification_task(self.intent.id)
        self.assertFalse(success)
        
        # Check DB log
        log = NotificationLog.objects.filter(intent=self.intent).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'Failed')


from notifications.models import InboundSMSLog
from django.urls import reverse

class TwilioWebhookTestCase(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            first_name="Bob",
            last_name="Jones",
            email="bob@example.com",
            phone_number="+15551234567"
        )

    def test_webhook_received_and_logged(self):
        """
        Verify that a POST request from Twilio is logged in the database and linked to the customer.
        """
        url = reverse('notifications:webhook')
        payload = {
            'From': '+15551234567',
            'To': '+15557654321',
            'Body': 'Yes, please restock size 42 Black'
        }
        
        response = self.client.post(url, data=payload)
        
        # Verify response status and XML format
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/xml')
        self.assertIn("Thank you for contacting Retail RMS", response.content.decode())
        
        # Verify db entry
        log = InboundSMSLog.objects.filter(from_number='+15551234567').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.body, 'Yes, please restock size 42 Black')
        self.assertEqual(log.to_number, '+15557654321')
        self.assertEqual(log.customer, self.customer)

    def test_webhook_received_unknown_contact(self):
        """
        Verify that messages from unknown numbers are still logged but customer is set to None.
        """
        url = reverse('notifications:webhook')
        payload = {
            'From': '+19999999999',
            'To': '+15557654321',
            'Body': 'Unknown sender text'
        }
        
        response = self.client.post(url, data=payload)
        self.assertEqual(response.status_code, 200)
        
        log = InboundSMSLog.objects.filter(from_number='+19999999999').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.body, 'Unknown sender text')
        self.assertIsNone(log.customer)

