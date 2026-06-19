from django.urls import path
from . import views

app_name = 'intents'

urlpatterns = [
    path('', views.IntentListView.as_view(), name='list'),
    path('create/', views.IntentCreateView.as_view(), name='create'),
    path('<int:pk>/update/', views.IntentUpdateView.as_view(), name='update'),
]
