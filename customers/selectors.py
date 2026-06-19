from .models import Customer

def get_all_customers():
    return Customer.objects.all().order_by('-created_at')

def get_customer_by_phone(phone_number):
    try:
        return Customer.objects.get(phone_number=phone_number)
    except Customer.DoesNotExist:
        return None
