"""Requests signed with an API key: "Authorization: Bearer ros_…". Each key works for its own shop only."""
from datetime import timedelta
from hmac import compare_digest

from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from rest_framework import permissions
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.throttling import SimpleRateThrottle

from .models import ApiKey, hash_key


class ApiKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = request.META.get('HTTP_AUTHORIZATION', '')
        if not header.startswith('Bearer '):
            return None
        raw = header[len('Bearer '):].strip()
        key = ApiKey.objects.select_related('shop').filter(prefix=raw[:12], revoked_at__isnull=True).first()
        if key is None or not compare_digest(key.key_hash, hash_key(raw)):
            raise AuthenticationFailed('That API key is wrong or was revoked.')
        now = timezone.now()
        if key.last_used_at is None or now - key.last_used_at > timedelta(minutes=1):
            ApiKey.objects.filter(pk=key.pk).update(last_used_at=now)
        request._request.shop = key.shop
        return AnonymousUser(), key

    def authenticate_header(self, request):
        return 'Bearer'


class KeyPermission(permissions.BasePermission):
    message = 'This key can only read. Create one that can change stock in Settings, Connections.'

    def has_permission(self, request, view):
        if not isinstance(request.auth, ApiKey):
            self.message = 'Send your API key: Authorization: Bearer <key>.'
            return False
        return request.method in permissions.SAFE_METHODS or request.auth.can_change_stock


class KeyThrottle(SimpleRateThrottle):
    rate = '300/min'

    def get_cache_key(self, request, view):
        return f'connect-{request.auth.pk}' if isinstance(request.auth, ApiKey) else None
