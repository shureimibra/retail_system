from customers.models import Customer

def create_customer(first_name, last_name, phone_number, email=None):
    """
    Creates or retrieves a customer based on their phone number.
    """
    customer, created = Customer.objects.get_or_create(
        phone_number=phone_number,
        defaults={
            'first_name': first_name,
            'last_name': last_name,
            'email': email
        }
    )
    if not created:
        # Update details if the user supplied new values
        customer.first_name = first_name
        customer.last_name = last_name
        if email:
            customer.email = email
        customer.save()
    return customer
