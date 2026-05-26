from django.urls import path
from core import views

urlpatterns = [
    path('dashboard/',
         views.admin_dashboard_view,
         name='admin_dashboard'),

    # Resident Records 
    path('residents/',
         views.resident_records_view,
         name='resident_records'),

    # TEMPORARILY COMMENTED OUT — functions not yet in views.py
    # path('residents/<int:user_id>/',
    #      views.resident_record_view,
    #      name='resident_record_view'),

    # path('residents/<int:user_id>/edit/',
    #      views.resident_record_edit,
    #      name='resident_record_edit'),

    # path('files/<int:rv_id>/<str:file_type>/',
    #      views.serve_verification_file,
    #      name='verification_file'),
]