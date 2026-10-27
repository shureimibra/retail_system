from django import forms
from core.shops import ShopFormMixin
from .models import BlockedPurchaseIntent

class BlockedPurchaseIntentForm(ShopFormMixin, forms.ModelForm):
    shop_scoped_fields = {'customer': 'shop', 'product': 'shop', 'variation': 'product__shop'}

    class Meta:
        model = BlockedPurchaseIntent
        fields = ['customer', 'product', 'variation', 'constraint_type', 'requested_quantity', 'estimated_value', 'status', 'notes']
        labels = {'constraint_type': "Why they didn't buy", 'variation': 'Size and colour',
                  'requested_quantity': 'Quantity', 'estimated_value': 'Value'}
        help_texts = {'estimated_value': 'Leave blank to use the price times the quantity.'}
        widgets = {
            'requested_quantity': forms.NumberInput(attrs={'inputmode': 'numeric', 'min': '1'}),
            'estimated_value': forms.NumberInput(attrs={'inputmode': 'decimal', 'min': '0'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Plain words instead of Django's "---------" for empty choices.
        for name, label in (('customer', 'Choose a customer'), ('product', 'Choose a product'),
                            ('variation', 'Any size or colour')):
            if name in self.fields:
                self.fields[name].empty_label = label
        if 'variation' in self.fields:
            self.fields['variation'].label_from_instance = lambda v: v.label or v.sku
        if 'constraint_type' in self.fields:
            choices = list(BlockedPurchaseIntent.CAPTURE_CHOICES)
            if self.instance.pk and self.instance.constraint_type == BlockedPurchaseIntent.OVER_BUDGET:
                choices = list(BlockedPurchaseIntent.CONSTRAINT_CHOICES)  # an older record keeps its value
            self.fields['constraint_type'].choices = [('', 'Choose a reason')] + choices
        if 'status' in self.fields and self.instance.pk:
            from .services import allowed_next_statuses
            allowed = {self.instance.status} | allowed_next_statuses(self.instance)
            self.fields['status'].choices = [c for c in BlockedPurchaseIntent.STATUS_CHOICES if c[0] in allowed]
