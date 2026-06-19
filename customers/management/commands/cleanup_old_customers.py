from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.db.models import Max
from customers.models import Customer
from intents.models import BlockedPurchaseIntent

class Command(BaseCommand):
    help = 'Cleanup customers who have been inactive for more than a year and have no pending/monitoring intents.'

    def handle(self, *args, **options):
        one_year_ago = timezone.now() - timedelta(days=365)
        
        # Find customers who currently have active (Pending or Monitoring) intents
        active_customer_ids = BlockedPurchaseIntent.objects.filter(
            status__in=['Pending', 'Monitoring']
        ).values_list('customer_id', flat=True).distinct()
        
        # Query customers who do not have any active intents
        eligible_customers = Customer.objects.exclude(id__in=active_customer_ids)
        
        deleted_count = 0
        for customer in eligible_customers:
            customer_intents = customer.intents.all()
            if customer_intents.exists():
                # Get the last time their intents were updated
                latest_intent_date = customer_intents.aggregate(latest=Max('updated_at'))['latest']
                if latest_intent_date and latest_intent_date < one_year_ago:
                    customer.delete()
                    deleted_count += 1
            else:
                # If no intents exist, delete if the customer profile was created over a year ago
                if customer.created_at < one_year_ago:
                    customer.delete()
                    deleted_count += 1
                    
        self.stdout.write(self.style.SUCCESS(f"Successfully cleaned up {deleted_count} inactive customers older than 1 year."))
