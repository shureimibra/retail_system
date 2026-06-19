import logging
from django.conf import settings
from .models import NotificationLog
from intents.models import BlockedPurchaseIntent

# Try to import Twilio Client
try:
    from twilio.rest import Client
except ImportError:
    Client = None

logger = logging.getLogger(__name__)

class SMSService:
    @staticmethod
    def send_restock_notification(intent_id):
        intent = None
        message = ""
        try:
            intent = BlockedPurchaseIntent.objects.get(id=intent_id)
            
            # Construct message
            product_name = intent.product.name
            variation_str = ""
            if intent.variation:
                variation_str = f" {intent.variation.size}/{intent.variation.color}"
            
            message = f"Hello {intent.customer.first_name}, the {product_name}{variation_str} you requested is now available."
            
            # Force use of user's verified phone number (+254797278281) for WhatsApp testing
            phone = "+254701266217"
            if not phone or not phone.startswith('+'):
                logger.warning(f"Failed to send SMS: Invalid phone number format '{phone}' for customer ID {intent.customer.id}")
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
                intent.status = 'Customer Notified'
                intent.save()
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to send SMS: {str(e)}")
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

