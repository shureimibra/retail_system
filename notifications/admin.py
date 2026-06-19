from django.contrib import admin
from .models import NotificationLog, InboundSMSLog

@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ('intent', 'status', 'sent_at')
    list_filter = ('status',)

@admin.register(InboundSMSLog)
class InboundSMSLogAdmin(admin.ModelAdmin):
    list_display = ('from_number', 'to_number', 'customer', 'received_at')
    list_filter = ('received_at',)
    search_fields = ('from_number', 'body')

