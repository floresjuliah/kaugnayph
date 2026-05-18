import json
import requests
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from .models import Users, Announcements, SMSOutbox
from django.shortcuts import render, redirect
from django.utils import timezone
from django.conf import settings
from django.contrib import messages
from django.utils import timezone
from .models import Users, UserTypes, Settings
from .auth_utils import (
    hash_password, check_password, generate_otp,
    verify_otp, send_sms, set_user_session, get_current_user
)
from .decorators import login_required, admin_required, resident_required
import random


def landing_page(request):
    return render(request, 'landing.html')

def login_page(request):
    return render(request, 'login.html')

def register_page(request):
    return render(request, 'register.html')


def get_users(request):
    data = list(Users.objects.all().values())
    return JsonResponse(data, safe=False)


def get_announcements(request):
    data = list(Announcements.objects.all().values())
    return JsonResponse(data, safe=False)


def get_announcement_detail(request, announcement_id):
    try:
        announcement = Announcements.objects.values().get(announcement_id=announcement_id)
        return JsonResponse(announcement, safe=False)
    except Announcements.DoesNotExist:
        return JsonResponse({"error": "Announcement not found"}, status=404)

def filecomplaint(request):
    return render(request, 'filecomplaint.html')

def aboutus(request):
    return render(request, 'aboutus.html')

def tracksub(request):
    return render(request, 'tracksub.html')

def documents(request):
    return render(request, 'documents.html')

def faqs(request):
    return render(request, 'faqs.html')

def contactus(request):
    return render(request, 'contactus.html')

@csrf_exempt
def create_announcement(request):
    if request.method == "POST":
        data = json.loads(request.body)

        send_sms_value = int(data.get("send_sms", 0))
        gateway_response = None

        announcement = Announcements.objects.create(
            title=data.get("title"),
            content=data.get("content"),
            send_sms=send_sms_value,
            category_id=1,
            posted_by_id=1
        )

        if send_sms_value == 1:
            gateway_response = send_sms(
                recipient_number="09175585424",
                message=f"New announcement: {announcement.title}",
                sent_by=1
            )

        return JsonResponse({
            "message": "Announcement created successfully",
            "announcement_id": announcement.announcement_id,
            "send_sms_value": send_sms_value,
            "gateway_response": gateway_response
        })

    return JsonResponse({"error": "POST request required"}, status=400)

@csrf_exempt
def update_announcement(request, announcement_id):
    if request.method == "PUT":
        data = json.loads(request.body)

        try:
            announcement = Announcements.objects.get(announcement_id=announcement_id)
            announcement.title = data.get("title", announcement.title)
            announcement.content = data.get("content", announcement.content)
            announcement.send_sms = data.get("send_sms", announcement.send_sms)
            announcement.save()

            return JsonResponse({"message": "Announcement updated successfully"})
        except Announcements.DoesNotExist:
            return JsonResponse({"error": "Announcement not found"}, status=404)

    return JsonResponse({"error": "PUT request required"}, status=400)

@csrf_exempt
def delete_announcement(request, announcement_id):
    if request.method == "DELETE":
        try:
            announcement = Announcements.objects.get(announcement_id=announcement_id)
            announcement.delete()
            return JsonResponse({"message": "Announcement deleted successfully"})
        except Announcements.DoesNotExist:
            return JsonResponse({"error": "Announcement not found"}, status=404)

    return JsonResponse({"error": "DELETE request required"}, status=400)


def send_sms(recipient_number, message, sent_by):

    url = settings.SMS_URL

    params = {
        "USERNAME": settings.SMS_USERNAME,
        "PASSWORD": settings.SMS_PASSWORD,
        "smsnum": recipient_number,
        "Memo": message,
        "method": "2",
        "smsprovider": settings.SMS_PROVIDER
    }

    response = requests.get(url, params=params)

    sms = SMSOutbox.objects.create(
        recipient_number=recipient_number,
        message=message,
        sent_by_id=sent_by,
        sent_at=timezone.now(),
        status="Sent",
        gateway_response=response.text
    )

    return sms


@csrf_exempt
def create_sms_log(request):
    if request.method == "POST":
        data = json.loads(request.body)

        sms = send_sms(
            data.get("recipient_number"),
            data.get("message"),
            data.get("sent_by")
        )

        return JsonResponse({
            "message": "SMS log created successfully",
            "outbox_id": sms.outboxid,
            "status": sms.status,
            "gateway_response": sms.gateway_response,
        })

    return JsonResponse({"error": "POST request required"}, status=400)

@csrf_exempt
def get_sms_logs(request):
    data = list(SMSOutbox.objects.all().values())
    return JsonResponse(data, safe=False)

def admin_dashboard(request):
    return render(request, 'admin_dashboard.html')

