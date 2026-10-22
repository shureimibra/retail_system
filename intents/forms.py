from django import forms
from core.shops import ShopFormMixin
from .models import BlockedPurchaseIntent

class BlockedPurchaseIntentForm(ShopFormMixin, forms.ModelForm):
    shop_scoped_fields = {'customer': 'shop', 'product': 'shop', 'variation': 'product__shop'}

    constraint_type = forms.CharField(
        widget=forms.Select(
            choices=BlockedPurchaseIntent.CONSTRAINT_CHOICES,
            attrs={'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-darkborder bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary focus:border-primary'}
        )
    )

    class Meta:
        model = BlockedPurchaseIntent
        fields = ['customer', 'product', 'variation', 'constraint_type', 'requested_quantity', 'estimated_value', 'status', 'notes']
        widgets = {
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
        if self.instance and self.instance.pk and self.instance.constraint_type:
            current_choice = self.instance.constraint_type
            choices = list(self.fields['constraint_type'].widget.choices)
            if not any(c[0] == current_choice for c in choices):
                choices.append((current_choice, current_choice))
                self.fields['constraint_type'].widget.choices = choices
