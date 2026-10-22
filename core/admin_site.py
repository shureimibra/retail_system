from django.contrib import admin
from django.contrib.admin.apps import AdminConfig


class OpsAdminSite(admin.AdminSite):
    """Back office for the people who run Retail OS, never for shop staff."""

    site_header = 'Retail OS operations'
    site_title = 'Retail OS operations'

    def has_permission(self, request):
        return request.user.is_active and request.user.is_superuser


class OpsAdminConfig(AdminConfig):
    default_site = 'core.admin_site.OpsAdminSite'
