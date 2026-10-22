import datetime
from urllib.parse import urlencode

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.views import View
from django.views.generic import TemplateView

from analytics.selectors import get_to_order
from core.periods import resolve_period
from core.shops import can_manage_catalog
from intents.models import BlockedPurchaseIntent
from .selectors import demand_by_item, get_report_data, recovered_by_month
from .services import generate_csv_report, generate_pdf_report, write_rows_csv


class ManagersOnlyMixin(LoginRequiredMixin):
    """Reports are for owners and managers; cashiers are refused on the server, not just hidden in the menu."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not can_manage_catalog(request):
            raise PermissionDenied('Only the owner or a manager can see reports.')
        return super().dispatch(request, *args, **kwargs)


def _attachment(content_type, name):
    response = HttpResponse(content_type=content_type)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M')
    response['Content-Disposition'] = f'attachment; filename="{name}-{stamp}.{content_type.split("/")[-1]}"'
    return response


class ExportCSVReportView(ManagersOnlyMixin, View):
    def get(self, request):
        intents = get_report_data(request.shop, request.GET.get('start_date'), request.GET.get('end_date'),
                                  request.GET.get('status'))
        return generate_csv_report(_attachment('text/csv', 'missed-sales'), intents)


class ExportPDFReportView(ManagersOnlyMixin, View):
    def get(self, request):
        intents = get_report_data(request.shop, request.GET.get('start_date'), request.GET.get('end_date'),
                                  request.GET.get('status'))
        return generate_pdf_report(_attachment('application/pdf', 'missed-sales'), intents)


class SummaryCSVView(ManagersOnlyMixin, View):
    """The three summary reports as spreadsheets: recovered by month, demand by item, and the to-order list."""

    def get(self, request, kind):
        period = resolve_period(request.GET)
        if kind == 'recovered':
            rows = [(r['month'].strftime('%Y-%m'), r['count'], f"{r['money']:.2f}")
                    for r in recovered_by_month(request.shop, period['start'], period['end'])]
            header = ['Month', 'Paid in full', 'Money recovered']
        elif kind == 'demand':
            rows = [(r['product'], r['option'], r['reason'], r['count'], f"{r['money']:.2f}")
                    for r in demand_by_item(request.shop, period['start'], period['end'])]
            header = ['Item', 'Option', 'Reason', 'Missed sales', 'Money']
        elif kind == 'to-order':
            rows = [(r['product_name'], r['variation_label'], r['sku'], r['to_order'], r['waiting'], r['on_order'],
                     f"{r['money_waiting']:.2f}", r['needed_by'].isoformat() if r['needed_by'] else '')
                    for r in get_to_order(request.shop)]
            header = ['Item', 'Option', 'SKU', 'To order', 'Customers waiting (units)', 'Already on order',
                      'Money waiting', 'Earliest needed by']
        else:
            raise Http404
        return write_rows_csv(_attachment('text/csv', kind), header, rows)


class ReportsIndexView(ManagersOnlyMixin, TemplateView):
    """Choose a period; see what was recovered, what customers asked for, and what to order; download any of it."""
    template_name = 'reports/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        shop = self.request.shop
        period = resolve_period(self.request.GET)
        status = self.request.GET.get('status', '')
        filters = {'start_date': period['start_str'], 'end_date': period['end_str'], 'status': status}
        period_query = {'period': period['key']}
        if period['key'] == 'custom':
            period_query.update(start_date=period['start_str'], end_date=period['end_str'])
        recovered = recovered_by_month(shop, period['start'], period['end'])
        context.update({
            'period': period,
            'filters': filters,
            'query': urlencode({k: v for k, v in filters.items() if v}),
            'period_query': urlencode({k: v for k, v in period_query.items() if v}),
            'status_choices': BlockedPurchaseIntent.STATUS_CHOICES,
            'count': get_report_data(shop, period['start_str'] or None, period['end_str'] or None, status or None).count(),
            'recovered': recovered,
            'recovered_total': sum(r['money'] for r in recovered),
            'demand': demand_by_item(shop, period['start'], period['end'])[:10],
            'to_order': [r for r in get_to_order(shop) if r['to_order'] > 0][:10],
        })
        return context
