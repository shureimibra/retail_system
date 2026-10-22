from .models import Customer


def get_or_create_customer(phone_number, first_name='', last_name='', email=None):
    """
    Find a customer by phone number or create one. Details that are supplied
    update the existing record; blank ones leave it unchanged.
    """
    customer, created = Customer.objects.get_or_create(
        phone_number=phone_number,
        defaults={'first_name': first_name, 'last_name': last_name, 'email': email},
    )
    if not created:
        changed = []
        for field, value in (('first_name', first_name), ('last_name', last_name), ('email', email)):
            if value and getattr(customer, field) != value:
                setattr(customer, field, value)
                changed.append(field)
        if changed:
            customer.save(update_fields=changed)
    return customer
