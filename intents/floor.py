"""Floor mode: the till screen. How did the visit end, and if they didn't buy, what, who and when, in three steps."""
from datetime import timedelta

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from core.phones import normalize_phone
from core.shops import ShopViewMixin, can_add_products
from customers.models import Customer
from products.models import Product, ProductVariation
from . import services
from .models import BlockedPurchaseIntent as Intent

NEEDED_WITHIN = [('2', '2 days'), ('4', '3–4 days'), ('7', 'A week'), ('', 'No rush')]


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
        context.update({
            'start': 'item' if get.get('start') == 'item' or customer else 'outcome',
            'products': products,
            'variations': variations,
            'catalog': {str(p.pk): {'price': float(p.base_price),
                                    'options': [name for name, _ in p.product_type.options] if p.product_type else ['Size', 'Colour']}
                        for p in products},
            'reasons': Intent.CONSTRAINT_CHOICES,
            'price_reasons': Intent.PRICE_DROP_REASONS,
            'needed_within': NEEDED_WITHIN,
            'customer': customer,
            'visit': get.get('visit', '') if (get.get('visit') or '').isdigit() else '',
            'can_add_products': can_add_products(self.request),
            'form': self.request.session.pop('floor_form', {}),
        })
        return context

    def post(self, request):
        shop = request.shop
        post = request.POST
        if post.get('action') == 'bought':
            services.record_bought_visit(shop, recorded_by=request.user)
            messages.success(request, 'Sale logged. Thank you!')
            return redirect('floor')

        product = Product.objects.filter(shop=shop, pk=post.get('product') or 0).first()
        variation = None
        if product and (post.get('variation') or '').isdigit():
            variation = ProductVariation.objects.filter(product=product, pk=post['variation']).first()
        reason = post.get('reason', '')
        problems = []
        if product is None:
            problems.append('Choose what they wanted.')
        if reason not in dict(Intent.CONSTRAINT_CHOICES):
            problems.append("Choose why they didn't buy.")
        customer = None
        if not problems:
            try:
                customer = services.find_or_add_customer(shop, post.get('phone', ''), post.get('name', ''),
                                                         post.get('email', '').strip())
            except ValueError as error:
                problems.append(str(error))
        if problems:
            for problem in problems:
                messages.error(request, problem)
            # Keep what was typed so nothing has to be entered twice.
            request.session['floor_form'] = {k: post.get(k, '') for k in
                                             ('product', 'variation', 'reason', 'phone', 'name', 'email', 'within')}
            return redirect(reverse('floor') + '?start=item')

        within = post.get('within', '')
        needed_by = timezone.localdate() + timedelta(days=int(within)) if within.isdigit() else None
        intent = services.capture_from_floor(shop, customer, product, variation, reason, needed_by=needed_by,
                                             consent_given=post.get('consent') == 'yes', recorded_by=request.user,
                                             visit_id=post.get('visit') if (post.get('visit') or '').isdigit() else None)
        item = f'{product.name}{" " + variation.label if variation else ""}'
        messages.success(request, f'Saved: {item} for {customer.first_name or customer.phone_number}')
        if post.get('then') == 'another':
            return redirect(reverse('floor') + f'?start=item&customer={customer.pk}&visit={intent.visit_id}')
        return redirect('floor')


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
