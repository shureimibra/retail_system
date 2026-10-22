from rest_framework import viewsets
from . import services
from .models import Category, Product, ProductVariation
from .serializers import CategorySerializer, ProductSerializer, ProductVariationSerializer

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().select_related('category').prefetch_related('variations')
    serializer_class = ProductSerializer

class ProductVariationViewSet(viewsets.ModelViewSet):
    queryset = ProductVariation.objects.all().select_related('product')
    serializer_class = ProductVariationSerializer
    filterset_fields = ['product']

    def perform_create(self, serializer):
        new_stock = serializer.validated_data.pop('stock_quantity', 0)
        variation = serializer.save(stock_quantity=0)
        if new_stock:
            services.set_stock(variation.id, new_stock)
        variation.refresh_from_db()

    def perform_update(self, serializer):
        new_stock = serializer.validated_data.pop('stock_quantity', None)
        variation = serializer.save()
        if new_stock is not None:
            services.set_stock(variation.id, new_stock)
        variation.refresh_from_db()
