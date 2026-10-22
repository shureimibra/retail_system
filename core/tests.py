from django.conf import settings
from django.test import TestCase

from accounts.models import User


class OpsAdminTests(TestCase):
    def setUp(self):
        self.url = '/' + settings.ADMIN_URL

    def test_staff_who_are_not_superusers_cannot_use_admin(self):
        User.objects.create_user('cashier', password='pw12345!', is_staff=True)
        self.client.login(username='cashier', password='pw12345!')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response['Location'])

    def test_superuser_can_use_admin(self):
        User.objects.create_superuser('ops', password='pw12345!')
        self.client.login(username='ops', password='pw12345!')
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_old_admin_path_is_gone(self):
        self.assertEqual(self.client.get('/admin/').status_code, 404)


class CurrentPagesSmokeTests(TestCase):
    """Every page of the current UI still loads for a shop owner."""

    def test_pages_load(self):
        from accounts.models import Membership, default_shop_id
        from customers.models import Customer
        from intents.services import create_blocked_purchase_intent
        from products.models import Category, Product, ProductVariation

        owner = User.objects.create_user('owner', password='pw12345!')
        Membership.objects.create(user=owner, shop_id=default_shop_id(), role=Membership.OWNER)
        category = Category.objects.create(name='Footwear')
        product = Product.objects.create(category=category, name='Nike Air Zoom', description='Running', base_price=12500)
        variation = ProductVariation.objects.create(product=product, option1='42', option2='Black', stock_quantity=0, sku='NIKE-AZ-42-BLK')
        customer = Customer.objects.create(first_name='John', last_name='Doe', phone_number='+254712345678')
        intent = create_blocked_purchase_intent(customer, product, variation, 'Size unavailable', recorded_by=owner)
        self.client.login(username='owner', password='pw12345!')

        for url in ['/dashboard/', '/intents/', '/intents/create/', f'/intents/{intent.id}/update/',
                    '/products/', '/products/create/', f'/products/update/{product.id}/',
                    '/customers/', '/customers/create/', f'/customers/update/{customer.id}/',
                    '/notifications/', '/reports/csv/', '/reports/pdf/', '/api/dashboard/', '/api/analytics/', '/api/reports/']:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
