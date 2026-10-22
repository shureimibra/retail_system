from rest_framework.views import APIView
from rest_framework.response import Response
from .selectors import get_dashboard_kpis, get_constraint_distribution, get_top_blocked_products, get_monthly_intent_trends, get_restock_recommendations

class DashboardStatsAPIView(APIView):
    def get(self, request):
        kpis = get_dashboard_kpis(request.shop)
        recent_recommendations = get_restock_recommendations(request.shop, threshold=4)
        return Response({
            'kpis': kpis,
            'recommendations': recent_recommendations
        })

class AnalyticsAPIView(APIView):
    def get(self, request):
        distribution = get_constraint_distribution(request.shop)
        top_products = get_top_blocked_products(request.shop)
        trends = get_monthly_intent_trends(request.shop)
        recommendations = get_restock_recommendations(request.shop, threshold=4)
        return Response({
            'constraint_distribution': distribution,
            'top_blocked_products': top_products,
            'monthly_trends': trends,
            'restock_recommendations': recommendations
        })
