from django.contrib import admin
from .models import BlockedPurchaseIntent, IntentEvent, Payment

@admin.register(BlockedPurchaseIntent)
class BlockedPurchaseIntentAdmin(admin.ModelAdmin):
    list_display = ('product', 'customer', 'status', 'constraint_type', 'created_at')
    list_filter = ('status', 'constraint_type')
    search_fields = ('product__name', 'customer__phone_number')
    readonly_fields = ('status',)
    inlines = []


class IntentEventInline(admin.TabularInline):
    model = IntentEvent
    extra = 0
    can_delete = False
    readonly_fields = ('kind', 'from_status', 'to_status', 'note', 'actor', 'created_at')


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    can_delete = False
    readonly_fields = ('amount', 'method', 'reference', 'recorded_by', 'created_at')


BlockedPurchaseIntentAdmin.inlines = [PaymentInline, IntentEventInline]
