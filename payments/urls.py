from django.urls import path

from . import views

app_name = 'payments'

urlpatterns = [
    path('mpesa/callback/<str:token>/', views.mpesa_callback, name='mpesa-callback'),
    path('mpesa/<int:pk>/status/', views.mpesa_status, name='mpesa-status'),
]
