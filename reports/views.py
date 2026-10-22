from django.views import View
from django.views.generic import TemplateView
from django.http import HttpResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from .selectors import get_report_data
from .services import generate_csv_report, generate_pdf_report
import datetime

class ExportCSVReportView(LoginRequiredMixin, View):
    def get(self, request):
        status = request.GET.get('status')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        intents = get_report_data(request.shop, start_date, end_date, status)
        
        response = HttpResponse(content_type='text/csv')
        filename = f"blocked_intents_report_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return generate_csv_report(response, intents)

class ExportPDFReportView(LoginRequiredMixin, View):
    def get(self, request):
        status = request.GET.get('status')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        intents = get_report_data(request.shop, start_date, end_date, status)
        
        response = HttpResponse(content_type='application/pdf')
        filename = f"blocked_intents_report_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return generate_pdf_report(response, intents)


class ReportsIndexView(LoginRequiredMixin, TemplateView):
    """Choose a period and download the missed-sales report."""
    template_name = 'reports/index.html'

    def get_context_data(self, **kwargs):
        from urllib.parse import urlencode
        from intents.models import BlockedPurchaseIntent
        context = super().get_context_data(**kwargs)
        filters = {key: self.request.GET.get(key, '') for key in ('start_date', 'end_date', 'status')}
        context['filters'] = filters
        context['query'] = urlencode({k: v for k, v in filters.items() if v})
        context['status_choices'] = BlockedPurchaseIntent.STATUS_CHOICES
        context['count'] = get_report_data(self.request.shop, filters['start_date'] or None,
                                           filters['end_date'] or None, filters['status'] or None).count()
        return context
