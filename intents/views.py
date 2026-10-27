from collections import OrderedDict
from urllib.parse import quote, urlencode

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import CreateView, TemplateView, UpdateView

from analytics.selectors import get_to_order
from core.periods import future_window, parse_future_date, resolve_period
from core.shops import ShopViewMixin, can_manage_catalog
from .forms import BlockedPurchaseIntentForm
from .models import BlockedPurchaseIntent
from .next_step import next_step
from .services import create_blocked_purchase_intent, decline, mark_ordered

Intent = BlockedPurchaseIntent
TABS = [
    # (key, label, statuses, reasons)
    ('stock', 'Waiting for stock', Intent.WAITING_STATUSES, None),
    ('price', 'Waiting for a lower price', Intent.WAITING_STATUSES, Intent.PRICE_DROP_REASONS),
    ('all', 'All records', None, None),
]
OLD_TABS = {'waiting': 'stock', 'active': 'all', 'closed': 'all'}


def _filter_tab(queryset, tab):
    key, _, statuses, reasons = tab
    if statuses:
        queryset = queryset.filter(status__in=statuses)
    if reasons:
        queryset = queryset.filter(constraint_type__in=reasons)
    elif key == 'stock':
        queryset = queryset.exclude(constraint_type__in=Intent.PRICE_DROP_REASONS)
    return queryset


def _capture_context(request, context):
    """What the capture form's "add new" dialogs need."""
    from products.models import ProductType
    from products.selectors import get_all_categories
    from core.shops import can_add_products
    context['all_categories'] = get_all_categories(request.shop)
    context['product_types'] = ProductType.objects.filter(shop=request.shop)
    context['can_add_products'] = can_add_products(request)
    intent = context.get('object')
    if intent is not None:
        context['events'] = intent.events.select_related('actor').order_by('-created_at')[:20]
        context['steps'] = _lifecycle_steps(intent)
    return context


def _lifecycle_steps(intent):
    """The status bar: done, current and upcoming stages of the main path."""
    path = [Intent.OPEN, Intent.BACK_IN_STOCK, Intent.NOTIFIED, Intent.IN_CONVERSATION, Intent.RESERVED, Intent.RECOVERED]
    labels = dict(Intent.STATUS_CHOICES)
    current = Intent.OPEN if intent.status == Intent.ON_ORDER else intent.status
    if current not in path:
        return []
    index = path.index(current)
    return [(labels[s] if not (s == Intent.OPEN and intent.status == Intent.ON_ORDER) else labels[Intent.ON_ORDER],
             'done' if i < index else 'now' if i == index else '') for i, s in enumerate(path)]


