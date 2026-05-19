from django.urls import path
from core import views

urlpatterns = [

    # RESIDENT LOGIN
    path(
        'login/',
        views.login_view,
        name='login'
    ),

    # ADMIN LOGIN
    path(
        'admin/login/',
        views.admin_login_view,
        name='admin_login'
    ),

    # LOGOUT
    path(
        'logout/',
        views.logout_view,
        name='logout'
    ),

    # REGISTER
    path(
        'register/',
        views.resident_register_view,
        name='register'
    ),

    # OTP
    path(
        'otp/',
        views.otp_verify_view,
        name='otp_verify'
    ),

    path(
        'otp/resend/',
        views.resend_otp_view,
        name='resend_otp'
    ),

    # FIRST LOGIN
    path(
        'first-login/',
        views.admin_first_login_view,
        name='admin_first_login'
    ),
]