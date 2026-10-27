from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from accounts.models import Membership
from core.shops import role_of
from dashboard.widgets import DEFAULTS, WIDGETS, layout_for
from products.models import ProductType
from . import forms

User = get_user_model()
EVERYONE, MANAGERS, OWNER = 'everyone', 'managers', 'owner'

# (url name, title, one-line description, who can open it, group)
SECTIONS = [
    ('account', 'Profile and password', 'Your name, phone, email and password', EVERYONE, 'Your account'),
    ('look', 'Look', 'Light, dark or match your device', EVERYONE, 'Your account'),
    ('shop', 'Shop details', 'Name, country, currency, time zone', OWNER, 'Shop'),
    ('product_types', 'Product types and options', 'Sizes, colours and other options', MANAGERS, 'Shop'),
    ('home_layout', 'Home layout', 'What each role sees on Home', OWNER, 'Shop'),
    ('team', 'Team and roles', 'Who works here and what they can do', OWNER, 'Shop'),
    ('follow_ups', 'Follow-ups and holds', 'Reminder days, holds and pickups', MANAGERS, 'Shop'),
    ('messaging', 'Messaging', 'How customers are contacted', MANAGERS, 'Shop'),
    ('payments', 'Payments', 'M-Pesa and how customers pay you', OWNER, 'Shop'),
    ('shop_link', 'Shop link', 'Customers ask for their size themselves', MANAGERS, 'Shop'),
    ('connections', 'Connections', 'API keys for a POS or other systems', OWNER, 'Shop'),
]


def can_open(request, who):
    role = role_of(request)
    if who == EVERYONE:
        return True
    if who == MANAGERS:
        return role in (Membership.OWNER, Membership.MANAGER)
    return role == Membership.OWNER


class SettingsView(LoginRequiredMixin, TemplateView):
    section = None
    who = EVERYONE
    denied_message = ''

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not can_open(request, self.who):
            raise PermissionDenied(self.denied_message or 'Only the owner or a manager can change this.')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sections'] = [s for s in SECTIONS if can_open(self.request, s[3])]
        context['section'] = self.section
        context['section_title'] = next((s[1] for s in SECTIONS if s[0] == self.section), 'Settings')
        return context

    def saved(self, what='Saved'):
        messages.success(self.request, what)
        return redirect(self.request.path)


class IndexView(SettingsView):
    template_name = 'shopsettings/index.html'


class AccountView(SettingsView):
    section = 'account'
    template_name = 'shopsettings/account.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('profile_form', forms.ProfileForm(instance=self.request.user))
        context.setdefault('password_form', PasswordChangeForm(self.request.user))
        return context

    def post(self, request):
        if request.POST.get('form') == 'password':
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                return self.saved('Password changed')
            return self.render_to_response(self.get_context_data(password_form=password_form))
        profile_form = forms.ProfileForm(request.POST, instance=request.user)
        if profile_form.is_valid():
            profile_form.save()
            return self.saved()
        return self.render_to_response(self.get_context_data(profile_form=profile_form))


class LookView(SettingsView):
    section = 'look'
    template_name = 'shopsettings/form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('form', forms.LookForm(instance=self.request.user))
        context['intro'] = 'Only changes your own screen. Light reads best under shop lights and in daylight.'
        return context

    def post(self, request):
        form = forms.LookForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            return self.saved()
        return self.render_to_response(self.get_context_data(form=form))


class ShopFormView(SettingsView):
    """A section that edits fields on the shop itself."""
    template_name = 'shopsettings/form.html'
    form_class = None
    intro = ''

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('form', self.form_class(instance=self.request.shop))
        context['intro'] = self.intro
        return context

    def post(self, request):
        form = self.form_class(request.POST, request.FILES, instance=request.shop)
        if form.is_valid():
            form.save()
            return self.saved()
        return self.render_to_response(self.get_context_data(form=form))


