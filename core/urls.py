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
    path('admin/announcements/', views.admin_announcements_view, name='announcements'),
    path(
    'admin/announcements/<int:announcement_id>/',
    views.admin_announcement_detail_view,
    name='admin_announcement_detail'
    ),
    path(
    'admin/announcements/<int:announcement_id>/edit/',
    views.admin_announcement_edit_view,
    name='admin_announcement_edit'
    ),
    path(
    'admin/announcements/<int:announcement_id>/delete/',
    views.admin_announcement_delete_view,
    name='admin_announcement_delete'
    ), 
    path('admin/first-login/', views.admin_first_login_view, name='admin_first_login'),
    
]