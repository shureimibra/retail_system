"""Phase 3b screens: Waiting, To order, Product detail and Customers."""
import shutil
import tempfile
from datetime import timedelta
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from accounts.models import Membership, Shop, User
from customers.models import Customer
from intents import services
from intents.models import BlockedPurchaseIntent as Intent
from products.models import Category, PriceChange, Product, ProductOptionPhoto, ProductVariation


class ScreensTestCase(TestCase):
    def setUp(self):
        self.shop = Shop.objects.create(name='Kimathi Street Store')
        self.users = {}
        for role in (Membership.OWNER, Membership.MANAGER, Membership.CASHIER):
            user = User.objects.create_user(role, password='pw12345!', first_name=role.title())
            Membership.objects.create(user=user, shop=self.shop, role=role)
            self.users[role] = user
        category = Category.objects.create(shop=self.shop, name='Running')
        self.product = Product.objects.create(shop=self.shop, category=category, name='Nike Air Zoom', base_price=12500,
                                              supplier='Kicks Wholesale')
        self.black42 = ProductVariation.objects.create(product=self.product, option1='42', option2='Black', sku='NAZ-42-BLA')
        self.white41 = ProductVariation.objects.create(product=self.product, option1='41', option2='White', sku='NAZ-41-WHI',
                                                       stock_quantity=3)
        self.n = 0

    def login(self, role):
        self.client.login(username=role, password='pw12345!')

    def customer(self, first, last='K', phone=None):
        self.n += 1
        return Customer.objects.create(shop=self.shop, first_name=first, last_name=last,
                                       phone_number=phone or f'+2547120000{self.n:02d}')

    def request(self, customer, reason=Intent.SIZE_MISSING, variation=None, **kwargs):
        with self.captureOnCommitCallbacks(execute=True):
            return services.create_blocked_purchase_intent(customer, self.product, variation or self.black42, reason,
                                                           recorded_by=self.users['owner'], **kwargs)


class WaitingTests(ScreensTestCase):
    def test_items_are_grouped_by_customer(self):
        jane = self.customer('Jane', 'Smith')
        self.request(jane)
        self.request(jane, variation=self.white41, reason=Intent.COLOUR_MISSING)
        self.request(self.customer('Peter'))
        self.login('owner')
        response = self.client.get('/intents/')
        groups = response.context['groups']
        self.assertEqual(len(groups), 2)
        self.assertEqual(sorted(len(g['items']) for g in groups), [1, 2])

    def test_tabs_split_stock_and_price(self):
        self.request(self.customer('Jane'))
        self.request(self.customer('Ali'), reason=Intent.PRICE_TOO_HIGH)
        self.login('owner')
        stock = self.client.get('/intents/?show=stock').context
        price = self.client.get('/intents/?show=price').context
        self.assertEqual((stock['item_count'], price['item_count']), (1, 1))
        self.assertEqual(price['groups'][0]['items'][0].constraint_type, Intent.PRICE_TOO_HIGH)
        # Old links keep working.
        self.assertEqual(self.client.get('/intents/?show=waiting').context['current_tab'], 'stock')

    def test_search_and_filters(self):
        self.request(self.customer('Jane', phone='+254722345678'))
        self.request(self.customer('Peter'), variation=self.white41)
        self.login('owner')
        self.assertEqual(self.client.get('/intents/?q=722345').context['item_count'], 1)
        self.assertEqual(self.client.get('/intents/?q=naz-41').context['item_count'], 1)
        self.assertEqual(self.client.get('/intents/?q=nobody').context['item_count'], 0)
        for query in ['?period=custom&start_date=275760-04-25', '?reason=junk', '?customer=abc', '?page=99']:
            self.assertEqual(self.client.get('/intents/' + query).status_code, 200)

    def test_cashier_cannot_mark_as_ordered(self):
        intent = self.request(self.customer('Jane'))
        self.login('cashier')
        self.assertNotContains(self.client.get('/intents/'), 'Mark as ordered')
        self.assertEqual(self.client.post('/intents/mark-ordered/', {'intent': [intent.pk]}).status_code, 403)
        intent.refresh_from_db()
        self.assertEqual(intent.status, Intent.OPEN)

    def test_manager_marks_selected_items_as_ordered(self):
        first = self.request(self.customer('Jane'))
        second = self.request(self.customer('Peter'))
        arrives = timezone.localdate() + timedelta(days=4)
        self.login('manager')
        response = self.client.post('/intents/mark-ordered/', {'intent': [first.pk], 'expected_at': arrives.isoformat(),
                                                               'next': 'https://evil.example/'})
        self.assertEqual(response['Location'], '/intents/to-order/')
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.status, first.expected_at), (Intent.ON_ORDER, arrives))
        self.assertEqual(second.status, Intent.OPEN)

    def test_another_shops_records_cannot_be_ordered(self):
        other = Shop.objects.create(name='Elsewhere')
        stranger = Customer.objects.create(shop=other, first_name='X', last_name='Y', phone_number='+254700000999')
        other_product = Product.objects.create(shop=other, category=Category.objects.create(shop=other, name='C'),
                                               name='Bag', base_price=100)
        theirs = services.create_blocked_purchase_intent(stranger, other_product, None, Intent.OUT_OF_STOCK)
        self.login('owner')
        self.client.post('/intents/mark-ordered/', {'intent': [theirs.pk]})
        theirs.refresh_from_db()
        self.assertEqual(theirs.status, Intent.OPEN)


