"""The owner's review of 26 Oct: Home, Conversations, dates, photos and logo, categories, reasons, one capture button."""
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
from dashboard import selectors as home
from intents import services
from intents.models import BlockedPurchaseIntent as Intent, Visit
from notifications import inbound
from notifications.models import Conversation, Message
from products.models import Category, Product, ProductType, ProductVariation

MEDIA = tempfile.mkdtemp()


def picture(size=(1200, 600), colour='black', fmt='PNG'):
    buffer = BytesIO()
    Image.new('RGB', size, colour).save(buffer, format=fmt)
    return SimpleUploadedFile(f'pic.{fmt.lower()}', buffer.getvalue(), content_type=f'image/{fmt.lower()}')


@override_settings(MEDIA_ROOT=MEDIA)
class FeedbackCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.shop = Shop.objects.create(name='Premium Store')
        self.owner = User.objects.create_user('owner', password='pw12345!')
        Membership.objects.create(user=self.owner, shop=self.shop, role=Membership.OWNER)
        self.client.login(username='owner', password='pw12345!')
        self.shoes = ProductType.objects.get(shop=self.shop, name='Shoes')
        self.clothing = ProductType.objects.get(shop=self.shop, name='Clothing')
        self.running = Category.objects.create(shop=self.shop, name='Running', product_type=self.shoes)
        self.denim = Category.objects.create(shop=self.shop, name='Denim', product_type=self.clothing)
        self.boost = Product.objects.create(shop=self.shop, category=self.running, product_type=self.shoes,
                                            name='Adidas Ultraboost', base_price=18700)
        self.grey42 = ProductVariation.objects.create(product=self.boost, option1='42', option2='Grey', sku='AU-42-GRE')
        self.n = 0

    def customer(self, name):
        self.n += 1
        return Customer.objects.create(shop=self.shop, first_name=name, last_name='K', phone_number=f'+2547110000{self.n:02d}')

    def told(self, name):
        """A customer who was messaged that their size is back."""
        intent = services.create_blocked_purchase_intent(self.customer(name), self.boost, self.grey42, Intent.SIZE_MISSING)
        with self.captureOnCommitCallbacks(execute=True):
            from products.services import receive_stock
            receive_stock(self.grey42.pk, 1)
        intent.refresh_from_db()
        return intent


class NeedsYouNowTests(FeedbackCase):
    def test_read_but_unanswered_still_needs_you_until_you_reply(self):
        jane = self.told('Jane')
        with self.captureOnCommitCallbacks(execute=True):
            inbound.receive('whatsapp', jane.customer.phone_number, 'Can I pay on Saturday?')
        conversation = Conversation.objects.get(customer=jane.customer)
        self.client.get(f'/notifications/c/{conversation.pk}/')  # opened = read
        rows = home.needs_you(self.shop)
        self.assertEqual(rows[0]['kind'], 'reply')
        self.assertIn('Jane is waiting for your answer', rows[0]['title'])
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f'/notifications/c/{conversation.pk}/', {'action': 'reply', 'body': 'Yes, see you then'})
        self.assertNotIn('reply', [r['kind'] for r in home.needs_you(self.shop)])

    def test_waiting_customers_come_before_failed_messages(self):
        failed_for = self.customer('Peter')
        intent = services.create_blocked_purchase_intent(failed_for, self.boost, None, Intent.OUT_OF_STOCK)
        Message.objects.create(shop=self.shop, conversation=Conversation.objects.create(shop=self.shop, customer=failed_for),
                               intent=intent, direction=Message.OUTBOUND, channel=Message.WHATSAPP, body='x',
                               status=Message.FAILED, error_code='63015', error_detail='Not joined')
        jane = self.told('Jane')
        with self.captureOnCommitCallbacks(execute=True):
            inbound.receive('whatsapp', jane.customer.phone_number, 'Yes')
        self.assertEqual([r['kind'] for r in home.needs_you(self.shop)], ['reply', 'failed'])

    def test_dismiss_hides_only_the_alert(self):
        peter = self.customer('Peter')
        intent = services.create_blocked_purchase_intent(peter, self.boost, None, Intent.OUT_OF_STOCK)
        message = Message.objects.create(shop=self.shop, conversation=Conversation.objects.create(shop=self.shop, customer=peter),
                                         intent=intent, direction=Message.OUTBOUND, channel=Message.WHATSAPP, body='x',
                                         status=Message.FAILED, error_code='network', error_detail='HTTPSConnectionPool…')
        row = home.needs_you(self.shop)[0]
        self.assertIn('internet problem', row['sub'])
        self.client.post(f'/dashboard/dismiss/{message.pk}/')
        self.assertEqual(home.needs_you(self.shop), [])
        intent.refresh_from_db()
        self.assertEqual(intent.status, Intent.OPEN)  # the customer isn't lost

    def test_home_shows_five_and_the_rest_on_show_all(self):
        for i in range(7):
            c = self.customer(f'C{i}')
            conv = Conversation.objects.create(shop=self.shop, customer=c, last_inbound_at=timezone.now())
            Message.objects.create(shop=self.shop, conversation=conv, direction=Message.INBOUND, channel='whatsapp',
                                   body=f'hello {i}', status=Message.RECEIVED)
        page = self.client.get('/dashboard/').content.decode()
        self.assertIn('Show all (7)', page)
        self.assertEqual(page.count('is waiting for your answer'), 7)


