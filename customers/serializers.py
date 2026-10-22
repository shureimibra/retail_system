from rest_framework import serializers
from core.phones import normalize_phone
from .models import Customer, INVALID_PHONE_MESSAGE

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'

    def validate_phone_number(self, value):
        normalized = normalize_phone(value)
        if not normalized:
            raise serializers.ValidationError(INVALID_PHONE_MESSAGE)
        queryset = Customer.objects.filter(phone_number=normalized)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError('A customer with this phone number already exists.')
        return normalized