class ShopDetailsView(ShopFormView):
    section, who = 'shop', OWNER
    form_class = forms.ShopDetailsForm
    denied_message = 'Only the owner can change shop details.'
    intro = 'Used on messages to customers, for money and for reading phone numbers.'


class FollowUpsView(ShopFormView):
    section, who = 'follow_ups', MANAGERS
    form_class = forms.FollowUpsForm
    intro = ('When stock arrives, a unit is held and the customer is told. If they don\'t reply, reminders go out on '
             'these days, then the request closes and the unit goes to the next customer waiting.')


class MessagingView(ShopFormView):
    section, who = 'messaging', MANAGERS
    template_name = 'shopsettings/messaging.html'
    form_class = forms.MessagingForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['connections'] = channel_connections()
        context['simulator_enabled'] = django_settings.SIMULATOR_ENABLED
        context.setdefault('test_form', forms.TestMessageForm(initial={'to': self.request.user.phone_number or ''}))
        context['test_result'] = self.request.session.pop('test_result', None)
        return context

    def post(self, request):
        if request.POST.get('action') != 'test':
            return super().post(request)
        form = forms.TestMessageForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(test_form=form))
        request.session['test_result'] = send_test_message(request.shop, form.cleaned_data['channel'], form.cleaned_data['to'])
        return redirect(request.path + '#test')


PROVIDER_NAMES = {'simulator': 'Simulator (nothing is sent)', 'whatsapp_cloud': 'Meta WhatsApp Cloud API',
                  'africastalking': "Africa's Talking", 'twilio': 'Twilio', 'twilio_whatsapp': 'Twilio WhatsApp',
                  'email': 'Email server'}


def channel_connections():
    """What each channel is connected to, and whether its keys are in place. Never shows the keys."""
    s = django_settings
    rows = []
    for channel, label in (('whatsapp', 'WhatsApp'), ('sms', 'SMS'), ('email', 'Email')):
        provider = s.MESSAGING_PROVIDERS.get(channel, 'simulator')
        missing, notes = [], []
        if provider == 'whatsapp_cloud':
            missing = [k for k in ('WHATSAPP_TOKEN', 'WHATSAPP_PHONE_NUMBER_ID') if not getattr(s, k)]
            approved = sum(1 for name in s.WHATSAPP_TEMPLATES.values() if name)
            notes.append(f'{approved} of {len(s.WHATSAPP_TEMPLATES)} message templates set. The rest go by SMS until approved.')
            if not (s.WHATSAPP_APP_SECRET and s.WHATSAPP_VERIFY_TOKEN):
                notes.append('Replies need WHATSAPP_APP_SECRET and WHATSAPP_VERIFY_TOKEN.')
        elif provider == 'twilio_whatsapp':
            missing = [k for k in ('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN') if not getattr(s, k)]
            if s.TWILIO_WHATSAPP_FROM == '+14155238886':
                notes.append('Twilio WhatsApp Sandbox: each phone must first send the join code to +1 415 523 8886.')
        elif provider == 'twilio':
            missing = [k for k in ('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_PHONE_NUMBER') if not getattr(s, k)]
            notes.append('On a trial account, only numbers verified in Twilio receive messages.')
        elif provider == 'africastalking':
            missing = [] if s.AFRICASTALKING_API_KEY else ['AFRICASTALKING_API_KEY']
            if s.AFRICASTALKING_SANDBOX:
                notes.append("Sandbox: messages show in Africa's Talking's web simulator, not on phones.")
        elif provider == 'email':
            if not s.EMAIL_HOST:
                missing = ['EMAIL_HOST']
        state = 'simulator' if provider == 'simulator' else ('missing' if missing else 'ready')
        rows.append({'channel': channel, 'label': label, 'provider': PROVIDER_NAMES.get(provider, provider),
                     'state': state, 'missing': missing, 'notes': notes})
    if not s.SITE_URL.startswith('https://'):
        rows[0]['notes'].append('Item photos and replies need a public https SITE_URL (the tunnel).')
    return rows


