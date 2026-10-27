from django.core.management.base import BaseCommand, CommandError

from accounts.models import Membership, Shop, User
from customers.models import Customer
from intents.demo import fill_sample_shop
from products.models import Product


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
        fill_sample_shop(shop, owner)

        self.stdout.write(self.style.SUCCESS(
            f'Sample shop "{shop.name}" ready. Sign in as amina / {options["password"]}.'))