class ToOrderTests(ScreensTestCase):
    def test_only_owners_and_managers(self):
        self.login('cashier')
        self.assertEqual(self.client.get('/intents/to-order/').status_code, 403)
        self.assertNotContains(self.client.get('/dashboard/'), '/intents/to-order/')

    def test_grouped_by_supplier_with_share_link(self):
        self.request(self.customer('Jane', 'Smith'))
        self.request(self.customer('Robert', 'Johnson'))
        self.login('owner')
        response = self.client.get('/intents/to-order/')
        group = response.context['groups'][0]
        self.assertEqual(group['supplier'], 'Kicks Wholesale')
        self.assertEqual(group['rows'][0]['to_order'], 2)
        self.assertEqual(group['rows'][0]['initials'], ['JS', 'RJ'])
        self.assertIn('Nike%20Air%20Zoom%2042%20%2F%20Black', group['share_url'])
        self.assertContains(response, 'Share list on WhatsApp')

    def test_mark_a_whole_row_as_ordered(self):
        a = self.request(self.customer('Jane'))
        b = self.request(self.customer('Peter'))
        self.login('owner')
        row = self.client.get('/intents/to-order/').context['groups'][0]['rows'][0]
        self.client.post('/intents/mark-ordered/', {'row': ','.join(map(str, row['open_ids']))})
        self.assertEqual(set(Intent.objects.filter(pk__in=[a.pk, b.pk]).values_list('status', flat=True)), {Intent.ON_ORDER})
        row = self.client.get('/intents/to-order/').context['groups'][0]['rows'][0]
        self.assertEqual((row['to_order'], row['open_ids']), (0, []))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProductDetailTests(ScreensTestCase):
    url = None

    @classmethod
    def tearDownClass(cls):
        from django.conf import settings
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.url = f'/products/{self.product.pk}/'

    def photo(self, colour='black'):
        buffer = BytesIO()
        Image.new('RGB', (20, 20), colour).save(buffer, format='PNG')
        return SimpleUploadedFile(f'{colour}.png', buffer.getvalue(), content_type='image/png')

    def test_grid_shows_stock_and_waiting(self):
        self.request(self.customer('Jane'))
        self.request(self.customer('Ali'), reason=Intent.PRICE_TOO_HIGH)
        self.login('cashier')
        response = self.client.get(self.url)
        detail = response.context['detail']
        self.assertEqual(detail['grid']['cols'], ['41', '42'])
        cells = dict(detail['grid']['rows'])
        self.assertEqual((cells['Black'][1].waiting, cells['White'][0].stock_quantity), (1, 3))
        self.assertEqual(detail['waiting_price']['customers'], 1)
        self.assertNotContains(response, 'Receive stock</h2>')

    def test_cashiers_cannot_change_anything(self):
        self.login('cashier')
        for data in ({'action': 'receive', 'variation': self.black42.pk, 'quantity': 2},
                     {'action': 'price', 'price': 9000}, {'action': 'add', 'option1': '43'}):
            self.assertEqual(self.client.post(self.url, data).status_code, 403)
        self.black42.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual((self.black42.stock_quantity, self.product.base_price), (0, 12500))

    def test_receiving_stock_serves_the_waiting_customer(self):
        intent = self.request(self.customer('Jane'))
        self.login('manager')
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url, {'action': 'receive', 'variation': self.black42.pk, 'quantity': 1, 'reference': 'DN-12'})
        self.black42.refresh_from_db()
        intent.refresh_from_db()
        self.assertEqual(self.black42.stock_quantity, 1)
        self.assertNotEqual(intent.status, Intent.OPEN)

    def test_price_drop_is_recorded(self):
        self.request(self.customer('Ali'), reason=Intent.PRICE_TOO_HIGH)
        self.login('owner')
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url, {'action': 'price', 'price': '11000'})
        self.assertTrue(PriceChange.objects.filter(product=self.product, new_price=11000).exists())
        self.client.post(self.url, {'action': 'price', 'price': 'cheap'})
        self.product.refresh_from_db()
        self.assertEqual(self.product.base_price, 11000)

    def test_add_a_size_with_a_made_up_sku(self):
        self.login('owner')
        self.client.post(self.url, {'action': 'add', 'option1': '43', 'option2': 'Black', 'stock': '2'})
        added = ProductVariation.objects.get(product=self.product, option1='43')
        self.assertEqual((added.sku, added.stock_quantity), ('NAZ-43-BLA', 2))
        self.client.post(self.url, {'action': 'add', 'option1': '43', 'option2': 'Black'})
        self.assertEqual(ProductVariation.objects.filter(product=self.product, option1='43').count(), 1)

    def test_photo_per_colour_is_used_for_every_size(self):
        self.login('owner')
        self.client.post(self.url, {'action': 'photo', 'value': 'Black', 'image': self.photo()})
        self.assertTrue(ProductOptionPhoto.objects.filter(product=self.product, value='Black').exists())
        black = ProductVariation.objects.get(pk=self.black42.pk)
        white = ProductVariation.objects.get(pk=self.white41.pk)
        self.assertIn('black', black.photo.name)
        self.assertFalse(white.photo)

    def test_another_shops_product_is_not_found(self):
        other = Shop.objects.create(name='Elsewhere')
        theirs = Product.objects.create(shop=other, category=Category.objects.create(shop=other, name='C'),
                                        name='Bag', base_price=100)
        self.login('owner')
        self.assertEqual(self.client.get(f'/products/{theirs.pk}/').status_code, 404)


