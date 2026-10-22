from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.ReportsIndexView.as_view(), name='index'),
    path('csv/', views.ExportCSVReportView.as_view(), name='export_csv'),
    path('pdf/', views.ExportPDFReportView.as_view(), name='export_pdf'),
    path('csv/<slug:kind>/', views.SummaryCSVView.as_view(), name='summary_csv'),
]
