from django import forms
from django.db.models import Q
from core.forms import PhotoFieldsMixin
from core.shops import ShopFormMixin
from .models import Category, Product

class ProductForm(PhotoFieldsMixin, ShopFormMixin, forms.ModelForm):
    photo_fields = ('image',)
    shop_scoped_fields = {'category': 'shop', 'product_type': 'shop'}

    class Meta:
        model = Product
        fields = ['name', 'product_type', 'category', 'description', 'base_price', 'supplier', 'image']
        labels = {'base_price': 'Price', 'product_type': 'Type'}
        widgets = {
            'base_price': forms.NumberInput(attrs={'inputmode': 'decimal', 'step': '1', 'min': '0'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    new_category = forms.CharField(required=False, max_length=100, label='Or a new category',
                                   widget=forms.TextInput(attrs={'placeholder': 'e.g. Running, Denim, Watches'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product_type'].empty_label = 'Choose a type'
        self.fields['product_type'].required = True
        self.fields['category'].empty_label = 'Choose a category'
        self.fields['category'].required = False  # a new one can be typed instead
        # Each option says which type it belongs to, so the page shows only the matching ones.
        self.fields['category'].widget = CategorySelect(choices=self.fields['category'].choices)

    def clean(self):
        cleaned = super().clean()
        product_type, category = cleaned.get('product_type'), cleaned.get('category')
        new_name = (cleaned.get('new_category') or '').strip()
        if new_name:
            shop = self.shop or getattr(self.instance, 'shop', None)
            existing = Category.objects.filter(shop=shop, name__iexact=new_name).filter(
                Q(product_type=product_type) | Q(product_type__isnull=True)).first()
            cleaned['category'] = existing or Category.objects.create(shop=shop, name=new_name, product_type=product_type)
        elif category is None:
            if product_type is not None and product_type.name.lower() == 'other':
                self.add_error('new_category', 'Say what it is, for example Watches or Belts.')
            else:
                self.add_error('category', 'Choose a category, or type a new one.')
        elif product_type is not None and category.product_type_id not in (None, product_type.pk):
            self.add_error('category', f'{category.name} belongs to {category.product_type.name}. Choose one for {product_type.name}.')
        return cleaned


class CategorySelect(forms.Select):
    """A category drop-down whose options carry their type, for the filtering script."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, 'instance', None)
        if instance is not None and instance.product_type_id:
            option['attrs']['data-type'] = str(instance.product_type_id)
        return option