class CustomerScreenTests(ScreensTestCase):
    def test_detail_shows_items_and_payments(self):
        jane = self.customer('Jane', 'Smith')
        paid = self.request(jane)
        services.record_payment(paid, 12500, 'mpesa', reference='QK7H2L9', actor=self.users['owner'])
        open_item = self.request(jane, variation=self.white41, reason=Intent.COLOUR_MISSING)
        self.login('cashier')
        response = self.client.get(f'/customers/{jane.pk}/')
        self.assertEqual([i.pk for i in response.context['open_items']], [open_item.pk])
        self.assertEqual([i.pk for i in response.context['closed_items']], [paid.pk])
        self.assertContains(response, 'QK7H2L9')

    def test_list_counts_and_search(self):
        jane = self.customer('Jane', 'Smith', phone='+254722345678')
        self.request(jane)
        self.customer('Peter')
        self.login('owner')
        customers = {c.first_name: c for c in self.client.get('/customers/').context['customers']}
        self.assertEqual((customers['Jane'].open_items, customers['Peter'].open_items), (1, 0))
        self.assertEqual([c.first_name for c in self.client.get('/customers/?q=722345').context['customers']], ['Jane'])

    def test_another_shops_customer_is_not_found(self):
        other = Shop.objects.create(name='Elsewhere')
        stranger = Customer.objects.create(shop=other, first_name='X', last_name='Y', phone_number='+254700000999')
        self.login('owner')
        self.assertEqual(self.client.get(f'/customers/{stranger.pk}/').status_code, 404)

    def test_log_another_item_starts_with_the_customer(self):
        jane = self.customer('Jane')
        self.login('cashier')
        response = self.client.get(f'/intents/create/?customer={jane.pk}')
        self.assertEqual(response.context['form'].initial.get('customer'), jane.pk)