def send_test_message(shop, channel, to):
    """Send one test message right now and report what the provider said, in plain words."""
    from core.phones import normalize_phone
    from notifications.models import Message
    from notifications.providers import provider_for
    address = to.strip() if channel == 'email' else normalize_phone(to, shop.phone_region)
    if not address:
        return {'ok': False, 'text': 'That phone number could not be read. Try 0712 345 678.'}
    provider = provider_for(channel)
    message = Message(shop=shop, channel=channel, to_address=address,
                      body=f'Test from {shop.name} on Retail OS. If you can read this, {channel} works.',
                      template_key='hello_world' if provider.name == 'whatsapp_cloud' else '')
    result = provider.send(message)
    where = PROVIDER_NAMES.get(provider.name, provider.name)
    if provider.name == 'simulator':
        return {'ok': True, 'text': f'Simulator: nothing was really sent. Choose a provider for {channel} in .env to send for real.'}
    if result.ok:
        extra = {'whatsapp_cloud': " WhatsApp test messages use Meta's \"hello world\" template.",
                 'twilio_whatsapp': ' If nothing arrives, check this phone has joined the Twilio WhatsApp Sandbox.'}.get(provider.name, '')
        return {'ok': True, 'text': f'Sent to {address} through {where}. Check the phone or inbox.{extra}'}
    return {'ok': False, 'text': f'{where} refused it: {result.error_detail or result.error_code}'}


class PaymentsView(ShopFormView):
    section, who = 'payments', OWNER
    template_name = 'shopsettings/payments.html'
    form_class = forms.PaymentsForm
    denied_message = 'Only the owner can change payments.'

    def get_context_data(self, **kwargs):
        from payments.services import mpesa_mode
        context = super().get_context_data(**kwargs)
        mode, ready = mpesa_mode()
        s = django_settings
        context.update({
            'mpesa_mode': mode,
            'mpesa_ready': ready,
            'mpesa_shortcode': s.MPESA_SHORTCODE,
            'mpesa_missing': [k for k in ('MPESA_CONSUMER_KEY', 'MPESA_CONSUMER_SECRET', 'MPESA_CALLBACK_TOKEN')
                              if not getattr(s, k)] if mode != 'off' else [],
            'site_is_public': s.SITE_URL.startswith('https://'),
        })
        return context


def shop_link_url(shop):
    from accounts.services import shop_link_name
    return django_settings.SITE_URL.rstrip('/') + reverse('ask', args=[shop_link_name(shop)])


class ShopLinkView(SettingsView):
    """The public "Ask for your size" link: copy it, print its QR code, switch it off."""
    section, who = 'shop_link', MANAGERS
    template_name = 'shopsettings/shop_link.html'

    def get_context_data(self, **kwargs):
        import segno
        context = super().get_context_data(**kwargs)
        url = shop_link_url(self.request.shop)
        context.update({
            'link_url': url,
            'link_on': self.request.shop.link_on,
            'qr_svg': segno.make(url, error='m').svg_inline(scale=5, border=2, dark='#1d2421', light='#fbfaf7'),
            'site_is_public': django_settings.SITE_URL.startswith('https://'),
        })
        return context

    def post(self, request):
        shop = request.shop
        shop.link_on = request.POST.get('link_on') == 'on'
        shop.save(update_fields=['link_on'])
        return self.saved('The link is on' if shop.link_on else "The link is off. Anyone opening it sees that it's closed.")


def shop_link_qr(request):
    """The QR code as a PNG to print and put up at the counter."""
    import io
    import segno
    if not request.user.is_authenticated or request.shop is None or not can_open(request, MANAGERS):
        raise PermissionDenied
    buffer = io.BytesIO()
    segno.make(shop_link_url(request.shop), error='m').save(buffer, kind='png', scale=12, border=3)
    response = HttpResponse(buffer.getvalue(), content_type='image/png')
    response['Content-Disposition'] = 'attachment; filename="shop-link-qr.png"'
    return response


