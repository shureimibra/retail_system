"""API keys that let a POS or another system work with one shop, and the requests they've sent."""
import hashlib
import secrets

from django.conf import settings
from django.db import models


def hash_key(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


class ApiKey(models.Model):
    READ = 'read'
    STOCK = 'stock'
    PERMISSION_CHOICES = [(READ, 'Read only'), (STOCK, 'Read and change stock')]

    shop = models.ForeignKey('accounts.Shop', on_delete=models.CASCADE, related_name='api_keys')
    name = models.CharField(max_length=60, help_text='What uses it, e.g. Loyverse or Website.')
    permission = models.CharField(max_length=10, choices=PERMISSION_CHOICES, default=READ)
    prefix = models.CharField(max_length=12, unique=True)
    key_hash = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.prefix}…)'

    @property
    def can_change_stock(self):
        return self.permission == self.STOCK

    @classmethod
    def issue(cls, shop, name, permission, created_by=None):
        """A new key. Returns (ApiKey, the full key). The full key is never stored, so it can be shown only now."""
        prefix = 'ros_' + secrets.token_hex(4)
        raw = f'{prefix}_{secrets.token_urlsafe(32)}'
        key = cls.objects.create(shop=shop, name=name, permission=permission, prefix=prefix,
                                 key_hash=hash_key(raw), created_by=created_by)
        return key, raw


class ConnectionRequest(models.Model):
    """A change sent with an Idempotency-Key: sending it again returns the first answer instead of applying it twice."""
    key = models.ForeignKey(ApiKey, on_delete=models.CASCADE, related_name='requests')
    idempotency_key = models.CharField(max_length=100)
    path = models.CharField(max_length=100)
    status_code = models.PositiveSmallIntegerField()
    response = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['key', 'idempotency_key'], name='unique_idempotency_key')]
