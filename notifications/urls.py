from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.NotificationListView.as_view(), name='list'),
    path('webhook/', views.twilio_webhook, name='webhook'),
    path('webhooks/whatsapp/', views.whatsapp_webhook, name='whatsapp-webhook'),
    path('webhooks/africastalking/<str:token>/', views.africastalking_webhook, name='africastalking-webhook'),
    path('simulator/', views.simulator, name='simulator'),
]
