"""
URL configuration for kaugnayph project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from core.views import (
    get_users, get_announcements, get_announcement_detail,
    create_announcement, update_announcement, delete_announcement,
    create_sms_log, get_sms_logs
)
from core import views
from core.views import admin_login_view
from django.conf import settings
from django.conf.urls.static import static

from django.conf.urls.i18n import i18n_patterns

urlpatterns = [
    path('django-admin/', admin.site.urls),

    # API
    path('users/', get_users),
    path('announcements/', get_announcements),
    # path('announcements/<int:announcement_id>/', get_announcement_detail),
    path('announcements/create/', create_announcement),
    path('announcements/<int:announcement_id>/update/', update_announcement),
    path('announcements/<int:announcement_id>/delete/', delete_announcement),
    path('sms/create/', create_sms_log),
    path('sms/', get_sms_logs),

    # Public pages
    path('landing', views.landing_page, name='landing'),
    path('filecomplaint/', views.filecomplaint, name='filecomplaint'),
    path('aboutus/', views.aboutus, name='aboutus'),
    path('tracksub/', views.tracksub, name='tracksub'),
    path('documents/', views.documents, name='documents'),
    path('faqs/', views.faqs, name='faqs'),
    path('contactus/', views.contactus, name='contactus'),
    path('announcementslist/', views.announcements_view, name='announcementslist'),


    # Resident profile
    path('residentprofile/', views.residentprofile, name='residentprofile'),
    path('profile/edit/', views.editprofile_view, name='editprofile'),

   
    # App includes
    path('', include('core.urls')),
    path('', include('core.public.urls')),
    path('auth/', include('core.auths.urls')),
    path('resident/', include('core.resident.urls')),
    path('adminpanel/', include('core.adminpanel.urls')),
    
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

urlpatterns += [
    path('i18n/', include('django.conf.urls.i18n')),
]