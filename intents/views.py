from django.views.generic import ListView, CreateView, UpdateView
from core.shops import ShopViewMixin
from django.urls import reverse_lazy
from .models import BlockedPurchaseIntent
from .forms import BlockedPurchaseIntentForm
from .services import create_blocked_purchase_intent
from django.http import HttpResponseRedirect

class IntentListView(ShopViewMixin, ListView):
    model = BlockedPurchaseIntent
    template_name = 'intents/intent_list.html'
    context_object_name = 'intents'
    paginate_by = 10
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = super().get_queryset()
        customer_id = self.request.GET.get('customer')
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)
        return queryset

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
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from products.selectors import get_all_categories
        context['all_categories'] = get_all_categories(self.request.shop)
        return context

class IntentUpdateView(ShopViewMixin, UpdateView):
    model = BlockedPurchaseIntent
    form_class = BlockedPurchaseIntentForm
    template_name = 'intents/intent_form.html'
    success_url = reverse_lazy('intents:list')

    def form_valid(self, form):
        if not form.instance.estimated_value:
            form.instance.estimated_value = form.instance.product.base_price * form.instance.requested_quantity
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from products.selectors import get_all_categories
        context['all_categories'] = get_all_categories(self.request.shop)
        return context
