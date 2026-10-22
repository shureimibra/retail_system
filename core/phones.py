import phonenumbers
from django.conf import settings


def normalize_phone(raw, region=None):
    """
    Return the number in E.164 form (+254712345678), or None if it can't be
    read as a phone number. Local formats like 0712 345 678 use the region.
    """
    if not raw:
        return None
    raw = str(raw).strip()
    for prefix in ('whatsapp:', 'tel:'):
        if raw.lower().startswith(prefix):
            raw = raw[len(prefix):]
    try:
        number = phonenumbers.parse(raw, region or settings.DEFAULT_PHONE_REGION)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_possible_number(number):
        return None
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
