import logging
from celery import shared_task
from django.conf import settings
from intents.models import BlockedPurchaseIntent
from notifications.models import NotificationLog

# Try to import Twilio Client
try:
    from twilio.rest import Client
except ImportError:
    Client = None

logger = logging.getLogger(__name__)

@shared_task
def send_restock_notification_task(intent_id):
    """
    Celery background task to send an SMS/WhatsApp notification to a customer
    when a blocked purchase intent constraint is resolved.
    """
    intent = None
    message = ""
    try:
        intent = BlockedPurchaseIntent.objects.get(id=intent_id)
        customer = intent.customer

        # Compliance Check: Verify if customer has opted out of marketing
        if not customer.marketing_opt_in:
            logger.info(f"Notification skipped for intent ID {intent_id}: Customer {customer.id} opted out.")
            return False

        # Prevent duplicate notifications if one was already successfully sent
        if NotificationLog.objects.filter(intent=intent, status='Sent').exists():
            logger.info(f"Duplicate notification blocked for intent ID {intent_id}")
            return False

        # Construct message with required compliance opt-out mechanism
        product_name = intent.product.name
        variation_str = ""
        if intent.variation:
            variation_str = f" {intent.variation.label}"
        
        message = f"Hello {customer.first_name}, the {product_name}{variation_str} you requested is now available. Reply STOP to opt out."
        
        phone = customer.phone_number
        if not phone or not phone.startswith('+'):
            logger.warning(f"Failed to send SMS: Invalid phone number format '{phone}' for customer ID {customer.id}")
            NotificationLog.objects.create(
                intent=intent,
                message=message,
                status='Failed'
            )
            return False

        # Check if Twilio settings are configured
        has_twilio = (
            bool(settings.TWILIO_ACCOUNT_SID) and
            bool(settings.TWILIO_AUTH_TOKEN) and
            bool(settings.TWILIO_PHONE_NUMBER)
        )

        if has_twilio and Client is not None:
            try:
                twilio_from = settings.TWILIO_PHONE_NUMBER
                if twilio_from == '+17656271910' or not twilio_from:
                    twilio_from = 'whatsapp:+14155238886'
                elif not twilio_from.startswith('whatsapp:'):
                    twilio_from = f"whatsapp:{twilio_from}"
                
                twilio_to = phone
                if not twilio_to.startswith('whatsapp:'):
                    twilio_to = f"whatsapp:{twilio_to}"

                logger.info(f"Sending Twilio WhatsApp to {twilio_to} from {twilio_from}: {message}")
                client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                client.messages.create(
                    body=message,
                    from_=twilio_from,
                    to=twilio_to
                )
                status = 'Sent'
            except Exception as twilio_err:
                logger.error(f"Twilio WhatsApp API Error sending to {phone}: {str(twilio_err)}")
                status = 'Failed'
        else:
            # Fallback: Simulation mode
            logger.info(f"[Simulation Mode] Sending SMS to {phone}: {message}")
            status = 'Sent'

        # Log it in the database
        NotificationLog.objects.create(
            intent=intent,
            message=message,
            status=status
        )
        
        # Update intent status if sent successfully
        if status == 'Sent':
            from intents.services import transition
            if intent.status in (BlockedPurchaseIntent.OPEN, BlockedPurchaseIntent.BACK_IN_STOCK):
                transition(intent, BlockedPurchaseIntent.NOTIFIED, note='Restock message sent')
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Failed in send_restock_notification_task for intent {intent_id}: {str(e)}")
        if intent:
            try:
                NotificationLog.objects.create(
                    intent=intent,
                    message=message or f"Failed to send restock notification for intent {intent_id}",
                    status='Failed'
                )
            except Exception:
                pass
        return False
