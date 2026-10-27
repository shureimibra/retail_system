"""
The public "Ask for your size" link: /ask/<link name>/. A customer picks the item and the size or colour,
leaves their number, and it lands in Waiting like any missed sale, marked "Shop link".
Never shows prices, stock counts or other customers.
"""
from datetime import timedelta

from django.core.cache import cache
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from accounts.models import Shop
from products.models import Product
from . import services
from .models import BlockedPurchaseIntent as Intent

PER_ADDRESS_PER_HOUR = 20
PER_PHONE_PER_DAY = 5


def _address(request):
    # Through the Cloudflare tunnel every request comes from 127.0.0.1; Cloudflare passes the real one on.
    return request.META.get('HTTP_CF_CONNECTING_IP') or request.META.get('REMOTE_ADDR', '')


def _too_many(request):
    key = f'ask:{_address(request)}'
    count = cache.get(key, 0)
    if count >= PER_ADDRESS_PER_HOUR:
        return True
    cache.set(key, count + 1, 60 * 60)
    return False


class AskView(View):
    template_name = 'intents/ask.html'

    def get_shop(self, name):
        shop = get_object_or_404(Shop, link_name=name, is_demo=False)
        if not shop.link_on:
            raise Http404('This link is switched off.')
        return shop

    def context(self, shop, **extra):
        products = list(Product.objects.filter(shop=shop).prefetch_related('variations__holds').order_by('name'))
        for product in products:
            # Only the sizes they can't buy today. Ones in stock aren't offered: they can come in for those.
            variations = list(product.variations.all())
            product.missing = [v for v in variations if v.label and v.available_quantity == 0]
            product.some_in_stock = any(v.available_quantity > 0 for v in variations)
        return {'shop': shop, 'products': products, **extra}

    def get(self, request, name):
        shop = self.get_shop(name)
        done = request.session.pop('ask_done', None)
        return render(request, self.template_name, self.context(shop, done=done))

    def post(self, request, name):
        shop = self.get_shop(name)
        post = request.POST
        if post.get('website'):  # a field people never see; bots fill it in
            request.session['ask_done'] = {'name': ''}
            return redirect('ask', name=name)
        errors = []
        product = Product.objects.filter(shop=shop, pk=post.get('product') or 0).first()
        if product is None:
            errors.append('Choose the item you want.')
        choice = post.get(f'want_{product.pk}', '') if product else ''
        wanted = post.get('wanted', '').strip()[:200]
        variation = product.variations.filter(pk=choice).first() if product and choice.isdigit() else None
        if product and variation is None and choice not in ('any', 'other'):
            errors.append('Choose the size or colour, or "Any".')
        if choice == 'other' and not wanted:
            errors.append('Tell us the size or colour you want.')
        consent = post.get('consent') == 'yes'
        if not errors and _too_many(request):
            errors.append('Too many requests from this connection. Please try again in an hour.')
        customer = None
        if not errors:
            try:
                customer = services.find_or_add_customer(shop, post.get('phone', ''), post.get('name', '').strip()[:100])
            except ValueError as error:
                errors.append(str(error))
        if customer and Intent.objects.filter(customer=customer, source=Intent.FROM_LINK,
                                              created_at__gte=timezone.now() - timedelta(days=1)).count() >= PER_PHONE_PER_DAY:
            errors.append("You've already asked for several items today. The shop will be in touch.")
        if errors:
            return render(request, self.template_name, self.context(shop, errors=errors, form=post), status=400)

        reason, note = self._reason(product, variation, choice, wanted)
        duplicate = Intent.objects.filter(customer=customer, product=product, variation=variation, constraint_type=reason,
                                          notes=note).exclude(status__in=Intent.CLOSED_STATUSES).exists()
        if not duplicate:
            services.create_blocked_purchase_intent(customer, product, variation, reason, notes=note,
                                                    consent_given=consent, source=Intent.FROM_LINK)
        item = f'{product.name} {variation.label if variation else wanted}'.strip()
        request.session['ask_done'] = {'name': customer.first_name, 'item': item, 'consent': consent}
        return redirect('ask', name=name)

    @staticmethod
    def _reason(product, variation, choice, wanted):
        """Why it's a missed sale, and a note for staff when someone needs to follow up by hand."""
        if choice == 'other':
            return Intent.OTHER, f'Asked through the shop link for: {wanted}'
        if variation is not None:
            if variation.available_quantity > 0:
                return Intent.OTHER, f"Asked through the shop link for {variation.label}. It's in stock: invite them in."
            return Intent.SIZE_MISSING, ''
        if any(v.available_quantity > 0 for v in product.variations.all()):
            return Intent.OTHER, 'Asked through the shop link for any size. Some are in stock: invite them in.'
        return Intent.OUT_OF_STOCK, ''