#New - Auth - Tam
# ── LOGIN ────────────────────────────────────────────
def login_view(request):
    if request.session.get('user_id'):
        return _redirect_by_type(request)
    if request.method == "POST":
        username = request.POST.get("username","").strip()
        password = request.POST.get("password","").strip()
        try:
            user = Users.objects.select_related(
                "user_type","role","position"
            ).get(username=username, is_active=True)
        except Users.DoesNotExist:
            messages.error(request, "Invalid credentials.")
            return render(request, "core/login.html")
        if not check_password(password, user.password):
            messages.error(request, "Invalid credentials.")
            return render(request, "core/login.html")
        if user.user_type.type_name == "Admin":
            request.session["pending_user_id"] = user.userid
            otp = generate_otp(user, purpose="login")
            send_sms(user.contactno,
                f"KaugnayPH OTP: {otp.code}. Valid 5 mins. Do not share.")
            return redirect("otp_verify")
        if user.user_type.type_name == "Resident":
            if not user.is_verified:
                messages.warning(request, "Account pending verification.")
                return render(request, "core/login.html")
            set_user_session(request, user)
            return redirect("resident_dashboard")
    return render(request, "core/login.html")
 
# ── OTP VERIFY ───────────────────────────────────────
def otp_verify_view(request):
    pending_id = request.session.get("pending_user_id")
    if not pending_id:
        return redirect("login")
    if request.method == "POST":
        code = request.POST.get("otp_code","").strip()
        try:
            user = Users.objects.select_related(
                "user_type","role","position"
            ).get(userid=pending_id)
        except Users.DoesNotExist:
            return redirect("login")
        if verify_otp(user, code, purpose="login"):
            del request.session["pending_user_id"]
            set_user_session(request, user)
            if user.is_first_login:
                return redirect("admin_first_login")
            return redirect("admin_dashboard")
        else:
            messages.error(request, "Invalid or expired OTP.")
    return render(request, "core/otp_verify.html")
 
def resend_otp_view(request):
    pending_id = request.session.get("pending_user_id")
    if not pending_id: return redirect("login")
    try:
        user = Users.objects.get(userid=pending_id)
        otp = generate_otp(user, purpose="login")
        send_sms(user.contactno,
            f"KaugnayPH new OTP: {otp.code}. Valid 5 mins.")
        messages.success(request, "New OTP sent.")
    except Users.DoesNotExist:
        return redirect("login")
    return redirect("otp_verify")
 
# ── FIRST LOGIN ──────────────────────────────────────
@login_required
def admin_first_login_view(request):
    user = get_current_user(request)
    if not user.is_first_login:
        return redirect("admin_dashboard")
    if request.method == "POST":
        new_pass = request.POST.get("new_password","")
        confirm  = request.POST.get("confirm_password","")
        if len(new_pass) < 8:
            messages.error(request, "Min. 8 characters.")
        elif new_pass != confirm:
            messages.error(request, "Passwords do not match.")
        else:
            user.password = hash_password(new_pass)
            user.is_first_login = False
            user.is_password_changed = True
            user.save()
            messages.success(request, "Password updated!")
            return redirect("admin_dashboard")
    return render(request, "core/admin_first_login.html", {"user": user})
 
# ── RESIDENT REGISTER ────────────────────────────────
def resident_register_view(request):
    if request.method == "POST":
        lastname   = request.POST.get("lastname","").strip()
        firstname  = request.POST.get("firstname","").strip()
        contact_no = request.POST.get("contact_no","").strip()
        address    = request.POST.get("address","").strip()
        password   = request.POST.get("password","").strip()
        receive_sms = request.POST.get("receive_sms") == "on"
        if Users.objects.filter(contactno=contact_no).exists():
            messages.error(request, "Mobile number already registered.")
            return render(request, "core/register.html")
        if len(password) < 8:
            messages.error(request, "Min. 8 characters.")
            return render(request, "core/register.html")
        try:
            resident_type = UserTypes.objects.get(type_name="Resident")
        except UserTypes.DoesNotExist:
            messages.error(request, "System error: seed the database first.")
            return render(request, "core/register.html")
        new_user = Users.objects.create(
            username=contact_no,
            password=hash_password(password),
            firstname=firstname, lastname=lastname,
            contactno=contact_no,
            user_type=resident_type,
            is_verified=False, is_active=True,
            is_first_login=False, is_password_changed=True,
        )
        Settings.objects.create(
            user=new_user, receive_sms=receive_sms,
            notifications_enabled=True, dark_mode=False,
            updated_at=timezone.now(),
        )
        messages.success(request, "Account created! Awaiting barangay verification.")
        return redirect("login")
    return render(request, "core/register.html")
 
# ── DASHBOARDS ───────────────────────────────────────
@login_required
@admin_required
def admin_dashboard_view(request):
    user = get_current_user(request)
    return render(request, "core/admin_dashboard.html", {"user": user})
 
@login_required
@resident_required
def resident_dashboard_view(request):
    user = get_current_user(request)
    return render(request, "core/resident_dashboard.html", {"user": user})
 
def pending_verification_view(request):
    return render(request, "core/pending_verification.html")
 
# ── LOGOUT ───────────────────────────────────────────
def logout_view(request):
    request.session.flush()
    return redirect("login")
 
# ── HELPER ───────────────────────────────────────────
def _redirect_by_type(request):
    user_type = request.session.get("user_type")
    if user_type == "Admin": return redirect("admin_dashboard")
    return redirect("resident_dashboard")
