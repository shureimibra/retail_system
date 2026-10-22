from rest_framework import serializers
from core.phones import normalize_phone
from .models import Customer, INVALID_PHONE_MESSAGE

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'
        read_only_fields = ['shop']
        validators = []  # phone uniqueness per shop is checked in validate_phone_number

    def validate_phone_number(self, value):
        normalized = normalize_phone(value)
        if not normalized:
            raise serializers.ValidationError(INVALID_PHONE_MESSAGE)
        shop = getattr(self.context.get('request'), 'shop', None)
        queryset = Customer.objects.filter(shop=shop, phone_number=normalized)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError('A customer with this phone number already exists.')
        return normalized
