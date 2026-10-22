from django.contrib.auth.mixins import UserPassesTestMixin
from django.views.generic import ListView, CreateView, UpdateView
from django.urls import reverse_lazy

from core.shops import ShopViewMixin, can_add_products, can_manage_catalog
from .models import Product
from .forms import ProductForm


class ProductListView(ShopViewMixin, ListView):
    model = Product
    template_name = 'products/product_list.html'
    context_object_name = 'products'
    paginate_by = 10
    ordering = ['name']


class ProductCreateView(ShopViewMixin, UserPassesTestMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'products/product_form.html'
    success_url = reverse_lazy('products:list')

    def test_func(self):
        return can_add_products(self.request)


class ProductUpdateView(ShopViewMixin, UserPassesTestMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'products/product_form.html'
    success_url = reverse_lazy('products:list')

    def test_func(self):
        return can_manage_catalog(self.request)
