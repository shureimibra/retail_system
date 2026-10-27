from django.urls import path

from . import views

urlpatterns = [
    path('products/', views.ProductsView.as_view(), name='connect-products'),
    path('to-order/', views.ToOrderView.as_view(), name='connect-to-order'),
    path('stock/', views.StockView.as_view(), name='connect-stock'),
    path('sales/', views.SalesView.as_view(), name='connect-sales'),
]
