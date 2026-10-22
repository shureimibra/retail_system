from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import Membership, Shop, User
from customers.models import Customer
from intents import services
from intents.models import BlockedPurchaseIntent as Intent
from notifications import inbound
from products.models import Category, Product, ProductType, ProductVariation
from products.services import receive_stock


class Command(BaseCommand):
    help = 'Fill an EMPTY database with a sample fashion shop, for trying Retail OS out. Never touches existing data.'

    def add_arguments(self, parser):
        parser.add_argument('--password', default='demo-pass-123', help='Password for the demo owner "amina".')

    def handle(self, *args, **options):
        # Not one big transaction: messages go out as each step commits, like real use.
        if Product.objects.exists() or Customer.objects.exists():
            raise CommandError('This database already has products or customers. seed_demo only fills an empty database.')

        shop = Shop.objects.order_by('id').first() or Shop.objects.create(name='Kimathi Street Store')
        shop.name = 'Kimathi Street Store'
        shop.save(update_fields=['name'])
        owner, _ = User.objects.get_or_create(username='amina', defaults={'first_name': 'Amina', 'last_name': 'Wanjiru'})
        owner.set_password(options['password'])
        owner.save()
        Membership.objects.get_or_create(user=owner, shop=shop, defaults={'role': Membership.OWNER})

        types = {t.name: t for t in ProductType.objects.filter(shop=shop)}
        running = Category.objects.create(shop=shop, name='Running')
        denim = Category.objects.create(shop=shop, name='Denim')
        bags = Category.objects.create(shop=shop, name='Bags')

        def product(name, category, type_name, price, options):
            p = Product.objects.create(shop=shop, category=category, product_type=types[type_name], name=name, base_price=price)
            variations = {}
            for size, colour, stock in options:
                sku = f"{''.join(w[0] for w in name.split()).upper()}-{size}-{colour[:3].upper()}".replace(' ', '')
                variations[(size, colour)] = ProductVariation.objects.create(product=p, option1=size, option2=colour, sku=sku)
                if stock:
                    receive_stock(variations[(size, colour)].id, stock)
            return p, variations

        nike, nike_v = product('Nike Air Zoom', running, 'Shoes', 12500,
                               [('41', 'Black', 2), ('42', 'Black', 0), ('43', 'Black', 0), ('42', 'White', 5)])
        adidas, adidas_v = product('Adidas Ultraboost', running, 'Shoes', 18700, [('42', 'Grey', 0), ('44', 'Grey', 3)])
        levis, levis_v = product("Levi's 511 Slim", denim, 'Clothing', 7200, [('32', 'Blue', 0), ('34', 'Blue', 4)])
        bag, bag_v = product('Leather Messenger Bag', bags, 'Bags', 14900, [('One size', 'Brown', 1)])

        people = [('Jane', 'Smith', '0722345678'), ('John', 'Doe', '0712345678'), ('Robert', 'Otieno', '0733345678'),
                  ('Mary', 'Achieng', '0744345678'), ('Peter', 'Kamau', '0755345678'), ('Ali', 'Hassan', '0766345678')]
        customers = [Customer.objects.create(shop=shop, first_name=f, last_name=l, phone_number=p) for f, l, p in people]
        jane, john, robert, mary, peter, ali = customers

        def miss(customer, prod, variation, reason, days_ago=0):
            intent = services.create_blocked_purchase_intent(customer, prod, variation, reason, recorded_by=owner)
            Intent.objects.filter(pk=intent.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
            return intent

        for c, days in ((john, 6), (robert, 5), (peter, 3)):
            miss(c, nike, nike_v[('42', 'Black')], Intent.SIZE_MISSING, days)
        jane_request = miss(jane, adidas, adidas_v[('42', 'Grey')], Intent.SIZE_MISSING, 9)
        miss(mary, levis, levis_v[('32', 'Blue')], Intent.COLOUR_MISSING, 4)
        miss(ali, bag, None, Intent.PRICE_TOO_HIGH, 2)
        miss(mary, nike, nike_v[('43', 'Black')], Intent.OUT_OF_STOCK, 1)

        receive_stock(adidas_v[('42', 'Grey')].id, 1, recorded_by=owner, reference='DN-2210')
        inbound.receive('whatsapp', jane.phone_number, 'Yes!! Can I pay a deposit on M-Pesa? I will pick up Saturday')
        jane_request.refresh_from_db()
        services.record_payment(jane_request, 5000, 'mpesa', reference='SJK4H7Q2LM', actor=owner)
        services.record_bought_visit(shop, recorded_by=owner)

        self.stdout.write(self.style.SUCCESS(
            f'Sample shop "{shop.name}" ready. Sign in as amina / {options["password"]}.'))