class IntentListView(ShopViewMixin, TemplateView):
    """Waiting: open demand grouped by customer, one card per customer with their items under it."""
    template_name = 'intents/intent_list.html'
    groups_per_page = 20

    def tab(self):
        default = 'all' if self.request.GET.get('status') in dict(Intent.STATUS_CHOICES) else 'stock'
        key = self.request.GET.get('show', default)
        key = OLD_TABS.get(key, key)
        return next((t for t in TABS if t[0] == key), TABS[0])

    def filtered(self):
        get = self.request.GET
        queryset = _filter_tab(Intent.objects.filter(shop=self.request.shop), self.tab())
        if get.get('status') in dict(Intent.STATUS_CHOICES):
            queryset = queryset.filter(status=get['status'])
        if get.get('reason') in dict(Intent.CONSTRAINT_CHOICES):
            queryset = queryset.filter(constraint_type=get['reason'])
        for field in ('customer', 'product'):
            if (get.get(field) or '').isdigit():
                queryset = queryset.filter(**{f'{field}_id': get[field]})
        q = (get.get('q') or '').strip()
        if q:
            queryset = queryset.filter(Q(customer__first_name__icontains=q) | Q(customer__last_name__icontains=q)
                                       | Q(customer__phone_number__icontains=q) | Q(product__name__icontains=q)
                                       | Q(variation__sku__icontains=q))
        period = resolve_period(get)
        if period['start']:
            queryset = queryset.filter(created_at__date__gte=period['start'])
        if period['end']:
            queryset = queryset.filter(created_at__date__lte=period['end'])
        return queryset, period

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset, period = self.filtered()
        today = timezone.localdate()
        groups = OrderedDict()
        manager = can_manage_catalog(self.request)
        for intent in (queryset.select_related('customer', 'product', 'variation')
                       .prefetch_related('customer__conversations', 'variation__holds').order_by('-created_at')):
            group = groups.setdefault(intent.customer_id, {'customer': intent.customer, 'items': [], 'money': 0})
            intent.days_waiting = (today - timezone.localdate(intent.created_at)).days
            intent.can_order = intent.status == Intent.OPEN and intent.constraint_type in Intent.RESTOCK_REASONS
            intent.next = next_step(intent, manager)
            intent.in_stock = intent.variation.available_quantity if intent.variation else None
            group['items'].append(intent)
            group['money'] += float(intent.estimated_value or 0)
        page = Paginator(list(groups.values()), self.groups_per_page).get_page(self.request.GET.get('page'))
        base = Intent.objects.filter(shop=self.request.shop)
        kept = {k: v for k, v in self.request.GET.items() if k not in ('page', 'show') and v}
        context.update({
            'tabs': [(t[0], t[1], _filter_tab(base, t).count()) for t in TABS],
            'current_tab': self.tab()[0],
            'groups': page.object_list,
            'page_obj': page,
            'item_count': sum(len(g['items']) for g in groups.values()),
            'period': period,
            'filters': self.request.GET,
            'status_choices': Intent.STATUS_CHOICES,
            'reason_choices': Intent.CONSTRAINT_CHOICES,
            'status_filter': dict(Intent.STATUS_CHOICES).get(self.request.GET.get('status'), ''),
            'filtered': any(k in kept for k in ('q', 'status', 'reason', 'customer', 'product', 'period',
                                                 'start_date', 'end_date')),
            'tab_query': urlencode(kept),
            'query': urlencode({**kept, 'show': self.tab()[0]}),
            'can_order': can_manage_catalog(self.request),
            'any_orderable': any(i.can_order for g in page.object_list for i in g['items']),
            'today': today,
            'date_min': future_window()[0], 'date_max': future_window()[1],
        })
        return context


class ManagersOnlyMixin:
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not can_manage_catalog(request):
            raise PermissionDenied('Only the owner or a manager can order stock.')
        return super().dispatch(request, *args, **kwargs)


class ToOrderView(ShopViewMixin, ManagersOnlyMixin, TemplateView):
    """The morning list: what to buy and who is waiting, grouped by supplier."""
    template_name = 'intents/to_order.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows = get_to_order(self.request.shop)
        suppliers = {}
        for row in rows:
            suppliers.setdefault(row['supplier'], []).append(row)
        groups = []
        for name in sorted(suppliers, key=lambda n: (n == '', n.lower())):
            group_rows = suppliers[name]
            lines = [f"- {r['product_name']} {r['variation_label']}{' (' + r['sku'] + ')' if r['sku'] else ''} x {r['to_order']}"
                     for r in group_rows if r['to_order'] > 0]
            text = f'Order from {self.request.shop.name}:\n' + '\n'.join(lines)
            groups.append({'supplier': name, 'rows': group_rows, 'text': text,
                           'share_url': 'https://wa.me/?text=' + quote(text, safe='') if lines else ''})
        context.update({
            'groups': groups,
            'item_count': sum(1 for r in rows if r['to_order'] > 0),
            'customer_count': sum(len(r['customers']) for r in rows),
            'money_waiting': sum(r['money_waiting'] for r in rows),
            'any_open': any(r['open_ids'] for r in rows),
            'date_min': future_window()[0], 'date_max': future_window()[1],
        })
        return context


