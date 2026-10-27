"""Phase 5: API keys and the connection points a POS uses."""
from django.core.cache import cache
from django.test import TestCase

from accounts.models import Membership, Shop, User
from customers.models import Customer
from intents import services as intents
from intents.models import BlockedPurchaseIntent as Intent, Visit
from products.models import Category, Product, ProductType, ProductVariation, StockMovement
from products.services import receive_stock
from .models import ApiKey, ConnectionRequest


class ConnectCase(TestCase):
    def setUp(self):
        cache.clear()
        self.shop = Shop.objects.create(name='Kimathi Street Store')
        self.owner = User.objects.create_user('owner', password='pw12345!')
        Membership.objects.create(user=self.owner, shop=self.shop, role=Membership.OWNER)
        shoes = ProductType.objects.get(shop=self.shop, name='Shoes')
        running = Category.objects.create(shop=self.shop, name='Running', product_type=shoes)
        self.boost = Product.objects.create(shop=self.shop, category=running, product_type=shoes,
                                            name='Adidas Ultraboost', base_price=18700)
        self.grey42 = ProductVariation.objects.create(product=self.boost, option1='42', option2='Grey', sku='AU-42-GRE')
        self.grey44 = ProductVariation.objects.create(product=self.boost, option1='44', option2='Grey', sku='AU-44-GRE',
                                                      stock_quantity=5)
        self.key, self.raw = ApiKey.issue(self.shop, 'Loyverse', ApiKey.STOCK, created_by=self.owner)

    def call(self, method, path, data=None, raw=None, **headers):
        auth = {'HTTP_AUTHORIZATION': f'Bearer {raw or self.raw}'} if raw is not False else {}
        extra = {f'HTTP_{k.upper().replace("-", "_")}': v for k, v in headers.items()}
        return getattr(self.client, method)(f'/api/v1/connect/{path}', data, content_type='application/json', **auth, **extra)

    def waiting(self, variation):
        customer = Customer.objects.create(shop=self.shop, first_name='Jane', phone_number='+254711000001')
        return intents.create_blocked_purchase_intent(customer, self.boost, variation, Intent.SIZE_MISSING)


class KeyTests(ConnectCase):
    def test_only_a_hash_is_stored(self):
        self.assertTrue(self.raw.startswith(self.key.prefix + '_'))
        self.assertNotIn(self.raw, self.key.key_hash)

    def test_missing_wrong_or_revoked_keys_are_refused(self):
        self.assertEqual(self.call('get', 'products/', raw=False).status_code, 401)
        self.assertEqual(self.call('get', 'products/', raw=self.raw[:-2] + 'xx').status_code, 401)
        self.assertEqual(self.call('get', 'products/').status_code, 200)
        self.key.revoked_at = self.key.created_at
        self.key.save()
        self.assertEqual(self.call('get', 'products/').status_code, 401)

    def test_a_read_key_cannot_change_stock(self):
        _, raw = ApiKey.issue(self.shop, 'Website', ApiKey.READ)
        response = self.call('post', 'stock/', {'changes': [{'sku': 'AU-42-GRE', 'add': 1}]}, raw=raw)
        self.assertEqual(response.status_code, 403)
        self.assertContains(self.call('get', 'to-order/', raw=raw), 'to_order')

    def test_a_key_sees_only_its_own_shop(self):
        other = Shop.objects.create(name='Other')
        _, raw = ApiKey.issue(other, 'Theirs', ApiKey.STOCK)
        self.assertEqual(self.call('get', 'products/', raw=raw).json(), {'products': []})
        response = self.call('post', 'stock/', {'changes': [{'sku': 'AU-42-GRE', 'add': 1}]}, raw=raw)
        self.assertFalse(response.json()['results'][0]['ok'])
        self.grey42.refresh_from_db()
        self.assertEqual(self.grey42.stock_quantity, 0)

    def test_last_used_is_recorded(self):
        self.call('get', 'products/')
        self.key.refresh_from_db()
        self.assertIsNotNone(self.key.last_used_at)


