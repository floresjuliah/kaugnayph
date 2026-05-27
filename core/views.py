import json
import random
import string as _string
import requests
import os

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from core.utils import validate_upload

from .models import (
    Users, UserTypes, Settings, Roles, Positions,
    Announcements, SMSOutbox, SMSSubscriptions,
    AuditLogs, ResidentVerification, TypeOfID,
)

from .auth_utils import (
    hash_password, check_password, generate_otp,
    verify_otp, send_sms, send_email_otp,
    set_user_session, get_current_user
)

from .decorators import (
    login_required,
    admin_login_required,
    resident_required,
    permission_required,
    chairman_required,
)


# PUBLIC PAGES

def landing_page(request):
    return render(request, 'public/landing.html')

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

def announcements_view(request):
    announcements = Announcements.objects.all().order_by("-announcement_id")
    return render(request, "public/announcements.html", {
        "announcements": announcements
    })


# API ENDPOINTS

def get_users(request):
    return JsonResponse(list(Users.objects.all().values()), safe=False)

def get_announcements(request):
    return JsonResponse(list(Announcements.objects.all().values()), safe=False)

def get_announcement_detail(request, announcement_id):
    try:
        a = Announcements.objects.values().get(announcement_id=announcement_id)
        return JsonResponse(a, safe=False)
    except Announcements.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)

#CREATE ANNOUNCEMENT
@csrf_exempt
def create_announcement(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)
    data         = json.loads(request.body)
    current_user = get_current_user(request)
    title        = data.get("title", "").strip()
    content      = data.get("content", "").strip()
    if not title:
        return JsonResponse({"error": "Title required"}, status=400)
    if not content:
        return JsonResponse({"error": "Content required"}, status=400)
    send_sms_flag = int(data.get("send_sms", 0))
    announcement  = Announcements.objects.create(
        title=title, content=content,
        send_sms=send_sms_flag,
        category_id=data.get("category_id", 1),
        posted_by=current_user, created_at=timezone.now()
    )
    if send_sms_flag == 1:
        for sub in SMSSubscriptions.objects.select_related("user").filter(is_active=True):
            send_sms(sub.user.contactno,
                     f"KaugnayPH: {announcement.title}", sent_by=current_user)
    AuditLogs.objects.create(
        user=current_user, action="Create Announcement",
        module_name="Announcements", table_name="Announcements",
        record_id=announcement.announcement_id,
        new_value=f"'{title}' created.", created_at=timezone.now()
    )
    return JsonResponse({"message": "Created", "announcement_id": announcement.announcement_id})

#UPDATE ANNOUNCEMENT
@csrf_exempt
def update_announcement(request, announcement_id):
    if request.method != "PUT":
        return JsonResponse({"error": "PUT required"}, status=400)
    data = json.loads(request.body)
    try:
        a = Announcements.objects.get(announcement_id=announcement_id)
    except Announcements.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)
    a.title       = data.get("title",       a.title)
    a.content     = data.get("content",     a.content)
    a.send_sms    = data.get("send_sms",    a.send_sms)
    a.category_id = data.get("category_id", a.category_id)
    a.save()
    return JsonResponse({"message": "Updated"})

#DELETE ANNOUNCEMENT
@csrf_exempt
def delete_announcement(request, announcement_id):
    if request.method != "DELETE":
        return JsonResponse({"error": "DELETE required"}, status=400)
    try:
        a = Announcements.objects.get(announcement_id=announcement_id)
    except Announcements.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)
    a.delete()
    return JsonResponse({"message": "Deleted"})

#CREATE SMS LOG
@admin_login_required
def create_sms_log(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)
    data = json.loads(request.body)
    send_sms(data.get("recipient_number"), data.get("message"))
    return JsonResponse({"message": "SMS logged"})

#GET SMS LOG
@admin_login_required
def get_sms_logs(request):
    return JsonResponse(list(SMSOutbox.objects.all().values()), safe=False)


# HELPERS

def _redirect_by_type(request):
    if request.session.get("user_type") == "Admin":
        return redirect("admin_dashboard")
    return redirect("resident_dashboard")

def _send_otp_or_error(request, user, purpose, template, context=None):
    otp, cooldown = generate_otp(user, purpose=purpose)
    if cooldown:
        mins = cooldown // 60
        secs = cooldown % 60
        messages.error(request,
            f"Please wait {mins}m {secs}s before requesting a new OTP.")
        return render(request, template, context or {})
    send_sms(user.contactno,
             f"KaugnayPH OTP: {otp.code}. Valid for 5 minutes.")
    return None


