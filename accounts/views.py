from django.contrib.auth import login
from django.shortcuts import redirect, render

from . import services
from .forms import AcceptInvitationForm
from .models import Membership


def invitation(request, token):
    """Open an invitation link: create an account and join the shop. Owners then go to "Set up your shop"."""
    invite = services.find_invitation(token)
    if invite is None:
        return render(request, 'accounts/invitation_closed.html', status=410)
    context = {'invite': invite, 'login_shop': invite.shop}
    if request.user.is_authenticated:
        return render(request, 'accounts/invitation.html', {**context, 'signed_in_as': request.user})
    form = AcceptInvitationForm(request.POST or None, initial={'first_name': invite.name.partition(' ')[0],
                                                               'last_name': invite.name.partition(' ')[2]})
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        try:
            user = services.accept_invitation(invite, data['first_name'], data['last_name'], data['username'],
                                              data['password'])
        except ValueError:
            return render(request, 'accounts/invitation_closed.html', status=410)
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return redirect('setup' if invite.role == Membership.OWNER else 'dashboard:home')
    return render(request, 'accounts/invitation.html', {**context, 'form': form})
