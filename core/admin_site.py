from django.contrib import admin
from django.contrib.admin.apps import AdminConfig


class OpsAdminSite(admin.AdminSite):
    """Back office for the people who run Retail OS, never for shop staff."""

    site_header = 'Retail OS operations'
    site_title = 'Retail OS operations'

    index_template = 'admin/ops_index.html'

    def has_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def get_urls(self):
        from django.urls import path
        return [path('invite-shop/', self.admin_view(self.invite_shop), name='invite_shop')] + super().get_urls()

    def invite_shop(self, request):
        """A new shop and its owner's one-time link, shown once to send by WhatsApp or email."""
        from django.template.response import TemplateResponse
        from accounts import services
        context = {**self.each_context(request), 'title': 'Invite a new shop'}
        if request.method == 'POST':
            shop_name = request.POST.get('shop_name', '').strip()
            owner_name = request.POST.get('owner_name', '').strip()
            contact = request.POST.get('contact', '').strip()
            if not shop_name or not owner_name:
                context.update({'error': "Enter the shop's name and the owner's name.", 'form': request.POST})
            else:
                shop, invitation, raw = services.invite_new_shop(shop_name, owner_name, contact, created_by=request.user)
                context.update({'shop': shop, 'invitation': invitation, 'link': services.invitation_url(raw)})
        return TemplateResponse(request, 'admin/invite_shop.html', context)


class OpsAdminConfig(AdminConfig):
    default_site = 'core.admin_site.OpsAdminSite'
