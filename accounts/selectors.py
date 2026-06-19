from .models import User

def get_all_users():
    return User.objects.all().order_by('username')

def get_user_by_id(user_id):
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return None