class ConversationOrderTests(FeedbackCase):
    def test_newest_message_first_like_whatsapp(self):
        old = Conversation.objects.create(shop=self.shop, customer=self.customer('Old'), unread_count=3,
                                          last_message_at=timezone.now() - timedelta(days=4))
        new = Conversation.objects.create(shop=self.shop, customer=self.customer('New'), unread_count=0,
                                          last_message_at=timezone.now())
        for conv in (old, new):
            Message.objects.create(shop=self.shop, conversation=conv, direction=Message.INBOUND, channel='whatsapp',
                                   body='hi', status=Message.RECEIVED)
        rows = self.client.get('/notifications/?show=all').context['conversations']
        self.assertEqual([c.pk for c in rows], [new.pk, old.pk])

    def test_automatic_messages_bring_the_chat_up(self):
        jane = self.told('Jane')
        conversation = Conversation.objects.get(customer=jane.customer)
        self.assertIsNotNone(conversation.last_message_at)


class DateLimitTests(FeedbackCase):
    def test_arrival_date_must_be_within_a_year(self):
        intent = services.create_blocked_purchase_intent(self.customer('Jane'), self.boost, self.grey42, Intent.SIZE_MISSING)
        for bad in ('275760-04-25', '2019-01-01', (timezone.localdate() + timedelta(days=400)).isoformat()):
            response = self.client.post('/intents/mark-ordered/', {'intent': [intent.pk], 'expected_at': bad}, follow=True)
            self.assertContains(response, 'must be between today and')
            intent.refresh_from_db()
            self.assertEqual(intent.status, Intent.OPEN)
        page = self.client.get('/intents/to-order/').content.decode()
        self.assertIn(f'min="{timezone.localdate().isoformat()}"', page)

    def test_api_refuses_impossible_dates(self):
        intent = services.create_blocked_purchase_intent(self.customer('Jane'), self.boost, self.grey42, Intent.SIZE_MISSING)
        response = self.client.post(f'/api/intents/{intent.pk}/mark-ordered/', {'expected_at': '2999-01-01'},
                                    content_type='application/json')
        self.assertEqual(response.status_code, 400)


