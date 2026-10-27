"""
Message providers. Each one sends a single Message and reports what happened;
only notifications.gateway calls them. Which provider serves each channel is
set by MESSAGING_PROVIDERS (simulator by default, so nothing leaves the machine).
"""
import logging
from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)
TIMEOUT_SECONDS = 15


@dataclass
class SendResult:
    ok: bool
    provider_message_id: str = ''
    status: str = 'sent'          # sent or delivered when ok
    error_code: str = ''
    error_detail: str = ''
    permanent: bool = False       # True: retrying won't help (bad number, not on WhatsApp...)


class SimulatorProvider:
    """Development default: the message is 'delivered' instantly and shown on /dev/simulator/."""
    name = 'simulator'

    def send(self, message):
        logger.info('[simulator] %s to %s: %s', message.channel, message.to_address, message.body)
        return SendResult(ok=True, provider_message_id=f'sim-{message.id}', status='delivered')


class EmailProvider:
    """Sends through Django's email settings (Mailpit locally, Brevo/Resend SMTP later)."""
    name = 'email'

    def send(self, message):
        shop = getattr(message, 'shop', None)
        subject = f'{shop.name}: an update about your request' if shop else 'An update about your request'
        email = EmailMessage(subject=settings.EMAIL_SUBJECT_PREFIX + subject, body=message.body, to=[message.to_address])
        try:
            email.send(fail_silently=False)
        except Exception as error:  # SMTP and connection errors
            return SendResult(ok=False, error_code='smtp', error_detail=str(error)[:300])
        return SendResult(ok=True, provider_message_id='')


class WhatsAppCloudProvider:
    """Meta WhatsApp Cloud API. Business-started messages use an approved template."""
    name = 'whatsapp_cloud'
    # Meta error codes where retrying won't help.
    PERMANENT_ERRORS = {'131026', '131021', '131047', '131051', '100', '132000', '132001'}

    def send(self, message):
        url = (f'https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/'
               f'{settings.WHATSAPP_PHONE_NUMBER_ID}/messages')
        to = message.to_address.lstrip('+')
        if message.template_key:
            template = self._template(message)
            if template is None:
                return SendResult(ok=False, error_code='no_template', permanent=True,
                                  error_detail='No approved WhatsApp template is set for this message yet')
            payload = {'messaging_product': 'whatsapp', 'to': to, 'type': 'template', 'template': template}
        else:
            payload = {'messaging_product': 'whatsapp', 'to': to, 'type': 'text', 'text': {'body': message.body}}
        try:
            response = requests.post(url, json=payload, timeout=TIMEOUT_SECONDS,
                                     headers={'Authorization': f'Bearer {settings.WHATSAPP_TOKEN}'})
            data = response.json()
        except (requests.RequestException, ValueError) as error:
            return SendResult(ok=False, error_code='network', error_detail=str(error)[:300])
        if response.ok and data.get('messages'):
            return SendResult(ok=True, provider_message_id=data['messages'][0].get('id', ''))
        error = data.get('error', {})
        code = str(error.get('code', response.status_code))
        return SendResult(ok=False, error_code=code, error_detail=str(error.get('message', ''))[:300],
                          permanent=code in self.PERMANENT_ERRORS)

    @staticmethod
    def _template(message):
        if message.template_key == 'hello_world':  # Meta's pre-approved test template (Settings test button)
            return {'name': 'hello_world', 'language': {'code': 'en_US'}}
        name = settings.WHATSAPP_TEMPLATES.get(message.template_key)
        if not name:
            return None
        template = {'name': name, 'language': {'code': settings.WHATSAPP_TEMPLATE_LANGUAGE}}
        components = [{'type': 'body', 'parameters': [{'type': 'text', 'text': str(value)[:1000]}
                                                      for value in (message.template_params or [])]}]
        if message.media_url and message.template_key in ('restock_alert', 'price_drop'):
            components.insert(0, {'type': 'header', 'parameters': [{'type': 'image', 'image': {'link': message.media_url}}]})
        template['components'] = components
        return template


