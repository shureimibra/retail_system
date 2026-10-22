from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from twilio.twiml.messaging_response import MessagingResponse

from .models import NotificationLog, InboundSMSLog
from customers.models import Customer
from core.phones import normalize_phone

class NotificationListView(LoginRequiredMixin, ListView):
    model = NotificationLog
    template_name = 'notifications/notification_list.html'
    context_object_name = 'notifications'
    paginate_by = 10
    ordering = ['-sent_at']

    def get_queryset(self):
        return super().get_queryset().filter(intent__shop=self.request.shop)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['inbound_logs'] = InboundSMSLog.objects.filter(customer__shop=self.request.shop).order_by('-received_at')
        return context

@csrf_exempt
@require_POST
def twilio_webhook(request):
    from_number = request.POST.get('From', '')
    to_number = request.POST.get('To', '')
    body = request.POST.get('Body', '')

    # Try to resolve Customer
    customer = None
    normalized_from = normalize_phone(from_number)
    if normalized_from:
        matches = list(Customer.objects.filter(phone_number=normalized_from)[:2])
        # Only attach the reply when exactly one shop knows this number.
        customer = matches[0] if len(matches) == 1 else None

    # Log incoming message
    InboundSMSLog.objects.create(
        from_number=from_number,
        to_number=to_number,
        body=body,
        customer=customer
    )

    # Compliance: If customer replies STOP, set marketing_opt_in to False
    if body and body.strip().upper() == 'STOP' and customer:
        customer.marketing_opt_in = False
        customer.save(update_fields=['marketing_opt_in'])

    # Reply with TwiML Response
    resp = MessagingResponse()
    resp.message("Thank you for contacting Retail RMS. Your response has been logged.")
    return HttpResponse(str(resp), content_type='text/xml')
