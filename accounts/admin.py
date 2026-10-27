from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ['username', 'email', 'phone_number', 'is_staff_member', 'is_staff']
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('phone_number', 'is_staff_member')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('phone_number', 'is_staff_member')}),
    )

admin.site.register(User, CustomUserAdmin)


from .models import Invitation, Shop  # noqa: E402


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_demo', 'created_at']
    list_filter = ['is_demo']
    search_fields = ['name']


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    """Who was invited where. The links themselves are never stored, so they can't be shown again here."""
    list_display = ['shop', 'role', 'name', 'contact', 'created_at', 'expires_at', 'used_at']
    list_filter = ['role']
    readonly_fields = ['shop', 'role', 'name', 'contact', 'created_by', 'created_at', 'expires_at', 'used_at', 'used_by']
    exclude = ['token_hash']

    def has_add_permission(self, request):
        return False  # use "Invite a new shop" on the operations home page
