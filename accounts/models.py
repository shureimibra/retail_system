from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    THEME_CHOICES = [('system', 'Match my device'), ('light', 'Light'), ('dark', 'Dark')]

    phone_number = models.CharField(max_length=15, blank=True, null=True)
    is_staff_member = models.BooleanField(default=False)
    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default='system')

    def __str__(self):
        return self.username


class Shop(models.Model):
    name = models.CharField(max_length=150)
    phone_region = models.CharField(max_length=2, default='KE', help_text='Used to read local phone numbers, e.g. KE.')
    currency = models.CharField(max_length=3, default='KES')
    timezone = models.CharField(max_length=64, default='Africa/Nairobi')
    cashiers_can_add_products = models.BooleanField(default=True)
    logo = models.ImageField(upload_to='shops/', blank=True)
    # How the shop follows up (Settings → Follow-ups and holds).
    follow_up_days = models.CharField(max_length=40, default='2,4,7',
                                      help_text='Days after the first message to send reminders, e.g. 2, 4, 7.')
    expire_days_after_last_follow_up = models.PositiveSmallIntegerField(default=1)
    stock_hold_days = models.PositiveSmallIntegerField(default=8)
    reserve_pickup_days = models.PositiveSmallIntegerField(default=5)
    # How long a supplier usually takes. To order suggests enough for the customers likely to ask meanwhile.
    delivery_days = models.PositiveSmallIntegerField(default=7)
    default_channel = models.CharField(max_length=20, default='whatsapp',
                                       choices=[('whatsapp', 'WhatsApp'), ('sms', 'SMS'), ('email', 'Email')])
    # Sent by the "Send payment details" quick reply in Conversations.
    payment_details = models.TextField(blank=True, help_text='For example: M-Pesa Till 123456, Kimathi Street Store.')
    # Settings → Home layout: role → ordered widget keys. Empty means the defaults in dashboard/widgets.py.
    home_layout = models.JSONField(default=dict, blank=True)
    # The public "Ask for your size" link: /ask/<link_name>/.
    link_name = models.SlugField(max_length=60, unique=True, null=True, blank=True)
    link_on = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        from core.images import square_logo
        square_logo(self.logo)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def follow_up_schedule(self):
        days = sorted({int(d) for d in self.follow_up_days.replace(' ', '').split(',') if d.isdigit() and int(d) > 0})
        return days


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
