from core.shops import can_manage_catalog, role_of

NAV = [
    # (key, label, url name, icon, group)
    ('dashboard', 'Home', 'dashboard:home', 'house', ''),
    ('intents', 'Missed sales', 'intents:list', 'clipboard-list', 'Customers'),
    ('customers', 'Customers', 'customers:list', 'users', 'Customers'),
    ('notifications', 'Messages', 'notifications:list', 'message-circle', 'Customers'),
    ('products', 'Products', 'products:list', 'package', 'Stock'),
    ('reports', 'Reports', 'reports:index', 'chart-column', 'Shop'),
]


def shell(request):
    """What the app shell needs on every page: navigation, current section, theme, unread replies."""
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {}
    match = getattr(request, 'resolver_match', None)
    current = match.app_name if match else ''
    unread = 0
    shop = getattr(request, 'shop', None)
    if shop is not None:
        from django.db.models import Sum
        unread = shop.conversations.aggregate(total=Sum('unread_count'))['total'] or 0
    theme = getattr(request.user, 'theme', 'system')
    return {
        'nav_items': NAV,
        'nav_current': current,
        'unread_replies': unread,
        'theme': theme if theme in ('light', 'dark') else '',
        'role': role_of(request),
        'is_manager': can_manage_catalog(request),
    }
