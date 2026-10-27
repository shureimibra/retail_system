from .models import User

def create_user(username, email, password, phone_number=None, is_staff_member=False, is_staff=False, is_superuser=False):
    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        phone_number=phone_number,
        is_staff_member=is_staff_member,
        is_staff=is_staff,
        is_superuser=is_superuser
    )
    return user


def shop_link_name(shop):
    """The shop's public link name (kimathi-street-store), made from its name the first time it's needed."""
    from django.utils.text import slugify
    from .models import Shop
    if shop.link_name:
        return shop.link_name
    base = slugify(shop.name)[:50] or 'shop'
    name, n = base, 2
    while Shop.objects.filter(link_name=name).exclude(pk=shop.pk).exists():
        name, n = f'{base}-{n}', n + 1
    shop.link_name = name
    shop.save(update_fields=['link_name'])
    return name
