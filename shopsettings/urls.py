from django.urls import path

from . import views

app_name = 'settings'

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),
    path('account/', views.AccountView.as_view(), name='account'),
    path('look/', views.LookView.as_view(), name='look'),
    path('shop/', views.ShopDetailsView.as_view(), name='shop'),
    path('product-types/', views.ProductTypesView.as_view(), name='product_types'),
    path('product-types/new/', views.ProductTypeEditView.as_view(), name='product_type_new'),
    path('product-types/<int:pk>/', views.ProductTypeEditView.as_view(), name='product_type_edit'),
    path('home-layout/', views.HomeLayoutView.as_view(), name='home_layout'),
    path('team/', views.TeamView.as_view(), name='team'),
    path('follow-ups/', views.FollowUpsView.as_view(), name='follow_ups'),
    path('messaging/', views.MessagingView.as_view(), name='messaging'),
    path('payments/', views.PaymentsView.as_view(), name='payments'),
]
