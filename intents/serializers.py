from rest_framework import serializers
from core.shops import ShopScopedSerializerMixin
from .models import BlockedPurchaseIntent
from customers.serializers import CustomerSerializer
from products.serializers import ProductSerializer, ProductVariationSerializer

class BlockedPurchaseIntentSerializer(ShopScopedSerializerMixin, serializers.ModelSerializer):
    shop_scoped_fields = {'customer': 'shop', 'product': 'shop', 'variation': 'product__shop'}
    customer_detail = CustomerSerializer(source='customer', read_only=True)
    product_detail = ProductSerializer(source='product', read_only=True)
    variation_detail = ProductVariationSerializer(source='variation', read_only=True)
    recorded_by_username = serializers.ReadOnlyField(source='recorded_by.username')

    class Meta:
        model = BlockedPurchaseIntent
        fields = [
            'id', 'customer', 'customer_detail',
            'product', 'product_detail',
            'variation', 'variation_detail',
            'constraint_type', 'status', 'notes',
            'requested_quantity', 'estimated_value',
            'created_at', 'updated_at', 'recorded_by', 'recorded_by_username'
        ]
        read_only_fields = ['recorded_by', 'created_at', 'updated_at']
