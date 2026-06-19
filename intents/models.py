from django.db import models
from products.models import Product, ProductVariation
from customers.models import Customer
from django.conf import settings

class BlockedPurchaseIntent(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Monitoring', 'Monitoring'),
        ('Customer Notified', 'Customer Notified'),
        ('Resolved', 'Resolved'),
        ('Recovered', 'Recovered'),
        ('Closed', 'Closed'),
    ]

    CONSTRAINT_CHOICES = [
        ('Size unavailable', 'Size unavailable'),
        ('Color unavailable', 'Color unavailable'),
        ('Out of stock', 'Out of stock'),
        ('Price too high', 'Price too high'),
        ('Authenticity concern', 'Authenticity concern'),
        ('Budget mismatch', 'Budget mismatch'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='intents')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='intents')
    variation = models.ForeignKey(ProductVariation, on_delete=models.SET_NULL, null=True, blank=True, related_name='intents')
    
    constraint_type = models.CharField(max_length=50)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Pending')
    
    requested_quantity = models.PositiveIntegerField(default=1)
    estimated_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"Intent for {self.product.name} by {self.customer.phone_number} - {self.status}"

