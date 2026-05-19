from django.urls import path
from core import views

urlpatterns = [

    # RESIDENT
    path('login/', views.login_view, name='login'),
    path('register/', views.resident_register_view, name='register'),

    # ADMIN
    path(
        'admin/login/',
        views.admin_login_view,
        name='admin_login'
    ),

    path('logout/', views.logout_view, name='logout'),

    path('otp/', views.otp_verify_view, name='otp_verify'),

    path(
        'otp/resend/',
        views.resend_otp_view,
        name='resend_otp'
    ),

    path(
        'first-login/',
        views.admin_first_login_view,
        name='admin_first_login'
    ),
]