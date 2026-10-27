"""
The sample fashion shop: products, waiting customers, a reply, a deposit. Used by `seed_demo` (one shop in an empty
database) and by "Try the demo" (a fresh copy per visitor, which only ever uses the simulator).
"""
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from accounts.models import Membership, Shop
from customers.models import Customer
from notifications import inbound
from notifications.gateway import conversation_for, send_reply
from products.models import Category, Product, ProductType, ProductVariation
from products.services import receive_stock
from . import services
from .models import BlockedPurchaseIntent as Intent

DEMO_DAYS = 2


def fill_sample_shop(shop, owner):
    """Add the sample items, customers and their story to an empty shop. Messages go out as each step commits."""
    types = {t.name: t for t in ProductType.objects.filter(shop=shop)}
    running = Category.objects.create(shop=shop, name='Running', product_type=types.get('Shoes'))
    denim = Category.objects.create(shop=shop, name='Denim', product_type=types.get('Clothing'))
    bags = Category.objects.create(shop=shop, name='Bags', product_type=types.get('Bags'))

    def product(name, category, type_name, price, options):
        p = Product.objects.create(shop=shop, category=category, product_type=types[type_name], name=name, base_price=price)
        variations = {}
        for size, colour, stock in options:
            sku = f"{''.join(w[0] for w in name.split()).upper()}-{size}-{colour[:3].upper()}".replace(' ', '')
            if ProductVariation.objects.filter(sku=sku).exists():
                sku = f'{sku}-{shop.pk}'  # SKUs are unique across Retail OS; demo copies get the shop's number
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
    inbound.receive('whatsapp', jane.phone_number, 'Yes!! Can I pay a deposit on M-Pesa? I will pick up Saturday',
                    shop=shop)
    jane_request.refresh_from_db()
    services.record_payment(jane_request, 5000, 'mpesa', reference='SJK4H7Q2LM', actor=owner)

    # A sale already recovered: John's size came in, he replied and paid in full.
    receive_stock(nike_v[('42', 'Black')].id, 1, recorded_by=owner, reference='DN-2214')
    john_request = john.intents.get()
    inbound.receive('whatsapp', john.phone_number, "Yes, I'll come for it today", shop=shop)
    john_request.refresh_from_db()
    services.record_payment(john_request, john_request.balance, 'mpesa', reference='SJL2K9P4XR', actor=owner)
    send_reply(conversation_for(john), 'Thank you John, see you today. Your Nike Air Zoom 42 is ready at the counter.')

    # A customer waiting for an answer, in Swahili: Home shows her first, and the chat suggests the Deposit reply.
    receive_stock(nike_v[('43', 'Black')].id, 1, recorded_by=owner, reference='DN-2214')
    inbound.receive('whatsapp', mary.phone_number, 'Asante! Naweza lipa nusu leo, nitakuja kesho?', shop=shop)

    services.record_bought_visit(shop, recorded_by=owner)
    return shop


def start_demo():
    """A fresh demo shop and a temporary owner for one visitor. Returns the user to sign in."""
    User = get_user_model()
    with transaction.atomic():
        shop = Shop.objects.create(name='Kimathi Street Store', is_demo=True, link_on=False,
                                   payment_details='M-Pesa Till 123456, Kimathi Street Store (demo)')
        user = User.objects.create(username=f'demo-{secrets.token_hex(6)}', first_name='Amina', last_name='Wanjiru')
        user.set_unusable_password()
        user.save(update_fields=['password'])
        Membership.objects.create(user=user, shop=shop, role=Membership.OWNER)
    fill_sample_shop(shop, user)
    return user


def end_demo(shop):
    """Delete a demo shop and its temporary people. Never touches a real shop."""
    if not shop.is_demo:
        raise ValueError('Only demo shops can be removed this way.')
    user_ids = list(shop.memberships.values_list('user_id', flat=True))
    shop.delete()
    get_user_model().objects.filter(pk__in=user_ids, username__startswith='demo-', memberships__isnull=True).delete()


def remove_old_demos(now=None):
    """Demo shops are kept for 2 days. Returns how many were removed."""
    cutoff = (now or timezone.now()) - timedelta(days=DEMO_DAYS)
    old = list(Shop.objects.filter(is_demo=True, created_at__lt=cutoff))
    for shop in old:
        end_demo(shop)
    return len(old)


DEMOS_PER_HOUR = 5


def demo_view(request):
    """Try the demo: a sample shop of your own, with a temporary account. Nothing is real; no messages leave Retail OS."""
    from django.contrib.auth import login, logout
    from django.core.cache import cache
    from django.shortcuts import redirect, render
    from .ask import _address

    shop = getattr(request, 'shop', None)
    in_demo = request.user.is_authenticated and shop is not None and shop.is_demo
    if request.method == 'POST':
        if request.user.is_authenticated and not in_demo:
            return render(request, 'intents/demo.html', {'signed_in_as': request.user}, status=400)
        key = f'demo:{_address(request)}'
        if cache.get(key, 0) >= DEMOS_PER_HOUR:
            return render(request, 'intents/demo.html', {'too_many': True}, status=429)
        cache.set(key, cache.get(key, 0) + 1, 60 * 60)
        if in_demo:  # "Start over": a fresh copy, the old one is removed
            logout(request)
            end_demo(shop)
        user = start_demo()
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return redirect('dashboard:home')
    if in_demo:
        return redirect('dashboard:home')
    return render(request, 'intents/demo.html', {'signed_in_as': request.user if request.user.is_authenticated else None})
