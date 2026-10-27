"""Phase 7: invitations, "Set up your shop" and the demo shop."""
import re
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts import services
from accounts.models import Invitation, Membership, Shop, User
from customers.models import Customer
from intents.demo import end_demo, remove_old_demos
from intents.models import BlockedPurchaseIntent as Intent
from notifications import inbound
from notifications.models import Message


class InvitationTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_superuser('ops', password='pw12345!x')

    def invite_shop(self):
        self.client.login(username='ops', password='pw12345!x')
        page = self.client.post('/ops/invite-shop/', {'shop_name': 'Mama Njeri Fashions', 'owner_name': 'Njeri Kamau',
                                                       'contact': 'njeri@example.com'}).content.decode()
        self.client.logout()
        return re.search(r'value="(http[^"]+/accounts/invite/[^"]+/)"', page).group(1)

    def accept(self, path, **extra):
        data = {'first_name': 'Njeri', 'last_name': 'Kamau', 'username': 'njeri', 'password': 'kitenge-2026!',
                'password_again': 'kitenge-2026!'}
        data.update(extra)
        return self.client.post(path, data)

    def test_the_team_invites_a_new_shop_and_the_owner_lands_in_setup(self):
        link = self.invite_shop()
        shop = Shop.objects.get(name='Mama Njeri Fashions')
        self.assertTrue(shop.product_types.exists())  # fashion basics ready for step 2
        path = link.split('testserver')[-1] if 'testserver' in link else '/' + link.split('/', 3)[3]
        page = self.client.get(path)
        self.assertContains(page, 'Join Mama Njeri Fashions')
        self.assertContains(page, 'value="Njeri"')
        response = self.accept(path)
        self.assertRedirects(response, '/setup/', fetch_redirect_response=False)
        njeri = User.objects.get(username='njeri')
        self.assertEqual(Membership.objects.get(user=njeri).shop, shop)
        self.assertEqual(njeri.email, 'njeri@example.com')
        # The link works once.
        self.client.logout()
        self.assertEqual(self.client.get(path).status_code, 410)

    def test_links_expire_and_only_a_hash_is_kept(self):
        shop = Shop.objects.create(name='S')
        invitation, raw = services.create_invitation(shop, Membership.CASHIER, 'Ben')
        self.assertNotIn(raw, invitation.token_hash)
        Invitation.objects.filter(pk=invitation.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.client.get(f'/accounts/invite/{raw}/').status_code, 410)
        self.assertEqual(self.client.get('/accounts/invite/not-a-real-link/').status_code, 410)

    def test_mistakes_are_explained(self):
        shop = Shop.objects.create(name='S')
        User.objects.create_user('njeri', password='x')
        _, raw = services.create_invitation(shop, Membership.OWNER, 'Njeri')
        page = self.accept(f'/accounts/invite/{raw}/', password_again='different-2026!').content.decode()
        self.assertIn('username is taken', page)
        self.assertIn("passwords don&#x27;t match", page)
        page = self.accept(f'/accounts/invite/{raw}/', username='njeri2', password='12345678',
                           password_again='12345678').content.decode()
        self.assertIn('entirely numeric', page)
        self.assertFalse(Membership.objects.exists())

    def test_someone_signed_in_is_asked_to_sign_out_first(self):
        shop = Shop.objects.create(name='S')
        _, raw = services.create_invitation(shop, Membership.CASHIER, 'Ben')
        self.client.login(username='ops', password='pw12345!x')
        self.assertContains(self.client.get(f'/accounts/invite/{raw}/'), 'Sign out first')

    def test_shop_owners_invite_staff_with_a_link(self):
        shop = Shop.objects.create(name='Mama Njeri Fashions')
        owner = User.objects.create_user('njeri', password='pw12345!x')
        Membership.objects.create(user=owner, shop=shop, role=Membership.OWNER)
        self.client.login(username='njeri', password='pw12345!x')
        page = self.client.post('/settings/team/', {'action': 'invite', 'name': 'Ben Otieno', 'role': 'cashier'},
                                follow=True).content.decode()
        self.assertIn('Shown once', page)
        self.assertIn('wa.me/?text=', page)
        path = re.search(r'value="http[^"]+?(/accounts/invite/[^"]+/)"', page).group(1)
        self.client.logout()
        response = self.accept(path, first_name='Ben', username='ben')
        self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)
        self.assertEqual(Membership.objects.get(user__username='ben').role, Membership.CASHIER)

    def test_only_operators_invite_shops(self):
        User.objects.create_user('someone', password='pw12345!x')
        self.client.login(username='someone', password='pw12345!x')
        self.assertEqual(self.client.get('/ops/invite-shop/').status_code, 302)  # to the operators' sign-in


