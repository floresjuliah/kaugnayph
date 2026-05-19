from django.urls import path
from core import views

urlpatterns = [
    path(
        'dashboard/',
        views.resident_dashboard_view,
        name='resident_dashboard'
    ),
]