class AfricasTalkingSMSProvider:
    """Africa's Talking SMS. The sandbox shows messages in their web simulator, not on real phones."""
    name = 'africastalking'

    def send(self, message):
        host = 'api.sandbox.africastalking.com' if settings.AFRICASTALKING_SANDBOX else 'api.africastalking.com'
        form = {'username': settings.AFRICASTALKING_USERNAME, 'to': message.to_address, 'message': message.body}
        if settings.AFRICASTALKING_SENDER_ID:
            form['from'] = settings.AFRICASTALKING_SENDER_ID
        try:
            response = requests.post(f'https://{host}/version1/messaging', data=form, timeout=TIMEOUT_SECONDS,
                                     headers={'apiKey': settings.AFRICASTALKING_API_KEY, 'Accept': 'application/json'})
            recipients = response.json().get('SMSMessageData', {}).get('Recipients', [])
        except (requests.RequestException, ValueError) as error:
            return SendResult(ok=False, error_code='network', error_detail=str(error)[:300])
        if recipients and recipients[0].get('status') == 'Success':
            return SendResult(ok=True, provider_message_id=recipients[0].get('messageId', ''))
        detail = recipients[0].get('status', '') if recipients else response.text[:300]
        return SendResult(ok=False, error_code=str(response.status_code), error_detail=detail,
                          permanent=detail in ('InvalidPhoneNumber', 'UserInBlacklist'))


class TwilioSMSProvider:
    """Twilio SMS (plain SMS, not the WhatsApp sandbox)."""
    name = 'twilio'

    def send(self, message):
        from twilio.base.exceptions import TwilioRestException
        from twilio.rest import Client
        try:
            extra = {}
            if settings.SITE_URL.startswith('https://'):
                extra['status_callback'] = settings.SITE_URL.rstrip('/') + '/notifications/webhook/'
            sent = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN).messages.create(
                body=message.body, from_=settings.TWILIO_PHONE_NUMBER, to=message.to_address, **extra)
        except TwilioRestException as error:
            return SendResult(ok=False, error_code=str(error.code), error_detail=str(error.msg)[:300],
                              permanent=error.code in (21211, 21610, 21614))
        except Exception as error:
            return SendResult(ok=False, error_code='network', error_detail=str(error)[:300])
        return SendResult(ok=True, provider_message_id=sent.sid)


class TwilioWhatsAppProvider:
    """
    WhatsApp through Twilio: the free WhatsApp Sandbox for testing and demos, or the shop's own
    approved WhatsApp number later (set TWILIO_WHATSAPP_FROM). Sends the written text, with the
    item photo when there is one.
    """
    name = 'twilio_whatsapp'
    # Not joined the sandbox (63015), outside the 24-hour window (63016), not on WhatsApp (63003).
    PERMANENT_ERRORS = {63015, 63016, 63003, 21211, 21610, 21614}

    def send(self, message):
        from twilio.base.exceptions import TwilioRestException
        from twilio.rest import Client
        extra = {}
        if message.media_url and message.media_url.startswith('https://'):
            extra['media_url'] = [message.media_url]
        if settings.SITE_URL.startswith('https://'):
            extra['status_callback'] = settings.SITE_URL.rstrip('/') + '/notifications/webhook/'
        try:
            sent = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN).messages.create(
                body=message.body, from_=f'whatsapp:{settings.TWILIO_WHATSAPP_FROM}',
                to=f'whatsapp:{message.to_address}', **extra)
        except TwilioRestException as error:
            detail = str(error.msg)[:300]
            if error.code == 63015:
                detail = 'This phone has not joined the Twilio WhatsApp Sandbox yet (send the join code first).'
            return SendResult(ok=False, error_code=str(error.code), error_detail=detail,
                              permanent=error.code in self.PERMANENT_ERRORS)
        except Exception as error:
            return SendResult(ok=False, error_code='network', error_detail=str(error)[:300])
        return SendResult(ok=True, provider_message_id=sent.sid)


PROVIDERS = {cls.name: cls for cls in (SimulatorProvider, EmailProvider, WhatsAppCloudProvider,
                                       AfricasTalkingSMSProvider, TwilioSMSProvider, TwilioWhatsAppProvider)}


def provider_for(channel):
    name = settings.MESSAGING_PROVIDERS.get(channel, 'simulator')
    return PROVIDERS[name]()
