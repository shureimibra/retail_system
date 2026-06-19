from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('csv/', views.ExportCSVReportView.as_view(), name='export_csv'),
    path('pdf/', views.ExportPDFReportView.as_view(), name='export_pdf'),
]
