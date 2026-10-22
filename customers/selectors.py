from core.phones import normalize_phone
from .models import Customer

def get_all_customers(shop):
    return Customer.objects.filter(shop=shop).order_by('-created_at')

def get_customer_by_phone(shop, phone_number):
    try:
        return Customer.objects.get(shop=shop, phone_number=normalize_phone(phone_number) or phone_number)
    except Customer.DoesNotExist:
        return None
