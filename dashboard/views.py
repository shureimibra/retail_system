from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from analytics.selectors import get_dashboard_kpis, get_constraint_distribution, get_top_blocked_products, get_monthly_intent_trends, get_restock_recommendations
from products.selectors import get_all_products, get_all_categories
from customers.selectors import get_all_customers
import json

class DashboardHomeView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        shop = self.request.shop
        
        # Get query filters
        status = self.request.GET.get('status')
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        
        # Pass filters back to pre-fill form
        context['status_filter'] = status or ''
        from intents.models import BlockedPurchaseIntent
        context['status_choices'] = BlockedPurchaseIntent.STATUS_CHOICES
        context['reason_choices'] = BlockedPurchaseIntent.CONSTRAINT_CHOICES
        context['start_date_filter'] = start_date or ''
        context['end_date_filter'] = end_date or ''
        
        # KPIs
        kpis = get_dashboard_kpis(shop, start_date=start_date, end_date=end_date, status=status)
        context['kpis'] = kpis
        
        # Constraint distribution (Pie/Doughnut Chart)
        constraints = get_constraint_distribution(shop, start_date=start_date, end_date=end_date, status=status)
        context['chart_labels'] = json.dumps([c['constraint_type'] for c in constraints])
        context['chart_data'] = json.dumps([c['count'] for c in constraints])
        
        # Top blocked products (Bar Chart)
        top_products = get_top_blocked_products(shop, limit=5, start_date=start_date, end_date=end_date, status=status)
        context['top_products_labels'] = json.dumps([p['product__name'] for p in top_products])
        context['top_products_data'] = json.dumps([p['count'] for p in top_products])
        
        # Monthly trends (Line Chart)
        trends = get_monthly_intent_trends(shop, start_date=start_date, end_date=end_date, status=status)
        context['trends_labels'] = json.dumps([t['month'] for t in trends])
        context['trends_data'] = json.dumps([t['count'] for t in trends])
        context['trends_recovered'] = json.dumps([t['recovered'] for t in trends])
        
        # Restock recommendations (threshold = 4)
        context['recommendations'] = get_restock_recommendations(shop, threshold=4, start_date=start_date, end_date=end_date, status=status)
        
        # Recent intents (last 5) filtered by parameters
        from reports.selectors import get_report_data
        context['recent_intents'] = get_report_data(shop, start_date_str=start_date, end_date_str=end_date, status=status)[:5]
        
        # Dropdowns for quick record intent modal
        context['all_products'] = get_all_products(shop)
        context['all_customers'] = get_all_customers(shop)
        context['all_categories'] = get_all_categories(shop)
        
        return context
