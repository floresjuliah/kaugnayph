from functools import wraps
#from pyexpat.errors import messages
from django.contrib import messages
from django.shortcuts import render, redirect
from django.http import HttpResponseForbidden
from .auth_utils import get_current_user


def login_required(view_func):

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        if not request.session.get("user_id"):
            messages.info(
                request,
                "Please log in to access this page."
            )
            return redirect("login")

        return view_func(
            request,
            *args,
            **kwargs
        )

    return wrapper


def admin_login_required(view_func):

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = get_current_user(request)

        if not user:
            # Clear any stale session
            request.session.flush()
            messages.error(request, "Session expired. Please log in again.")
            return redirect('admin_login')

        if user.user_type.type_name != 'Admin':
            return HttpResponseForbidden('Admin access only.')

        return view_func(request, *args, **kwargs)
    return wrapper


def admin_required(view_func):

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        user = get_current_user(request)

        if not user:
            return redirect("login")

        if user.user_type.type_name != "Admin":
            return HttpResponseForbidden(
                "Access denied."
            )

        return view_func(
            request,
            *args,
            **kwargs
        )

    return wrapper


def resident_required(view_func):

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        user = get_current_user(request)

        if not user:
            return redirect("login")

        if user.user_type.type_name != "Resident":
            messages.error(
                request,
                "Resident-only page. You have been redirected to the Admin Dashboard."
            )
            return redirect("admin_dashboard")

        if not user.is_verified:
            return redirect(
                "pending_verification"
            )

        return view_func(
            request,
            *args,
            **kwargs
        )

    return wrapper

def role_required(*role_names):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = get_current_user(request)
            if not user or not user.role:
                return HttpResponseForbidden('Access denied.')
            if user.role.rolename not in role_names:
                return HttpResponseForbidden('Insufficient role.')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

def permission_required(*permission_names):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            from .models import RolePermissions

            user = get_current_user(request)

            if not user:
                return redirect("admin_login")

            if not user.role:
                return render(
                    request,
                    "adminpanel/no_permission.html",
                    status=403
                )

            #Chairman HAS access to everything
            if user.role.rolename == "Barangay Chairman":
                return view_func(request, *args, **kwargs)

            #User has ANY of the listed permissions
            has_permission = RolePermissions.objects.filter(
                role=user.role,
                permission__name__in=permission_names
            ).exists()

            if not has_permission:
                return render(
                    request,
                    "adminpanel/no_permission.html",
                    status=403
                )

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator

def chairman_required(view_func):
    """Shortcut: only Barangay Chairman can access."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = get_current_user(request)
        if not user:
            return redirect('admin_login')
        if not user.role or user.role.rolename != 'Barangay Chairman':
            return HttpResponseForbidden('Chairman access only.')
        return view_func(request, *args, **kwargs)
    return wrapper

