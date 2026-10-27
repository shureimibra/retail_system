"""Phase 5b: Log missed sale saved on the phone while offline, sent later."""
import json
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import Membership, Shop, User
from products.models import Category, Product, ProductType, ProductVariation
from products.services import receive_stock
from .models import BlockedPurchaseIntent as Intent, Visit


class OfflineCase(TestCase):
    def setUp(self):
        self.shop = Shop.objects.create(name='Kimathi Street Store')
        self.amina = User.objects.create_user('amina', password='pw12345!', first_name='Amina')
        Membership.objects.create(user=self.amina, shop=self.shop, role=Membership.CASHIER)
        self.client.login(username='amina', password='pw12345!')
        shoes = ProductType.objects.get(shop=self.shop, name='Shoes')
        running = Category.objects.create(shop=self.shop, name='Running', product_type=shoes)
        self.boost = Product.objects.create(shop=self.shop, category=running, product_type=shoes,
                                            name='Adidas Ultraboost', base_price=18700)
        self.grey42 = ProductVariation.objects.create(product=self.boost, option1='42', option2='Grey', sku='AU-42-GRE')

    def fields(self, ref='ref-1', **extra):
        data = {'client_ref': ref, 'product': str(self.boost.pk), 'variation': str(self.grey42.pk),
                'reason': Intent.SIZE_MISSING, 'phone': '0712 345 678', 'name': 'Wanjiku', 'consent': 'yes',
                'within': '7', 'logged_at': (timezone.now() - timedelta(hours=3)).isoformat()}
        data.update(extra)
        return data

    def sync(self, fields, kind='missed'):
        return self.client.post('/floor/sync/', json.dumps({'kind': kind, 'fields': fields}),
                                content_type='application/json')


class SyncTests(OfflineCase):
    def test_a_record_saved_offline_arrives_once_with_its_time(self):
        first = self.sync(self.fields())
        again = self.sync(self.fields())
        self.assertEqual((first.json()['status'], again.json()['status']), ('saved', 'already'))
        intent = Intent.objects.get()
        self.assertEqual((intent.client_ref, intent.recorded_by), ('ref-1', self.amina))
        self.assertLess(intent.created_at, timezone.now() - timedelta(hours=2))
        self.assertEqual(Visit.objects.count(), 1)

    def test_a_size_that_came_back_in_stock_becomes_something_else(self):
        receive_stock(self.grey42.pk, 1)
        self.sync(self.fields())
        intent = Intent.objects.get()
        self.assertEqual(intent.constraint_type, Intent.OTHER)
        self.assertIn("It's in stock now: invite them in", intent.notes)

    def test_same_customer_another_item_offline_is_one_visit(self):
        self.sync(self.fields('ref-1'))
        self.sync(self.fields('ref-2', variation='', reason=Intent.OUT_OF_STOCK, visit_ref='ref-1'))
        self.assertEqual(Intent.objects.count(), 2)
        self.assertEqual(Visit.objects.count(), 1)

    def test_another_item_arriving_before_the_first_still_shares_the_visit(self):
        self.sync(self.fields('ref-2', variation='', reason=Intent.OUT_OF_STOCK, visit_ref='ref-1'))
        self.sync(self.fields('ref-1'))
        self.assertEqual(Intent.objects.count(), 2)
        self.assertEqual(Visit.objects.count(), 1)

    def test_bought_offline_counts_once(self):
        for _ in range(2):
            self.sync({'action': 'bought', 'client_ref': 'sale-1'}, kind='bought')
        self.assertEqual(Visit.objects.filter(outcome=Visit.BOUGHT).count(), 1)

    def test_records_typed_by_a_colleague_keep_their_name(self):
        other = User.objects.create_user('ben', password='pw12345!')
        Membership.objects.create(user=other, shop=self.shop, role=Membership.CASHIER)
        stranger = User.objects.create_user('stranger', password='pw12345!')
        self.client.login(username='ben', password='pw12345!')
        self.sync(self.fields('ref-a', logged_by=str(self.amina.pk)))
        self.sync(self.fields('ref-b', logged_by=str(stranger.pk), phone='0712 000 001'))
        by_ref = dict(Intent.objects.values_list('client_ref', 'recorded_by__username'))
        self.assertEqual(by_ref, {'ref-a': 'amina', 'ref-b': 'ben'})  # a non-member can't be named

    def test_mistakes_come_back_so_the_phone_can_show_them(self):
        answer = self.sync(self.fields(phone='12')).json()
        self.assertEqual(answer['status'], 'refused')
        self.assertIn('phone number', answer['problems'][0])

    def test_time_is_never_in_the_future_or_older_than_a_week(self):
        self.sync(self.fields('f', logged_at=(timezone.now() + timedelta(days=2)).isoformat()))
        self.sync(self.fields('o', phone='0712 000 002', logged_at='2020-01-01T10:00:00+03:00'))
        future, old = Intent.objects.get(client_ref='f'), Intent.objects.get(client_ref='o')
        self.assertLessEqual(future.created_at, timezone.now())
        self.assertGreater(old.created_at, timezone.now() - timedelta(days=8))

    def test_signed_out_phone_is_told_to_sign_in(self):
        self.client.logout()
        self.assertEqual(self.sync(self.fields()).status_code, 401)
        self.assertEqual(self.client.get('/floor/token/').status_code, 401)
        self.assertFalse(Intent.objects.exists())

    def test_sync_needs_the_csrf_token(self):
        from django.test import Client
        strict = Client(enforce_csrf_checks=True)
        strict.login(username='amina', password='pw12345!')
        response = strict.post('/floor/sync/', json.dumps({'kind': 'missed', 'fields': self.fields()}),
                               content_type='application/json')
        self.assertEqual(response.status_code, 403)
        token = strict.get('/floor/token/').json()['token']
        response = strict.post('/floor/sync/', json.dumps({'kind': 'missed', 'fields': self.fields()}),
                               content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.json()['status'], 'saved')


class OnlineUnchangedTests(OfflineCase):
    def test_double_tapped_save_online_is_kept_once(self):
        data = self.fields()
        del data['logged_at']
        for _ in range(2):
            self.client.post('/floor/', data)
        self.assertEqual(Intent.objects.count(), 1)

    def test_only_a_clean_page_is_marked_for_keeping_offline(self):
        self.assertEqual(self.client.get('/floor/')['X-Offline-Copy'], 'yes')
        self.client.post('/floor/', {'action': 'bought'})
        self.assertFalse(self.client.get('/floor/').has_header('X-Offline-Copy'))  # shows "Sale logged"

    def test_offline_helper_and_manifest_are_served(self):
        sw = self.client.get('/sw.js')
        self.assertEqual(sw['Content-Type'], 'application/javascript; charset=utf-8')
        self.assertIn("var FLOOR = '/floor/'", sw.content.decode())
        manifest = self.client.get('/manifest.webmanifest').json()
        self.assertEqual((manifest['name'], manifest['display']), ('Kimathi Street Store', 'standalone'))
        self.assertIn('data-sync-url="/floor/sync/"', self.client.get('/floor/').content.decode())
