from .models import SMSSubscriptions
from .auth_utils import get_current_user

def sms_subscription_status(request):
    user = get_current_user(request)

    if not user:
        return {"sms_subscription_active": False}

    subscription = SMSSubscriptions.objects.filter(user=user).first()

    return {
        "sms_subscription_active": subscription.is_active if subscription else False
    }