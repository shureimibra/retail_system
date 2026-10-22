from django import forms
from core.shops import ShopFormMixin
from .models import Product

class ProductForm(ShopFormMixin, forms.ModelForm):
    shop_scoped_fields = {'category': 'shop', 'product_type': 'shop'}

    class Meta:
        model = Product
        fields = ['name', 'product_type', 'category', 'description', 'base_price', 'supplier', 'image']
        labels = {'base_price': 'Price'}
        widgets = {
            'base_price': forms.NumberInput(attrs={'inputmode': 'decimal', 'step': '1', 'min': '0'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product_type'].empty_label = 'Choose a type'
        self.fields['category'].empty_label = 'Choose a category'