# RESIDENT LOGIN

def login_view(request):
    if request.session.get("user_id"):
        if request.session.get("user_type") == "Resident":
            return redirect("resident_dashboard")
        return redirect("landing")

    if request.method != "POST":
        return render(request, "auth/login.html")

    contact_no = request.POST.get("contact_no", "").strip()
    password   = request.POST.get("password", "").strip()

    try:
        user = Users.objects.select_related(
            "user_type", "role", "position"
        ).get(contactno=contact_no, is_active=True)
    except Users.DoesNotExist:
        messages.error(request, "Invalid credentials.")
        return render(request, "auth/login.html")

    if user.user_type.type_name == "Admin":
        messages.error(request, "Invalid credentials.")
        return render(request, "auth/login.html")

    if not check_password(password, user.password):
        messages.error(request, "Invalid credentials.")
        return render(request, "auth/login.html")


    if not user.is_verified:
        rv = ResidentVerification.objects.filter(user=user).first()
        if rv and rv.status == "Rejected":
            messages.error(request,
                "Your registration was rejected. Please contact the barangay office.")
        else:
            messages.warning(request,
                "Your account is pending verification. You will be notified via SMS.")
        return render(request, "auth/login.html")

    set_user_session(request, user)
    return redirect("resident_dashboard")


# ADMIN LOGIN

def admin_login_view(request):
    if request.session.get("user_id"):
        if request.session.get("user_type") == "Admin":
            return redirect("admin_dashboard")
        return redirect("landing")

    if request.method != "POST":
        return render(request, "auth/login_admin.html")

    username = request.POST.get("username", "").strip()
    password = request.POST.get("password", "").strip()

    try:
        user = Users.objects.select_related(
            "user_type", "role", "position"
        ).get(username=username, is_active=True)
    except Users.DoesNotExist:
        messages.error(request, "Invalid credentials.")
        return render(request, "auth/login_admin.html")

    if user.user_type.type_name != "Admin":
        messages.error(request, "Invalid credentials.")
        return render(request, "auth/login_admin.html")

    if not check_password(password, user.password):
        messages.error(request, "Invalid credentials.")
        return render(request, "auth/login_admin.html")

    request.session["pending_user_id"] = user.userid

    if user.is_first_login:
        return redirect("admin_first_login")

    otp, cooldown = generate_otp(user, purpose="login")

    if cooldown:
        messages.error(request, f"Please wait {cooldown} before requesting another OTP.")
        return render(request, "auth/login_admin.html")

    send_email_otp(user.email, otp.code)
    request.session["otp_method"] = "email"

    return redirect("otp_verify")


# FIRST LOGIN

def _validate_first_login_form(data, current_user_id):
    errors = []

    if not data['firstname'] or not data['lastname']:
        errors.append("First name and last name are required.")

    if not data['username'] or len(data['username']) < 4:
        errors.append("Username must be at least 4 characters.")
    elif Users.objects.filter(
        username=data['username']
    ).exclude(userid=current_user_id).exists():
        errors.append("Username is already taken.")

    if not data['email'] or '@' not in data['email']:
        errors.append("A valid email address is required.")
    elif Users.objects.filter(
        email=data['email']
    ).exclude(userid=current_user_id).exists():
        errors.append("Email is already in use.")

    if not data['contact_no'].startswith("09") or len(data['contact_no']) != 11:
        errors.append("Enter a valid 11-digit PH mobile number (e.g. 09XXXXXXXXX).")
    elif Users.objects.filter(
        contactno=data['contact_no']
    ).exclude(userid=current_user_id).exists():
        errors.append("Contact number is already in use.")

    pw = data['new_password']
    if len(pw) < 8:
        errors.append("Password must be at least 8 characters.")
    else:
        if not any(c.isdigit() for c in pw):
            errors.append("Password must contain at least one number.")
        if not any(c.isalpha() for c in pw):
            errors.append("Password must contain at least one letter.")

    if pw != data['confirm_password']:
        errors.append("Passwords do not match.")

    return errors

# FIRST LOGIN

