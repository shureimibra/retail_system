from django.views.generic import ListView, CreateView, UpdateView
from core.shops import ShopViewMixin
from django.urls import reverse_lazy
from .models import BlockedPurchaseIntent
from .forms import BlockedPurchaseIntentForm
from .services import create_blocked_purchase_intent, transition
from django.contrib import messages
from django.http import HttpResponseRedirect

Intent = BlockedPurchaseIntent
TABS = [
    ('waiting', 'Waiting', Intent.WAITING_STATUSES),
    ('active', 'In progress', [Intent.BACK_IN_STOCK, Intent.NOTIFIED, Intent.IN_CONVERSATION, Intent.RESERVED]),
    ('closed', 'Closed', Intent.CLOSED_STATUSES),
    ('all', 'All', None),
]


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


class IntentListView(ShopViewMixin, ListView):
    model = BlockedPurchaseIntent
    template_name = 'intents/intent_list.html'
    context_object_name = 'intents'
    paginate_by = 20
    ordering = ['-created_at']

    def tab(self):
        key = self.request.GET.get('show', 'waiting')
        return next((t for t in TABS if t[0] == key), TABS[0])

    def get_queryset(self):
        queryset = super().get_queryset().select_related('customer', 'product', 'variation')
        statuses = self.tab()[2]
        if statuses:
            queryset = queryset.filter(status__in=statuses)
        customer_id = self.request.GET.get('customer')
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base = BlockedPurchaseIntent.objects.filter(shop=self.request.shop)
        context['tabs'] = [(key, label, base.filter(status__in=statuses).count() if statuses else base.count())
                           for key, label, statuses in TABS]
        context['current_tab'] = self.tab()[0]
        context['query'] = f'show={self.tab()[0]}'
        return context

class IntentCreateView(ShopViewMixin, CreateView):
    model = BlockedPurchaseIntent
    form_class = BlockedPurchaseIntentForm
    template_name = 'intents/intent_form.html'
    success_url = reverse_lazy('intents:list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields.pop('status', None)
        return form

    def form_valid(self, form):
        data = form.cleaned_data
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

    def form_valid(self, form):
        if not form.instance.estimated_value:
            form.instance.estimated_value = form.instance.product.base_price * form.instance.requested_quantity
        new_status = form.cleaned_data.get('status', self.object.status)
        form.instance.status = BlockedPurchaseIntent.objects.get(pk=self.object.pk).status
        response = super().form_valid(form)
        if new_status != self.object.status:
            transition(self.object, new_status, actor=self.request.user, note='Changed on the edit page')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return _capture_context(self.request, context)
