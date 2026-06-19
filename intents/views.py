from django.views.generic import ListView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from .models import BlockedPurchaseIntent
from .forms import BlockedPurchaseIntentForm

class IntentListView(LoginRequiredMixin, ListView):
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

class IntentCreateView(LoginRequiredMixin, CreateView):
    model = BlockedPurchaseIntent
    form_class = BlockedPurchaseIntentForm
    template_name = 'intents/intent_form.html'
    success_url = reverse_lazy('intents:list')

    def form_valid(self, form):
        form.instance.recorded_by = self.request.user
        if not form.instance.estimated_value:
            form.instance.estimated_value = form.instance.product.base_price * form.instance.requested_quantity
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from products.selectors import get_all_categories
        context['all_categories'] = get_all_categories()
        return context

class IntentUpdateView(LoginRequiredMixin, UpdateView):
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
        context['all_categories'] = get_all_categories()
        return context
