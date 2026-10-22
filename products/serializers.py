from rest_framework import serializers
from core.shops import ShopScopedSerializerMixin
from .models import Category, Product, ProductVariation

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'
        read_only_fields = ['shop']

class ProductVariationSerializer(ShopScopedSerializerMixin, serializers.ModelSerializer):
    shop_scoped_fields = {'product': 'shop'}

    class Meta:
        model = ProductVariation
        fields = '__all__'

class ProductSerializer(ShopScopedSerializerMixin, serializers.ModelSerializer):
    shop_scoped_fields = {'category': 'shop'}
    category_name = serializers.ReadOnlyField(source='category.name')
    variations = ProductVariationSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = ['id', 'category', 'category_name', 'name', 'description', 'base_price', 'created_at', 'updated_at', 'variations']
