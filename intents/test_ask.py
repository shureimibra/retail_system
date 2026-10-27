"""Phase 5: the public "Ask for your size" link."""
from django.core.cache import cache
from django.test import TestCase

from accounts.models import Membership, Shop, User
from accounts.services import shop_link_name
from customers.models import Customer
from products.models import Category, Product, ProductType, ProductVariation
from products.services import receive_stock
from .models import BlockedPurchaseIntent as Intent, Visit


class AskCase(TestCase):
    def setUp(self):
        cache.clear()
        self.shop = Shop.objects.create(name='Kimathi Street Store')
        self.shoes = ProductType.objects.get(shop=self.shop, name='Shoes')
        running = Category.objects.create(shop=self.shop, name='Running', product_type=self.shoes)
        self.boost = Product.objects.create(shop=self.shop, category=running, product_type=self.shoes,
                                            name='Adidas Ultraboost', base_price=18700)
        self.grey42 = ProductVariation.objects.create(product=self.boost, option1='42', option2='Grey', sku='AU-42-GRE')
        self.grey44 = ProductVariation.objects.create(product=self.boost, option1='44', option2='Grey', sku='AU-44-GRE')
        self.url = f'/ask/{shop_link_name(self.shop)}/'

    def ask(self, want, **extra):
        data = {'product': self.boost.pk, f'want_{self.boost.pk}': want, 'phone': '0712 345 678', 'name': 'Wanjiku',
                'consent': 'yes'}
        data.update(extra)
        return self.client.post(self.url, data, follow=True)


