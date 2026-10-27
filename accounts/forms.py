from django import forms
from django.contrib.auth.password_validation import validate_password

from .models import User


class AcceptInvitationForm(forms.Form):
    first_name = forms.CharField(label='First name', max_length=150)
    last_name = forms.CharField(label='Last name', max_length=150, required=False)
    username = forms.CharField(label='Username', max_length=150,
                               help_text='What you\'ll sign in with. Letters, numbers and . _ - only.')
    password = forms.CharField(label='Password', widget=forms.PasswordInput(render_value=False),
                               help_text='At least 8 characters, not only numbers.')
    password_again = forms.CharField(label='Password again', widget=forms.PasswordInput(render_value=False))

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if not all(c.isalnum() or c in '._-' for c in username):
            raise forms.ValidationError('Use letters, numbers and . _ - only.')
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('That username is taken. Try another, e.g. with your shop name.')
        return username

    def clean(self):
        data = super().clean()
        password, again = data.get('password'), data.get('password_again')
        if password and again and password != again:
            self.add_error('password_again', "The two passwords don't match.")
        if password:
            try:
                validate_password(password, User(username=data.get('username', ''), first_name=data.get('first_name', '')))
            except forms.ValidationError as error:
                self.add_error('password', error)
        return data
