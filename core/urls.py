from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('otp/', views.otp_verify_view, name='otp_verify'),
    path('otp/resend/', views.resend_otp_view, name='resend_otp'),
    path('first-login/', views.admin_first_login_view, name='admin_first_login'),
    path('register/', views.resident_register_view, name='resident_register'),
    path('dashboard/admin/', views.admin_dashboard_view, name='admin_dashboard'),
    path('dashboard/resident/', views.resident_dashboard_view, name='resident_dashboard'),
    path('pending/', views.pending_verification_view, name='pending_verification'),
]