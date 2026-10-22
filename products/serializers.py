from rest_framework import serializers

from core.shops import ShopScopedSerializerMixin
from .models import Category, Product, ProductType, ProductVariation


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'
        read_only_fields = ['shop']


class ProductTypeSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()

    class Meta:
        model = ProductType
        fields = ['id', 'name', 'options']

    def get_options(self, obj):
        return [{'name': name, 'values': values} for name, values in obj.options]


class ProductVariationSerializer(ShopScopedSerializerMixin, serializers.ModelSerializer):
    shop_scoped_fields = {'product': 'shop'}
    label = serializers.ReadOnlyField()
    available_quantity = serializers.ReadOnlyField()
    effective_price = serializers.ReadOnlyField()

    class Meta:
        model = ProductVariation
        fields = ['id', 'product', 'option1', 'option2', 'option3', 'label', 'sku', 'price',
                  'effective_price', 'image', 'stock_quantity', 'available_quantity']


class ProductSerializer(ShopScopedSerializerMixin, serializers.ModelSerializer):
    shop_scoped_fields = {'category': 'shop', 'product_type': 'shop'}
    category_name = serializers.ReadOnlyField(source='category.name')
    product_type_name = serializers.ReadOnlyField(source='product_type.name')
    variations = ProductVariationSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = ['id', 'category', 'category_name', 'product_type', 'product_type_name', 'name', 'description',
                  'base_price', 'image', 'needs_review', 'created_at', 'updated_at', 'variations']
        read_only_fields = ['needs_review']


class ReceiveStockSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
