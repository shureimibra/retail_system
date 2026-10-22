from django.test import TestCase

from accounts.models import Membership, Shop, User
from customers.models import Customer
from intents.models import BlockedPurchaseIntent
from products.models import Category, Product, ProductVariation


def make_shop(name):
    shop = Shop.objects.create(name=name)
    category = Category.objects.create(shop=shop, name='Footwear')
    product = Product.objects.create(shop=shop, category=category, name=f'{name} sneaker', description='', base_price=5000)
    variation = ProductVariation.objects.create(product=product, option1='42', option2='Black', stock_quantity=0, sku=f'{name}-42-BLK')
    customer = Customer.objects.create(shop=shop, first_name='Cust', last_name=name, phone_number='+254712345678')
    return shop, product, variation, customer


def member(shop, username, role):
    user = User.objects.create_user(username, password='pw12345!')
    Membership.objects.create(user=user, shop=shop, role=role)
    return user


class NoShopTests(TestCase):
    def test_user_without_a_shop_sees_an_explanation(self):
        User.objects.create_user('lost', password='pw12345!')
        self.client.login(username='lost', password='pw12345!')
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 403)
        self.assertIn("isn't linked to a shop", response.content.decode())

    def test_superuser_without_membership_uses_the_first_shop(self):
        shop, *_ = make_shop('Alpha')
        User.objects.create_superuser('ops', password='pw12345!')
        self.client.login(username='ops', password='pw12345!')
        self.assertEqual(self.client.get('/dashboard/').status_code, 200)


class ShopIsolationTests(TestCase):
    def setUp(self):
        self.shop_a, self.product_a, self.variation_a, self.customer_a = make_shop('Alpha')
        self.shop_b, self.product_b, self.variation_b, self.customer_b = make_shop('Beta')
        member(self.shop_a, 'alice', Membership.OWNER)
        self.client.login(username='alice', password='pw12345!')

    def test_lists_only_show_own_shop(self):
        api = self.client.get('/api/customers/').json()
        self.assertEqual([c['id'] for c in api], [self.customer_a.id])
        self.assertEqual([p['id'] for p in self.client.get('/api/products/').json()], [self.product_a.id])
        page = self.client.get('/customers/').content.decode()
        self.assertIn('Alpha', page)
        self.assertNotIn('Beta', page)

    def test_cannot_open_another_shops_records(self):
        self.assertEqual(self.client.get(f'/api/customers/{self.customer_b.id}/').status_code, 404)
        self.assertEqual(self.client.get(f'/customers/update/{self.customer_b.id}/').status_code, 404)
        self.assertEqual(self.client.get(f'/customers/update/{self.customer_a.id}/').status_code, 200)
        self.assertEqual(self.client.patch(f'/api/variations/{self.variation_b.id}/', {'stock_quantity': 9}, content_type='application/json').status_code, 404)

    def test_cannot_record_a_missed_sale_with_another_shops_product(self):
        response = self.client.post('/api/intents/', {
            'customer': self.customer_a.id, 'product': self.product_b.id,
            'constraint_type': 'Out of stock', 'requested_quantity': 1,
        }, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BlockedPurchaseIntent.objects.exists())

    def test_new_records_belong_to_the_users_shop(self):
        self.client.post('/api/customers/', {'first_name': 'New', 'last_name': 'One', 'phone_number': '0722 000 111'}, content_type='application/json')
        self.assertEqual(Customer.objects.get(phone_number='+254722000111').shop, self.shop_a)

    def test_same_phone_can_exist_in_two_shops(self):
        self.assertEqual(self.customer_a.phone_number, self.customer_b.phone_number)


class CashierRoleTests(TestCase):
    def setUp(self):
        self.shop, self.product, self.variation, self.customer = make_shop('Alpha')
        member(self.shop, 'cashier', Membership.CASHIER)
        self.client.login(username='cashier', password='pw12345!')

    def test_cashier_records_missed_sales_and_customers(self):
        response = self.client.post('/api/intents/', {
            'customer': self.customer.id, 'product': self.product.id, 'variation': self.variation.id,
            'constraint_type': 'Size unavailable', 'requested_quantity': 1,
        }, content_type='application/json')
        self.assertEqual(response.status_code, 201)
        response = self.client.post('/api/customers/', {'first_name': 'A', 'last_name': 'B', 'phone_number': '0733 000 222'}, content_type='application/json')
        self.assertEqual(response.status_code, 201)

    def test_cashier_cannot_change_stock_or_prices(self):
        self.assertEqual(self.client.patch(f'/api/variations/{self.variation.id}/', {'stock_quantity': 5}, content_type='application/json').status_code, 403)
        self.assertEqual(self.client.patch(f'/api/products/{self.product.id}/', {'base_price': 1}, content_type='application/json').status_code, 403)
        self.assertEqual(self.client.get(f'/products/update/{self.product.id}/').status_code, 403)

    def test_cashier_cannot_delete(self):
        self.assertEqual(self.client.delete(f'/api/customers/{self.customer.id}/').status_code, 403)
        self.assertTrue(Customer.objects.filter(id=self.customer.id).exists())

    def test_cashier_quick_add_follows_the_shop_setting(self):
        payload = {'category': self.product.category_id, 'name': 'New bag', 'description': 'Leather tote', 'base_price': '2500'}
        self.assertEqual(self.client.post('/api/products/', payload, content_type='application/json').status_code, 201)
        self.shop.cashiers_can_add_products = False
        self.shop.save()
        payload['name'] = 'Another bag'
        self.assertEqual(self.client.post('/api/products/', payload, content_type='application/json').status_code, 403)

    def test_cashier_added_variation_starts_with_no_stock(self):
        response = self.client.post('/api/variations/', {
            'product': self.product.id, 'size': '43', 'color': 'Black', 'stock_quantity': 50, 'sku': 'ALPHA-43-BLK',
        }, content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ProductVariation.objects.get(sku='ALPHA-43-BLK').stock_quantity, 0)


class ManagerRoleTests(TestCase):
    def test_manager_changes_stock(self):
        shop, product, variation, _ = make_shop('Alpha')
        member(shop, 'manager', Membership.MANAGER)
        self.client.login(username='manager', password='pw12345!')
        response = self.client.patch(f'/api/variations/{variation.id}/', {'stock_quantity': 5}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        variation.refresh_from_db()
        self.assertEqual(variation.stock_quantity, 5)
