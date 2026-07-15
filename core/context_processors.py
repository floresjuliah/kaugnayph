from .models import SMSSubscriptions, RolePermissions
from .auth_utils import get_current_user


def sms_subscription_status(request):
    user = get_current_user(request)

    if not user:
        return {"sms_subscription_active": False}

    subscription = SMSSubscriptions.objects.filter(user=user).first()

    return {
        "sms_subscription_active": subscription.is_active if subscription else False
    }


def user_permissions(request):
    if not hasattr(request, "session"):
        return {
            "user_permissions": [],
            "user_role": None,
        }

    user = get_current_user(request)

    if not user or not user.role:
        return {
            "user_permissions": [],
            "user_role": None,
        }

    permissions = list(
        RolePermissions.objects.filter(role=user.role)
        .values_list("permission__name", flat=True)
    )

    return {
        "user_permissions": permissions,
        "user_role": user.role.rolename,
    }