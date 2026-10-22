from django import forms
from core.shops import ShopFormMixin
from .models import Product

class ProductForm(ShopFormMixin, forms.ModelForm):
    shop_scoped_fields = {'category': 'shop'}

    class Meta:
        model = Product
        fields = ['name', 'category', 'description', 'base_price']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-darkborder bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary focus:border-primary'}),
            'category': forms.Select(attrs={'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-darkborder bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary focus:border-primary'}),
            'description': forms.Textarea(attrs={'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-darkborder bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary focus:border-primary', 'rows': 4}),
            'base_price': forms.NumberInput(attrs={'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-darkborder bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary focus:border-primary'}),
        }
