from core.shops import can_manage_catalog, role_of

NAV = [
    # (key, label, url name, icon, group, managers only)
    ('dashboard', 'Home', 'dashboard:home', 'house', '', False),
    ('intents', 'Waiting', 'intents:list', 'clipboard-list', 'Customers', False),
    ('notifications', 'Conversations', 'notifications:list', 'message-circle', 'Customers', False),
    ('to_order', 'To order', 'intents:to_order', 'boxes', 'Stock', True),
    ('products', 'Products', 'products:list', 'package', 'Stock', False),
    ('customers', 'Customers', 'customers:list', 'users', 'Shop', False),
    ('reports', 'Reports', 'reports:index', 'chart-column', 'Shop', True),
]


def shell(request):
    """What the app shell needs on every page: navigation, current section, theme, unread replies."""
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {}
    match = getattr(request, 'resolver_match', None)
    current = match.app_name if match else ''
    if match and match.url_name == 'to_order':
        current = 'to_order'
    unread = waiting = to_order = 0
    shop = getattr(request, 'shop', None)
    if shop is not None:
        from django.db.models import Sum
        from intents.models import BlockedPurchaseIntent
        unread = shop.conversations.aggregate(total=Sum('unread_count'))['total'] or 0
        waiting = shop.intents.filter(status__in=BlockedPurchaseIntent.WAITING_STATUSES).count()
    manager = can_manage_catalog(request)
    if shop is not None and manager:
        to_order = (shop.intents.filter(status=BlockedPurchaseIntent.OPEN,
                                        constraint_type__in=BlockedPurchaseIntent.RESTOCK_REASONS)
                    .values('product_id', 'variation_id').distinct().count())
    theme = getattr(request.user, 'theme', 'system')
    return {
        'nav_items': [item[:5] for item in NAV if manager or not item[5]],
        'nav_current': current,
        'unread_replies': unread,
        'waiting_count': waiting,
        'to_order_count': to_order,
        'theme': theme if theme in ('light', 'dark') else '',
        'role': role_of(request),
        'is_manager': manager,
    }
