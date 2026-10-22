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
