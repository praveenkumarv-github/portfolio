from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('upload/', views.upload_file, name='upload_file'),
    path('metal-prices/', views.update_metal_prices, name='update_metal_prices'),
]
