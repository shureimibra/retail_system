import shutil
import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from accounts.models import Membership, Shop, User
from customers.models import Customer
from intents.services import create_blocked_purchase_intent
from notifications.models import NotificationLog
from products.models import Category, PriceChange, Product, ProductType, ProductVariation, StockHold, StockMovement
from products.services import change_price, receive_stock, set_stock


class CatalogTestCase(TestCase):
    def setUp(self):
        self.shop = Shop.objects.create(name='Kimathi Street Store')
        self.owner = User.objects.create_user('owner', password='pw12345!')
        Membership.objects.create(user=self.owner, shop=self.shop, role=Membership.OWNER)
        self.shoes = ProductType.objects.get(shop=self.shop, name='Shoes')
        category = Category.objects.create(shop=self.shop, name='Running')
        self.product = Product.objects.create(shop=self.shop, category=category, product_type=self.shoes,
                                              name='Nike Air Zoom', base_price=12500)
        self.variation = ProductVariation.objects.create(product=self.product, option1='42', option2='Black', sku='NIKE-AZ-42-BLK')

    def customer(self, n):
        return Customer.objects.create(shop=self.shop, first_name=f'C{n}', last_name='X', phone_number=f'+25471200000{n}')

    def waiting(self, n, constraint_type='Size unavailable', variation='default'):
        return create_blocked_purchase_intent(self.customer(n), self.product,
                                              self.variation if variation == 'default' else variation,
                                              constraint_type, recorded_by=self.owner)


class ProductTypeTests(CatalogTestCase):
    def test_new_shop_gets_fashion_types(self):
        self.assertEqual(list(ProductType.objects.filter(shop=self.shop).values_list('name', flat=True)),
                         ['Shoes', 'Clothing', 'Bags', 'Accessories', 'Other'])
        clothing = ProductType.objects.get(shop=self.shop, name='Clothing')
        self.assertEqual(clothing.options[0], ('Size', ['XS', 'S', 'M', 'L', 'XL', 'XXL']))
        self.assertEqual([name for name, _ in clothing.options], ['Size', 'Colour', 'Fit'])

    def test_variation_label_and_compatible_names(self):
        self.assertEqual(self.variation.label, '42 / Black')
        self.assertEqual((self.variation.size, self.variation.color), ('42', 'Black'))
        self.assertEqual(self.variation.effective_price, 12500)

    def test_api_lists_the_shops_types(self):
        self.client.login(username='owner', password='pw12345!')
        names = [t['name'] for t in self.client.get('/api/product-types/').json()]
        self.assertEqual(names, ['Shoes', 'Clothing', 'Bags', 'Accessories', 'Other'])


class ReceiveStockTests(CatalogTestCase):
    def test_receiving_adds_stock_and_records_it(self):
        receive_stock(self.variation.id, 5, recorded_by=self.owner, reference='DN-2210')
        self.variation.refresh_from_db()
        self.assertEqual(self.variation.stock_quantity, 5)
        movement = StockMovement.objects.get()
        self.assertEqual((movement.kind, movement.quantity_change, movement.stock_after, movement.reference),
                         ('received', 5, 5, 'DN-2210'))

    def test_partial_restock_serves_oldest_customers_first(self):
        first, second, third = self.waiting(1), self.waiting(2), self.waiting(3)
        with self.captureOnCommitCallbacks(execute=True):
            receive_stock(self.variation.id, 2)
        for intent in (first, second, third):
            intent.refresh_from_db()
        self.assertEqual([first.status, second.status, third.status], ['Customer Notified', 'Customer Notified', 'Pending'])
        self.assertEqual(StockHold.objects.filter(status=StockHold.ACTIVE).count(), 2)
        self.variation.refresh_from_db()
        self.assertEqual((self.variation.stock_quantity, self.variation.available_quantity), (2, 0))
        self.assertEqual(NotificationLog.objects.count(), 2)

        with self.captureOnCommitCallbacks(execute=True):
            receive_stock(self.variation.id, 1)
        third.refresh_from_db()
        self.assertEqual(third.status, 'Customer Notified')
        self.assertEqual(NotificationLog.objects.count(), 3)

    def test_held_customers_are_not_served_twice(self):
        self.waiting(1)
        with self.captureOnCommitCallbacks(execute=True):
            receive_stock(self.variation.id, 1)
            receive_stock(self.variation.id, 3)
        self.assertEqual(StockHold.objects.count(), 1)
        self.variation.refresh_from_db()
        self.assertEqual((self.variation.stock_quantity, self.variation.available_quantity), (4, 3))

    def test_product_level_request_is_served(self):
        intent = self.waiting(1, constraint_type='Out of stock', variation=None)
        with self.captureOnCommitCallbacks(execute=True):
            receive_stock(self.variation.id, 1)
        intent.refresh_from_db()
        self.assertEqual(intent.status, 'Customer Notified')
        self.assertEqual(intent.holds.get().variation, self.variation)

    def test_stock_count_down_serves_nobody(self):
        receive_stock(self.variation.id, 3)
        self.waiting(1)
        with self.captureOnCommitCallbacks(execute=True):
            set_stock(self.variation.id, 1)
        self.assertEqual(StockHold.objects.count(), 0)

    def test_zero_or_negative_receive_is_rejected(self):
        with self.assertRaises(ValueError):
            receive_stock(self.variation.id, 0)