class PublicPageTests(AskCase):
    def test_link_name_comes_from_the_shop_name(self):
        self.assertEqual(self.url, '/ask/kimathi-street-store/')
        other = Shop.objects.create(name='Kimathi Street Store')
        self.assertEqual(shop_link_name(other), 'kimathi-street-store-2')

    def test_page_shows_items_but_never_prices_or_stock(self):
        receive_stock(self.grey44.pk, 3)
        page = self.client.get(self.url).content.decode()
        self.assertIn('Adidas Ultraboost', page)
        self.assertIn('42 / Grey', page)
        self.assertNotIn('18', page.split('<main')[1].split('<script')[0].replace('18px', ''))
        self.assertNotIn('in stock', page)

    def test_only_sizes_not_in_stock_are_offered(self):
        receive_stock(self.grey44.pk, 2)
        page = self.client.get(self.url).content.decode()
        self.assertIn(f'value="{self.grey42.pk}"', page)
        self.assertNotIn(f'value="{self.grey44.pk}"', page)
        self.assertNotIn('value="any"', page)  # some sizes are in the shop: they can come in

    def test_call_or_message_opens_a_chat_even_before_they_have_written(self):
        receive_stock(self.grey44.pk, 2)
        self.ask(self.grey44.pk)  # in stock: staff follow up by hand
        owner = User.objects.create_user('owner2', password='pw12345!')
        Membership.objects.create(user=owner, shop=self.shop, role=Membership.OWNER)
        self.client.login(username='owner2', password='pw12345!')
        intent = Intent.objects.get()
        response = self.client.get(f'/notifications/customer/{intent.customer_id}/')
        self.assertRedirects(response, f'/notifications/c/{intent.customer.conversations.get().pk}/',
                             fetch_redirect_response=False)
        self.assertContains(self.client.get('/intents/?show=all'), f'/notifications/c/')

    def test_a_missing_size_lands_in_waiting_as_a_shop_link_request(self):
        response = self.ask(self.grey42.pk)
        self.assertContains(response, 'Thank you, Wanjiku')
        self.assertContains(response, "You'll get a WhatsApp")
        intent = Intent.objects.get()
        self.assertEqual((intent.source, intent.constraint_type, intent.variation), (Intent.FROM_LINK, Intent.SIZE_MISSING, self.grey42))
        self.assertEqual(intent.customer.phone_number, '+254712345678')
        self.assertEqual(Visit.objects.count(), 0)  # not a walk-in
        owner = User.objects.create_user('owner', password='pw12345!')
        Membership.objects.create(user=owner, shop=self.shop, role=Membership.OWNER)
        self.client.login(username='owner', password='pw12345!')
        self.assertContains(self.client.get('/intents/?show=all'), 'Shop link')

    def test_receiving_stock_messages_the_customer(self):
        self.ask(self.grey42.pk)
        with self.captureOnCommitCallbacks(execute=True):
            receive_stock(self.grey42.pk, 1)
        self.assertEqual(Intent.objects.get().status, Intent.NOTIFIED)

    def test_in_stock_or_typed_requests_are_for_staff_to_follow_up(self):
        receive_stock(self.grey44.pk, 2)
        self.ask(self.grey44.pk)
        self.ask('other', wanted='45 in black', phone='0712 000 001')
        notes = sorted(Intent.objects.values_list('constraint_type', 'notes'))
        self.assertEqual(notes[0], (Intent.OTHER, 'Asked through the shop link for 44 / Grey. '
                                                   "It's in stock: invite them in."))
        self.assertEqual(notes[1], (Intent.OTHER, 'Asked through the shop link for: 45 in black'))

    def test_any_size_when_none_are_in_stock(self):
        self.ask('any')
        intent = Intent.objects.get()
        self.assertEqual((intent.constraint_type, intent.variation), (Intent.OUT_OF_STOCK, None))

    def test_asking_twice_records_once(self):
        self.ask(self.grey42.pk)
        self.ask(self.grey42.pk)
        self.assertEqual(Intent.objects.count(), 1)

    def test_mistakes_are_explained_and_nothing_saved(self):
        response = self.client.post(self.url, {'phone': 'abc'})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'Choose the item you want', status_code=400)
        response = self.ask('other', wanted='')
        self.assertContains(response, 'Tell us the size or colour', status_code=400)
        response = self.ask(self.grey42.pk, phone='12')
        self.assertContains(response, 'phone number', status_code=400)
        self.assertFalse(Intent.objects.exists())

    def test_bots_filling_the_hidden_field_are_ignored(self):
        response = self.ask(self.grey42.pk, website='http://spam.example')
        self.assertContains(response, 'Thank you')
        self.assertFalse(Intent.objects.exists())

    def test_limits_per_connection_and_per_phone(self):
        for i in range(5):
            self.ask('other', wanted=f'size {i}')
        response = self.ask('other', wanted='size 6')
        self.assertContains(response, 'already asked for several items', status_code=400)
        cache.clear()
        for i in range(20):
            self.ask('other', wanted=f'x{i}', phone=f'07120000{i:02d}')
        response = self.ask('other', wanted='one more', phone='0799000000')
        self.assertContains(response, 'Too many requests', status_code=400)

    def test_switched_off_link_says_so(self):
        self.shop.link_on = False
        self.shop.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.get('/ask/no-such-shop/').status_code, 404)


class SettingsTests(AskCase):
    def login(self, role):
        user = User.objects.create_user(role, password='pw12345!')
        Membership.objects.create(user=user, shop=self.shop, role=role)
        self.client.login(username=role, password='pw12345!')

    def test_manager_sees_link_and_qr_and_can_switch_it_off(self):
        self.login(Membership.MANAGER)
        page = self.client.get('/settings/shop-link/').content.decode()
        self.assertIn('/ask/kimathi-street-store/', page)
        self.assertIn('<svg', page)
        qr = self.client.get('/settings/shop-link/qr.png')
        self.assertEqual((qr.status_code, qr['Content-Type']), (200, 'image/png'))
        self.client.post('/settings/shop-link/', {})
        self.shop.refresh_from_db()
        self.assertFalse(self.shop.link_on)

    def test_cashier_cannot_open_it(self):
        self.login(Membership.CASHIER)
        self.assertEqual(self.client.get('/settings/shop-link/').status_code, 403)
        self.assertEqual(self.client.get('/settings/shop-link/qr.png').status_code, 403)