def admin_first_login_view(request):
    pending_id = request.session.get("pending_user_id")

    if not pending_id:
        return redirect("admin_login")

    try:
        user = Users.objects.select_related(
            "user_type", "role", "position"
        ).get(userid=pending_id)

    except Users.DoesNotExist:
        return redirect("admin_login")

    if not user.is_first_login:
        return redirect("admin_login")

    positions = Positions.objects.all()
    context = {
        "positions": positions,
        "user": user
    }

    if request.method != "POST":
        return render(
            request,
            "auth/admin_first_login.html",
            context
        )

    data = {
        'firstname':        request.POST.get("firstname", "").strip(),
        'lastname':         request.POST.get("lastname", "").strip(),
        'username':         request.POST.get("username", "").strip(),
        'email':            request.POST.get("email", "").strip(),
        'contact_no':       request.POST.get("contact_no", "").strip(),
        'position_id':      request.POST.get("position_id", "").strip(),
        'new_password':     request.POST.get("new_password", "").strip(),
        'confirm_password': request.POST.get("confirm_password", "").strip(),
    }

    errors = _validate_first_login_form(
        data,
        user.userid
    )

    if errors:
        for e in errors:
            messages.error(request, e)

        return render(
            request,
            "auth/admin_first_login.html",
            context
        )

    # STORE TEMP DATA ONLY
    request.session["pending_first_login_data"] = data
    request.session["from_first_login"] = True

    otp, cooldown = generate_otp(
        user,
        purpose="first_login"
    )

    if cooldown:
        messages.error(
            request,
            "Please wait before requesting another OTP."
        )

        return render(
            request,
            "auth/admin_first_login.html",
            context
        )

    # SEND OTP TO NEW NUMBER
    send_sms(
        data["contact_no"],
        f"KaugnayPH OTP: {otp.code}. Valid for 5 minutes."
    )
    request.session["otp_method"] = "sms"
    return redirect("otp_verify")


# OTP VERIFY

def otp_verify_view(request):
    pending_id = request.session.get("pending_user_id")

    if not pending_id:
        messages.error(request, "Session expired. Please log in again.")
        return redirect("admin_login")

    try:
        user = Users.objects.select_related(
            "user_type", "role", "position"
        ).get(userid=pending_id)
    except Users.DoesNotExist:
        return redirect("admin_login")

    if request.method != "POST":
        return render(request, "auth/otp_verify.html")

    code = request.POST.get("otp_code", "").strip()

    if not code or len(code) != 6 or not code.isdigit():
        messages.error(request, "Please enter a valid 6-digit OTP.")
        return render(request, "auth/otp_verify.html")

    purpose = "first_login" if request.session.get("from_first_login") else "login"

    result = verify_otp(user, code, purpose=purpose)

    if result == 'ok':

        # FIRST LOGIN FLOW
        if request.session.get("from_first_login"):
            data = request.session.get("pending_first_login_data")

            if data:
                user.firstname = data['firstname']
                user.lastname  = data['lastname']
                user.username  = data['username']
                user.email     = data['email']
                user.contactno = data['contact_no']
                user.password  = hash_password(data['new_password'])
                user.is_first_login      = False
                user.is_password_changed = True

                if data['position_id']:
                    try:
                        position = Positions.objects.get(positionid=data['position_id'])
                    except Positions.DoesNotExist:
                        print(f"[ROLE DEBUG] Position ID {data['position_id']} not found")
                    else:
                        user.position = position

                        try:
                            role_name = position.name.strip()

                            # Special case only for Kagawad
                            if role_name == "Kagawad":
                                role_name = "Barangay Kagawad"

                            role = Roles.objects.get(rolename=role_name)
                            user.role = role

                            print(f"[ROLE DEBUG] Assigned role: {role.rolename}")

                        except Roles.DoesNotExist:
                            print(f"[ROLE DEBUG] Role '{position.name}' not found")

                user.save()

                # Confirm save
                refreshed = Users.objects.select_related('role', 'position').get(userid=user.userid)
                print(f"[ROLE DEBUG] After save — role='{refreshed.role}' position='{refreshed.position}'")

                del request.session["pending_first_login_data"]

            del request.session["pending_user_id"]
            request.session.pop("from_first_login", None)

            messages.success(request,
                "Account setup complete! Please log in with your new credentials.")
            return redirect("admin_login")

        #NORMAL LOGIN
        fresh_user = Users.objects.select_related(
                "user_type",
                "role",
                "position"
        ).get(userid=pending_id)

        del request.session["pending_user_id"]

        request.session.pop("role", None)
        request.session.pop("user_type", None)

        set_user_session(request, fresh_user)

        return redirect("admin_dashboard")

    elif result.startswith('locked:'):
        minutes = result.split(':')[1]
        messages.error(request,
            f"Too many incorrect attempts. Please wait {minutes} minute(s).")

    elif result.startswith('wrong:'):
        remaining = result.split(':')[1]
        messages.error(request,
            f"Incorrect OTP. {remaining} attempt(s) remaining.")

    else:
        messages.error(request, "OTP has expired. Please request a new one.")

    return render(request, "auth/otp_verify.html")


