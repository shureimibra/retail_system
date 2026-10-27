from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    path('', views.ProductListView.as_view(), name='list'),
    path('<int:pk>/', views.ProductDetailView.as_view(), name='detail'),
    path('create/', views.ProductCreateView.as_view(), name='create'),
    path('update/<int:pk>/', views.ProductUpdateView.as_view(), name='update'),
    path('import/', views.StockImportView.as_view(), name='import'),
    path('import/template/', views.stock_template, name='import_template'),
    path('import/<int:pk>/', views.StockImportPreviewView.as_view(), name='import_preview'),
]
