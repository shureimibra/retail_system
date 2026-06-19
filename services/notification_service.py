import logging
from notifications.models import NotificationLog

logger = logging.getLogger(__name__)

def send_resolution_notification(intent):
    """
    Sends an SMS notification to the customer when a blocked purchase is resolved.
    Logs the result and prevents duplicate notifications for the same intent.
    """
    # Prevent duplicates
    if NotificationLog.objects.filter(intent=intent, status='Sent').exists():
        logger.info(f"Duplicate notification blocked for intent ID {intent.id}")
        return None

    customer_name = f"{intent.customer.first_name} {intent.customer.last_name}"
    product_name = intent.product.name
    if intent.variation:
        product_name += f" ({intent.variation.size}/{intent.variation.color})"
        
    message = f"Hello {customer_name}, your requested product {product_name} is now available."
    
    phone = intent.customer.phone_number
    if not phone or not phone.startswith('+'):
        logger.warning(f"Failed to send SMS: Invalid phone number format '{phone}' for customer ID {intent.customer.id}")
        log_entry = NotificationLog.objects.create(
            intent=intent,
            message=message,
            status='Failed'
        )
        return log_entry

    try:
        # Simulate SMS dispatch via Africa's Talking API
        logger.info(f"Simulating SMS to {phone}: {message}")
        
        # Create notification log entry
        log_entry = NotificationLog.objects.create(
            intent=intent,
            message=message,
            status='Sent'
        )
        
        # Update intent status to Customer Notified
        intent.status = 'Customer Notified'
        intent.save()
        
        return log_entry
    except Exception as e:
        logger.error(f"Error dispatching SMS: {str(e)}")
        log_entry = NotificationLog.objects.create(
            intent=intent,
            message=message,
            status='Failed'
        )
        return log_entry
