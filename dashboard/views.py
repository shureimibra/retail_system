from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from core.periods import resolve_period
from core.shops import role_of
from . import selectors
from .widgets import layout_for


class DashboardHomeView(LoginRequiredMixin, TemplateView):
    """Home: the work queue. Which widgets show, and in what order, is set per role in Settings → Home layout."""
    template_name = 'dashboard/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        shop = self.request.shop
        period = resolve_period(self.request.GET)
        keys = layout_for(shop, role_of(self.request))
        context['period'] = period
        context['widgets'] = [(key, f'dashboard/widgets/{key}.html') for key in keys]
        context['data'] = {key: selectors.BUILDERS[key](shop, period) for key in keys}
        context['uses_period'] = any(key in ('key_numbers', 'reasons', 'conversion') for key in keys)
        return context


@login_required
@require_POST
def dismiss_alert(request, pk):
    """Hide a "couldn't reach" alert. The customer's item and conversation are untouched."""
    from notifications.models import Message
    Message.objects.filter(pk=pk, shop=request.shop, status=Message.FAILED).update(alert_dismissed=True)
    return redirect('dashboard:home')
