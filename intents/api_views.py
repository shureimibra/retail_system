from rest_framework import viewsets
from .models import BlockedPurchaseIntent
from .serializers import BlockedPurchaseIntentSerializer
from .services import create_blocked_purchase_intent

class BlockedPurchaseIntentViewSet(viewsets.ModelViewSet):
    queryset = BlockedPurchaseIntent.objects.all().select_related('customer', 'product', 'variation', 'recorded_by')
    serializer_class = BlockedPurchaseIntentSerializer
    filterset_fields = ['customer', 'product', 'variation', 'constraint_type', 'status']

    def perform_create(self, serializer):
        serializer.instance = create_blocked_purchase_intent(
            customer=serializer.validated_data['customer'],
            product=serializer.validated_data['product'],
            variation=serializer.validated_data.get('variation'),
            constraint_type=serializer.validated_data['constraint_type'],
            requested_quantity=serializer.validated_data.get('requested_quantity', 1),
            estimated_value=serializer.validated_data.get('estimated_value'),
            notes=serializer.validated_data.get('notes', ''),
            recorded_by=self.request.user
        )
