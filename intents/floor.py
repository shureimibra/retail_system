"""Log missed sale: what they wanted, who, and when, in three steps. Saving returns you to where you started."""
import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urlsplit

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from accounts.models import Membership
from core.phones import normalize_phone
from core.shops import ShopViewMixin, can_add_products, can_manage_catalog
from customers.models import Customer
from products.models import Category, Product, ProductType, ProductVariation
from products.services import create_product_variation, suggest_sku
from . import services
from .models import BlockedPurchaseIntent as Intent, Visit

NEEDED_WITHIN = [('2', '2 days'), ('4', '3–4 days'), ('7', 'A week'), ('', 'No rush')]
# One line under each reason so staff pick the right one.
REASON_HINTS = {
    Intent.SIZE_MISSING: "The size they want isn't in stock",
    Intent.COLOUR_MISSING: "The colour they want isn't in stock",
    Intent.OUT_OF_STOCK: 'None left in any size or colour',
    Intent.PRICE_TOO_HIGH: "They think it costs too much, or it's over their budget. Messaged when you lower the price",
    Intent.OTHER: 'Write what happened in the note',
}
FORM_FIELDS = ('product', 'variation', 'reason', 'phone', 'name', 'email', 'within', 'note', 'new_option1', 'new_option2',
               'new_name', 'new_type', 'new_price')


def _back(request, url):
    """A safe page on this site to return to after saving (never Log missed sale itself); Home otherwise."""
    safe = url and url_has_allowed_host_and_scheme(url, {request.get_host()}, request.is_secure())
    parts = urlsplit(url or '')
    if safe and parts.path.startswith('/') and not parts.path.startswith(reverse('floor')):
        return parts.path + (f'?{parts.query}' if parts.query else '')
    return reverse('dashboard:home')


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
            'back': _back(self.request, get.get('back') or self.request.META.get('HTTP_REFERER')),
            'products': products,
            'variations': variations,
            'catalog': {str(p.pk): {'price': float(p.base_price),
                                    'options': [name for name, _ in p.product_type.options][:2] if p.product_type else ['Size', 'Colour']}
                        for p in products},
            'reasons': [(value, label, REASON_HINTS.get(value, '')) for value, label in Intent.CAPTURE_CHOICES],
            'restock_reasons': Intent.RESTOCK_REASONS,
            'needed_within': NEEDED_WITHIN,
            'product_types': ProductType.objects.filter(shop=shop),
            'customer': customer,
            'visit': get.get('visit', '') if (get.get('visit') or '').isdigit() else '',
            'can_add_products': can_add_products(self.request),
            'form': form,
        })
        return context

    def get(self, request, *args, **kwargs):
        clean = len(messages.get_messages(request)) == 0
        response = super().get(request, *args, **kwargs)
        context = response.context_data
        if clean and not context['form'] and not context['customer']:
            # A copy the phone may keep for working offline: no one-off messages, typed values or customer in it.
            response['X-Offline-Copy'] = 'yes'
        return response

    def post(self, request):
        post = request.POST
        back = _back(request, post.get('back'))
        if post.get('action') == 'bought':
            record_bought(request, post)
            messages.success(request, 'Sale logged. Thank you!')
            return redirect(back)

        result = capture(request, post)
        if result['status'] == 'refused':
            for problem in result['problems']:
                messages.error(request, problem)
            # Keep what was typed so nothing has to be entered twice.
            request.session['floor_form'] = {k: post.get(k, '') for k in FORM_FIELDS}
            return redirect(reverse('floor') + '?' + urlencode({'back': back}))

        intent = result['intent']
        if result['status'] == 'saved':
            messages.success(request, f'Saved: {result["item"]} for {intent.customer.first_name or intent.customer.phone_number}')
        if post.get('then') == 'another':
            return redirect(reverse('floor') + '?' + urlencode({'customer': intent.customer_id, 'visit': intent.visit_id,
                                                                'back': back}))
        return redirect(back)


def _client_ref(data):
    ref = (data.get('client_ref') or '').strip()[:40]
    return ref or None


def record_bought(request, data):
    """A walk-in who bought. Returns 'saved', or 'already' when this phone already sent it."""
    ref = _client_ref(data)
    if ref and Visit.objects.filter(shop=request.shop, client_ref=ref).exists():
        return 'already'
    try:
        with transaction.atomic():
            visit = services.record_bought_visit(request.shop, recorded_by=_logged_by(request, data))
            if ref:
                visit.client_ref = ref
                visit.save(update_fields=['client_ref'])
            _backdate(visit, data)
    except IntegrityError:
        return 'already'
    return 'saved'


