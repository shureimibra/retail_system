from django.core.management.base import BaseCommand

from intents.automation import process_due


class Command(BaseCommand):
    help = 'Send due follow-ups, expire old requests, return lapsed holds and retry failed messages.'

    def handle(self, *args, **options):
        summary = process_due()
        for key, count in summary.items():
            self.stdout.write(f"{key.replace('_', ' ')}: {count}")
