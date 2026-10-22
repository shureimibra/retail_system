from django import forms
from core.shops import ShopFormMixin
from .models import BlockedPurchaseIntent

class BlockedPurchaseIntentForm(ShopFormMixin, forms.ModelForm):
    shop_scoped_fields = {'customer': 'shop', 'product': 'shop', 'variation': 'product__shop'}

    class Meta:
        model = BlockedPurchaseIntent
        fields = ['customer', 'product', 'variation', 'constraint_type', 'requested_quantity', 'estimated_value', 'status', 'notes']
        widgets = {
            'constraint_type': forms.Select(attrs={'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-darkborder bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary focus:border-primary'}),
            'customer': forms.Select(attrs={'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-darkborder bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary focus:border-primary'}),
            'product': forms.Select(attrs={'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-darkborder bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary focus:border-primary'}),
            'variation': forms.Select(attrs={'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-darkborder bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary focus:border-primary'}),
            'requested_quantity': forms.NumberInput(attrs={'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-darkborder bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary focus:border-primary'}),
            'estimated_value': forms.NumberInput(attrs={'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-darkborder bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary focus:border-primary'}),
            'status': forms.Select(attrs={'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-darkborder bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary focus:border-primary'}),
            'notes': forms.Textarea(attrs={'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-darkborder bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary focus:border-primary', 'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'status' in self.fields and self.instance.pk:
            from .services import allowed_next_statuses
            allowed = {self.instance.status} | allowed_next_statuses(self.instance)
            self.fields['status'].choices = [c for c in BlockedPurchaseIntent.STATUS_CHOICES if c[0] in allowed]
