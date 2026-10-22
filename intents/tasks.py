from celery import shared_task


@shared_task
def process_due_task():
    from .automation import process_due
    return process_due()
