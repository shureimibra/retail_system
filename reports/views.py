from django.views import View
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
        
        intents = get_report_data(start_date, end_date, status)
        
        response = HttpResponse(content_type='text/csv')
        filename = f"blocked_intents_report_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return generate_csv_report(response, intents)

class ExportPDFReportView(LoginRequiredMixin, View):
    def get(self, request):
        status = request.GET.get('status')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        intents = get_report_data(start_date, end_date, status)
        
        response = HttpResponse(content_type='application/pdf')
        filename = f"blocked_intents_report_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return generate_pdf_report(response, intents)
