from django.core.exceptions import ValidationError
from django.db import models

from core.phones import normalize_phone

INVALID_PHONE_MESSAGE = 'Enter a valid phone number, for example 0712 345 678 or +254712345678.'

class Customer(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20, unique=True)
    email = models.EmailField(blank=True, null=True)
    marketing_opt_in = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        normalized = normalize_phone(self.phone_number)
        if not normalized:
            raise ValidationError({'phone_number': INVALID_PHONE_MESSAGE})
        self.phone_number = normalized

    def save(self, *args, **kwargs):
        # Store every readable number as +254...; unreadable legacy values stay
        # as they are (forms and the API reject new ones).
        self.phone_number = normalize_phone(self.phone_number) or self.phone_number
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.phone_number})"
