"""
"Set up your shop": six steps from an empty shop to ready. Each step opens the real Settings or Products page,
so everything stays editable later in the usual place. Steps tick themselves off where Retail OS can tell.
"""
from django.conf import settings as django_settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import TemplateView

from accounts.models import Membership
from core.shops import role_of

# (key, title, what it's for, where to do it, how Retail OS can tell it's done)
STEPS = [
    ('shop', 'Your shop', 'Name, logo, country and currency, as customers will see them.', 'settings:shop',
     lambda shop: bool(shop.logo)),
    ('types', 'What you sell', 'Shoes, clothing, bags… and their sizes and colours. Fashion basics are already filled in.',
     'settings:product_types', None),
    ('products', 'Your products', 'Download your Excel list, fill in what you have, upload it. Or add a few by hand.',
     'products:import', lambda shop: shop.products.exists()),
    ('team', 'Your team', 'Invite your cashiers and managers with a link.', 'settings:team',
     lambda shop: shop.memberships.count() > 1),
    ('payments', 'Payments and messages', 'Your M-Pesa till or paybill for customers, and how long items are held.',
     'settings:payments', lambda shop: bool(shop.payment_details.strip())),
    ('try', 'Try it', "Log a practice missed sale with your own number, and see the customer's message. "
                      'Then print your shop link QR code for the counter.', 'floor', lambda shop: shop.intents.exists()),
]


def progress(shop):
    """[(key, title, why, url name, state)] with state 'done', 'skipped' or 'todo', and how many are finished."""
    rows = []
    for key, title, why, url, check in STEPS:
        state = shop.setup.get(key, '')
        if state not in ('done', 'skipped'):
            state = 'done' if check and check(shop) else 'todo'
        rows.append({'key': key, 'title': title, 'why': why, 'url': url, 'state': state})
    finished = sum(1 for r in rows if r['state'] != 'todo')
    return rows, finished


def home_reminder(request):
    """The one line on Home while setup isn't finished (owners of real shops only), or None."""
    shop = getattr(request, 'shop', None)
    if shop is None or shop.is_demo or shop.setup.get('closed') or role_of(request) != Membership.OWNER:
        return None
    rows, finished = progress(shop)
    if finished == len(rows):
        return None
    return {'finished': finished, 'total': len(rows)}


class SetupView(LoginRequiredMixin, TemplateView):
    template_name = 'shopsettings/setup.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and role_of(request) != Membership.OWNER:
            raise PermissionDenied('Only the owner sets up the shop.')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.request.session.pop('setup_step', None)
        rows, finished = progress(self.request.shop)
        context.update({'steps': rows, 'finished': finished, 'total': len(rows),
                        'simulator': django_settings.SIMULATOR_ENABLED})
        return context

    def post(self, request):
        shop = request.shop
        action, _, key = request.POST.get('action', '').partition(':')
        if action == 'open' and key in {s[0] for s in STEPS}:
            request.session['setup_step'] = key
            return redirect(next(reverse(url) for k, _, _, url, _ in STEPS if k == key))
        if action in ('done', 'skip', 'undo') and key in {s[0] for s in STEPS}:
            if action == 'undo':
                shop.setup.pop(key, None)
            else:
                shop.setup[key] = 'done' if action == 'done' else 'skipped'
        if action == 'later':
            return redirect('dashboard:home')  # the line on Home stays until it's finished or hidden
        if action == 'close':
            shop.setup['closed'] = True  # "Hide" on Home, or finished: the line on Home goes away
        shop.save(update_fields=['setup'])
        return redirect('dashboard:home' if action == 'close' else 'setup')
