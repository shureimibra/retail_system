from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from core.shops import ShopViewMixin, can_add_products, can_manage_catalog
from . import services
from .forms import ProductForm
from .models import Product, ProductVariation
from .selectors import product_detail


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

    def get_success_url(self):
        return reverse('products:detail', args=[self.object.pk])

    def test_func(self):
        return can_add_products(self.request)

    def form_valid(self, form):
        form.instance.needs_review = not can_manage_catalog(self.request)
        return super().form_valid(form)


class ProductUpdateView(ShopViewMixin, UserPassesTestMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'products/product_form.html'

    def get_success_url(self):
        return reverse('products:detail', args=[self.object.pk])

    def test_func(self):
        return can_manage_catalog(self.request)

    def form_valid(self, form):
        # Price changes go through the service so they're recorded (and can trigger price-drop messages).
        new_price = form.cleaned_data['base_price']
        form.instance.base_price = Product.objects.get(pk=form.instance.pk).base_price
        response = super().form_valid(form)
        services.change_price(self.object, new_price, changed_by=self.request.user)
        return response


class ProductDetailView(ShopViewMixin, TemplateView):
    """One product: stock and waiting customers for every size and colour, price, photos and deliveries."""
    template_name = 'products/product_detail.html'

    def get_product(self):
        return get_object_or_404(Product.objects.select_related('product_type', 'category'),
                                 pk=self.kwargs['pk'], shop=self.request.shop)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_product()
        context['product'] = product
        context['detail'] = product_detail(product)
        context['can_manage'] = can_manage_catalog(self.request)
        receive = self.request.GET.get('receive', '')
        context['receive_id'] = int(receive) if receive.isdigit() else None
        return context

    def post(self, request, pk):
        if not can_manage_catalog(request):
            raise PermissionDenied('Only the owner or a manager can change stock, prices and photos.')
        product = self.get_product()
        action = request.POST.get('action')
        here = reverse('products:detail', args=[product.pk])
        if action == 'receive':
            variation = get_object_or_404(ProductVariation, pk=request.POST.get('variation'), product=product)
            try:
                quantity = int(request.POST.get('quantity') or 0)
            except ValueError:
                quantity = 0
            if quantity < 1:
                messages.error(request, 'Enter how many units arrived (1 or more).')
                return redirect(f'{here}?receive={variation.pk}#receive')
            services.receive_stock(variation.pk, quantity, recorded_by=request.user,
                                   reference=request.POST.get('reference', '')[:100])
            messages.success(request, f'{quantity} × {variation.label or variation.sku} received. '
                                      'Customers waiting for it are being told.')
        elif action == 'price':
            try:
                new_price = Decimal(request.POST.get('price') or '')
            except InvalidOperation:
                new_price = None
            if new_price is None or new_price < 0:
                messages.error(request, 'Enter the new price as a number.')
            else:
                change = services.change_price(product, new_price, changed_by=request.user)
                if change and change.is_drop:
                    messages.success(request, 'Price lowered. Customers who said it was too expensive are being told.')
                else:
                    messages.success(request, 'Price saved')
        elif action == 'photo':
            image = request.FILES.get('image')
            value = request.POST.get('value', '')
            if not image:
                messages.error(request, 'Choose a photo first.')
            elif value:
                services.set_option_photo(product, value, image)
                messages.success(request, f'Photo for {value} saved')
            else:
                product.image = image
                product.save()
                messages.success(request, 'Product photo saved')
        elif action == 'add':
            values = [request.POST.get(f'option{i}', '').strip()[:50] for i in (1, 2, 3)]
            if not any(values):
                messages.error(request, 'Fill in at least one option, for example the size.')
            elif ProductVariation.objects.filter(product=product, option1=values[0] or None,
                                                 option2=values[1] or None, option3=values[2] or None).exists():
                messages.error(request, 'That size and colour is already listed.')
            else:
                try:
                    stock = max(0, int(request.POST.get('stock') or 0))
                except ValueError:
                    stock = 0
                variation = services.create_product_variation(
                    product, values[0] or None, values[1] or None, stock,
                    services.suggest_sku(product, *values), option3=values[2] or None, recorded_by=request.user)
                messages.success(request, f'{variation.label} added')
        return redirect(here)