class ConnectionsView(SettingsView):
    """API keys: a POS or another system uses one to send stock and sales, and read To order."""
    section, who = 'connections', OWNER
    template_name = 'shopsettings/connections.html'
    denied_message = 'Only the owner can manage connections.'

    def get_context_data(self, **kwargs):
        from connections.models import ApiKey
        context = super().get_context_data(**kwargs)
        context.update({
            'keys': ApiKey.objects.filter(shop=self.request.shop, revoked_at__isnull=True).select_related('created_by'),
            'new_key': self.request.session.pop('new_api_key', None),
            'permissions': ApiKey.PERMISSION_CHOICES,
            'api_base': django_settings.SITE_URL.rstrip('/') + '/api/v1/connect/',
        })
        return context

    def post(self, request):
        from django.utils import timezone
        from connections.models import ApiKey
        if request.POST.get('action') == 'revoke':
            key = get_object_or_404(ApiKey, shop=request.shop, pk=request.POST.get('key') or 0, revoked_at__isnull=True)
            key.revoked_at = timezone.now()
            key.save(update_fields=['revoked_at'])
            return self.saved(f'{key.name} can no longer connect.')
        name = request.POST.get('name', '').strip()[:60]
        permission = request.POST.get('permission')
        if not name or permission not in dict(ApiKey.PERMISSION_CHOICES):
            messages.error(request, 'Give the key a name and choose what it may do.')
            return redirect(request.path)
        key, raw = ApiKey.issue(request.shop, name, permission, created_by=request.user)
        request.session['new_api_key'] = {'name': key.name, 'key': raw}
        return redirect(request.path)


class ProductTypesView(SettingsView):
    section, who = 'product_types', MANAGERS
    template_name = 'shopsettings/product_types.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['types'] = ProductType.objects.filter(shop=self.request.shop)
        return context


class ProductTypeEditView(SettingsView):
    section, who = 'product_types', MANAGERS
    template_name = 'shopsettings/product_type_form.html'

    def get_object(self):
        if 'pk' not in self.kwargs:
            return ProductType(shop=self.request.shop, option3_name='')
        return get_object_or_404(ProductType, pk=self.kwargs['pk'], shop=self.request.shop)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = self.get_object()
        context.setdefault('form', forms.ProductTypeForm(instance=obj, shop=self.request.shop))
        context['object'] = obj
        context['in_use'] = obj.pk and obj.products.exists()
        return context

    def post(self, request, pk=None):
        obj = self.get_object()
        if request.POST.get('action') == 'delete' and obj.pk:
            if obj.products.exists():
                messages.error(request, f'{obj.name} is used by products, so it can\'t be deleted.')
                return redirect(request.path)
            obj.delete()
            messages.success(request, f'{obj.name} deleted')
            return redirect('settings:product_types')
        form = forms.ProductTypeForm(request.POST, instance=obj, shop=request.shop)
        if form.is_valid():
            form.save()
            messages.success(request, 'Saved')
            return redirect('settings:product_types')
        return self.render_to_response(self.get_context_data(form=form))


