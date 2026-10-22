from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import Membership, Shop, User
from customers.models import Customer
from intents import services
from intents.automation import process_due
from intents.models import BlockedPurchaseIntent as Intent
from products.models import Category, Product, ProductType, ProductVariation
from products.services import receive_stock


class SettingsTestCase(TestCase):
    def setUp(self):
        self.shop = Shop.objects.create(name='Kimathi Street Store')
        self.users = {}
        for role in (Membership.OWNER, Membership.MANAGER, Membership.CASHIER):
            user = User.objects.create_user(role, password='pw12345!', first_name=role.title())
            Membership.objects.create(user=user, shop=self.shop, role=role)
            self.users[role] = user

    def login(self, role):
        self.client.login(username=role, password='pw12345!')


class AccessTests(SettingsTestCase):
    SECTIONS = ['account', 'look', 'shop', 'product-types', 'team', 'follow-ups', 'messaging']
    ALLOWED = {
        'owner': set(SECTIONS),
        'manager': {'account', 'look', 'product-types', 'follow-ups', 'messaging'},
        'cashier': {'account', 'look'},
    }

    def test_each_role_sees_only_its_sections(self):
        for role, allowed in self.ALLOWED.items():
            self.login(role)
            for section in self.SECTIONS:
                with self.subTest(role=role, section=section):
                    status = self.client.get(f'/settings/{section}/').status_code
                    self.assertEqual(status, 200 if section in allowed else 403)
            menu = self.client.get('/settings/').content.decode()
            self.assertEqual('Team and roles' in menu, role == 'owner')

    def test_cashier_cannot_change_follow_ups_by_posting(self):
        self.login('cashier')
        self.client.post('/settings/follow-ups/', {'follow_up_days': '1', 'expire_days_after_last_follow_up': 1,
                                                   'stock_hold_days': 1, 'reserve_pickup_days': 1})
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.follow_up_days, '2,4,7')


class AccountAndLookTests(SettingsTestCase):
    def test_profile_and_password(self):
        self.login('cashier')
        response = self.client.post('/settings/account/', {'form': 'profile', 'first_name': 'Grace', 'last_name': 'W',
                                                           'email': 'grace@example.com', 'phone_number': '0711 000 222'})
        self.assertRedirects(response, '/settings/account/')
        user = User.objects.get(username='cashier')
        self.assertEqual((user.first_name, user.phone_number), ('Grace', '+254711000222'))
        self.client.post('/settings/account/', {'form': 'password', 'old_password': 'pw12345!',
                                                'new_password1': 'Shoes-and-bags-42', 'new_password2': 'Shoes-and-bags-42'})
        self.assertTrue(User.objects.get(username='cashier').check_password('Shoes-and-bags-42'))
        self.assertEqual(self.client.get('/settings/account/').status_code, 200)  # still signed in

    def test_theme_is_applied_to_pages(self):
        self.login('cashier')
        self.client.post('/settings/look/', {'theme': 'dark'})
        self.assertIn('data-theme="dark"', self.client.get('/dashboard/').content.decode())
        self.client.post('/settings/look/', {'theme': 'system'})
        self.assertNotIn('data-theme=', self.client.get('/dashboard/').content.decode())


class ShopAndFollowUpTests(SettingsTestCase):
    def test_shop_details(self):
        self.login('owner')
        self.client.post('/settings/shop/', {'name': 'Moi Avenue Shoes', 'phone_region': 'UG', 'currency': 'UGX',
                                             'timezone': 'Africa/Kampala'})
        self.shop.refresh_from_db()
        self.assertEqual((self.shop.name, self.shop.phone_region, self.shop.timezone), ('Moi Avenue Shoes', 'UG', 'Africa/Kampala'))

    def test_follow_up_days_are_validated_and_tidied(self):
        self.login('manager')
        bad = self.client.post('/settings/follow-ups/', {'follow_up_days': 'tomorrow', 'expire_days_after_last_follow_up': 1,
                                                         'stock_hold_days': 8, 'reserve_pickup_days': 5})
        self.assertContains(bad, 'Use whole days between 1 and 60')
        self.client.post('/settings/follow-ups/', {'follow_up_days': '5, 1, 3, 3', 'expire_days_after_last_follow_up': 2,
                                                   'stock_hold_days': 10, 'reserve_pickup_days': 3})
        self.shop.refresh_from_db()
        self.assertEqual((self.shop.follow_up_days, self.shop.follow_up_schedule), ('1, 3, 5', [1, 3, 5]))

    def test_automation_uses_the_shops_schedule(self):
        self.shop.follow_up_days = '1'
        self.shop.expire_days_after_last_follow_up = 1
        self.shop.save()
        category = Category.objects.create(shop=self.shop, name='Running')
        product = Product.objects.create(shop=self.shop, category=category, name='Nike Air Zoom', base_price=12500,
                                         product_type=ProductType.objects.get(shop=self.shop, name='Shoes'))
        variation = ProductVariation.objects.create(product=product, option1='42', option2='Black', sku='NAZ-42')
        jane = Customer.objects.create(shop=self.shop, first_name='Jane', last_name='S', phone_number='0722345678')
        intent = services.create_blocked_purchase_intent(jane, product, variation, Intent.SIZE_MISSING)
        with self.captureOnCommitCallbacks(execute=True):
            receive_stock(variation.id, 1)
        hold = intent.holds.get()
        self.assertEqual((hold.expires_at - timezone.now()).days, self.shop.stock_hold_days - 1)
        with self.captureOnCommitCallbacks(execute=True):
            process_due(now=timezone.now() + timedelta(days=1))
        process_due(now=timezone.now() + timedelta(days=2))
        intent.refresh_from_db()
        self.assertEqual(intent.status, Intent.EXPIRED)

    def test_new_requests_use_the_shops_channel(self):
        self.shop.default_channel = 'sms'
        self.shop.save()
        category = Category.objects.create(shop=self.shop, name='Bags')
        product = Product.objects.create(shop=self.shop, category=category, name='Tote', base_price=3000)
        customer = Customer.objects.create(shop=self.shop, first_name='Ali', last_name='H', phone_number='0766345678')
        intent = services.create_blocked_purchase_intent(customer, product, None, Intent.OUT_OF_STOCK)
        self.assertEqual(intent.preferred_channel, 'sms')


