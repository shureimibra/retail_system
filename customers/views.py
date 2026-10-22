from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from core.shops import ShopViewMixin
from intents.models import BlockedPurchaseIntent as Intent, Payment
from .forms import CustomerForm
from .models import Customer


class CustomerListView(ShopViewMixin, ListView):
    model = Customer
    template_name = 'customers/customer_list.html'
    context_object_name = 'customers'
    paginate_by = 20

    def get_queryset(self):
        queryset = (super().get_queryset()
                    .annotate(open_items=Count('intents', filter=~Q(intents__status__in=Intent.CLOSED_STATUSES)),
                              all_items=Count('intents'),
                              last_contact=Max('conversations__last_message_at'))
                    .order_by('-created_at'))
        q = (self.request.GET.get('q') or '').strip()
        if q:
            queryset = queryset.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q)
                                       | Q(phone_number__icontains=q) | Q(email__icontains=q))
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        q = self.request.GET.get('q', '')
        context['q'] = q
        context['query'] = f'q={q}' if q else ''
        return context


class CustomerDetailView(ShopViewMixin, TemplateView):
    """One customer: everything they asked for, where each item stands, and what they've paid. No balance profile."""
    template_name = 'customers/customer_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = get_object_or_404(Customer, pk=self.kwargs['pk'], shop=self.request.shop)
        intents = list(customer.intents.select_related('product', 'variation').order_by('-created_at'))
        context.update({
            'customer': customer,
            'open_items': [i for i in intents if i.status not in Intent.CLOSED_STATUSES],
            'closed_items': [i for i in intents if i.status in Intent.CLOSED_STATUSES],
            'payments': Payment.objects.filter(intent__customer=customer).select_related('intent__product', 'recorded_by')
                                       .order_by('-created_at'),
            'conversation': customer.conversations.first(),
        })
        return context


class CustomerCreateView(ShopViewMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'customers/customer_form.html'

    def get_success_url(self):
        return reverse('customers:detail', args=[self.object.pk])


class CustomerUpdateView(ShopViewMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'customers/customer_form.html'

    def get_success_url(self):
        return reverse('customers:detail', args=[self.object.pk])
