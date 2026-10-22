from django.views.generic import ListView, CreateView, UpdateView
from django.urls import reverse_lazy

from core.shops import ShopViewMixin
from .models import Customer
from .forms import CustomerForm


class CustomerListView(ShopViewMixin, ListView):
    model = Customer
    template_name = 'customers/customer_list.html'
    context_object_name = 'customers'
    paginate_by = 10
    ordering = ['-created_at']


class CustomerCreateView(ShopViewMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'customers/customer_form.html'
    success_url = reverse_lazy('customers:list')


class CustomerUpdateView(ShopViewMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'customers/customer_form.html'
    success_url = reverse_lazy('customers:list')
