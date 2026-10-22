from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.shops import ManagersDeletePermission, ShopScopedViewSetMixin, can_manage_catalog
from products.models import ProductVariation
from . import services
from .models import BlockedPurchaseIntent, Payment
from .serializers import BlockedPurchaseIntentSerializer, IntentEventSerializer, PaymentSerializer


class TransitionInput(serializers.Serializer):
    status = serializers.ChoiceField(choices=BlockedPurchaseIntent.STATUS_CHOICES)
    note = serializers.CharField(max_length=300, required=False, allow_blank=True)


class PaymentInput(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    method = serializers.ChoiceField(choices=Payment.METHOD_CHOICES)
    reference = serializers.CharField(max_length=60, required=False, allow_blank=True)
    pickup_by = serializers.DateField(required=False, allow_null=True)


class MarkOrderedInput(serializers.Serializer):
    expected_at = serializers.DateField(required=False, allow_null=True)


def _bad_request(error):
    return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)


class BlockedPurchaseIntentViewSet(ShopScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = BlockedPurchaseIntent.objects.all().select_related('customer', 'product', 'variation', 'recorded_by')
    serializer_class = BlockedPurchaseIntentSerializer
    filterset_fields = ['customer', 'product', 'variation', 'constraint_type', 'status']
    permission_classes = [IsAuthenticated, ManagersDeletePermission]

    def perform_create(self, serializer):
        data = serializer.validated_data
        serializer.instance = services.create_blocked_purchase_intent(
            customer=data['customer'],
            product=data['product'],
            variation=data.get('variation'),
            constraint_type=data['constraint_type'],
            requested_quantity=data.get('requested_quantity', 1),
            estimated_value=data.get('estimated_value'),
            notes=data.get('notes', ''),
            recorded_by=self.request.user,
            consent_given=data.get('consent_given', True),
            preferred_channel=data.get('preferred_channel', BlockedPurchaseIntent.WHATSAPP),
            needed_by=data.get('needed_by'),
        )

    def _respond(self, intent):
        intent.refresh_from_db()
        return Response(self.get_serializer(intent).data)

    @action(detail=True, methods=['post'])
    def transition(self, request, pk=None):
        intent = self.get_object()
        payload = TransitionInput(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            services.transition(intent, payload.validated_data['status'], actor=request.user,
                                note=payload.validated_data.get('note', ''))
        except services.TransitionError as error:
            return _bad_request(error)
        return self._respond(intent)

    @action(detail=True, methods=['post'])
    def payments(self, request, pk=None):
        intent = self.get_object()
        payload = PaymentInput(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        try:
            services.record_payment(intent, data['amount'], data['method'], reference=data.get('reference', ''),
                                    actor=request.user, pickup_by=data.get('pickup_by'))
        except ValueError as error:
            return _bad_request(error)
        return self._respond(intent)

    @action(detail=True, methods=['post'], url_path='change-item')
    def change_item(self, request, pk=None):
        intent = self.get_object()
        variation = ProductVariation.objects.filter(pk=request.data.get('variation'), product__shop=request.shop).first()
        if variation is None:
            return _bad_request('Choose a size and colour from this shop.')
        try:
            services.change_item(intent, variation, actor=request.user)
        except ValueError as error:
            return _bad_request(error)
        return self._respond(intent)

    @action(detail=True, methods=['post'], url_path='mark-ordered')
    def mark_ordered(self, request, pk=None):
        if not can_manage_catalog(request):
            return Response({'detail': 'Only owners and managers place orders.'}, status=status.HTTP_403_FORBIDDEN)
        intent = self.get_object()
        payload = MarkOrderedInput(data=request.data)
        payload.is_valid(raise_exception=True)
        if not services.mark_ordered([intent], payload.validated_data.get('expected_at'), actor=request.user):
            return _bad_request('Only open requests can be marked as ordered.')
        return self._respond(intent)

    @action(detail=True, methods=['get'])
    def timeline(self, request, pk=None):
        intent = self.get_object()
        return Response({
            'events': IntentEventSerializer(intent.events.all(), many=True).data,
            'payments': PaymentSerializer(intent.payments.all(), many=True).data,
        })


@api_view(['POST'])
def record_bought_visit(request):
    """A walk-in who bought something (counts towards walk-in conversion)."""
    visit = services.record_bought_visit(request.shop, recorded_by=request.user)
    return Response({'id': visit.id, 'outcome': visit.outcome}, status=status.HTTP_201_CREATED)
