from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/admin/',    views.admin_dashboard_view,     name='admin_dashboard'),
    path('dashboard/resident/', views.resident_dashboard_view,  name='resident_dashboard'),
    path('pending/',            views.pending_verification_view, name='pending_verification'),
]