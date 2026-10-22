from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.shops import CatalogPermission, ShopScopedViewSetMixin, can_manage_catalog
from . import services
from .models import Category, Product, ProductType, ProductVariation
from .serializers import (CategorySerializer, ProductSerializer, ProductTypeSerializer,
                          ProductVariationSerializer, ReceiveStockSerializer)


class CategoryViewSet(ShopScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated, CatalogPermission]


class ProductTypeViewSet(ShopScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ProductType.objects.all()
    serializer_class = ProductTypeSerializer


class ProductViewSet(ShopScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Product.objects.all().select_related('category', 'product_type').prefetch_related('variations')
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated, CatalogPermission]
    cashier_can_create = True

    def perform_create(self, serializer):
        serializer.save(shop=self.request.shop, needs_review=not can_manage_catalog(self.request))

    def perform_update(self, serializer):
        new_price = serializer.validated_data.pop('base_price', None)
        product = serializer.save()
        if new_price is not None:
            services.change_price(product, new_price, changed_by=self.request.user)
        product.refresh_from_db()


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
        # Cashiers can add a missing size or colour, but only managers add stock.
        if new_stock and can_manage_catalog(self.request):
            services.receive_stock(variation.id, new_stock, recorded_by=self.request.user)
        variation.refresh_from_db()

    def perform_update(self, serializer):
        new_stock = serializer.validated_data.pop('stock_quantity', None)
        new_price = serializer.validated_data.pop('price', None)
        variation = serializer.save()
        if new_price is not None:
            services.change_price(variation.product, new_price, changed_by=self.request.user, variation=variation)
        if new_stock is not None:
            services.set_stock(variation.id, new_stock, recorded_by=self.request.user)
        variation.refresh_from_db()

    @action(detail=True, methods=['post'])
    def receive(self, request, pk=None):
        """A delivery arrived: add stock (owners and managers only)."""
        if not can_manage_catalog(request):
            return Response({'detail': 'Only owners and managers can receive stock.'}, status=status.HTTP_403_FORBIDDEN)
        variation = self.get_object()
        payload = ReceiveStockSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        services.receive_stock(variation.id, payload.validated_data['quantity'],
                               recorded_by=request.user, reference=payload.validated_data.get('reference', ''))
        variation.refresh_from_db()
        return Response(self.get_serializer(variation).data)
