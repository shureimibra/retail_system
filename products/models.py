from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models
from PIL import Image, ImageOps

from accounts.models import default_shop_id

MAX_PHOTO_PX = 1200

# Starter product types for fashion shops. Option 1 is always the size and
# option 2 the colour, so every type reads the same way at the till.
# (name, option 1, its values, option 2, its values, option 3, its values)
FASHION_PRODUCT_TYPES = [
    ('Shoes', 'Size', '36,37,38,39,40,41,42,43,44,45,46', 'Colour', '', '', ''),
    ('Clothing', 'Size', 'XS,S,M,L,XL,XXL', 'Colour', '', 'Fit', 'Slim,Regular,Relaxed'),
    ('Bags', 'Size', 'One size,Small,Medium,Large', 'Colour', '', 'Style', ''),
    ('Accessories', 'Size', 'One size,S,M,L', 'Colour', '', '', ''),
    ('Other', 'Size', '', 'Colour', '', '', ''),
]


def _shrink_photo(image_field):
    """Resize a newly uploaded photo so its longest side is at most MAX_PHOTO_PX."""
    if not image_field or getattr(image_field, '_committed', True):
        return
    image = ImageOps.exif_transpose(Image.open(image_field))
    if max(image.size) <= MAX_PHOTO_PX:
        image_field.seek(0)
        return
    image.thumbnail((MAX_PHOTO_PX, MAX_PHOTO_PX))
    buffer = BytesIO()
    image.convert('RGB').save(buffer, format='JPEG', quality=85, optimize=True)
    image_field.save(Path(image_field.name).stem + '.jpg', ContentFile(buffer.getvalue()), save=False)


class Category(models.Model):
    shop = models.ForeignKey('accounts.Shop', on_delete=models.CASCADE, default=default_shop_id, related_name='categories')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name


class ProductType(models.Model):
    """What kind of item this is (Shoes, Clothing...) and what its options are called."""
    shop = models.ForeignKey('accounts.Shop', on_delete=models.CASCADE, default=default_shop_id, related_name='product_types')
    name = models.CharField(max_length=60)
    option1_name = models.CharField(max_length=30, default='Size')
    option1_values = models.TextField(blank=True, help_text='Suggested values, separated by commas.')
    option2_name = models.CharField(max_length=30, default='Colour')
    option2_values = models.TextField(blank=True)
    option3_name = models.CharField(max_length=30, blank=True)
    option3_values = models.TextField(blank=True)

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(fields=['shop', 'name'], name='unique_product_type_per_shop'),
        ]

    def __str__(self):
        return self.name

    @property
    def options(self):
        """[(name, [suggested values]), ...] for the options this type uses."""
        result = []
        for name, values in ((self.option1_name, self.option1_values),
                             (self.option2_name, self.option2_values),
                             (self.option3_name, self.option3_values)):
            if name:
                result.append((name, [v.strip() for v in values.split(',') if v.strip()]))
        return result


class Product(models.Model):
    shop = models.ForeignKey('accounts.Shop', on_delete=models.CASCADE, default=default_shop_id, related_name='products')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    product_type = models.ForeignKey(ProductType, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to='products/', blank=True)
    needs_review = models.BooleanField(default=False, help_text='Added by a cashier; an owner or manager should check price and options.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        _shrink_photo(self.image)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductVariation(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variations')
    option1 = models.CharField(max_length=50, blank=True, null=True)
    option2 = models.CharField(max_length=50, blank=True, null=True)
    option3 = models.CharField(max_length=50, blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text='Leave blank to use the product price.')
    image = models.ImageField(upload_to='products/', blank=True, help_text='Photo of this colour, sent with restock messages.')
    stock_quantity = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=100, unique=True)

    def save(self, *args, **kwargs):
        _shrink_photo(self.image)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} - {self.label}"

    # Older screens and reports read size and colour directly.
    @property
    def size(self):
        return self.option1

    @property
    def color(self):
        return self.option2

    @property
    def label(self):
        return ' / '.join(v for v in (self.option1, self.option2, self.option3) if v)

    @property
    def effective_price(self):
        return self.price if self.price is not None else self.product.base_price

    @property
    def photo(self):
        return self.image or self.product.image

    @property
    def held_quantity(self):
        return sum(self.holds.filter(status=StockHold.ACTIVE).values_list('quantity', flat=True))

    @property
    def available_quantity(self):
        return max(0, self.stock_quantity - self.held_quantity)


class PriceChange(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='price_changes')
    variation = models.ForeignKey(ProductVariation, on_delete=models.CASCADE, null=True, blank=True, related_name='price_changes')
    old_price = models.DecimalField(max_digits=10, decimal_places=2)
    new_price = models.DecimalField(max_digits=10, decimal_places=2)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def is_drop(self):
        return self.new_price < self.old_price


class StockMovement(models.Model):
    RECEIVED = 'received'
    ADJUSTED = 'adjusted'
    SOLD = 'sold'
    KIND_CHOICES = [
        (RECEIVED, 'Received'),
        (ADJUSTED, 'Adjusted'),
        (SOLD, 'Sold to a waiting customer'),
    ]

    variation = models.ForeignKey(ProductVariation, on_delete=models.CASCADE, related_name='stock_movements')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    quantity_change = models.IntegerField()
    stock_after = models.PositiveIntegerField()
    reference = models.CharField(max_length=100, blank=True, help_text='For example a delivery note number.')
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class StockHold(models.Model):
    """One unit put aside for a waiting customer so a walk-in can't buy it first."""
    ACTIVE = 'active'
    RELEASED = 'released'
    SOLD = 'sold'
    STATUS_CHOICES = [
        (ACTIVE, 'Active'),
        (RELEASED, 'Released'),
        (SOLD, 'Sold'),
    ]

    variation = models.ForeignKey(ProductVariation, on_delete=models.CASCADE, related_name='holds')
    intent = models.ForeignKey('intents.BlockedPurchaseIntent', on_delete=models.CASCADE, related_name='holds')
    quantity = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=ACTIVE)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
