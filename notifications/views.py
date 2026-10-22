import hashlib
import hmac
import json

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import ListView
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from . import gateway, inbound
from .models import Message


class NotificationListView(LoginRequiredMixin, ListView):
    model = Message
    template_name = 'notifications/notification_list.html'
    context_object_name = 'notifications'
    paginate_by = 10

    def get_queryset(self):
        return (Message.objects.filter(shop=self.request.shop, direction=Message.OUTBOUND)
                .select_related('conversation__customer', 'intent__product').order_by('-created_at'))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['inbound_logs'] = (Message.objects.filter(shop=self.request.shop, direction=Message.INBOUND)
                                   .select_related('conversation__customer').order_by('-created_at')[:20])
        context['simulator_enabled'] = settings.SIMULATOR_ENABLED
        return context


# --- Twilio (SMS, and WhatsApp if Twilio is the WhatsApp provider) ------------------------

TWILIO_STATUS = {'delivered': Message.DELIVERED, 'read': Message.READ, 'failed': Message.FAILED,
                 'undelivered': Message.FAILED}


@csrf_exempt
@require_POST
def twilio_webhook(request):
    if settings.TWILIO_AUTH_TOKEN:
        signature = request.headers.get('X-Twilio-Signature', '')
        if not RequestValidator(settings.TWILIO_AUTH_TOKEN).validate(request.build_absolute_uri(), request.POST, signature):
            return HttpResponseForbidden('Invalid signature')

    if request.POST.get('MessageStatus') and request.POST.get('MessageSid') and not request.POST.get('Body'):
        status = TWILIO_STATUS.get(request.POST['MessageStatus'])
        if status:
            gateway.update_delivery_status(request.POST['MessageSid'], status, request.POST.get('ErrorCode', ''),
                                           request.POST.get('ErrorMessage', ''))
        return HttpResponse(status=204)

    from_number = request.POST.get('From', '')
    channel = Message.WHATSAPP if from_number.startswith('whatsapp:') else Message.SMS
    _, auto_reply = inbound.receive(channel, from_number, request.POST.get('Body', ''),
                                    to_address=request.POST.get('To', ''),
                                    provider_message_id=request.POST.get('MessageSid', ''))
    response = MessagingResponse()
    if auto_reply:
        response.message(auto_reply)
    return HttpResponse(str(response), content_type='text/xml')


# --- Meta WhatsApp Cloud API ---------------------------------------------------------------

WHATSAPP_STATUS = {'delivered': Message.DELIVERED, 'read': Message.READ, 'failed': Message.FAILED}


@csrf_exempt
def whatsapp_webhook(request):
    if request.method == 'GET':
        if (request.GET.get('hub.mode') == 'subscribe' and settings.WHATSAPP_VERIFY_TOKEN
                and request.GET.get('hub.verify_token') == settings.WHATSAPP_VERIFY_TOKEN):
            return HttpResponse(request.GET.get('hub.challenge', ''))
        return HttpResponseForbidden('Verification failed')
    if request.method != 'POST':
        return HttpResponse(status=405)

    if not settings.WHATSAPP_APP_SECRET:
        return HttpResponseForbidden('WHATSAPP_APP_SECRET is not set')
    expected = 'sha256=' + hmac.new(settings.WHATSAPP_APP_SECRET.encode(), request.body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, request.headers.get('X-Hub-Signature-256', '')):
        return HttpResponseForbidden('Invalid signature')

    try:
        payload = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=400)
    for entry in payload.get('entry', []):
        for change in entry.get('changes', []):
            value = change.get('value', {})
            for msg in value.get('messages', []):
                body = msg.get('text', {}).get('body') or msg.get('button', {}).get('text') or f"[{msg.get('type', 'message')}]"
                inbound.receive(Message.WHATSAPP, msg.get('from', ''), body, provider_message_id=msg.get('id', ''))
            for status in value.get('statuses', []):
                mapped = WHATSAPP_STATUS.get(status.get('status'))
                if mapped:
                    error = (status.get('errors') or [{}])[0]
                    gateway.update_delivery_status(status.get('id', ''), mapped, str(error.get('code', '')),
                                                   error.get('title', ''), permanent=mapped == Message.FAILED)
    return JsonResponse({'ok': True})


# --- Africa's Talking (SMS replies and delivery reports) -----------------------------------

AT_STATUS = {'Success': Message.DELIVERED, 'Failed': Message.FAILED, 'Rejected': Message.FAILED}


@csrf_exempt
@require_POST
def africastalking_webhook(request, token):
    if not settings.AFRICASTALKING_WEBHOOK_TOKEN or not hmac.compare_digest(token, settings.AFRICASTALKING_WEBHOOK_TOKEN):
        return HttpResponseForbidden('Invalid token')
    if request.POST.get('text') is not None:
        inbound.receive(Message.SMS, request.POST.get('from', ''), request.POST.get('text', ''),
                        to_address=request.POST.get('to', ''), provider_message_id=request.POST.get('id', ''))
    elif request.POST.get('status') in AT_STATUS:
        gateway.update_delivery_status(request.POST.get('id', ''), AT_STATUS[request.POST['status']],
                                       request.POST.get('failureReason', ''), request.POST.get('failureReason', ''),
                                       permanent=request.POST.get('failureReason') in ('InvalidPhoneNumber', 'UserInBlacklist'))
    return HttpResponse('OK')


# --- Customer simulator (development only) ----------------------------------------------

def simulator(request):
    """Play the customer: see what they'd receive and reply as them, with no phone or account."""
    if not settings.SIMULATOR_ENABLED:
        raise Http404
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    if request.method == 'POST':
        inbound.receive(request.POST.get('channel', Message.WHATSAPP), request.POST.get('from', ''),
                        request.POST.get('body', ''))
        return redirect('notifications:simulator')
    messages = (Message.objects.filter(shop=request.shop).select_related('conversation__customer', 'intent__product')
                .order_by('-created_at')[:60])
    customers = request.shop.customers.order_by('first_name')
    return render(request, 'notifications/simulator.html', {'messages_list': messages, 'customers': customers,
                                                            'channels': Message.CHANNEL_CHOICES})