def capture(request, data, offline=False):
    """
    Save one missed sale from Log missed sale (typed now, or saved on the phone while offline).
    Returns {'status': 'saved' | 'already' | 'refused', 'problems': [...], 'intent', 'item'}.
    """
    shop = request.shop
    ref = _client_ref(data)
    if ref:
        earlier = Intent.objects.filter(shop=shop, client_ref=ref).select_related('customer').first()
        if earlier:
            return {'status': 'already', 'problems': [], 'intent': earlier, 'item': str(earlier.product.name)}
    problems = []
    reason = data.get('reason', '')
    if reason not in dict(Intent.CONSTRAINT_CHOICES):
        problems.append("Choose why they didn't buy.")
    note = data.get('note', '').strip()[:500]
    if reason == Intent.OTHER and not note:
        problems.append('Write a short note for "Something else", so the team knows what to do.')
    try:
        with transaction.atomic():
            product, variation = _item(request, data, problems)
            if problems:
                raise ValueError('')
            if offline and reason in Intent.RESTOCK_REASONS and variation is not None and variation.available_quantity > 0:
                # Stock arrived while the phone was offline: don't lose the customer, ask staff to invite them in.
                label = dict(Intent.CONSTRAINT_CHOICES)[reason]
                note = (f'Logged offline as "{label}" for {variation.label}. It\'s in stock now: invite them in.'
                        + (f' Note: {note}' if note else ''))[:500]
                reason = Intent.OTHER
            customer = services.find_or_add_customer(shop, data.get('phone', ''), data.get('name', ''),
                                                     data.get('email', '').strip())
            within = data.get('within', '')
            needed_by = timezone.localdate() + timedelta(days=int(within)) if within.isdigit() else None
            visit_id = data.get('visit') if (data.get('visit') or '').isdigit() else None
            # Same customer, another item, saved offline: both items belong to one visit, whichever arrives first.
            visit_ref = str(data.get('visit_ref') or '')[:40] or ref
            if not visit_id and visit_ref:
                visit_id = Visit.objects.filter(shop=shop, client_ref=visit_ref).values_list('pk', flat=True).first()
                if visit_id is None and visit_ref != ref:
                    visit_id = Visit.objects.create(shop=shop, customer=customer, outcome=Visit.DIDNT_BUY,
                                                    recorded_by=_logged_by(request, data), client_ref=visit_ref).pk
            intent = services.capture_from_floor(shop, customer, product, variation, reason, needed_by=needed_by,
                                                 consent_given=data.get('consent') == 'yes',
                                                 recorded_by=_logged_by(request, data), visit_id=visit_id, notes=note,
                                                 client_ref=ref)
            _backdate(intent, data)
            if intent.visit is not None and not visit_id:
                _backdate(intent.visit, data)
    except IntegrityError:
        earlier = Intent.objects.filter(shop=shop, client_ref=ref).first()
        return {'status': 'already', 'problems': [], 'intent': earlier, 'item': ''}
    except ValueError as error:
        if str(error):
            problems.append(str(error))
        return {'status': 'refused', 'problems': problems, 'intent': None, 'item': ''}
    item = f'{product.name}{" " + variation.label if variation else ""}'
    return {'status': 'saved', 'problems': [], 'intent': intent, 'item': item}


def _logged_by(request, data):
    """Who logged it: the person signed in, or, for records saved offline, the colleague who typed them."""
    user_id = str(data.get('logged_by') or '')
    if user_id.isdigit() and int(user_id) != request.user.pk:
        membership = Membership.objects.filter(shop=request.shop, user_id=user_id).select_related('user').first()
        if membership:
            return membership.user
    return request.user


def _backdate(record, data):
    """Records saved offline keep the time they were typed (never in the future, never more than 7 days ago)."""
    logged_at = parse_datetime(str(data.get('logged_at') or ''))
    if logged_at is None:
        return
    if timezone.is_naive(logged_at):
        logged_at = timezone.make_aware(logged_at)
    now = timezone.now()
    logged_at = min(max(logged_at, now - timedelta(days=7)), now)
    type(record).objects.filter(pk=record.pk).update(created_at=logged_at)


def _item(request, data, problems):
    """The product and size/colour they wanted, adding a new item or option when the shop doesn't have it."""
    shop, post = request.shop, data
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
        category, _ = Category.objects.get_or_create(shop=shop, name=product_type.name if product_type else 'Other',
                                                     defaults={'product_type': product_type})
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


@require_POST
def floor_sync(request):
    """One record saved on the phone while offline: {"kind": "missed" | "bought", "fields": {...}}."""
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'signin'}, status=401)
    if request.shop is None:
        return JsonResponse({'status': 'refused', 'problems': ['No shop for this sign-in.']}, status=403)
    try:
        record = json.loads(request.body or b'{}')
    except ValueError:
        return JsonResponse({'status': 'refused', 'problems': ['Not a record.']}, status=400)
    fields = record.get('fields') if isinstance(record, dict) else None
    if not isinstance(fields, dict):
        return JsonResponse({'status': 'refused', 'problems': ['Not a record.']}, status=400)
    data = {str(k): str(v) for k, v in fields.items() if isinstance(v, (str, int, float))}
    if fields.get('action') == 'bought':
        return JsonResponse({'status': record_bought(request, data), 'problems': [], 'item': 'Sale'})
    result = capture(request, data, offline=True)
    return JsonResponse({'status': result['status'], 'problems': result['problems'], 'item': result['item']})


def floor_token(request):
    """A fresh CSRF token and who's signed in, so the phone can send what it saved offline."""
    if not request.user.is_authenticated:
        return JsonResponse({'signed_in': False}, status=401)
    return JsonResponse({'signed_in': True, 'token': get_token(request), 'user': request.user.pk})


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
