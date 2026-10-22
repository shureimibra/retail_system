"""The widgets Home can show, and which ones each role sees (Settings → Home layout)."""
from accounts.models import Membership

# (key, title, what it shows)
WIDGETS = [
    ('key_numbers', 'Key numbers', 'Waiting demand, in conversation, reserved, recovered'),
    ('needs_you', 'Needs you now', 'Replies, promises due, pickups overdue, failed messages'),
    ('reasons', "Why people didn't buy", 'Share of each reason in the period'),
    ('to_order', 'To order today', 'Top items with customers waiting'),
    ('recovered_weekly', 'Recovered per week', 'Paid recoveries, last 8 weeks'),
    ('conversion', 'Walk-in conversion', 'Visits that ended in a sale'),
]
KEYS = [key for key, _, _ in WIDGETS]
DEFAULTS = {
    Membership.OWNER: KEYS,
    Membership.MANAGER: KEYS,
    Membership.CASHIER: ['needs_you', 'key_numbers'],
}


def layout_for(shop, role):
    """The widget keys this role sees on Home, in order. Unknown keys are dropped."""
    role = role if role in DEFAULTS else Membership.CASHIER
    saved = (shop.home_layout or {}).get(role)
    keys = saved if isinstance(saved, list) else DEFAULTS[role]
    return [key for key in keys if key in KEYS]
