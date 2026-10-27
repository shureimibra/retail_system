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


# --- Invitations -------------------------------------------------------------

INVITATION_DAYS = 7


def _hash(raw):
    import hashlib
    return hashlib.sha256(raw.encode()).hexdigest()


def create_invitation(shop, role, name='', contact='', created_by=None, days=INVITATION_DAYS):
    """A one-time link to join the shop. Returns (invitation, token); only a hash of the token is stored."""
    import secrets
    from datetime import timedelta
    from django.utils import timezone
    from .models import Invitation
    raw = secrets.token_urlsafe(24)
    invitation = Invitation.objects.create(shop=shop, role=role, name=name[:150], contact=contact[:150],
                                           token_hash=_hash(raw), created_by=created_by,
                                           expires_at=timezone.now() + timedelta(days=days))
    return invitation, raw


def invitation_url(raw):
    from django.conf import settings
    from django.urls import reverse
    return settings.SITE_URL.rstrip('/') + reverse('accounts:invitation', args=[raw])


def find_invitation(raw):
    """The invitation for this link if it can still be used, else None."""
    from .models import Invitation
    invitation = Invitation.objects.select_related('shop').filter(token_hash=_hash(raw or '')).first()
    return invitation if invitation and invitation.is_open else None


def accept_invitation(invitation, first_name, last_name, username, password):
    """Create the person's account and add them to the shop. The link can't be used again."""
    from django.db import transaction
    from django.utils import timezone
    from .models import Invitation, Membership, User
    with transaction.atomic():
        invitation = Invitation.objects.select_for_update().get(pk=invitation.pk)
        if not invitation.is_open:
            raise ValueError('This invitation has already been used or has expired. Ask for a new one.')
        user = User.objects.create_user(username, password=password, first_name=first_name[:150],
                                        last_name=last_name[:150],
                                        email=invitation.contact if '@' in invitation.contact else '')
        Membership.objects.create(user=user, shop=invitation.shop, role=invitation.role)
        invitation.used_at, invitation.used_by = timezone.now(), user
        invitation.save(update_fields=['used_at', 'used_by'])
    return user


def invite_new_shop(shop_name, owner_name, contact, created_by=None, days=INVITATION_DAYS):
    """For the Retail OS team: a new, empty shop and its owner's invitation link."""
    from .models import Membership, Shop
    shop = Shop.objects.create(name=shop_name[:150])
    shop_link_name(shop)
    invitation, raw = create_invitation(shop, Membership.OWNER, owner_name, contact, created_by, days)
    return shop, invitation, raw