class ReceiveStockApiTests(CatalogTestCase):
    def test_manager_receives_stock(self):
        self.client.login(username='owner', password='pw12345!')
        response = self.client.post(f'/api/variations/{self.variation.id}/receive/', {'quantity': 4, 'reference': 'DN-1'},
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.data['stock_quantity'], response.data['available_quantity']), (4, 4))
        self.assertEqual(self.client.post(f'/api/variations/{self.variation.id}/receive/', {'quantity': 0},
                                          content_type='application/json').status_code, 400)

    def test_cashier_cannot_receive_stock(self):
        cashier = User.objects.create_user('cashier', password='pw12345!')
        Membership.objects.create(user=cashier, shop=self.shop, role=Membership.CASHIER)
        self.client.login(username='cashier', password='pw12345!')
        response = self.client.post(f'/api/variations/{self.variation.id}/receive/', {'quantity': 4},
                                    content_type='application/json')
        self.assertEqual(response.status_code, 403)
        self.variation.refresh_from_db()
        self.assertEqual(self.variation.stock_quantity, 0)


class PriceTests(CatalogTestCase):
    def test_price_changes_are_recorded(self):
        drop = change_price(self.product, 9900, changed_by=self.owner)
        self.assertTrue(drop.is_drop)
        self.assertEqual((drop.old_price, drop.new_price), (12500, 9900))
        self.assertIsNone(change_price(self.product, 9900))
        rise = change_price(self.product, 11000, variation=self.variation)
        self.assertFalse(rise.is_drop)
        self.variation.refresh_from_db()
        self.assertEqual(self.variation.effective_price, 11000)

    def test_api_price_edit_goes_through_the_record(self):
        self.client.login(username='owner', password='pw12345!')
        self.client.patch(f'/api/products/{self.product.id}/', {'base_price': '9900.00'}, content_type='application/json')
        self.product.refresh_from_db()
        self.assertEqual(self.product.base_price, 9900)
        self.assertEqual(PriceChange.objects.get().old_price, 12500)

    def test_page_price_edit_goes_through_the_record(self):
        self.client.login(username='owner', password='pw12345!')
        response = self.client.post(f'/products/update/{self.product.id}/', {
            'name': 'Nike Air Zoom', 'product_type': self.shoes.id, 'category': self.product.category_id,
            'description': '', 'base_price': '9500'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PriceChange.objects.get().new_price, 9500)


class CashierProductTests(CatalogTestCase):
    def test_cashier_added_product_needs_review(self):
        cashier = User.objects.create_user('cashier', password='pw12345!')
        Membership.objects.create(user=cashier, shop=self.shop, role=Membership.CASHIER)
        self.client.login(username='cashier', password='pw12345!')
        response = self.client.post('/api/products/', {'category': self.product.category_id, 'product_type': self.shoes.id,
                                                       'name': 'Puma Suede', 'base_price': '8000'}, content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Product.objects.get(name='Puma Suede').needs_review)


class PhotoTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)

    def test_large_photo_is_resized(self):
        buffer = BytesIO()
        Image.new('RGB', (3000, 1500), 'black').save(buffer, format='PNG')
        with override_settings(MEDIA_ROOT=self.media):
            self.variation.image = SimpleUploadedFile('black.png', buffer.getvalue(), content_type='image/png')
            self.variation.save()
            with Image.open(self.variation.image.path) as saved:
                self.assertEqual(max(saved.size), 1200)
            self.assertEqual(self.variation.photo, self.variation.image)
