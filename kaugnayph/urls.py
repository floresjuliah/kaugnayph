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
from django.urls import path
from core.views import get_users, get_announcements, get_announcement_detail, create_announcement, update_announcement, delete_announcement
urlpatterns = [
    path('admin/', admin.site.urls),
    path('users/', get_users),
    path('announcements/', get_announcements),
    path('announcements/<int:announcement_id>/', get_announcement_detail),
    path('announcements/create/', create_announcement),
    path('announcements/<int:announcement_id>/update/', update_announcement),
    path('announcements/<int:announcement_id>/delete/', delete_announcement),
]