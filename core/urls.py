from django.urls import path
from . import views

urlpatterns = [

    #PUBLIC
    path('', views.landing_page, name='landing_page'),
    path('aboutus/', views.aboutus, name='aboutus'),
    path('faqs/', views.faqs, name='faqs'),
    path('contactus/', views.contactus, name='contactus'),
    path('announcements/', views.announcements_view, name='public_announcements'),
    path('privacypolicy/', views.privacypolicy, name='privacypolicy'),

    #AUTH
    path('login/', views.login_view, name='login'),
    path('register/', views.resident_register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('admin/login/', views.admin_login_view, name='admin_login'),
    path('admin/first-login/', views.admin_first_login_view, name='admin_first_login'),
    path('otp/verify/', views.otp_verify_view, name='otp_verify'),
    path('otp/resend/', views.resend_otp_view, name='resend_otp'),
    path('otp/send-email/', views.send_email_otp_view, name='send_email_otp'),

    #RESIDENT
    path('dashboard/resident/', views.resident_dashboard_view, name='resident_dashboard'),
    path('pending/', views.pending_verification_view, name='pending_verification'),
    path('profile/', views.residentprofile, name='residentprofile'),
    path('file-complaint/', views.filecomplaint, name='filecomplaint'),
    path('documents/', views.documents, name='documents'),
    path('documents/request/', views.document_request_view, name='document_request'),
    path('documents/fields/<int:dtid>/', views.get_document_fields, name='document_fields_api'),
    path('announcements/<int:announcement_id>/feedback/', views.submit_announcement_feedback, name='submit_feedback'),
    path('announcements/<int:announcement_id>/', views.announcement_detail, name='announcement_detail'),
    path('track/', views.tracksub, name='tracksub'),
    
    
    path(
    'track/complaint/<int:complaint_id>/',
    views.complaint_timeline_view,
    name='complaint_timeline'
    ),

    #ADMIN DASHBOARD
    path('dashboard/admin/', views.admin_dashboard_view, name='admin_dashboard'),
    path('admin/register/', views.admin_register, name='admin_register'),

    #ADMIN: RESIDENTS
    path('admin/residents/', views.resident_records_view, name='resident_records'),
    path('admin/residents/<int:user_id>/', views.resident_record_view, name='resident_record_view'),
    path('admin/residents/<int:user_id>/edit/', views.resident_record_edit, name='resident_record_edit'),
    path('admin/verification/<int:rv_id>/<str:file_type>/', views.serve_verification_file, name='verification_file'),

    #ADMIN: ANNOUNCEMENTS
    path('admin/announcements/', views.admin_announcements_view, name='announcements'),
    path('admin/announcements/create/', views.admin_announcement_create_view, name='admin_announcement_create'),
    path('admin/announcements/<int:announcement_id>/', views.admin_announcement_detail_view, name='admin_announcement_detail'),
    path('admin/announcements/<int:announcement_id>/edit/', views.admin_announcement_edit_view, name='admin_announcement_edit'),
    path('admin/announcements/<int:announcement_id>/delete/', views.admin_announcement_delete_view, name='admin_announcement_delete'),

    #ADMIN: CASES
    path('admin/cases/', views.case_records_view, name='case_records'),
    path('admin/cases/<int:complaint_id>/', views.case_detail_view, name='case_detail'),

    #ADMIN: DOCUMENT REQUESTS
    path('admin/document-requests/', views.admin_document_requests_view, name='admin_document_requests'),
    path('admin/document-requests/<int:drid>/', views.admin_document_request_detail_view, name='admin_document_request_detail'),

    #ADMIN: INQUIRIES
    path('admin/inquiries/', views.admin_inquiries_view, name='admin_inquiries'),
    path('admin/inquiries/<int:cuid>/', views.admin_inquiry_detail_view, name='admin_inquiry_detail'),
    path("admin/inquiries/<int:inquiry_id>/add-to-faq/", views.add_inquiry_to_faq, name="add_inquiry_to_faq"),

    # ADMIN: FEEDBACK MONITORING
    path('admin/feedback/', views.admin_feedback_view, name='admin_feedback'),
    path('admin/feedback/<int:announcement_id>/', views.admin_feedback_detail_view, name='admin_feedback_detail'),

    # ADMIN: FAQS
    path('admin/faqs/', views.admin_faqs, name='admin_faqs'),
    path('admin/faqs/add/', views.admin_add_faq, name='admin_add_faq'),
    path('admin/faqs/<int:faq_id>/edit/', views.admin_edit_faq, name='admin_edit_faq'),
    path('admin/faqs/<int:faq_id>/toggle/', views.admin_toggle_faq, name='admin_toggle_faq'),
    path('admin/faqs/<int:faq_id>/edit/', views.admin_edit_faq, name='admin_edit_faq'),
    path('admin/faqs/<int:faq_id>/toggle/', views.admin_toggle_faq, name='admin_toggle_faq'),

    #ADMIN: AUDIT LOGS
    path("admin/audit-logs/", views.audit_logs_view, name="audit_logs"),

    # ADMIN: SMS OUTBOX
    path("admin/sms-outbox/", views.sms_outbox_view, name="sms_outbox"),

    #ADMIN: ADMIN REGISTER
    path("admin/<int:user_id>/deactivate/", views.admin_deactivate_view, name="admin_deactivate"),
    path("admin/<int:user_id>/edit/", views.admin_edit_view, name="admin_edit"),
    path("admin/<int:user_id>/reactivate/", views.admin_reactivate_view, name="admin_reactivate"),
    path("admin/<int:user_id>/", views.admin_detail_view, name="admin_detail"),
    path("admin/", views.admins_list_view, name="admins_list"),

    #ADMIN: SETTINGS
    path("admin/settings/", views.settings_page, name="settings_page"),
    path("admin/settings/change-password/", views.admin_change_password, name="admin_change_password"),
    path("admin/settings/update-contact/start/", views.admin_update_contact_start, name="admin_update_contact_start"),
    path("admin/settings/update-contact/verify/", views.admin_update_contact_verify, name="admin_update_contact_verify"),
    path("admin/settings/update-email/start/", views.admin_update_email_start, name="admin_update_email_start"),
    path("admin/settings/update-email/verify/", views.admin_update_email_verify, name="admin_update_email_verify"),
    path("admin/settings/avatar/", views.admin_change_avatar, name="admin_change_avatar"),
]