from .models import Customer

def create_customer(first_name, last_name, phone_number, email=None):
    return Customer.objects.create(
        first_name=first_name,
        last_name=last_name,
        phone_number=phone_number,
        email=email
    )
