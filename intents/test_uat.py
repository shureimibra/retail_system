"""
UAT walkthrough: every customer scenario end to end, through the same screens staff use.
Each test is one row of docs/uat/uat-checklist.md. Messages go through the simulator, so nothing is sent.

Who moves the status (never a drop-down):
  Open         staff log it in Floor mode
  On order     staff: To order / Waiting → Mark as ordered
  Back in stock + Notified   AUTOMATIC when staff receive stock (unit held, message sent)
  In conversation            AUTOMATIC when the customer replies
  Reserved / Recovered       staff record a deposit / full payment (or M-Pesa confirms it)
  Declined     staff close it;   Expired   AUTOMATIC (no reply, not collected, quiet, 30 days)
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import Membership, Shop, User
from customers.models import Customer
from dashboard import selectors as home
from intents import services
from intents.automation import process_due
from intents.models import BlockedPurchaseIntent as Intent, Visit
from notifications import inbound
from notifications.models import Conversation, Message
from products.models import Category, Product, ProductType, ProductVariation


class UATCase(TestCase):
    def setUp(self):
        self.shop = Shop.objects.create(name='Premium Store')
        self.users = {}
        for role in (Membership.OWNER, Membership.CASHIER):
            user = User.objects.create_user(role, password='pw12345!', first_name=role.title())
            Membership.objects.create(user=user, shop=self.shop, role=role)
            self.users[role] = user
        shoes = ProductType.objects.get(shop=self.shop, name='Shoes')
        category = Category.objects.create(shop=self.shop, name='Shoes')
        self.boost = Product.objects.create(shop=self.shop, category=category, product_type=shoes, name='Adidas Ultraboost',
                                            base_price=18700, supplier='Kicks Wholesale')
        self.grey42 = ProductVariation.objects.create(product=self.boost, option1='42', option2='Grey', sku='AU-42-GRE')
        self.grey44 = ProductVariation.objects.create(product=self.boost, option1='44', option2='Grey', sku='AU-44-GRE',
                                                      stock_quantity=3)
        self.as_role('owner')

    # --- what staff do ------------------------------------------------------------------
    def as_role(self, role):
        self.client.logout()
        self.client.login(username=role, password='pw12345!')

    def floor(self, phone='0797278281', name='Ibrahim K', product=None, variation=None, reason=Intent.SIZE_MISSING,
              consent=True, **extra):
        data = {'product': product if isinstance(product, str) else (product or self.boost).pk, 'reason': reason, 'phone': phone, 'name': name, 'within': '',
                'then': 'done'}
        if variation is not None:
            data['variation'] = variation.pk
        if consent:
            data['consent'] = 'yes'
        data.update(extra)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post('/floor/', data, follow=True)

    def latest(self):
        return Intent.objects.order_by('-pk').first()

    def receive(self, variation, quantity):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(f'/products/{variation.product_id}/',
                                    {'action': 'receive', 'variation': variation.pk, 'quantity': quantity})

    def reply(self, phone, body):
        with self.captureOnCommitCallbacks(execute=True):
            return inbound.receive('whatsapp', f'whatsapp:{phone}', body)

    def chat(self, intent, data):
        conversation = Conversation.objects.get(customer=intent.customer)
        data.setdefault('intent', intent.pk)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(f'/notifications/c/{conversation.pk}/', data, follow=True)

    def due(self, days):
        with self.captureOnCommitCallbacks(execute=True):
            return process_due(now=timezone.now() + timedelta(days=days))

    def status(self, intent):
        intent.refresh_from_db()
        return intent.status

    def sent(self, intent, key):
        return Message.objects.filter(intent=intent, template_key=key, direction=Message.OUTBOUND).count()


class S01_SizeMissingAllTheWayToPaid(UATCase):
    """The main road: log → order → receive → told → reply → deposit → paid."""

    def test_full_journey(self):
        self.floor(variation=self.grey42)
        jane = self.latest()
        self.assertEqual(self.status(jane), Intent.OPEN)
        self.assertEqual(self.client.get('/intents/to-order/').context['item_count'], 1)

        arrives = timezone.localdate() + timedelta(days=40)
        self.client.post('/intents/mark-ordered/', {'intent': [jane.pk], 'expected_at': arrives.isoformat()})
        self.assertEqual(self.status(jane), Intent.ON_ORDER)
        self.assertGreater(jane.expires_at.date(), arrives)  # ordered items don't expire before they arrive

        self.receive(self.grey42, 1)  # AUTOMATIC from here: hold + message
        self.assertEqual(self.status(jane), Intent.NOTIFIED)
        self.assertEqual(self.sent(jane, 'restock_alert'), 1)

        self.reply('+254797278281', 'Yes, can I pay a deposit?')  # AUTOMATIC: in conversation, reminders stop
        self.assertEqual(self.status(jane), Intent.IN_CONVERSATION)
        self.assertEqual(self.due(3)['follow_ups_sent'], 0)

        self.chat(jane, {'action': 'deposit', 'amount': '5000', 'method': 'mpesa', 'reference': 'QK7H2L9'})
        self.assertEqual(self.status(jane), Intent.RESERVED)
        self.assertEqual(self.sent(jane, 'deposit_receipt'), 1)

        self.chat(jane, {'action': 'paid', 'method': 'cash'})
        self.assertEqual(self.status(jane), Intent.RECOVERED)
        self.grey42.refresh_from_db()
        self.assertEqual(self.grey42.stock_quantity, 0)  # the held unit was sold
        numbers = home.key_numbers(self.shop, {'start': None, 'end': None})
        self.assertEqual((numbers['recovered_money'], numbers['recovered_count']), (18700.0, 1))


class S02_InStockSizeCannotBeLoggedAsMissing(UATCase):
    def test_refused_with_a_clear_message_but_price_reasons_are_fine(self):
        page = self.floor(variation=self.grey44, reason=Intent.SIZE_MISSING)
        self.assertContains(page, 'is in stock (3 free)')
        self.assertFalse(Intent.objects.exists())
        self.assertFalse(Customer.objects.exists())  # nothing half-saved

        self.floor(variation=self.grey44, reason=Intent.PRICE_TOO_HIGH)
        self.assertEqual(self.latest().constraint_type, Intent.PRICE_TOO_HIGH)
        self.assertEqual(self.client.get('/intents/to-order/').context['item_count'], 0)  # price isn't an order


class S03_ColourNeverStocked(UATCase):
    def test_typed_colour_becomes_an_option_to_order_and_receive(self):
        self.floor(new_option1='42', new_option2='Black', reason=Intent.COLOUR_MISSING)
        mary = self.latest()
        self.assertEqual((mary.variation.label, mary.variation.stock_quantity), ('42 / Black', 0))
        rows = self.client.get('/intents/to-order/').context['groups'][0]['rows']
        self.assertEqual(rows[0]['variation_label'], '42 / Black')
        self.receive(mary.variation, 2)
        self.assertEqual(self.status(mary), Intent.NOTIFIED)

        # Typing an option that exists reuses it instead of duplicating.
        self.floor(phone='0711000222', name='Ali', new_option1='42', new_option2='black', reason=Intent.COLOUR_MISSING)
        self.assertEqual(self.latest().variation_id, mary.variation_id)


class S04_ItemTheShopDoesNotCarry(UATCase):
    def test_cashier_adds_it_from_the_floor_for_review(self):
        self.as_role('cashier')
        shoes = ProductType.objects.get(shop=self.shop, name='Shoes')
        self.floor(product='new', new_option1='40', new_option2='White', reason=Intent.OUT_OF_STOCK,
                   new_name='Puma Suede Classic', new_type=shoes.pk, new_price='9500')
        item = self.latest()
        self.assertEqual((item.product.name, item.product.needs_review, item.variation.label), ('Puma Suede Classic', True, '40 / White'))
        self.as_role('owner')
        self.assertIn('Puma Suede Classic', [r['product_name'] for r in home.to_order_top(self.shop)])

    def test_cashier_cannot_add_items_when_the_owner_turned_it_off(self):
        self.shop.cashiers_can_add_products = False
        self.shop.save()
        self.as_role('cashier')
        page = self.floor(product='new', new_name='Mystery', new_price='100')
        self.assertContains(page, 'Ask the owner or a manager to add new items')
        self.assertFalse(Product.objects.filter(name='Mystery').exists())


class S05_AnySizeWillDo(UATCase):
    def test_any_size_customer_is_told_when_any_size_arrives(self):
        self.floor(reason=Intent.OUT_OF_STOCK)  # no size chosen
        any_size = self.latest()
        self.receive(self.grey42, 1)
        self.assertEqual(self.status(any_size), Intent.NOTIFIED)


class S06_PriceTooHigh(UATCase):
    def test_lower_price_tells_them_and_a_higher_one_does_not(self):
        self.floor(variation=self.grey44, reason=Intent.OVER_BUDGET)
        ali = self.latest()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f'/products/{self.boost.pk}/', {'action': 'price', 'price': '19900'})
        self.assertEqual(self.sent(ali, 'price_drop'), 0)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f'/products/{self.boost.pk}/', {'action': 'price', 'price': '16500'})
        self.assertEqual(self.sent(ali, 'price_drop'), 1)
        self.assertEqual(self.status(ali), Intent.NOTIFIED)
        # Receiving stock does not message price customers.
        self.receive(self.grey44, 2)
        self.assertEqual(self.sent(ali, 'restock_alert'), 0)


class S07_SomethingElse(UATCase):
    def test_note_is_required_and_next_step_is_to_follow_up(self):
        page = self.floor(reason=Intent.OTHER)
        self.assertContains(page, 'Write a short note')
        self.floor(reason=Intent.OTHER, note='Wants it gift-wrapped by Friday')
        item = self.latest()
        self.assertEqual(item.notes, 'Wants it gift-wrapped by Friday')
        self.assertIn('Follow up', self.client.get('/intents/?show=all').content.decode())


class S08_NoConsentToMessages(UATCase):
    def test_unit_is_held_and_staff_are_told_to_call(self):
        self.floor(variation=self.grey42, consent=False)
        quiet = self.latest()
        self.receive(self.grey42, 1)
        self.assertEqual(self.status(quiet), Intent.BACK_IN_STOCK)
        self.assertEqual(Message.objects.get(intent=quiet).status, Message.SKIPPED)
        self.assertContains(self.client.get(f'/intents/{quiet.pk}/update/'), "didn&#x27;t agree to messages. Call them.")


class S09_TwoCustomersOneUnit(UATCase):
    def test_oldest_first_and_a_decline_passes_the_unit_on(self):
        self.floor(variation=self.grey42, phone='0711000111', name='Jane')
        jane = self.latest()
        self.floor(variation=self.grey42, phone='0711000222', name='John')
        john = self.latest()
        self.receive(self.grey42, 1)
        self.assertEqual((self.status(jane), self.status(john)), (Intent.NOTIFIED, Intent.OPEN))
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f'/intents/{jane.pk}/update/', {'action': 'decline', 'reason': 'Bought elsewhere'})
        self.assertEqual(self.status(jane), Intent.DECLINED)
        self.assertEqual(self.status(john), Intent.NOTIFIED)


class S10_CustomerSaysStop(UATCase):
    def test_stop_ends_all_messages(self):
        self.floor(variation=self.grey42)
        jane = self.latest()
        self.receive(self.grey42, 1)
        self.reply('+254797278281', 'STOP')
        jane.customer.refresh_from_db()
        self.assertFalse(jane.customer.marketing_opt_in)
        self.due(3)
        self.assertEqual(Message.objects.filter(intent=jane, template_key='reminder_1', status=Message.SKIPPED).count(), 1)


class S11_NoReplyAtAll(UATCase):
    def test_reminders_then_expiry_then_next_customer(self):
        self.floor(variation=self.grey42, phone='0711000111', name='Jane')
        jane = self.latest()
        self.floor(variation=self.grey42, phone='0711000222', name='John')
        john = self.latest()
        self.receive(self.grey42, 1)
        for day in (2, 4, 7):
            self.due(day)
        self.assertEqual([self.sent(jane, k) for k in ('reminder_1', 'reminder_2', 'reminder_3')], [1, 1, 1])
        self.due(8)
        self.assertEqual((self.status(jane), self.status(john)), (Intent.EXPIRED, Intent.NOTIFIED))


class S12_RepliedThenWentQuiet(UATCase):
    def test_no_deposit_before_the_hold_ends_frees_the_unit(self):
        self.floor(variation=self.grey42, phone='0711000111', name='Jane')
        jane = self.latest()
        self.floor(variation=self.grey42, phone='0711000222', name='John')
        john = self.latest()
        self.receive(self.grey42, 1)
        self.reply('+254711000111', 'Maybe')
        self.due(9)
        self.assertEqual((self.status(jane), self.status(john)), (Intent.EXPIRED, Intent.NOTIFIED))


class S13_PickupDay(UATCase):
    def test_overdue_without_deposit_expires_and_with_deposit_needs_you(self):
        self.floor(variation=self.grey42)
        jane = self.latest()
        self.receive(self.grey42, 1)
        self.reply('+254797278281', 'Yes')
        self.chat(jane, {'action': 'deposit', 'amount': '2000', 'method': 'cash'})
        Intent.objects.filter(pk=jane.pk).update(pickup_by=timezone.localdate() - timedelta(days=1))
        self.due(0)
        self.assertEqual(self.status(jane), Intent.RESERVED)
        self.assertIn('pickup', [row['kind'] for row in home.needs_you(self.shop)])


class S14_ChangeItemInTheChat(UATCase):
    def test_hold_moves_to_the_new_size(self):
        self.floor(variation=self.grey42)
        jane = self.latest()
        self.receive(self.grey42, 1)
        self.reply('+254797278281', 'Do you have 44?')
        self.chat(jane, {'action': 'change', 'variation': self.grey44.pk})
        jane.refresh_from_db()
        self.assertEqual(jane.variation, self.grey44)
        self.assertEqual(jane.holds.filter(status='active').get().variation, self.grey44)
        self.grey42.refresh_from_db()
        self.assertEqual(self.grey42.available_quantity, 1)  # the 42 went back on sale


class S15_SameCustomerAnotherItem(UATCase):
    def test_counts_as_one_visit(self):
        response = self.floor(variation=self.grey42, then='another')
        first = self.latest()
        self.floor(new_option1='45', new_option2='Grey', visit=first.visit_id, reason=Intent.SIZE_MISSING)
        self.assertEqual(Visit.objects.count(), 1)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertTrue(response.redirect_chain[-1][0].startswith('/floor/?start=item&customer='))


class S16_CashierDoesTheFloorAndTheChat(UATCase):
    def test_what_a_cashier_can_and_cannot_do(self):
        self.as_role('cashier')
        self.floor(variation=self.grey42)
        jane = self.latest()
        for url in ('/intents/to-order/', '/reports/', '/settings/payments/'):
            self.assertEqual(self.client.get(url).status_code, 403, url)
        self.assertEqual(self.client.post(f'/products/{self.boost.pk}/', {'action': 'receive', 'variation': self.grey42.pk,
                                                                          'quantity': 1}).status_code, 403)
        self.as_role('owner')
        self.receive(self.grey42, 1)
        self.as_role('cashier')
        self.reply('+254797278281', 'Yes')
        self.chat(jane, {'action': 'reply', 'body': 'Great, see you Saturday'})
        self.chat(jane, {'action': 'deposit', 'amount': '3000', 'method': 'mpesa'})
        self.assertEqual(self.status(jane), Intent.RESERVED)


class S17_LiveChatAndCheckIn(UATCase):
    def test_new_reply_arrives_without_refresh_and_check_in_is_always_there(self):
        self.floor(variation=self.grey42)
        jane = self.latest()
        self.receive(self.grey42, 1)
        self.reply('+254797278281', 'Yes')
        conversation = Conversation.objects.get(customer=jane.customer)
        page = self.client.get(f'/notifications/c/{conversation.pk}/')
        self.assertContains(page, 'Send the check-in message instead')
        last = conversation.messages.order_by('-pk').first().pk
        self.reply('+254797278281', 'Can I pay a deposit?')
        data = self.client.get(f'/notifications/c/{conversation.pk}/updates/?after={last}').json()
        self.assertEqual(data['count'], 1)
        self.assertIn('Can I pay a deposit?', data['html'])
        conversation.refresh_from_db()
        self.assertEqual(conversation.unread_count, 0)


class S18_WaitingShowsTheNextStep(UATCase):
    def test_each_status_says_what_to_do(self):
        self.floor(variation=self.grey42, phone='0711000111', name='Jane')
        self.floor(variation=self.grey44, reason=Intent.PRICE_TOO_HIGH, phone='0711000222', name='Ali')
        page = self.client.get('/intents/?show=all').content.decode()
        self.assertIn('Next: Order it from your supplier.', page)
        self.assertIn('Next: Waiting for a lower price.', page)
        self.assertIn('0 in stock', page)
        self.as_role('cashier')
        self.assertIn('Waiting for the owner or a manager to order it.', self.client.get('/intents/?show=all').content.decode())
