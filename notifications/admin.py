from django.contrib import admin

from .models import Conversation, Message


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'direction', 'channel', 'to_address', 'from_address', 'template_key', 'status', 'provider')
    list_filter = ('direction', 'channel', 'status', 'provider')
    search_fields = ('to_address', 'from_address', 'body', 'provider_message_id')
    readonly_fields = [f.name for f in Message._meta.fields]


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('customer', 'shop', 'unread_count', 'last_message_at')
    list_filter = ('shop',)