# RESEND OTP

def resend_otp_view(request):
    pending_id = request.session.get("pending_user_id")
    if not pending_id:
        return redirect("login")

    try:
        user = Users.objects.get(userid=pending_id)
    except Users.DoesNotExist:
        return redirect("login")

    purpose = "first_login" if request.session.get("from_first_login") else "login"
    otp, cooldown = generate_otp(user, purpose=purpose)

    if cooldown:
        mins = cooldown // 60
        secs = cooldown % 60

        messages.error(
            request,
            f"Please wait {mins}m {secs}s before requesting a new OTP."
        )

        return render(request, "auth/otp_verify.html")

    if purpose == "login":
        send_email_otp(user.email, otp.code)
        request.session["otp_method"] = "email"
    
    else:
        send_sms(
            user.contactno,
            f"KaugnayPH OTP: {otp.code}. Valid for 5 minutes."
        )

        request.session["otp_method"] = "sms"

    messages.success(request, "New OTP sent.")
    return redirect("otp_verify")


# RESIDENT REGISTER

def _validate_register_form(data, files):
    errors = []
    if not data['firstname'] or not data['lastname']:
        errors.append("First name and last name are required.")
    if not data['contact_no'].startswith("09") or len(data['contact_no']) != 11:
        errors.append("Enter a valid 11-digit PH mobile number.")
    elif Users.objects.filter(contactno=data['contact_no']).exists():
        errors.append("Mobile number is already registered.")
    if len(data['password']) < 8:
        errors.append("Password must be at least 8 characters.")
    if not data['toid']:
        errors.append("Please select a type of ID.")
    allowed_types = {'image/jpeg', 'image/png', 'image/jpg'}
    for label, f in [("ID Photo", files['id_image']), ("Selfie", files['selfie'])]:
        if not f:
            errors.append(f"Please upload a {label}.")
        else:
            ok, err = validate_upload(f)
            if not ok:
                errors.append(f"{label}: {err}")
            elif f.content_type not in allowed_types:
                errors.append(f"{label} must be JPG or PNG.")
            elif f.size > 5 * 1024 * 1024:
                errors.append(f"{label} must be less than 5MB.")
    return errors


def resident_register_view(request):
    if request.method != "POST":
        return render(request, "auth/register.html", {
            "id_types": TypeOfID.objects.all()
        })

    data = {
        'firstname':   request.POST.get("firstname", "").strip(),
        'lastname':    request.POST.get("lastname", "").strip(),
        'contact_no':  request.POST.get("contact_no", "").strip(),
        'password':    request.POST.get("password", "").strip(),
        'toid':        request.POST.get("type_of_id", "").strip(),
        'receive_sms': request.POST.get("receive_sms") == "on",
    }
    files = {
        'id_image': request.FILES.get("id_image"),
        'selfie':   request.FILES.get("selfie_image"),
    }

    errors = _validate_register_form(data, files)
    if errors:
        for e in errors:
            messages.error(request, e)
        return render(request, "auth/register.html", {
            "id_types": TypeOfID.objects.all()
        })

    try:
        resident_type = UserTypes.objects.get(type_name="Resident")
    except UserTypes.DoesNotExist:
        messages.error(request, "System error. Please contact admin.")
        return render(request, "auth/register.html", {
            "id_types": TypeOfID.objects.all()
        })

    new_user = Users.objects.create(
        username=data['contact_no'],
        password=hash_password(data['password']),
        firstname=data['firstname'],
        lastname=data['lastname'],
        contactno=data['contact_no'],
        user_type=resident_type,
        is_verified=False,
        is_active=True,
        is_first_login=False,
        is_password_changed=True,
    )

    upload_dir  = f"uploads/verification/{new_user.userid}/"
    id_path     = default_storage.save(
        upload_dir + "id_" + files['id_image'].name,
        ContentFile(files['id_image'].read())
    )
    selfie_path = default_storage.save(
        upload_dir + "selfie_" + files['selfie'].name,
        ContentFile(files['selfie'].read())
    )

    try:
        id_type = TypeOfID.objects.get(toid=data['toid'])
    except TypeOfID.DoesNotExist:
        id_type = None

    ResidentVerification.objects.create(
        user=new_user,
        toid=id_type,
        id_image_path=id_path,
        selfie_image_path=selfie_path,
        status="Pending",
    )

    Settings.objects.create(
        user=new_user,
        receive_sms=data['receive_sms'],
        notifications_enabled=True,
        dark_mode=False,
        updated_at=timezone.now(),
    )

    messages.success(request,
        "Account created! Please wait for admin verification before logging in.")
    return redirect("login")


