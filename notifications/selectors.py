from .models import NotificationLog

def get_all_notification_logs():
    return NotificationLog.objects.all().select_related('intent', 'intent__customer', 'intent__product').order_by('-sent_at')