class PhotoAndLogoTests(FeedbackCase):
    def product_post(self, **extra):
        data = {'name': 'Adidas Ultraboost', 'product_type': self.shoes.pk, 'category': self.running.pk,
                'base_price': '18700', 'description': '', 'supplier': ''}
        data.update(extra)
        return self.client.post(f'/products/update/{self.boost.pk}/', data)

    def test_choosing_a_new_photo_replaces_the_old_and_remove_clears_it(self):
        self.product_post(image=picture(colour='red'))
        self.boost.refresh_from_db()
        first = self.boost.image.name
        self.assertTrue(first)
        # A new photo while "remove" is ticked: the new photo wins, no error.
        response = self.product_post(image=picture(colour='blue'), remove_image='on')
        self.assertEqual(response.status_code, 302)
        self.boost.refresh_from_db()
        self.assertNotEqual(self.boost.image.name, first)
        self.product_post(remove_image='on')
        self.boost.refresh_from_db()
        self.assertFalse(self.boost.image)

    def test_logo_is_made_square_and_shown(self):
        self.client.post('/settings/shop/', {'name': 'Premium Store', 'phone_region': 'KE', 'currency': 'KES',
                                             'timezone': 'Africa/Nairobi', 'logo': picture(size=(1600, 400))})
        self.shop.refresh_from_db()
        with Image.open(self.shop.logo.path) as logo:
            self.assertEqual(logo.size, (256, 256))
        self.assertContains(self.client.get('/dashboard/'), 'class="brand-mark brand-logo"')
        self.client.logout()
        self.assertContains(self.client.get('/accounts/login/'), 'brand-logo')


class CategoryTests(FeedbackCase):
    def add(self, **data):
        base = {'name': 'Item', 'base_price': '1000', 'description': '', 'supplier': ''}
        base.update(data)
        return self.client.post('/products/create/', base)

    def test_category_must_match_the_type(self):
        response = self.add(product_type=self.shoes.pk, category=self.denim.pk)
        self.assertContains(response, 'Denim belongs to Clothing')
        self.assertFalse(Product.objects.filter(name='Item').exists())

    def test_type_a_new_category(self):
        self.add(product_type=self.shoes.pk, new_category='Casual')
        product = Product.objects.get(name='Item')
        self.assertEqual((product.category.name, product.category.product_type), ('Casual', self.shoes))

    def test_other_must_say_what_it_is(self):
        other = ProductType.objects.get(shop=self.shop, name='Other')
        response = self.add(product_type=other.pk)
        self.assertContains(response, 'Say what it is')
        self.add(product_type=other.pk, new_category='Watches')
        self.assertEqual(Product.objects.get(name='Item').category.name, 'Watches')

    def test_options_carry_their_type_for_filtering(self):
        page = self.client.get('/products/create/').content.decode()
        self.assertIn(f'data-type="{self.shoes.pk}"', page)


class ReasonAndCaptureTests(FeedbackCase):
    def test_one_price_reason_on_the_floor(self):
        page = self.client.get('/floor/?start=item').content.decode()
        self.assertIn('Price too high / over budget', page)
        self.assertNotIn('value="over_budget"', page)

    def test_old_over_budget_records_count_with_price(self):
        services.create_blocked_purchase_intent(self.customer('A'), self.boost, None, Intent.OVER_BUDGET)
        services.create_blocked_purchase_intent(self.customer('B'), self.boost, None, Intent.PRICE_TOO_HIGH)
        rows = home.reasons(self.shop, {'start': None, 'end': None})
        self.assertEqual(rows, [{'label': 'Price too high / over budget', 'count': 2, 'percent': 100}])

    def test_they_bought_after_all_from_log_missed_sale(self):
        page = self.client.get('/floor/?start=item').content.decode()
        self.assertIn('They bought after all', page)
        self.assertNotIn('>Floor mode<', self.client.get('/dashboard/').content.decode())
        self.client.post('/floor/', {'action': 'bought'})
        self.assertEqual(Visit.objects.filter(outcome=Visit.BOUGHT).count(), 1)

    def test_process_due_once(self):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('process_due', stdout=out)
        self.assertIn('follow ups sent: 0', out.getvalue())
