import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from intents.automation import process_due


class Command(BaseCommand):
    help = ('Send due follow-ups, expire old requests, return lapsed holds and retry failed messages. '
            'With --every N it keeps running and does this every N minutes (for a laptop without Celery).')

    def add_arguments(self, parser):
        parser.add_argument('--every', type=int, default=0, metavar='MINUTES',
                            help='Keep running, every MINUTES minutes (e.g. --every 15). Stop with Ctrl+C.')

    def handle(self, *args, **options):
        every = max(0, options['every'])
        while True:
            summary = process_due()
            done = ', '.join(f"{key.replace('_', ' ')}: {count}" for key, count in summary.items() if count)
            self.stdout.write(f"{timezone.localtime():%H:%M} {done or 'nothing due'}" if every else
                              '\n'.join(f"{key.replace('_', ' ')}: {count}" for key, count in summary.items()))
            if not every:
                return
            try:
                time.sleep(every * 60)
            except KeyboardInterrupt:
                return
