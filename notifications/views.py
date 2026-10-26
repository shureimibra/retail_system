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
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.generic import ListView, TemplateView

from intents.models import BlockedPurchaseIntent as Intent, Payment
from intents.services import TransitionError, change_item, decline, record_payment
from payments.daraja import DarajaError
from payments.services import mpesa_mode, request_payment as request_mpesa_payment
from products.models import ProductVariation
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from . import compose, gateway, inbound, selectors, services
from .models import Conversation, Message


class NotificationListView(LoginRequiredMixin, ListView):
    """Conversations: one row per customer, replies waiting first. The Sent tab keeps the delivery log."""
    model = Message
    template_name = 'notifications/notification_list.html'
    context_object_name = 'notifications'
    paginate_by = 20

    def show(self):
        show = self.request.GET.get('show', 'all')
        return show if show in ('needs_reply', 'all', 'sent') else 'all'

    def get_queryset(self):
        return (Message.objects.filter(shop=self.request.shop, direction=Message.OUTBOUND)
                .select_related('conversation__customer', 'intent__product').order_by('-created_at'))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        show = self.show()
        q = self.request.GET.get('q', '')
        context.update({
            'show': show,
            'q': q,
            'query': f'show={show}',
            'conversations': selectors.inbox(self.request.shop, show, q) if show != 'sent' else [],
            'needs_reply_count': Conversation.objects.filter(shop=self.request.shop, unread_count__gt=0).count(),
        })
        return context


class ConversationView(LoginRequiredMixin, TemplateView):
    """One customer: the chat, a reply box, and the deal for each open item beside it."""
    template_name = 'notifications/conversation.html'

    def get_conversation(self):
        return get_object_or_404(Conversation.objects.select_related('customer', 'shop'),
                                 pk=self.kwargs['pk'], shop=self.request.shop)

    def get(self, request, *args, **kwargs):
        self.conversation = services.mark_read(self.get_conversation())
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        conversation = self.conversation
        last_in = conversation.messages.filter(direction=Message.INBOUND).order_by('-created_at').first()
        channel = last_in.channel if last_in else Message.WHATSAPP
        hours_left = selectors.reply_window(conversation)
        deals = selectors.deals(conversation)
        context.update({
            'conversation': conversation,
            'customer': conversation.customer,
            'chat': selectors.chat(conversation),
            'channel': channel,
            'channel_label': dict(Message.CHANNEL_CHOICES)[channel],
            'hours_left': hours_left,
            'can_write': channel != Message.WHATSAPP or hours_left > 0,
            'deals': deals,
            'main': deals[0] if deals else None,
            'quick_replies': [(key, label, compose.quick_reply(key, deals[0])) for key, label in compose.QUICK_REPLIES]
                             if deals else [],
            'payment_methods': Payment.METHOD_CHOICES,
            'mpesa_mode': mpesa_mode()[0],
            'mpesa_ready': mpesa_mode()[1],
            'inbox': selectors.inbox(self.request.shop, limit=25),
            'draft': self.request.GET.get('draft', ''),
        })
        return context

    def post(self, request, pk):
        conversation = self.get_conversation()
        action = request.POST.get('action')
        here = reverse('notifications:conversation', args=[conversation.pk])
        intent = None
        if request.POST.get('intent', '').isdigit():
            intent = (Intent.objects.filter(pk=request.POST['intent'], customer=conversation.customer, shop=request.shop)
                      .exclude(status__in=Intent.CLOSED_STATUSES).first())
            if intent is None:
                messages.error(request, 'That item is closed or belongs to someone else.')
                return redirect(here)
        try:
            with transaction.atomic():
                return self.act(request, conversation, intent, action, here)
        except (ValueError, TransitionError, DarajaError) as error:
            messages.error(request, str(error))
            return redirect(here + '#deal')

    def act(self, request, conversation, intent, action, here):
        if action == 'reply' or (action or '').startswith('quick:'):
            body = request.POST.get('body', '').strip()
            if action.startswith('quick:') and intent:
                # Without JavaScript the quick reply is sent as written; with it, it only fills the box.
                body = compose.quick_reply(action.split(':', 1)[1], intent)
            if not body:
                messages.error(request, 'Write a message first.')
                return redirect(here + '#composer')
            last_in = conversation.messages.filter(direction=Message.INBOUND).order_by('-created_at').first()
            channel = last_in.channel if last_in else Message.WHATSAPP
            if channel == Message.WHATSAPP and not selectors.reply_window(conversation):
                messages.error(request, "WhatsApp only allows your own words within 24 hours of the customer's "
                                        'last message. Send the check-in message instead.')
                return redirect(here + '#composer')
            gateway.send_reply(conversation, body[:1000], channel)
            return redirect(here + '#composer')
        if intent is None:
            messages.error(request, 'Choose the item first.')
            return redirect(here + '#deal')
        if action == 'mpesa':
            mpesa = request_mpesa_payment(intent, request.POST.get('amount', ''), request.POST.get('phone', ''),
                                          actor=request.user)
            messages.success(request, f'Payment prompt sent to {mpesa.phone}. Ask the customer to enter their M-Pesa PIN.')
            return redirect(here + '#deal')
        if action == 'check_in':
            gateway.queue_message(intent, 'check_in')
            messages.success(request, 'Check-in message sent')
        elif action == 'deposit':
            amount = _amount(request.POST.get('amount'))
            record_payment(intent, amount, _method(request), request.POST.get('reference', '')[:60], actor=request.user)
            intent.refresh_from_db()
            messages.success(request, 'Paid in full. Counted as recovered.' if intent.status == Intent.RECOVERED
                             else 'Deposit saved. The item is reserved and a receipt is on its way.')
        elif action == 'paid':
            if intent.balance <= 0:
                raise ValueError('Nothing is left to pay.')
            record_payment(intent, intent.balance, _method(request), request.POST.get('reference', '')[:60],
                           actor=request.user)
            messages.success(request, 'Paid in full. Counted as recovered.')
        elif action == 'decline':
            decline(intent, request.POST.get('reason', '').strip()[:200], actor=request.user)
            messages.success(request, 'Closed as declined. It is not counted as revenue.')
        elif action == 'change':
            variation = get_object_or_404(ProductVariation, pk=request.POST.get('variation'), product=intent.product)
            change_item(intent, variation, actor=request.user)
            messages.success(request, f'Changed to {variation.label}')
        return redirect(here + '#deal')


