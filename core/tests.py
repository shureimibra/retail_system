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
        intent = create_blocked_purchase_intent(customer, product, variation, 'size_missing', recorded_by=owner)
        self.client.login(username='owner', password='pw12345!')

        for url in ['/dashboard/', '/intents/', '/intents/create/', f'/intents/{intent.id}/update/',
                    '/products/', '/products/create/', f'/products/update/{product.id}/',
                    '/customers/', '/customers/create/', f'/customers/update/{customer.id}/',
                    '/notifications/', '/reports/csv/', '/reports/pdf/', '/api/dashboard/', '/api/analytics/', '/api/reports/']:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


class PeriodTests(TestCase):
    """The period picker on Home and Reports never accepts impossible dates."""

    def setUp(self):
        from django.utils import timezone
        self.today = timezone.localdate()

    def resolve(self, **params):
        from core.periods import resolve_period
        return resolve_period(params)

    def test_default_is_all_time(self):
        period = self.resolve()
        self.assertEqual((period['key'], period['start'], period['end']), ('all', None, None))

    def test_presets(self):
        from datetime import timedelta
        self.assertEqual(self.resolve(period='today')['start'], self.today)
        self.assertEqual(self.resolve(period='7d')['start'], self.today - timedelta(days=6))
        self.assertEqual(self.resolve(period='30d')['start'], self.today - timedelta(days=29))
        self.assertEqual(self.resolve(period='month')['start'], self.today.replace(day=1))

    def test_unknown_period_falls_back(self):
        self.assertEqual(self.resolve(period='forever')['key'], 'all')

    def test_absurd_year_is_ignored(self):
        period = self.resolve(start_date='275760-04-25')
        self.assertEqual((period['key'], period['start']), ('all', None))

    def test_dates_are_clamped_and_swapped(self):
        from datetime import date
        period = self.resolve(period='custom', start_date='2999-01-01', end_date='2010-05-05')
        self.assertEqual((period['start'], period['end']), (date(2020, 1, 1), self.today))

    def test_pages_accept_any_period(self):
        from accounts.models import Membership, default_shop_id
        owner = User.objects.create_user('owner', password='pw12345!')
        Membership.objects.create(user=owner, shop_id=default_shop_id(), role=Membership.OWNER)
        self.client.login(username='owner', password='pw12345!')
        for query in ['', 'period=7d', 'period=custom&start_date=275760-04-25', 'start_date=2024-13-40', 'period=junk']:
            for url in ['/dashboard/', '/reports/']:
                with self.subTest(url=url, query=query):
                    self.assertEqual(self.client.get(f'{url}?{query}').status_code, 200)
