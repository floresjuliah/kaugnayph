from django.urls import path
from core import views

urlpatterns = [
    path(
        'dashboard/',
        views.admin_dashboard_view,
        name='admin_dashboard'
    ),
]