class SetupTests(TestCase):
    def setUp(self):
        self.shop = Shop.objects.create(name='Mama Njeri Fashions')
        self.owner = User.objects.create_user('njeri', password='pw12345!x')
        Membership.objects.create(user=self.owner, shop=self.shop, role=Membership.OWNER)
        self.client.login(username='njeri', password='pw12345!x')

    def test_steps_tick_off_by_themselves_or_by_hand(self):
        page = self.client.get('/setup/').content.decode()
        self.assertIn('0 of 6 done', page)
        self.shop.payment_details = 'M-Pesa Till 999'
        self.shop.save()
        self.client.post('/setup/', {'action': 'done:types'})
        self.client.post('/setup/', {'action': 'skip:team'})
        page = self.client.get('/setup/').content.decode()
        self.assertIn('3 of 6 done', page)
        self.assertIn('Skipped', page)
        self.client.post('/setup/', {'action': 'undo:team'})
        self.assertIn('2 of 6 done', self.client.get('/setup/').content.decode())

    def test_each_step_opens_the_real_page_with_a_way_back(self):
        response = self.client.post('/setup/', {'action': 'open:products'})
        self.assertRedirects(response, '/products/import/', fetch_redirect_response=False)
        self.assertContains(self.client.get('/products/import/'), 'Back to Set up your shop')
        self.client.get('/setup/')
        self.assertNotContains(self.client.get('/products/import/'), 'Back to Set up your shop')

    def test_one_line_on_home_until_finished_or_hidden(self):
        self.assertContains(self.client.get('/dashboard/'), 'Finish setting up your shop · 0 of 6')
        self.client.post('/setup/', {'action': 'later'})
        self.assertContains(self.client.get('/dashboard/'), 'Finish setting up your shop')
        self.client.post('/setup/', {'action': 'close'})
        self.assertNotContains(self.client.get('/dashboard/'), 'Finish setting up your shop')

    def test_staff_do_not_set_up_the_shop(self):
        cashier = User.objects.create_user('ben', password='pw12345!x')
        Membership.objects.create(user=cashier, shop=self.shop, role=Membership.CASHIER)
        self.client.login(username='ben', password='pw12345!x')
        self.assertEqual(self.client.get('/setup/').status_code, 403)
        self.assertNotContains(self.client.get('/dashboard/'), 'Finish setting up')


@override_settings(MESSAGING_PROVIDERS={'whatsapp': 'twilio_whatsapp', 'sms': 'twilio', 'email': 'email'},
                   SIMULATOR_ENABLED=False)
class DemoTests(TestCase):
    def setUp(self):
        cache.clear()

    def open_demo(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post('/demo/')
        return response, Shop.objects.filter(is_demo=True).order_by('-id').first()

    def test_a_visitor_gets_their_own_sample_shop(self):
        self.assertContains(self.client.get('/accounts/login/'), 'Try the demo shop')
        response, shop = self.open_demo()
        self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)
        self.assertEqual(shop.products.count(), 4)
        self.assertTrue(shop.intents.filter(status=Intent.RESERVED).exists())
        home = self.client.get('/dashboard/').content.decode()
        self.assertIn('Demo shop.', home)
        self.assertNotIn('Finish setting up', home)
        self.assertEqual(self.client.get('/notifications/simulator/').status_code, 200)  # even with it off elsewhere

    def test_demo_messages_never_leave_retail_os(self):
        _, shop = self.open_demo()
        sent = Message.objects.filter(shop=shop, direction=Message.OUTBOUND)
        self.assertTrue(sent.exists())
        self.assertEqual(set(sent.values_list('provider', flat=True)) - {''}, {'simulator'})
        self.assertEqual(self.client.get(f'/ask/{shop.link_name or "x"}/').status_code, 404)

    def test_real_replies_never_reach_a_demo_customer(self):
        _, shop = self.open_demo()
        number = shop.customers.first().phone_number
        message, _ = inbound.receive('whatsapp', number, 'Hello')
        self.assertIsNone(message.conversation)
        real = Shop.objects.create(name='Real')
        Customer.objects.create(shop=real, first_name='Real', phone_number=number)
        message, _ = inbound.receive('whatsapp', number, 'Hello again')
        self.assertEqual(message.conversation.shop, real)

    def test_mpesa_prompts_are_off_in_the_demo(self):
        from payments.services import request_payment
        _, shop = self.open_demo()
        intent = shop.intents.filter(status=Intent.RESERVED).first()
        with self.assertRaisesMessage(ValueError, 'M-Pesa is off in the demo shop'):
            request_payment(intent, 100, '0712345678')

    def test_start_over_gives_a_fresh_copy_and_removes_the_old(self):
        _, first = self.open_demo()
        _, second = self.open_demo()
        self.assertNotEqual(first.pk, second.pk)
        self.assertFalse(Shop.objects.filter(pk=first.pk).exists())
        self.assertEqual(User.objects.filter(username__startswith='demo-').count(), 1)

    def test_old_demos_are_removed_and_real_shops_never(self):
        real = Shop.objects.create(name='Real')
        _, shop = self.open_demo()
        Shop.objects.filter(pk=shop.pk).update(created_at=timezone.now() - timedelta(days=3))
        self.assertEqual(remove_old_demos(), 1)
        self.assertTrue(Shop.objects.filter(pk=real.pk).exists())
        self.assertFalse(User.objects.filter(username__startswith='demo-').exists())
        with self.assertRaises(ValueError):
            end_demo(real)

    def test_limits_and_real_accounts(self):
        for _ in range(5):
            self.client.logout()
            self.open_demo()
        self.client.logout()
        self.assertEqual(self.client.post('/demo/').status_code, 429)
        cache.clear()
        User.objects.create_user('njeri', password='pw12345!x')
        self.client.login(username='njeri', password='pw12345!x')
        response = self.client.post('/demo/')
        self.assertContains(response, 'private window', status_code=400)
