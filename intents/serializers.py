from rest_framework import serializers
from core.shops import ShopScopedSerializerMixin
from .models import BlockedPurchaseIntent, IntentEvent, Payment
from customers.serializers import CustomerSerializer
from products.serializers import ProductSerializer, ProductVariationSerializer


class BlockedPurchaseIntentSerializer(ShopScopedSerializerMixin, serializers.ModelSerializer):
    shop_scoped_fields = {'customer': 'shop', 'product': 'shop', 'variation': 'product__shop'}
    customer_detail = CustomerSerializer(source='customer', read_only=True)
    product_detail = ProductSerializer(source='product', read_only=True)
    variation_detail = ProductVariationSerializer(source='variation', read_only=True)
    recorded_by_username = serializers.ReadOnlyField(source='recorded_by.username')
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    reason_label = serializers.CharField(source='get_constraint_type_display', read_only=True)
    amount_paid = serializers.ReadOnlyField()
    balance = serializers.ReadOnlyField()

    class Meta:
        model = BlockedPurchaseIntent
        fields = [
            'id', 'customer', 'customer_detail',
            'product', 'product_detail',
            'variation', 'variation_detail',
            'constraint_type', 'reason_label', 'status', 'status_label', 'notes',
            'requested_quantity', 'estimated_value', 'amount_paid', 'balance',
            'consent_given', 'preferred_channel', 'needed_by', 'expected_at', 'pickup_by', 'closed_reason',
            'created_at', 'updated_at', 'expires_at', 'recorded_by', 'recorded_by_username'
        ]
        # Status only changes through the transition, payment and change-item actions.
        read_only_fields = ['status', 'expected_at', 'pickup_by', 'closed_reason',
                            'recorded_by', 'created_at', 'updated_at', 'expires_at']


class IntentEventSerializer(serializers.ModelSerializer):
    actor = serializers.ReadOnlyField(source='actor.username')

    class Meta:
        model = IntentEvent
        fields = ['kind', 'from_status', 'to_status', 'note', 'data', 'actor', 'created_at']


class PaymentSerializer(serializers.ModelSerializer):
    recorded_by = serializers.ReadOnlyField(source='recorded_by.username')

    class Meta:
        model = Payment
        fields = ['amount', 'method', 'reference', 'recorded_by', 'created_at']
