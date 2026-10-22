from celery import shared_task


@shared_task
def deliver_message(message_id):
    from .gateway import deliver
    deliver(message_id)
