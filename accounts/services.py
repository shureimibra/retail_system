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
