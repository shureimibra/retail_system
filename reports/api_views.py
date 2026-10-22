from rest_framework.views import APIView
from rest_framework.response import Response
from .selectors import get_report_data

class ReportsAPIView(APIView):
    def get(self, request):
        status = request.query_params.get('status')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        intents = get_report_data(request.shop, start_date, end_date, status)
        data = []
        for intent in intents:
            data.append({
                'id': intent.id,
                'customer': f"{intent.customer.first_name} {intent.customer.last_name}",
                'product': intent.product.name,
                'variation': f"{intent.variation.size}/{intent.variation.color}" if intent.variation else "N/A",
                'constraint_type': intent.get_constraint_type_display(),
                'estimated_value': float(intent.estimated_value) if intent.estimated_value else 0.00,
                'status': intent.get_status_display(),
                'created_at': intent.created_at.strftime('%Y-%m-%d %H:%M:%S')
            })
        return Response(data)