class MarkOrderedView(ShopViewMixin, ManagersOnlyMixin, View):
    """Mark selected waiting requests (or whole To order rows) as ordered, with an optional arrival date."""

    def post(self, request):
        ids = [i for i in request.POST.getlist('intent') if i.isdigit()]
        for row in request.POST.getlist('row'):
            ids += [i for i in row.split(',') if i.isdigit()]
        next_url = request.POST.get('next', '')
        if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            next_url = reverse('intents:to_order')
        try:
            expected_at = parse_future_date(request.POST.get('expected_at'), 'The arrival date')
        except ValueError as error:
            messages.error(request, str(error))
            return HttpResponseRedirect(next_url)
        intents = list(Intent.objects.filter(shop=request.shop, id__in=ids, status=Intent.OPEN))
        if not intents:
            messages.error(request, 'Choose at least one item that is still waiting.')
        else:
            moved = mark_ordered(intents, expected_at=expected_at, actor=request.user)
            when = f', due {expected_at.day} {expected_at:%b}' if expected_at else ''
            messages.success(request, f'{moved} marked as ordered{when}')
        return HttpResponseRedirect(next_url)


class IntentCreateView(ShopViewMixin, CreateView):
    model = BlockedPurchaseIntent
    form_class = BlockedPurchaseIntentForm
    template_name = 'intents/intent_form.html'
    success_url = reverse_lazy('intents:list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields.pop('status', None)
        return form

    def get_initial(self):
        initial = super().get_initial()
        customer = self.request.GET.get('customer', '')
        if customer.isdigit() and self.request.shop.customers.filter(pk=customer).exists():
            initial['customer'] = int(customer)
        return initial

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            self.object = create_blocked_purchase_intent(
                customer=data['customer'],
                product=data['product'],
                variation=data.get('variation'),
                constraint_type=data['constraint_type'],
                requested_quantity=data.get('requested_quantity') or 1,
                estimated_value=data.get('estimated_value'),
                notes=data.get('notes', ''),
                recorded_by=self.request.user,
            )
        except ValueError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)
        messages.success(self.request, 'Missed sale saved')
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return _capture_context(self.request, context)

class IntentUpdateView(ShopViewMixin, UpdateView):
    model = BlockedPurchaseIntent
    form_class = BlockedPurchaseIntentForm
    template_name = 'intents/intent_form.html'
    success_url = reverse_lazy('intents:list')

    LOCKED_WHEN_MOVING = ('customer', 'product', 'variation', 'constraint_type', 'requested_quantity', 'estimated_value')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields.pop('status', None)
        if self.object.status not in Intent.WAITING_STATUSES:
            # A unit may be held and the customer messaged: change the item from the conversation instead.
            for name in self.LOCKED_WHEN_MOVING:
                if name in form.fields:
                    form.fields[name].disabled = True
        return form

    def form_valid(self, form):
        if not form.instance.estimated_value:
            form.instance.estimated_value = form.instance.product.base_price * form.instance.requested_quantity
        variation = form.cleaned_data.get('variation')
        if (self.object.status in Intent.WAITING_STATUSES and form.cleaned_data.get('constraint_type') in Intent.RESTOCK_REASONS
                and variation is not None and variation.available_quantity > 0):
            form.add_error('variation', f'{variation.label or variation.sku} is in stock ({variation.available_quantity} free). '
                                        'Sell it now, or choose another reason.')
            return self.form_invalid(form)
        messages.success(self.request, 'Saved')
        return super().form_valid(form)

    def post(self, request, *args, **kwargs):
        if request.POST.get('action') == 'decline':
            intent = self.get_object()
            if intent.status in Intent.CLOSED_STATUSES:
                messages.error(request, 'This item is already closed.')
            else:
                decline(intent, request.POST.get('reason', '').strip()[:200], actor=request.user)
                messages.success(request, 'Closed as declined. It is not counted as revenue.')
            return HttpResponseRedirect(reverse('intents:update', args=[intent.pk]))
        return super().post(request, *args, **kwargs)

    def get_success_url(self):
        return reverse('intents:update', args=[self.object.pk])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['next'] = next_step(self.object, can_manage_catalog(self.request))
        context['locked'] = self.object.status not in Intent.WAITING_STATUSES
        return _capture_context(self.request, context)
