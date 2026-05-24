from django.urls import path
from core import views

urlpatterns = [
    path(
        'dashboard/',
        views.admin_dashboard_view,
        name='admin_dashboard'
    ),
    
    path('verification/', views.resident_verification_list, name='verification_list'),
    path('verification/<int:rv_id>/', views.resident_verification_detail, name='verification_detail'),
    path('verification/<int:rv_id>/file/<str:file_type>/',
     views.serve_verification_file,
     name='verification_file'),
]