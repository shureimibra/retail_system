from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseForbidden
from django.template.loader import render_to_string
from rest_framework import permissions

from accounts.models import Membership, Shop

OPEN_PATH_PREFIXES = ('/accounts/', '/static/', '/media/', '/api/health/', '/notifications/webhook')


class CurrentShopMiddleware:
    """
    Sets request.shop and request.membership for signed-in users. Shop staff
    without a shop get a clear explanation instead of an empty app. Superusers
    (platform operators) without a membership act as owner of the first shop.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.shop = None
        request.membership = None
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            membership = (Membership.objects.select_related('shop')
                          .filter(user=user).order_by('id').first())
            if membership:
                request.membership = membership
                request.shop = membership.shop
            elif user.is_superuser:
                request.shop = Shop.objects.order_by('id').first()
            elif not self._is_open_path(request.path):
                return HttpResponseForbidden(render_to_string('accounts/no_shop.html', request=request))
        return self.get_response(request)

    @staticmethod
    def _is_open_path(path):
        from django.conf import settings
        return path.startswith(OPEN_PATH_PREFIXES) or path.startswith('/' + settings.ADMIN_URL)


def role_of(request):
    if request.membership:
        return request.membership.role
    if request.user.is_authenticated and request.user.is_superuser:
        return Membership.OWNER
    return None


def can_manage_catalog(request):
    return role_of(request) in (Membership.OWNER, Membership.MANAGER)


def can_add_products(request):
    if can_manage_catalog(request):
        return True
    return role_of(request) == Membership.CASHIER and bool(request.shop and request.shop.cashiers_can_add_products)


class CatalogPermission(permissions.BasePermission):
    """Everyone in the shop reads the catalog; owners and managers change it.
    Cashiers may add products and variations when the shop allows it."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        if request.method == 'POST' and getattr(view, 'cashier_can_create', False):
            return can_add_products(request)
        return can_manage_catalog(request)


class ManagersDeletePermission(permissions.BasePermission):
    """Any shop member can create and edit; only owners and managers delete."""

    def has_permission(self, request, view):
        if request.method == 'DELETE':
            return can_manage_catalog(request)
        return True


class ShopScopedViewSetMixin:
    """Limit an API viewset to the request's shop and stamp new records with it."""
    shop_lookup = 'shop'

    def get_queryset(self):
        return super().get_queryset().filter(**{self.shop_lookup: self.request.shop})

    def perform_create(self, serializer):
        if self.shop_lookup == 'shop':
            serializer.save(shop=self.request.shop)
        else:
            serializer.save()


class ShopScopedSerializerMixin:
    """Only let related fields point at records in the request's shop."""
    shop_scoped_fields = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        shop = getattr(self.context.get('request'), 'shop', None)
        if shop is None:
            return
        for name, lookup in self.shop_scoped_fields.items():
            field = self.fields.get(name)
            if field is not None and getattr(field, 'queryset', None) is not None:
                field.queryset = field.queryset.filter(**{lookup: shop})


class ShopFormMixin:
    """Form side of shop scoping: related choices come from the shop only,
    and new records are stamped with the shop."""
    shop_scoped_fields = {}

    def __init__(self, *args, shop=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.shop = shop
        if shop is None:
            return
        if not self.instance.pk:
            self.instance.shop = shop
        for name, lookup in self.shop_scoped_fields.items():
            if name in self.fields:
                self.fields[name].queryset = self.fields[name].queryset.filter(**{lookup: shop})


class ShopViewMixin(LoginRequiredMixin):
    """View side of shop scoping for list, create and update pages."""

    def get_queryset(self):
        return super().get_queryset().filter(shop=self.request.shop)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['shop'] = self.request.shop
        return kwargs
