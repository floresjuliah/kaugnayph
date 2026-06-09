from django.urls import path
from . import views

urlpatterns = [

    path('', views.landing_page, name='landing_page'),

    path(
        'dashboard/admin/',
        views.admin_dashboard_view,
        name='admin_dashboard'
    ),

    path(
        'dashboard/resident/',
        views.resident_dashboard_view,
        name='resident_dashboard'
    ),

    path(
        'pending/',
        views.pending_verification_view,
        name='pending_verification'
    ),

    path(
        'admin/login/',
        views.admin_login_view,
        name='admin_login'
    ),

    path(
        'admin/register/',
        views.admin_register,
        name='admin_register'
    ),

    path(
        'admin/residents/',
        views.resident_records_view,
        name='resident_records'
    ),

    path(
        'admin/announcements/',
        views.admin_announcements_view,
        name='announcements'
    ),

    path(
        'admin/announcements/create/',
        views.admin_announcement_create_view,
        name='admin_announcement_create'
    ),

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

    path(
        'admin/first-login/',
        views.admin_first_login_view,
        name='admin_first_login'
    ),

    path( 
        'otp/verify/', 
        views.otp_verify_view, 
        name='otp_verify' 
    ), 
    
    path( 
        'otp/resend/', 
        views.resend_otp_view, 
        name='resend_otp' 
    ),
    
    path(
        'otp/send-email/',
        views.send_email_otp_view,
        name='send_email_otp'
    ),

    path(
        'file-complaint/',
        views.filecomplaint,
        name='filecomplaint'
    ),

    path('login/', views.login_view, name='login'),
    path('register/', views.resident_register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),

    path('admin/residents/<int:user_id>/', views.resident_record_view, name='resident_record_view'),
    path('admin/residents/<int:user_id>/edit/', views.resident_record_edit, name='resident_record_edit'),
    path('admin/verification/<int:rv_id>/<str:file_type>/', views.serve_verification_file, name='verification_file'),

    path(
        'admin/cases/',
        views.case_records_view,
         name='case_records'
    ),

    path('admin/cases/<int:complaint_id>/', views.case_detail_view, name='case_detail'),

    # Document Requests: Resident side
    path(
        'documents/request/',
        views.document_request_view,
        name='document_request'
    ),

    path(
        'documents/fields/<int:dtid>/',
        views.get_document_fields,
        name='document_fields_api'
    ),

    # Admin: Document Requests
    path(
        'admin/document-requests/',
        views.admin_document_requests_view,
        name='admin_document_requests'
    ),

    path(
        'admin/document-requests/<int:drid>/',
        views.admin_document_request_detail_view,
        name='admin_document_request_detail'
    ),

    path(
        'admin/inquiries/',
        views.admin_inquiries_view,
        name='admin_inquiries'
    ),

    path(
        'admin/inquiries/<int:cuid>/',
        views.admin_inquiry_detail_view,
        name='admin_inquiry_detail'
    ),

]