class StockTests(ConnectCase):
    def test_products_list_skus_and_stock(self):
        rows = self.call('get', 'products/').json()['products']
        self.assertIn({'sku': 'AU-44-GRE', 'item': 'Adidas Ultraboost', 'type': 'Shoes', 'size': '44', 'colour': 'Grey',
                       'price': '18700.00', 'in_stock': 5, 'held_for_customers': 0, 'available': 5}, rows)

    def test_a_delivery_tells_waiting_customers(self):
        intent = self.waiting(self.grey42)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.call('post', 'stock/', {'changes': [{'sku': 'au-42-gre', 'add': 2}], 'reference': 'DN-77'})
        self.assertEqual(response.json(), {'results': [{'sku': 'AU-42-GRE', 'ok': True, 'in_stock': 2}]})
        intent.refresh_from_db()
        self.assertEqual(intent.status, Intent.NOTIFIED)
        self.assertEqual(StockMovement.objects.filter(variation=self.grey42).first().reference, 'Loyverse: DN-77')

    def test_set_and_remove_and_their_mistakes(self):
        response = self.call('post', 'stock/', {'changes': [
            {'sku': 'AU-44-GRE', 'set': 3}, {'sku': 'AU-44-GRE', 'remove': 1}, {'sku': 'NOPE', 'set': 1},
            {'sku': 'AU-42-GRE', 'set': -1}, {'sku': 'AU-42-GRE', 'add': 1, 'set': 2}, {'sku': 'AU-42-GRE', 'add': 1.5},
        ]})
        results = response.json()['results']
        self.assertEqual([r['ok'] for r in results], [True, True, False, False, False, False])
        self.assertEqual(results[1]['in_stock'], 2)
        self.assertIn('No item', results[2]['error'])
        self.assertIn('exactly one', results[4]['error'])

    def test_stock_never_goes_below_units_held_for_customers(self):
        self.waiting(self.grey42)
        with self.captureOnCommitCallbacks(execute=True):
            receive_stock(self.grey42.pk, 1)
        result = self.call('post', 'stock/', {'changes': [{'sku': 'AU-42-GRE', 'set': 0}]}).json()['results'][0]
        self.assertFalse(result['ok'])
        self.assertIn('put aside', result['error'])

    def test_bad_bodies_are_explained(self):
        self.assertEqual(self.call('post', 'stock/', {'changes': 'x'}).status_code, 400)
        self.assertContains(self.call('post', 'sales/', {}), 'Send \\"items\\" as a list', status_code=400)


class SalesTests(ConnectCase):
    def test_a_till_sale_takes_stock_down_and_counts_a_walk_in(self):
        response = self.call('post', 'sales/', {'items': [{'sku': 'AU-44-GRE', 'quantity': 2}], 'reference': 'Receipt 1043'})
        self.assertEqual(response.json(), {'results': [{'sku': 'AU-44-GRE', 'ok': True, 'sold': 2, 'in_stock': 3}]})
        self.assertEqual(Visit.objects.filter(shop=self.shop, outcome=Visit.BOUGHT).count(), 1)
        move = StockMovement.objects.get(variation=self.grey44, kind=StockMovement.TILL_SALE)
        self.assertEqual((move.quantity_change, move.reference), (-2, 'Loyverse: Receipt 1043'))

    def test_a_sale_never_takes_a_unit_held_for_a_customer(self):
        self.waiting(self.grey42)
        with self.captureOnCommitCallbacks(execute=True):
            receive_stock(self.grey42.pk, 2)  # 1 held for Jane, 1 free
        result = self.call('post', 'sales/', {'items': [{'sku': 'AU-42-GRE', 'quantity': 2}]}).json()['results'][0]
        self.assertEqual((result['sold'], result['in_stock']), (1, 1))
        self.assertIn('Count this item again', result['warning'])

    def test_sending_the_same_sale_twice_counts_once(self):
        body = {'items': [{'sku': 'AU-44-GRE', 'quantity': 1}]}
        first = self.call('post', 'sales/', body, **{'Idempotency-Key': 'receipt-1043'})
        again = self.call('post', 'sales/', body, **{'Idempotency-Key': 'receipt-1043'})
        self.assertEqual(first.json(), again.json())
        self.assertEqual(again['Idempotent-Replay'], 'true')
        self.grey44.refresh_from_db()
        self.assertEqual(self.grey44.stock_quantity, 4)
        self.assertEqual(ConnectionRequest.objects.count(), 1)
        self.call('post', 'sales/', body, **{'Idempotency-Key': 'receipt-1044'})
        self.grey44.refresh_from_db()
        self.assertEqual(self.grey44.stock_quantity, 3)


class SettingsTests(ConnectCase):
    def test_owner_creates_a_key_seen_once_and_revokes_it(self):
        self.client.login(username='owner', password='pw12345!')
        page = self.client.post('/settings/connections/', {'name': 'Website', 'permission': 'read'}, follow=True)
        key = ApiKey.objects.get(name='Website')
        self.assertContains(page, 'Shown once')
        self.assertContains(page, key.prefix)
        again = self.client.get('/settings/connections/').content.decode()
        self.assertNotIn('Shown once', again)
        self.assertIn(key.prefix, again)
        self.client.post('/settings/connections/', {'action': 'revoke', 'key': key.pk})
        key.refresh_from_db()
        self.assertIsNotNone(key.revoked_at)

    def test_managers_cannot_open_connections(self):
        manager = User.objects.create_user('man', password='pw12345!')
        Membership.objects.create(user=manager, shop=self.shop, role=Membership.MANAGER)
        self.client.login(username='man', password='pw12345!')
        self.assertEqual(self.client.get('/settings/connections/').status_code, 403)
