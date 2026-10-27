from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from rest_framework.routers import DefaultRouter
from products.api_views import CategoryViewSet, ProductTypeViewSet, ProductViewSet, ProductVariationViewSet
from customers.api_views import CustomerViewSet
from intents.ask import AskView
from intents.floor import FloorView, customer_lookup
from intents.api_views import BlockedPurchaseIntentViewSet, record_bought_visit
from analytics.api_views import DashboardStatsAPIView, AnalyticsAPIView, FunnelAPIView, ToOrderAPIView
from reports.api_views import ReportsAPIView
from notifications.api_views import ConversationViewSet
from core.api_views import health_check

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='api-category')
router.register(r'products', ProductViewSet, basename='api-product')
router.register(r'product-types', ProductTypeViewSet, basename='api-product-type')
router.register(r'variations', ProductVariationViewSet, basename='api-variation')
router.register(r'customers', CustomerViewSet, basename='api-customer')
router.register(r'intents', BlockedPurchaseIntentViewSet, basename='api-intent')
router.register(r'conversations', ConversationViewSet, basename='api-conversation')

@csrf_exempt
def site_root(request):
    """Home for people; and if Twilio's console points at the bare site address, its messages still arrive."""
    if request.method == 'POST' and 'X-Twilio-Signature' in request.headers:
        from notifications.views import twilio_webhook
        return twilio_webhook(request)
    return redirect('dashboard:home')


urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('products/', include('products.urls')),
    path('customers/', include('customers.urls')),
    path('intents/', include('intents.urls')),
    path('notifications/', include('notifications.urls')),
    path('reports/', include('reports.urls')),
    path('settings/', include('shopsettings.urls')),
    path('payments/', include('payments.urls')),
    path('floor/', FloorView.as_view(), name='floor'),
    path('floor/customer/', customer_lookup, name='floor-customer'),
    path('ask/<slug:name>/', AskView.as_view(), name='ask'),

    
    # API endpoints
    path('api/health/', health_check, name='api-health'),
    path('api/dashboard/', DashboardStatsAPIView.as_view(), name='api-dashboard'),
    path('api/analytics/', AnalyticsAPIView.as_view(), name='api-analytics'),
    path('api/reports/', ReportsAPIView.as_view(), name='api-reports'),
    path('api/visits/bought/', record_bought_visit, name='api-visit-bought'),
    path('api/to-order/', ToOrderAPIView.as_view(), name='api-to-order'),
    path('api/funnel/', FunnelAPIView.as_view(), name='api-funnel'),
    path('api/', include(router.urls)),
    # The same API under a versioned path, for integrations (POS plug-ins, the capture widget).
    path('api/v1/to-order/', ToOrderAPIView.as_view()),
    path('api/v1/funnel/', FunnelAPIView.as_view()),
    path('api/v1/visits/bought/', record_bought_visit),
    path('api/v1/', include((router.urls, 'api-v1'))),
    
    path('', site_root),
]

if settings.DEBUG:
    from django.conf.urls.static import static
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