class TeamView(SettingsView):
    section, who = 'team', OWNER
    template_name = 'shopsettings/team.html'
    denied_message = 'Only the owner can change the team.'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['members'] = Membership.objects.filter(shop=self.request.shop).select_related('user').order_by('id')
        context['roles'] = Membership.ROLE_CHOICES
        context.setdefault('new_member_form', forms.NewMemberForm())
        context.setdefault('team_form', forms.TeamSettingsForm(instance=self.request.shop))
        context['new_link'] = self.request.session.pop('team_invite', None)
        return context

    def _owners(self):
        return Membership.objects.filter(shop=self.request.shop, role=Membership.OWNER)

    def post(self, request):
        action = request.POST.get('action')
        if action == 'invite':
            from urllib.parse import quote
            from accounts import services as accounts
            role = request.POST.get('role')
            name = request.POST.get('name', '').strip()
            if role not in dict(Membership.ROLE_CHOICES) or not name:
                messages.error(request, 'Enter their name and choose a role.')
                return redirect(request.path)
            _, raw = accounts.create_invitation(request.shop, role, name, request.POST.get('contact', '').strip(),
                                                created_by=request.user)
            link = accounts.invitation_url(raw)
            text = (f'Hi {name.partition(" ")[0]}, join {request.shop.name} on Retail OS as '
                    f'{dict(Membership.ROLE_CHOICES)[role].lower()}: {link}')
            request.session['team_invite'] = {'name': name, 'link': link, 'whatsapp': 'https://wa.me/?text=' + quote(text)}
            return redirect(request.path)
        if action == 'add':
            form = forms.NewMemberForm(request.POST)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(new_member_form=form))
            data = form.cleaned_data
            with transaction.atomic():
                user = User.objects.create_user(data['username'], password=data['password'],
                                                first_name=data['first_name'], last_name=data['last_name'])
                Membership.objects.create(user=user, shop=request.shop, role=data['role'])
            return self.saved(f"{data['first_name']} added as {dict(Membership.ROLE_CHOICES)[data['role']].lower()}")

        if action == 'settings':
            form = forms.TeamSettingsForm(request.POST, instance=request.shop)
            if form.is_valid():
                form.save()
                return self.saved()
            return self.render_to_response(self.get_context_data(team_form=form))

        member = get_object_or_404(Membership, pk=request.POST.get('member'), shop=request.shop)
        last_owner = member.role == Membership.OWNER and self._owners().count() == 1
        if action == 'role':
            role = request.POST.get('role')
            if role not in dict(Membership.ROLE_CHOICES):
                return redirect(request.path)
            if last_owner and role != Membership.OWNER:
                messages.error(request, 'The shop needs at least one owner. Make someone else owner first.')
                return redirect(request.path)
            member.role = role
            member.save(update_fields=['role'])
            return self.saved(f'{member.user.get_full_name() or member.user.username} is now {member.get_role_display().lower()}')
        if action == 'remove':
            if last_owner:
                messages.error(request, "You can't remove the only owner.")
                return redirect(request.path)
            name = member.user.get_full_name() or member.user.username
            member.delete()
            return self.saved(f'{name} removed from the team')
        return redirect(request.path)


class HomeLayoutView(SettingsView):
    """Which widgets each role sees on Home, and in what order. Staff can't change their own Home."""
    section, who = 'home_layout', OWNER
    template_name = 'shopsettings/home_layout.html'
    denied_message = 'Only the owner can change what each role sees on Home.'

    def role(self, data):
        role = data.get('role')
        return role if role in DEFAULTS else Membership.OWNER

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        role = self.role(self.request.GET)
        shown = layout_for(self.request.shop, role)
        titles = {key: (title, desc) for key, title, desc in WIDGETS}
        order = shown + [key for key, _, _ in WIDGETS if key not in shown]
        context['role'] = role
        context['roles'] = Membership.ROLE_CHOICES
        context['rows'] = [(key, *titles[key], key in shown) for key in order]
        return context

    def post(self, request):
        role = self.role(request.POST)
        layout = dict(request.shop.home_layout or {})
        if request.POST.get('action') == 'reset':
            layout.pop(role, None)
            message = 'Back to the default Home'
        else:
            known = [key for key, _, _ in WIDGETS]
            order = [key for key in request.POST.getlist('order') if key in known]
            order += [key for key in known if key not in order]
            shown = set(request.POST.getlist('show'))
            key, _, direction = (request.POST.get('move') or '').partition(':')
            if key in order:
                i = order.index(key)
                j = i - 1 if direction == 'up' else i + 1
                if 0 <= j < len(order):
                    order[i], order[j] = order[j], order[i]
            layout[role] = [key for key in order if key in shown]
            message = None if request.POST.get('move') else 'Saved'
        request.shop.home_layout = layout
        request.shop.save(update_fields=['home_layout'])
        if message:
            messages.success(request, message)
        return redirect(f"{request.path}?role={role}")
