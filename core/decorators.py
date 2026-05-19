from functools import wraps
from django.shortcuts import redirect
from django.http import HttpResponseForbidden
from .auth_utils import get_current_user


def login_required(view_func):

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        if not request.session.get("user_id"):
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
            return redirect('admin_login')

        if user.user_type.type_name != 'Admin':
            return HttpResponseForbidden(
                'Admin access only.'
            )

        return view_func(
            request,
            *args,
            **kwargs
        )

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
            return HttpResponseForbidden(
                "Residents only."
            )

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

def permission_required(permission_name):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            from .models import RolePermissions
            user = get_current_user(request)
            if not user or not user.role:
                return HttpResponseForbidden('Access denied.')
            has_perm = RolePermissions.objects.filter(
                role=user.role,
                permission__name=permission_name
            ).exists()
            if not has_perm:
                return HttpResponseForbidden('No permission.')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