class ProductTypeTests(SettingsTestCase):
    def test_add_edit_and_delete_rules(self):
        self.login('manager')
        self.client.post('/settings/product-types/new/', {'name': 'Watches', 'option1_name': 'Size', 'option1_values': '38mm, 42mm',
                                                          'option2_name': 'Colour', 'option2_values': '', 'option3_name': '', 'option3_values': ''})
        watches = ProductType.objects.get(shop=self.shop, name='Watches')
        self.assertEqual(watches.options[0], ('Size', ['38mm', '42mm']))
        duplicate = self.client.post('/settings/product-types/new/', {'name': 'watches', 'option1_name': 'Size', 'option2_name': 'Colour'})
        self.assertContains(duplicate, 'already a product type with this name')

        shoes = ProductType.objects.get(shop=self.shop, name='Shoes')
        Product.objects.create(shop=self.shop, category=Category.objects.create(shop=self.shop, name='X'),
                               product_type=shoes, name='Boot', base_price=1)
        self.client.post(f'/settings/product-types/{shoes.pk}/', {'action': 'delete'})
        self.assertTrue(ProductType.objects.filter(pk=shoes.pk).exists())
        self.client.post(f'/settings/product-types/{watches.pk}/', {'action': 'delete'})
        self.assertFalse(ProductType.objects.filter(pk=watches.pk).exists())

    def test_other_shops_types_are_not_reachable(self):
        other = Shop.objects.create(name='Other')
        self.login('manager')
        theirs = ProductType.objects.get(shop=other, name='Shoes')
        self.assertEqual(self.client.get(f'/settings/product-types/{theirs.pk}/').status_code, 404)


class TeamTests(SettingsTestCase):
    def test_add_member_who_can_then_sign_in(self):
        self.login('owner')
        self.client.post('/settings/team/', {'action': 'add', 'first_name': 'Grace', 'last_name': 'W', 'username': 'grace',
                                             'password': 'temporary-123', 'role': 'cashier'})
        membership = Membership.objects.get(user__username='grace')
        self.assertEqual((membership.shop, membership.role), (self.shop, 'cashier'))
        self.client.logout()
        self.assertTrue(self.client.login(username='grace', password='temporary-123'))

    def test_last_owner_cannot_be_removed_or_demoted(self):
        self.login('owner')
        owner_membership = Membership.objects.get(user__username='owner')
        self.client.post('/settings/team/', {'action': 'role', 'member': owner_membership.pk, 'role': 'cashier'})
        self.client.post('/settings/team/', {'action': 'remove', 'member': owner_membership.pk})
        owner_membership.refresh_from_db()
        self.assertEqual(owner_membership.role, 'owner')

    def test_change_role_and_remove(self):
        self.login('owner')
        cashier = Membership.objects.get(user__username='cashier')
        self.client.post('/settings/team/', {'action': 'role', 'member': cashier.pk, 'role': 'manager'})
        cashier.refresh_from_db()
        self.assertEqual(cashier.role, 'manager')
        self.client.post('/settings/team/', {'action': 'remove', 'member': cashier.pk})
        self.assertFalse(Membership.objects.filter(pk=cashier.pk).exists())

    def test_cashiers_can_add_products_switch(self):
        self.login('owner')
        self.client.post('/settings/team/', {'action': 'settings'})  # unticked checkbox = off
        self.shop.refresh_from_db()
        self.assertFalse(self.shop.cashiers_can_add_products)


class NewPagesTests(SettingsTestCase):
    def test_reports_page_and_signin_page(self):
        self.login('cashier')
        self.assertContains(self.client.get('/reports/'), 'Spreadsheet (CSV)')
        self.client.logout()
        self.assertContains(self.client.get('/accounts/login/'), 'Sign in to your shop')
