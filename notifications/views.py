from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from twilio.twiml.messaging_response import MessagingResponse

from .models import NotificationLog, InboundSMSLog
from customers.models import Customer

class NotificationListView(LoginRequiredMixin, ListView):
    model = NotificationLog
    template_name = 'notifications/notification_list.html'
    context_object_name = 'notifications'
    paginate_by = 10
    ordering = ['-sent_at']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['inbound_logs'] = InboundSMSLog.objects.all().order_by('-received_at')
        return context

@csrf_exempt
@require_POST
def twilio_webhook(request):
    from_number = request.POST.get('From', '')
    to_number = request.POST.get('To', '')
    body = request.POST.get('Body', '')

    # Try to resolve Customer
    customer = None
    if from_number:
        clean_from = from_number.replace('whatsapp:', '') if 'whatsapp:' in from_number else from_number
        customer = Customer.objects.filter(phone_number=clean_from).first()
        if not customer:
            alt_number = clean_from.replace('+', '')
            customer = Customer.objects.filter(phone_number__icontains=alt_number).first()

    # Log incoming message
    InboundSMSLog.objects.create(
        from_number=from_number,
        to_number=to_number,
        body=body,
        customer=customer
    )

    # Reply with TwiML Response
    resp = MessagingResponse()
    resp.message("Thank you for contacting Retail RMS. Your response has been logged.")
    return HttpResponse(str(resp), content_type='text/xml')
