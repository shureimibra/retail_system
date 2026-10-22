from django.contrib.auth.mixins import UserPassesTestMixin
from django.views.generic import ListView, CreateView, UpdateView
from django.urls import reverse_lazy

from core.shops import ShopViewMixin, can_add_products, can_manage_catalog
from . import services
from .models import Product
from .forms import ProductForm


class ProductListView(ShopViewMixin, ListView):
    model = Product
    template_name = 'products/product_list.html'
    context_object_name = 'products'
    paginate_by = 20
    ordering = ['name']

    def get_queryset(self):
        return super().get_queryset().select_related('category', 'product_type').prefetch_related('variations__holds')


class ProductCreateView(ShopViewMixin, UserPassesTestMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'products/product_form.html'
    success_url = reverse_lazy('products:list')

    def test_func(self):
        return can_add_products(self.request)

    def form_valid(self, form):
        form.instance.needs_review = not can_manage_catalog(self.request)
        return super().form_valid(form)


class ProductUpdateView(ShopViewMixin, UserPassesTestMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'products/product_form.html'
    success_url = reverse_lazy('products:list')

    def test_func(self):
        return can_manage_catalog(self.request)

    def form_valid(self, form):
        # Price changes go through the service so they're recorded (and can trigger price-drop messages).
        new_price = form.cleaned_data['base_price']
        form.instance.base_price = Product.objects.get(pk=form.instance.pk).base_price
        response = super().form_valid(form)
        services.change_price(self.object, new_price, changed_by=self.request.user)
        return response
