from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.shops import CatalogPermission, ShopScopedViewSetMixin, can_manage_catalog
from . import services
from .models import Category, Product, ProductVariation
from .serializers import CategorySerializer, ProductSerializer, ProductVariationSerializer


class CategoryViewSet(ShopScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated, CatalogPermission]


class ProductViewSet(ShopScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Product.objects.all().select_related('category').prefetch_related('variations')
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated, CatalogPermission]
    cashier_can_create = True


class ProductVariationViewSet(ShopScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = ProductVariation.objects.all().select_related('product')
    serializer_class = ProductVariationSerializer
    filterset_fields = ['product']
    permission_classes = [IsAuthenticated, CatalogPermission]
    shop_lookup = 'product__shop'
    cashier_can_create = True

    def perform_create(self, serializer):
        new_stock = serializer.validated_data.pop('stock_quantity', 0)
        variation = serializer.save(stock_quantity=0)
        # Cashiers can add a missing size or colour, but only managers set stock.
        if new_stock and can_manage_catalog(self.request):
            services.set_stock(variation.id, new_stock)
        variation.refresh_from_db()

    def perform_update(self, serializer):
        new_stock = serializer.validated_data.pop('stock_quantity', None)
        variation = serializer.save()
        if new_stock is not None:
            services.set_stock(variation.id, new_stock)
        variation.refresh_from_db()
