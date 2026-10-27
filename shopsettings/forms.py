from django import forms

from core.forms import PhotoFieldsMixin
from django.contrib.auth import get_user_model

from accounts.models import Membership, Shop
from core.phones import normalize_phone
from products.models import ProductType

User = get_user_model()

REGIONS = [('KE', 'Kenya (+254)'), ('UG', 'Uganda (+256)'), ('TZ', 'Tanzania (+255)'), ('RW', 'Rwanda (+250)'),
           ('ET', 'Ethiopia (+251)'), ('NG', 'Nigeria (+234)'), ('GH', 'Ghana (+233)'), ('ZA', 'South Africa (+27)'),
           ('GB', 'United Kingdom (+44)'), ('US', 'United States (+1)')]
CURRENCIES = [('KES', 'Kenyan shilling (KSh)'), ('UGX', 'Ugandan shilling'), ('TZS', 'Tanzanian shilling'),
              ('RWF', 'Rwandan franc'), ('ETB', 'Ethiopian birr'), ('NGN', 'Nigerian naira'), ('GHS', 'Ghanaian cedi'),
              ('ZAR', 'South African rand'), ('GBP', 'Pound sterling'), ('USD', 'US dollar')]
TIMEZONES = [(tz, tz.replace('_', ' ').split('/')[-1]) for tz in (
    'Africa/Nairobi', 'Africa/Kampala', 'Africa/Dar_es_Salaam', 'Africa/Kigali', 'Africa/Addis_Ababa',
    'Africa/Lagos', 'Africa/Accra', 'Africa/Johannesburg', 'Europe/London', 'UTC')]


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone_number']
        labels = {'phone_number': 'Phone'}
        widgets = {'phone_number': forms.TextInput(attrs={'inputmode': 'tel', 'autocomplete': 'tel'})}

    def clean_phone_number(self):
        value = self.cleaned_data.get('phone_number')
        if not value:
            return value
        normalized = normalize_phone(value)
        if not normalized:
            raise forms.ValidationError('Enter a phone number like 0712 345 678.')
        return normalized


class LookForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['theme']
        labels = {'theme': 'Screen'}
        widgets = {'theme': forms.RadioSelect}


class ShopDetailsForm(PhotoFieldsMixin, forms.ModelForm):
    photo_fields = ('logo',)
    phone_region = forms.ChoiceField(choices=REGIONS, label='Country for phone numbers',
                                     help_text='Local numbers like 0712 345 678 are saved with this country code.')
    currency = forms.ChoiceField(choices=CURRENCIES)
    timezone = forms.ChoiceField(choices=TIMEZONES, label='Time zone')

    class Meta:
        model = Shop
        fields = ['name', 'phone_region', 'currency', 'timezone', 'logo']
        labels = {'name': 'Shop name'}


class FollowUpsForm(forms.ModelForm):
    class Meta:
        model = Shop
        fields = ['follow_up_days', 'expire_days_after_last_follow_up', 'stock_hold_days', 'reserve_pickup_days',
                  'delivery_days']
        labels = {
            'follow_up_days': 'Send reminders on these days',
            'expire_days_after_last_follow_up': 'Close the request this many days after the last reminder',
            'stock_hold_days': 'Hold a unit for a waiting customer for (days)',
            'reserve_pickup_days': 'Reserved items wait for pickup for (days)',
            'delivery_days': 'Your supplier usually delivers in (days)',
        }
        help_texts = {'follow_up_days': 'Days after the first message, separated by commas. For example: 2, 4, 7.',
                      'delivery_days': 'To order suggests enough for the customers likely to ask before a delivery arrives.'}

    def clean_follow_up_days(self):
        raw = self.cleaned_data['follow_up_days']
        parts = [p.strip() for p in raw.split(',') if p.strip()]
        if not parts or not all(p.isdigit() and 0 < int(p) <= 60 for p in parts):
            raise forms.ValidationError('Use whole days between 1 and 60, separated by commas, like 2, 4, 7.')
        return ', '.join(str(d) for d in sorted({int(p) for p in parts}))

    def clean_delivery_days(self):
        days = self.cleaned_data['delivery_days']
        if not 1 <= days <= 90:
            raise forms.ValidationError('Use a number of days between 1 and 90.')
        return days


class MessagingForm(forms.ModelForm):
    class Meta:
        model = Shop
        fields = ['default_channel']
        labels = {'default_channel': 'Message new customers on'}
        widgets = {'default_channel': forms.RadioSelect}
        help_texts = {'default_channel': "If a customer can't be reached there, the next channel is tried."}


class PaymentsForm(forms.ModelForm):
    class Meta:
        model = Shop
        fields = ['payment_details']
        labels = {'payment_details': 'How customers pay you'}
        widgets = {'payment_details': forms.Textarea(attrs={'rows': 2})}
        help_texts = {'payment_details': 'Sent by the "Send payment details" quick reply, e.g. M-Pesa Till 123456, Kimathi Street Store.'}


class TestMessageForm(forms.Form):
    channel = forms.ChoiceField(choices=[('whatsapp', 'WhatsApp'), ('sms', 'SMS'), ('email', 'Email')])
    to = forms.CharField(max_length=254)


class ProductTypeForm(forms.ModelForm):
    class Meta:
        model = ProductType
        fields = ['name', 'option1_name', 'option1_values', 'option2_name', 'option2_values', 'option3_name', 'option3_values']
        labels = {'option1_name': 'First option', 'option1_values': 'Suggested values',
                  'option2_name': 'Second option', 'option2_values': 'Suggested values',
                  'option3_name': 'Third option', 'option3_values': 'Suggested values'}
        help_texts = {'option1_values': 'Separated by commas, for example 36, 37, 38.',
                      'option3_name': 'Leave blank if this type has only two options.'}
        widgets = {f'option{i}_values': forms.TextInput for i in (1, 2, 3)}

    def __init__(self, *args, shop=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.shop = shop

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        taken = ProductType.objects.filter(shop=self.shop, name__iexact=name).exclude(pk=self.instance.pk)
        if taken.exists():
            raise forms.ValidationError('There is already a product type with this name.')
        return name


class NewMemberForm(forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150, required=False)
    username = forms.CharField(max_length=150, help_text='What they type to sign in.')
    password = forms.CharField(widget=forms.PasswordInput, min_length=8, label='Temporary password',
                               help_text='At least 8 characters. Ask them to change it in Settings → Your account.')
    role = forms.ChoiceField(choices=Membership.ROLE_CHOICES, initial=Membership.CASHIER)

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('That username is taken. Try another.')
        return username


class TeamSettingsForm(forms.ModelForm):
    class Meta:
        model = Shop
        fields = ['cashiers_can_add_products']
        labels = {'cashiers_can_add_products': 'Cashiers can add new products from the till'}
        help_texts = {'cashiers_can_add_products': 'Products they add are marked "needs review" until an owner or manager checks them.'}