# DASHBOARDS

@admin_login_required
def admin_dashboard_view(request):
    user = get_current_user(request)

    # Live stats from DB
    total_residents = Users.objects.filter(
        user_type__type_name="Resident"
    ).count()

    pending_verifications = ResidentVerification.objects.filter(
        status="Pending"
    ).count()

    total_sms = SMSOutbox.objects.count()

    return render(request, "adminpanel/dashboard.html", {
        "user":                  user,
        "total_residents":       total_residents,
        "pending_verifications": pending_verifications,
        "total_sms":             total_sms,
    })


@login_required
@resident_required
def resident_dashboard_view(request):
    return render(request, "resident/dashboard.html", {
        "user": get_current_user(request)
    })

def pending_verification_view(request):
    return render(request, "resident/pending_verification.html")


# LOGOUT

def logout_view(request):
    user_type = request.session.get("user_type", "Resident")
    request.session.flush()
    messages.success(request, "You have been logged out successfully.")
    if user_type == "Admin":
        return redirect("admin_login")
    return redirect("login")


# ADMIN — CREATE STAFF (Chairman only)

@admin_login_required
@permission_required('create_users')
def admin_register(request):
    if request.method != "POST":
        return render(request, "auth/admin_register.html", {
            "roles":     Roles.objects.all(),
            "positions": Positions.objects.all(),
        })

    firstname   = request.POST.get("firstname", "").strip()
    lastname    = request.POST.get("lastname", "").strip()
    contact_no  = request.POST.get("contact_no", "").strip()
    role_id     = request.POST.get("role_id", "").strip()
    position_id = request.POST.get("position_id", "").strip()

    if not all([firstname, lastname, contact_no, role_id]):
        messages.error(request, "All required fields must be filled.")
        return redirect("admin_register")

    if Users.objects.filter(contactno=contact_no).exists():
        messages.error(request, "Contact number already exists.")
        return redirect("admin_register")

    suffix   = ''.join(random.choices(_string.digits, k=4))
    username = (lastname.lower().replace(" ", "") + suffix)[:20]
    while Users.objects.filter(username=username).exists():
        suffix   = ''.join(random.choices(_string.digits, k=4))
        username = (lastname.lower().replace(" ", "") + suffix)[:20]

    temp_password = ''.join(random.choices(
        _string.ascii_letters + _string.digits, k=10
    ))

    try:
        admin_type = UserTypes.objects.get(type_name="Admin")
        role       = Roles.objects.get(roleid=role_id)
    except (UserTypes.DoesNotExist, Roles.DoesNotExist):
        messages.error(request, "Invalid role selected.")
        return redirect("admin_register")

    position = None
    if position_id:
        try:
            position = Positions.objects.get(positionid=position_id)
        except Positions.DoesNotExist:
            pass

    current_admin = get_current_user(request)

    new_user = Users.objects.create(
        username=username,
        password=hash_password(temp_password),
        firstname=firstname,
        lastname=lastname,
        contactno=contact_no,
        user_type=admin_type,
        role=role,
        position=position,
        is_verified=True,
        is_active=True,
        is_first_login=True,
        is_password_changed=False,
    )

    send_sms(contact_no,
        f"KaugnayPH: Account created. "
        f"Username: {username} | Temp Password: {temp_password} "
        f"Log in and change your password immediately.",
        sent_by=current_admin
    )

    AuditLogs.objects.create(
        user=current_admin, action="Create Staff Account",
        module_name="UserManagement", table_name="Users",
        record_id=new_user.userid,
        new_value=f"Staff '{username}' created by {current_admin.username}.",
        created_at=timezone.now()
    )

    messages.success(request,
        f"Staff account created! Username: {username} | "
        f"Temp Password: {temp_password} (also sent via SMS)")
    return redirect("admin_register")


