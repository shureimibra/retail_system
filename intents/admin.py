from django.contrib import admin
from .models import BlockedPurchaseIntent

@admin.register(BlockedPurchaseIntent)
class BlockedPurchaseIntentAdmin(admin.ModelAdmin):
    list_display = ('product', 'customer', 'status', 'constraint_type', 'created_at')
    list_filter = ('status', 'constraint_type')
    search_fields = ('product__name', 'customer__phone_number')
