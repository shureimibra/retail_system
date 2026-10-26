"""Floor mode: the till screen. How did the visit end, and if they didn't buy, what, who and when, in three steps."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from core.phones import normalize_phone
from core.shops import ShopViewMixin, can_add_products, can_manage_catalog
from customers.models import Customer
from products.models import Category, Product, ProductType, ProductVariation
from products.services import create_product_variation, suggest_sku
from . import services
from .models import BlockedPurchaseIntent as Intent

NEEDED_WITHIN = [('2', '2 days'), ('4', '3–4 days'), ('7', 'A week'), ('', 'No rush')]
# One line under each reason so staff pick the right one.
REASON_HINTS = {
    Intent.SIZE_MISSING: "The size they want isn't in stock",
    Intent.COLOUR_MISSING: "The colour they want isn't in stock",
    Intent.OUT_OF_STOCK: 'None left in any size or colour',
    Intent.PRICE_TOO_HIGH: 'They think it costs too much. Messaged when you lower the price',
    Intent.OVER_BUDGET: "They like the price but can't afford it today. Messaged when you lower the price",
    Intent.OTHER: 'Write what happened in the note',
}
FORM_FIELDS = ('product', 'variation', 'reason', 'phone', 'name', 'email', 'within', 'note', 'new_option1', 'new_option2',
               'new_name', 'new_type', 'new_price')


class FloorView(ShopViewMixin, TemplateView):
    template_name = 'intents/floor.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        shop = self.request.shop
        get = self.request.GET
        customer = None
        if (get.get('customer') or '').isdigit():
            customer = Customer.objects.filter(shop=shop, pk=get['customer']).first()
        products = list(Product.objects.filter(shop=shop).select_related('product_type').order_by('name'))
        variations = list(ProductVariation.objects.filter(product__shop=shop).prefetch_related('holds')
                          .order_by('product__name', 'option1', 'option2', 'option3'))
        form = self.request.session.pop('floor_form', {})
        context.update({
            'start': 'item' if get.get('start') == 'item' or customer or form else 'outcome',
            'products': products,
            'variations': variations,
            'catalog': {str(p.pk): {'price': float(p.base_price),
                                    'options': [name for name, _ in p.product_type.options][:2] if p.product_type else ['Size', 'Colour']}
                        for p in products},
            'reasons': [(value, label, REASON_HINTS.get(value, '')) for value, label in Intent.CONSTRAINT_CHOICES],
            'restock_reasons': Intent.RESTOCK_REASONS,
            'needed_within': NEEDED_WITHIN,
            'product_types': ProductType.objects.filter(shop=shop),
            'customer': customer,
            'visit': get.get('visit', '') if (get.get('visit') or '').isdigit() else '',
            'can_add_products': can_add_products(self.request),
            'form': form,
        })
        return context

    def post(self, request):
        shop = request.shop
        post = request.POST
        if post.get('action') == 'bought':
            services.record_bought_visit(shop, recorded_by=request.user)
            messages.success(request, 'Sale logged. Thank you!')
            return redirect('floor')

        problems = []
        reason = post.get('reason', '')
        if reason not in dict(Intent.CONSTRAINT_CHOICES):
            problems.append("Choose why they didn't buy.")
        note = post.get('note', '').strip()[:500]
        if reason == Intent.OTHER and not note:
            problems.append('Write a short note for "Something else", so the team knows what to do.')
        try:
            with transaction.atomic():
                product, variation = self._item(request, problems)
                if problems:
                    raise ValueError('')
                customer = services.find_or_add_customer(shop, post.get('phone', ''), post.get('name', ''),
                                                         post.get('email', '').strip())
                within = post.get('within', '')
                needed_by = timezone.localdate() + timedelta(days=int(within)) if within.isdigit() else None
                visit_id = post.get('visit') if (post.get('visit') or '').isdigit() else None
                intent = services.capture_from_floor(shop, customer, product, variation, reason, needed_by=needed_by,
                                                     consent_given=post.get('consent') == 'yes', recorded_by=request.user,
                                                     visit_id=visit_id, notes=note)
        except ValueError as error:
            if str(error):
                problems.append(str(error))
            for problem in problems:
                messages.error(request, problem)
            # Keep what was typed so nothing has to be entered twice.
            request.session['floor_form'] = {k: post.get(k, '') for k in FORM_FIELDS}
            return redirect(reverse('floor') + '?start=item')

        item = f'{product.name}{" " + variation.label if variation else ""}'
        messages.success(request, f'Saved: {item} for {customer.first_name or customer.phone_number}')
        if post.get('then') == 'another':
            return redirect(reverse('floor') + f'?start=item&customer={customer.pk}&visit={intent.visit_id}')
        return redirect('floor')

    def _item(self, request, problems):
        """The product and size/colour they wanted, adding a new item or option when the shop doesn't have it."""
        shop, post = request.shop, request.POST
        manager = can_manage_catalog(request)
        if post.get('product') == 'new':
            if not can_add_products(request):
                problems.append('Ask the owner or a manager to add new items.')
                return None, None
            name = post.get('new_name', '').strip()[:200]
            try:
                price = Decimal(post.get('new_price', '').replace(',', '').strip())
            except InvalidOperation:
                price = None
            product_type = ProductType.objects.filter(shop=shop, pk=post.get('new_type') or 0).first()
            if not name or price is None or price < 0:
                problems.append("For a new item, enter its name and the price you'd sell it at.")
                return None, None
            category, _ = Category.objects.get_or_create(shop=shop, name=product_type.name if product_type else 'Other')
            product = Product.objects.create(shop=shop, category=category, product_type=product_type, name=name,
                                             base_price=price, needs_review=not manager)
        else:
            product = Product.objects.filter(shop=shop, pk=post.get('product') or 0).first()
            if product is None:
                problems.append('Choose what they wanted.')
                return None, None
        typed = [post.get('new_option1', '').strip()[:50], post.get('new_option2', '').strip()[:50]]
        if any(typed):
            existing = ProductVariation.objects.filter(product=product, option1__iexact=typed[0] or None,
                                                       option2__iexact=typed[1] or None).first()
            if existing:
                return product, existing
            if not can_add_products(request):
                problems.append('Ask the owner or a manager to add this size or colour.')
                return product, None
            variation = create_product_variation(product, typed[0] or None, typed[1] or None, 0,
                                                 suggest_sku(product, *typed), recorded_by=request.user)
            if not manager and not product.needs_review:
                product.needs_review = True
                product.save(update_fields=['needs_review'])
            return product, variation
        variation = None
        if (post.get('variation') or '').isdigit():
            variation = ProductVariation.objects.filter(product=product, pk=post['variation']).first()
        return product, variation


def customer_lookup(request):
    """Floor mode fills in the name when the phone number belongs to a known customer."""
    if not request.user.is_authenticated or request.shop is None:
        return JsonResponse({'found': False}, status=403)
    number = normalize_phone(request.GET.get('phone', ''), request.shop.phone_region)
    customer = Customer.objects.filter(shop=request.shop, phone_number=number).first() if number else None
    if customer is None:
        return JsonResponse({'found': False})
    return JsonResponse({'found': True, 'name': f'{customer.first_name} {customer.last_name}'.strip(),
                         'email': customer.email or '', 'open': customer.intents.exclude(status__in=Intent.CLOSED_STATUSES).count()})