# RESIDENT RECORDS

@admin_login_required
@permission_required('view_residents')
def resident_records_view(request):
    residents = Users.objects.filter(
        user_type__type_name="Resident"
    ).order_by("lastname", "firstname")

    records = []
    for u in residents:
        rv  = ResidentVerification.objects.filter(user=u).first()
        s   = Settings.objects.filter(user=u).first()
        records.append({
            "user":    u,
            "rv":      rv,
            "status":  rv.status if rv else "No Submission",
            "sms_sub": s.receive_sms if s else False,
        })

    return render(request, "adminpanel/resident_records.html", {
        "records": records,
        "user":    get_current_user(request),
    })


@admin_login_required
@permission_required('view_residents')
def resident_record_view(request, user_id):
    try:
        resident = Users.objects.get(
            userid=user_id, user_type__type_name="Resident"
        )
    except Users.DoesNotExist:
        messages.error(request, "Resident not found.")
        return redirect("resident_records")

    rv      = ResidentVerification.objects.select_related("toid").filter(user=resident).first()
    s       = Settings.objects.filter(user=resident).first()
    sms_sub = s.receive_sms if s else False
    admin   = get_current_user(request)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "approve" and rv:
            rv.status = "Approved"
            rv.reviewed_by = admin
            rv.reviewed_at = timezone.now()
            rv.save()
            resident.is_verified = True
            resident.save()
            send_sms(resident.contactno,
                "KaugnayPH: Your account has been verified! You can now log in.",
                sent_by=admin)
            AuditLogs.objects.create(
                user=admin, action="Approve Resident",
                module_name="Verification", table_name="ResidentVerification",
                record_id=rv.rv_id,
                new_value=f"Resident {resident.username} approved.",
                created_at=timezone.now()
            )
            messages.success(request,
                f"{resident.firstname} {resident.lastname} approved.")

        elif action == "reject" and rv:
            rv.status = "Rejected"
            rv.reviewed_by = admin
            rv.reviewed_at = timezone.now()
            rv.save()
            resident.is_verified = False
            resident.save()
            send_sms(resident.contactno,
                "KaugnayPH: Your registration was not approved. "
                "Please visit the barangay office.",
                sent_by=admin)
            AuditLogs.objects.create(
                user=admin, action="Reject Resident",
                module_name="Verification", table_name="ResidentVerification",
                record_id=rv.rv_id,
                new_value=f"Resident {resident.username} rejected.",
                created_at=timezone.now()
            )
            messages.warning(request,
                f"{resident.firstname} {resident.lastname} rejected.")

        return redirect("resident_record_view", user_id=user_id)

    return render(request, "adminpanel/resident_profile.html", {
        "resident": resident,
        "rv":       rv,
        "sms_sub":  sms_sub,
        "admin":    admin,
    })


