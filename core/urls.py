from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_page, name='landing_page'),
    path('dashboard/admin/',    views.admin_dashboard_view,     name='admin_dashboard'),
    path('dashboard/resident/', views.resident_dashboard_view,  name='resident_dashboard'),
    path('pending/',            views.pending_verification_view, name='pending_verification'),
    path('admin/login/', views.admin_login_view, name='admin_login'),
    path('admin/register/', views.admin_register, name='admin_register'),
    path('admin/residents/', views.resident_records_view, name='resident_records'),
    path('admin/announcements/', views.announcements_view, name='announcements'),
    
]