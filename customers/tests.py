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
        self.old_cust_resolved = Customer.objects.create(first_name='Old', last_name='Resolved', phone_number='+254700000003')
        Customer.objects.filter(id=self.old_cust_resolved.id).update(created_at=timezone.now() - timedelta(days=370))
        self.old_cust_resolved.refresh_from_db()
        
        self.intent1 = BlockedPurchaseIntent.objects.create(
            customer=self.old_cust_resolved, product=self.product,
            constraint_type='Out of stock', status='Resolved',
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
            constraint_type='Out of stock', status='Pending',
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
            constraint_type='Out of stock', status='Resolved',
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
