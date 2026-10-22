from django import forms
from core.phones import normalize_phone
from core.shops import ShopFormMixin
from .models import Customer, INVALID_PHONE_MESSAGE

class CustomerForm(ShopFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['first_name', 'last_name', 'phone_number', 'email']
        labels = {'phone_number': 'Phone'}
        widgets = {
            'phone_number': forms.TextInput(attrs={'inputmode': 'tel', 'autocomplete': 'tel', 'placeholder': '0712 345 678'}),
            'email': forms.EmailInput(attrs={'autocomplete': 'email'}),
        }

    def clean_phone_number(self):
        normalized = normalize_phone(self.cleaned_data.get('phone_number'))
        if not normalized:
            raise forms.ValidationError(INVALID_PHONE_MESSAGE)
        duplicates = Customer.objects.filter(shop_id=self.instance.shop_id, phone_number=normalized)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError('A customer with this phone number already exists.')
        return normalized
