from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
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
        names = {'simulator': 'Simulator (nothing is sent)', 'whatsapp_cloud': 'WhatsApp Cloud API',
                 'africastalking': "Africa's Talking", 'twilio': 'Twilio', 'email': 'Email server'}
        context['connections'] = [(label, names.get(django_settings.MESSAGING_PROVIDERS.get(key), 'Not set'))
                                  for key, label in (('whatsapp', 'WhatsApp'), ('sms', 'SMS'), ('email', 'Email'))]
        context['simulator_enabled'] = django_settings.SIMULATOR_ENABLED
        return context


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
        return context

    def _owners(self):
        return Membership.objects.filter(shop=self.request.shop, role=Membership.OWNER)

    def post(self, request):
        action = request.POST.get('action')
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
