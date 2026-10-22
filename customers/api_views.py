from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.shops import ManagersDeletePermission, ShopScopedViewSetMixin
from .models import Customer
from .serializers import CustomerSerializer


class CustomerViewSet(ShopScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated, ManagersDeletePermission]
