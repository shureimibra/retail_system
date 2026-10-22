from django import forms
from core.phones import normalize_phone
from core.shops import ShopFormMixin
from .models import Customer, INVALID_PHONE_MESSAGE

class CustomerForm(ShopFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['first_name', 'last_name', 'phone_number', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-darkborder bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary focus:border-primary'}),
            'last_name': forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-darkborder bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary focus:border-primary'}),
            'phone_number': forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-darkborder bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary focus:border-primary'}),
            'email': forms.EmailInput(attrs={'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-darkborder bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary focus:border-primary'}),
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
