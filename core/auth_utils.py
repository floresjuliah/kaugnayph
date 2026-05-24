from django.http import HttpResponseForbidden
import bcrypt, random, string, requests
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from .models import OTP, Users, SMSOutbox, RolePermissions

# PASSWORD HASHING 
def hash_password(plain):
    return bcrypt.hashpw(
        plain.encode('utf-8'), bcrypt.gensalt()
    ).decode('utf-8')
 
def check_password(plain, hashed):
    try:
        return bcrypt.checkpw(
            plain.encode('utf-8'), hashed.encode('utf-8')
        )
    except Exception:
        return False


# OTP 
def generate_otp(user, purpose='login'):
    OTP.objects.filter(
        user=user, purpose=purpose, is_used=False
    ).update(is_used=True)
    code = ''.join(random.choices(string.digits, k=6))
    expires_at = timezone.now() + timedelta(minutes=5)
    return OTP.objects.create(
        user=user, code=code, purpose=purpose,
        expires_at=expires_at, is_used=False,
    )
 
OTP_MAX_ATTEMPTS = 3
OTP_LOCKOUT_MINUTES = 5 
def verify_otp(user, code, purpose='login'):
    try:
        otp = OTP.objects.get(
            user=user,
            purpose=purpose,
            is_used=False,
            expires_at__gt=timezone.now()
        )
    except OTP.DoesNotExist:
        return 'invalid'

    # Check if locked out
    if otp.locked_until and timezone.now() < otp.locked_until:
        remaining = int((otp.locked_until - timezone.now()).total_seconds() / 60) + 1
        return f'locked:{remaining}'

    # Wrong code
    if otp.code != code:
        otp.attempts += 1

        if otp.attempts >= OTP_MAX_ATTEMPTS:
            otp.locked_until = timezone.now() + timedelta(minutes=OTP_LOCKOUT_MINUTES)
            otp.save()
            return f'locked:{OTP_LOCKOUT_MINUTES}'

        otp.save()
        remaining_attempts = OTP_MAX_ATTEMPTS - otp.attempts
        return f'wrong:{remaining_attempts}'

    # Correct code
    otp.is_used = True
    otp.save()
    return 'ok'
 
#otp = generate_otp(user, purpose="login")
#send_sms(
    user.contactno,
    f"KaugnayPH OTP: {otp.code}. Valid for 5 minutes.",
    sent_by=user  # or the requesting user
# ) 

# SMS 
def send_sms(contact_number, message, sent_by=None):
    success = False
    gateway_response = ""
    error_message = ""

    try:
        r = requests.get(settings.SMS_URL, params={
            "USERNAME": settings.SMS_USERNAME,
            "PASSWORD": settings.SMS_PASSWORD,
            "smsnum": contact_number,
            "Memo": message,
            "method": "2",
            "smsprovider": settings.SMS_PROVIDER,
        }, timeout=10)

        gateway_response = r.text

        success = r.status_code == 200 and "Failure:1" not in gateway_response

    except requests.Timeout:
        error_message = "Request timed out"
    except requests.RequestException as e:
        error_message = str(e)

    from .models import SMSOutbox
    SMSOutbox.objects.create(
        recipient_number=contact_number,
        message=message,
        sent_by=sent_by,
        sent_at=timezone.now(),
        status="sent" if success else "failed",
        error_message=error_message,
        gateway_response=gateway_response,
    )

    return success
 
# SESSION HELPERS 
def set_user_session(request, user):
    request.session['user_id']   = user.userid
    request.session['user_type'] = user.user_type.type_name
    request.session['role']      = user.role.rolename if user.role else None
    request.session['username']  = user.username
    request.session['fullname']  = f'{user.firstname} {user.lastname}'
 
def get_current_user(request):
    uid = request.session.get('user_id')
    if not uid:
        return None
    try:
        return Users.objects.select_related(
            'user_type','role','position'
        ).get(userid=uid, is_active=True)
    except Users.DoesNotExist:
        return None

# PERMISSION CHECK
def has_permission(user, permission_name):

    return RolePermissions.objects.filter(
        role=user.role,
        permission__name=permission_name
    ).exists()