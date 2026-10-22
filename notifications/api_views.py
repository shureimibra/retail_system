from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.shops import ShopScopedViewSetMixin
from . import gateway
from .models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    channel_label = serializers.CharField(source='get_channel_display', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Message
        fields = ['id', 'direction', 'channel', 'channel_label', 'body', 'media_url', 'template_key', 'intent',
                  'status', 'status_label', 'error_detail', 'created_at', 'sent_at', 'delivered_at', 'read_at']


class ConversationSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    phone_number = serializers.ReadOnlyField(source='customer.phone_number')
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ['id', 'customer', 'customer_name', 'phone_number', 'unread_count', 'last_message_at', 'last_message']

    def get_customer_name(self, obj):
        return f'{obj.customer.first_name} {obj.customer.last_name}'.strip()

    def get_last_message(self, obj):
        last = obj.messages.order_by('-created_at').first()
        return MessageSerializer(last).data if last else None


class ReplyInput(serializers.Serializer):
    body = serializers.CharField(max_length=1000)
    channel = serializers.ChoiceField(choices=Message.CHANNEL_CHOICES, required=False)


class ConversationViewSet(ShopScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """The inbox: one conversation per customer, newest first."""
    queryset = Conversation.objects.select_related('customer')
    serializer_class = ConversationSerializer

    @action(detail=True, methods=['get', 'post'])
    def messages(self, request, pk=None):
        conversation = self.get_object()
        if request.method == 'POST':
            payload = ReplyInput(data=request.data)
            payload.is_valid(raise_exception=True)
            gateway.send_reply(conversation, payload.validated_data['body'], payload.validated_data.get('channel'))
        return Response(MessageSerializer(conversation.messages.all(), many=True).data)

    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        conversation = self.get_object()
        conversation.unread_count = 0
        conversation.save(update_fields=['unread_count'])
        return Response(self.get_serializer(conversation).data)