def conversation_updates(request, pk):
    """New messages since the last one on screen, for the live chat. Opening them marks them read."""
    from django.contrib.auth.views import redirect_to_login
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    conversation = get_object_or_404(Conversation, pk=pk, shop=request.shop)
    after = request.GET.get('after', '0')
    new = list(conversation.messages.filter(pk__gt=int(after) if after.isdigit() else 0).order_by('created_at'))
    if new:
        services.mark_read(conversation)
    last_in = conversation.messages.filter(direction=Message.INBOUND).order_by('-created_at').first()
    channel = last_in.channel if last_in else Message.WHATSAPP
    html = ''.join(render_to_string('notifications/_bubble.html', {'m': m}, request=request) for m in new)
    return JsonResponse({'count': len(new), 'html': html,
                         'can_write': channel != Message.WHATSAPP or selectors.reply_window(conversation) > 0})


def _amount(value):
    try:
        return Decimal(str(value).replace(',', '').strip())
    except (InvalidOperation, ValueError):
        raise ValueError('Enter the amount as a number.')


def _method(request):
    method = request.POST.get('method', Payment.MPESA)
    if method not in dict(Payment.METHOD_CHOICES):
        raise ValueError('Choose how they paid.')
    return method


# --- Twilio (SMS, and WhatsApp if Twilio is the WhatsApp provider) ------------------------

TWILIO_STATUS = {'delivered': Message.DELIVERED, 'read': Message.READ, 'failed': Message.FAILED,
                 'undelivered': Message.FAILED}


@csrf_exempt
@require_POST
def twilio_webhook(request):
    if settings.TWILIO_AUTH_TOKEN:
        signature = request.headers.get('X-Twilio-Signature', '')
        url = (settings.SITE_URL.rstrip('/') + request.get_full_path() if settings.SITE_URL.startswith('https://')
               else request.build_absolute_uri())
        validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
        # Twilio signs the address exactly as typed in its console, with or without the final slash.
        if not any(validator.validate(u, request.POST, signature) for u in {url, url.rstrip('/')}):
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
    sent = (Message.objects.filter(shop=request.shop).select_related('conversation__customer', 'intent__product')
            .order_by('-created_at')[:60])
    customers = request.shop.customers.order_by('first_name')
    return render(request, 'notifications/simulator.html', {'messages_list': sent, 'customers': customers,
                                                            'channels': Message.CHANNEL_CHOICES})
