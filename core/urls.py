from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from rest_framework.routers import DefaultRouter
from products.api_views import CategoryViewSet, ProductTypeViewSet, ProductViewSet, ProductVariationViewSet
from customers.api_views import CustomerViewSet
from intents.api_views import BlockedPurchaseIntentViewSet, record_bought_visit
from analytics.api_views import DashboardStatsAPIView, AnalyticsAPIView
from reports.api_views import ReportsAPIView
from core.api_views import health_check

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='api-category')
router.register(r'products', ProductViewSet, basename='api-product')
router.register(r'product-types', ProductTypeViewSet, basename='api-product-type')
router.register(r'variations', ProductVariationViewSet, basename='api-variation')
router.register(r'customers', CustomerViewSet, basename='api-customer')
router.register(r'intents', BlockedPurchaseIntentViewSet, basename='api-intent')

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('products/', include('products.urls')),
    path('customers/', include('customers.urls')),
    path('intents/', include('intents.urls')),
    path('notifications/', include('notifications.urls')),
    path('reports/', include('reports.urls')),

    
    # API endpoints
    path('api/health/', health_check, name='api-health'),
    path('api/dashboard/', DashboardStatsAPIView.as_view(), name='api-dashboard'),
    path('api/analytics/', AnalyticsAPIView.as_view(), name='api-analytics'),
    path('api/reports/', ReportsAPIView.as_view(), name='api-reports'),
    path('api/visits/bought/', record_bought_visit, name='api-visit-bought'),
    path('api/', include(router.urls)),
    
    path('', lambda req: redirect('dashboard:home')),
]

if settings.DEBUG:
    from django.conf.urls.static import static
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
