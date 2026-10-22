from django.test import TestCase
from django.core.management import call_command
from django.utils import timezone
from datetime import timedelta
from customers.models import Customer
from products.models import Category, Product
from intents.models import BlockedPurchaseIntent
from accounts.models import User

class CustomerCleanupTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='staff2', password='password123')
        self.category = Category.objects.create(name='Apparel')
        self.product = Product.objects.create(category=self.category, name='Jeans', base_price=50.00)

        # Create customers
        # 1. Old customer with no intents (should be deleted)
        self.old_cust_no_intents = Customer.objects.create(first_name='Old', last_name='NoIntents', phone_number='+254700000001')
        Customer.objects.filter(id=self.old_cust_no_intents.id).update(created_at=timezone.now() - timedelta(days=370))
        self.old_cust_no_intents.refresh_from_db()

        # 2. New customer with no intents (should NOT be deleted)
        self.new_cust_no_intents = Customer.objects.create(first_name='New', last_name='NoIntents', phone_number='+254700000002')

        # 3. Old customer with old resolved intents (should be deleted)
        self.old_cust_resolved = Customer.objects.create(first_name='Old', last_name='back_in_stock', phone_number='+254700000003')
        Customer.objects.filter(id=self.old_cust_resolved.id).update(created_at=timezone.now() - timedelta(days=370))
        self.old_cust_resolved.refresh_from_db()
        
        self.intent1 = BlockedPurchaseIntent.objects.create(
            customer=self.old_cust_resolved, product=self.product,
            constraint_type='out_of_stock', status='declined',
            requested_quantity=1, estimated_value=50.00, recorded_by=self.user
        )
        BlockedPurchaseIntent.objects.filter(id=self.intent1.id).update(
            created_at=timezone.now() - timedelta(days=370),
            updated_at=timezone.now() - timedelta(days=370)
        )

        # 4. Old customer with active intents (should NOT be deleted)
        self.old_cust_active = Customer.objects.create(first_name='Old', last_name='Active', phone_number='+254700000004')
        Customer.objects.filter(id=self.old_cust_active.id).update(created_at=timezone.now() - timedelta(days=370))
        self.old_cust_active.refresh_from_db()
        
        self.intent2 = BlockedPurchaseIntent.objects.create(
            customer=self.old_cust_active, product=self.product,
            constraint_type='out_of_stock', status='open',
            requested_quantity=1, estimated_value=50.00, recorded_by=self.user
        )
        BlockedPurchaseIntent.objects.filter(id=self.intent2.id).update(
            created_at=timezone.now() - timedelta(days=370),
            updated_at=timezone.now() - timedelta(days=370)
        )

        # 5. Old customer with recently updated resolved intents (should NOT be deleted)
        self.old_cust_recent_resolved = Customer.objects.create(first_name='Old', last_name='RecentResolved', phone_number='+254700000005')
        Customer.objects.filter(id=self.old_cust_recent_resolved.id).update(created_at=timezone.now() - timedelta(days=370))
        self.old_cust_recent_resolved.refresh_from_db()
        
        self.intent3 = BlockedPurchaseIntent.objects.create(
            customer=self.old_cust_recent_resolved, product=self.product,
            constraint_type='out_of_stock', status='declined',
            requested_quantity=1, estimated_value=50.00, recorded_by=self.user
        )
        BlockedPurchaseIntent.objects.filter(id=self.intent3.id).update(
            created_at=timezone.now() - timedelta(days=370),
            updated_at=timezone.now() - timedelta(days=10)
        )

    def test_cleanup_command(self):
        call_command('cleanup_old_customers')
        self.assertFalse(Customer.objects.filter(id=self.old_cust_no_intents.id).exists())
        self.assertFalse(Customer.objects.filter(id=self.old_cust_resolved.id).exists())
        self.assertTrue(Customer.objects.filter(id=self.new_cust_no_intents.id).exists())
        self.assertTrue(Customer.objects.filter(id=self.old_cust_active.id).exists())
        self.assertTrue(Customer.objects.filter(id=self.old_cust_recent_resolved.id).exists())


class PhoneNumberTests(TestCase):
    def test_local_formats_are_saved_as_one_international_number(self):
        for raw in ('0712 345 678', '+254 712 345 678', '254712345678', '0712-345-678'):
            customer = Customer(first_name='A', last_name='B', phone_number=raw)
            customer.save()
            self.assertEqual(customer.phone_number, '+254712345678', raw)
            customer.delete()

    def test_form_rejects_unreadable_number(self):
        from customers.forms import CustomerForm
        form = CustomerForm(data={'first_name': 'A', 'last_name': 'B', 'phone_number': '12345'})
        self.assertFalse(form.is_valid())
        self.assertIn('phone_number', form.errors)

    def test_form_rejects_same_number_in_another_format(self):
        from customers.forms import CustomerForm
        Customer.objects.create(first_name='A', last_name='B', phone_number='+254712345678')
        form = CustomerForm(data={'first_name': 'C', 'last_name': 'D', 'phone_number': '0712 345 678'})
        self.assertFalse(form.is_valid())
        self.assertIn('phone_number', form.errors)

    def test_api_normalizes_and_rejects_duplicates(self):
        User.objects.create_superuser('ops', password='pw12345!')
        self.client.login(username='ops', password='pw12345!')
        r = self.client.post('/api/customers/', {'first_name': 'A', 'last_name': 'B', 'phone_number': '0712 345 678'}, content_type='application/json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['phone_number'], '+254712345678')
        r = self.client.post('/api/customers/', {'first_name': 'C', 'last_name': 'D', 'phone_number': '254712345678'}, content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_reply_matches_customer_exactly_not_by_partial_number(self):
        from notifications.models import InboundSMSLog
        jane = Customer.objects.create(first_name='Jane', last_name='S', phone_number='+254712345678')
        Customer.objects.create(first_name='Other', last_name='X', phone_number='+254712345679')
        self.client.post('/notifications/webhook/', {'From': 'whatsapp:0712345678', 'To': '+1', 'Body': 'Yes'})
        self.client.post('/notifications/webhook/', {'From': '+2547123456', 'To': '+1', 'Body': 'partial'})
        self.assertEqual(InboundSMSLog.objects.get(body='Yes').customer, jane)
        self.assertIsNone(InboundSMSLog.objects.get(body='partial').customer)
