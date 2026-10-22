from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    is_staff_member = models.BooleanField(default=False)

    def __str__(self):
        return self.username


class Shop(models.Model):
    name = models.CharField(max_length=150)
    phone_region = models.CharField(max_length=2, default='KE', help_text='Used to read local phone numbers, e.g. KE.')
    currency = models.CharField(max_length=3, default='KES')
    timezone = models.CharField(max_length=64, default='Africa/Nairobi')
    cashiers_can_add_products = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


def default_shop_id():
    """
    The shop new records belong to when none is given. While Retail OS runs one
    shop per installation this is that shop; views always pass the shop explicitly.
    """
    shop_id = Shop.objects.order_by('id').values_list('id', flat=True).first()
    if shop_id is None:
        shop_id = Shop.objects.create(name='My Shop').id
    return shop_id


class Membership(models.Model):
    OWNER = 'owner'
    MANAGER = 'manager'
    CASHIER = 'cashier'
    ROLE_CHOICES = [
        (OWNER, 'Owner'),
        (MANAGER, 'Manager'),
        (CASHIER, 'Cashier'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memberships')
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=CASHIER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'shop'], name='unique_membership_per_shop'),
        ]

    def __str__(self):
        return f'{self.user} – {self.get_role_display()} at {self.shop}'

    @property
    def can_manage_catalog(self):
        return self.role in (self.OWNER, self.MANAGER)