@admin_login_required
@permission_required('manage_residents')
def resident_record_edit(request, user_id):
    try:
        resident = Users.objects.get(
            userid=user_id, user_type__type_name="Resident"
        )
    except Users.DoesNotExist:
        messages.error(request, "Resident not found.")
        return redirect("resident_records")

    rv       = ResidentVerification.objects.filter(user=resident).first()
    id_types = TypeOfID.objects.all()
    admin    = get_current_user(request)

    if request.method != "POST":
        return render(request, "adminpanel/resident_record_edit.html", {
            "resident": resident,
            "rv":       rv,
            "id_types": id_types,
            "admin":    admin,
        })

    action = request.POST.get("action")

    if action == "delete":
        name = f"{resident.firstname} {resident.lastname}"
        uid  = resident.userid
        # Delete verification record first to avoid FK constraint
        ResidentVerification.objects.filter(user=resident).delete()
        Settings.objects.filter(user=resident).delete()
        resident.delete()
        AuditLogs.objects.create(
            user=admin, action="Delete Resident",
            module_name="Residents", table_name="Users",
            record_id=uid,
            new_value=f"Resident '{name}' deleted.",
            created_at=timezone.now()
        )
        messages.success(request, f"Resident {name} deleted.")
        return redirect("resident_records")

    if action == "save":
        old = {
            "firstname": resident.firstname,
            "lastname":  resident.lastname,
            "contactno": resident.contactno,
            "sex":       resident.sex,
        }

        resident.firstname = request.POST.get("firstname", resident.firstname).strip()
        resident.lastname  = request.POST.get("lastname",  resident.lastname).strip()
        resident.sex       = request.POST.get("sex",       resident.sex or "").strip()

        new_contact = request.POST.get("contact_no", resident.contactno).strip()
        if new_contact != resident.contactno:
            if Users.objects.filter(contactno=new_contact).exclude(userid=user_id).exists():
                messages.error(request, "Contact number already in use.")
                return render(request, "adminpanel/resident_record_edit.html", {
                    "resident": resident, "rv": rv,
                    "id_types": id_types, "admin": admin,
                })
            resident.contactno = new_contact

        resident.save()

        if rv:
            new_toid = request.POST.get("type_of_id", "").strip()
            if new_toid:
                try:
                    rv.toid = TypeOfID.objects.get(toid=new_toid)
                    rv.save()
                except TypeOfID.DoesNotExist:
                    pass

        AuditLogs.objects.create(
            user=admin, action="Edit Resident",
            module_name="Residents", table_name="Users",
            record_id=user_id,
            old_value=str(old),
            new_value=f"Updated by {admin.username}",
            created_at=timezone.now()
        )
        messages.success(request, "Resident updated successfully.")
        return redirect("resident_record_view", user_id=user_id)

    return render(request, "adminpanel/resident_record_edit.html", {
        "resident": resident, "rv": rv,
        "id_types": id_types, "admin": admin,
    })


# VERIFICATION FILE SERVING
@admin_login_required
@permission_required('verify_residents')
def serve_verification_file(request, rv_id, file_type):
    from pathlib import Path
    import mimetypes
    from django.http import FileResponse, Http404

    try:
        rv = ResidentVerification.objects.get(rv_id=rv_id)
    except ResidentVerification.DoesNotExist:
        raise Http404

    path = rv.id_image_path if file_type == "id" else \
           rv.selfie_image_path if file_type == "selfie" else None
    if not path:
        raise Http404

    full_path = Path(settings.MEDIA_ROOT) / path
    if not full_path.exists():
        raise Http404

    mime_type, _ = mimetypes.guess_type(str(full_path))
    return FileResponse(
        open(full_path, 'rb'),
        content_type=mime_type or 'image/jpeg'
    )

# Admin Announcement List 
@admin_login_required
def admin_announcements_view(request):

    announcements = Announcements.objects.all().order_by(
        "-announcement_id"
    )

    return render(
        request,
        "adminpanel/announcements_list.html",
        {
            "announcements": announcements,
            "user": get_current_user(request),
        }
    )

# ADMIN ANNOUNCEMENT DETAIL

@admin_login_required
def admin_announcement_detail_view(request, announcement_id):

    try:
        announcement = Announcements.objects.get(
            announcement_id=announcement_id
        )

    except Announcements.DoesNotExist:
        messages.error(request, "Announcement not found.")
        return redirect("announcements")

    return render(
        request,
        "adminpanel/announcement_detail.html",
        {
            "announcement": announcement,
            "user": get_current_user(request),
        }
    )

# ADMIN ANNOUNCEMENT EDIT

@admin_login_required
def admin_announcement_edit_view(request, announcement_id):

    try:
        announcement = Announcements.objects.get(
            announcement_id=announcement_id
        )

    except Announcements.DoesNotExist:
        messages.error(request, "Announcement not found.")
        return redirect("announcements")

    if request.method == "POST":
        announcement.title = request.POST.get("title", "").strip()
        announcement.content = request.POST.get("content", "").strip()

        if not announcement.title:
            messages.error(request, "Title is required.")
            return render(request, "adminpanel/announcement_edit.html", {
                "announcement": announcement,
                "user": get_current_user(request),
            })

        if not announcement.content:
            messages.error(request, "Content is required.")
            return render(request, "adminpanel/announcement_edit.html", {
                "announcement": announcement,
                "user": get_current_user(request),
            })

        announcement.save()

        messages.success(request, "Announcement updated successfully.")
        return redirect("admin_announcement_detail", announcement_id=announcement.announcement_id)

    return render(request, "adminpanel/announcement_edit.html", {
        "announcement": announcement,
        "user": get_current_user(request),
    })