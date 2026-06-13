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
from django.db.models import Q
 
from core.utils import validate_upload
from core.moderation import moderate_text, moderate_image
from core.sla_utils import (
    create_sla,
    record_first_response,
    resolve_sla,
    get_sla_for_record,
    get_sla_status_live,
)
 
from .models import (
    Inquiry, Users, UserTypes, Settings, Roles, Positions,
    Announcements, SMSOutbox, SMSSubscriptions,
    AuditLogs, ResidentVerification, TypeOfID,
    OTP, Complaints, ComplaintType,
    DocumentTypes, DocumentFields, DocumentRequests,
    DocumentRequestFieldValues, ComplaintUpdates,
    HearingLevel, HearingStatus, ComplaintHearing,
    HearingOfficials,
    AnnouncementFeedback,
    AnnouncementCategories,
)
 
from .auth_utils import (
    hash_password, check_password, generate_otp,
    verify_otp, send_sms, send_email_otp,
    set_user_session, get_current_user,
    has_permission,
)
 
from .decorators import (
    login_required,
    admin_login_required,
    resident_required,
    permission_required,
    chairman_required,
)

from core.moderation import moderate_text, moderate_image


# PUBLIC PAGES

def landing_page(request):
    announcements = Announcements.objects.select_related(
        "category",
        "posted_by"
    ).order_by("-created_at")[:4]

    return render(request, "public/landing.html", {
        "announcements": announcements
    })

@login_required
@resident_required
def filecomplaint(request):
    complaint_types = ComplaintType.objects.all()
 
    if request.method == "POST":
        complaint_type_id = request.POST.get("complaint_type", "").strip()
        incident_date     = request.POST.get("incident_date")
        complainee        = request.POST.get("complainee", "").strip()
        complainee_address = request.POST.get("complainee_address", "").strip()
        title             = request.POST.get("title", "").strip()
        description       = request.POST.get("description", "").strip()
        evidence          = request.FILES.get("evidence")
 
        if not complaint_type_id:
            messages.error(request, "Please select a complaint type.")
            return render(request, "filecomplaint.html", {"complaint_types": complaint_types})
 
        if not complainee:
            messages.error(request, "Name of complainee is required.")
            return render(request, "filecomplaint.html", {"complaint_types": complaint_types})
 
        if not title:
            messages.error(request, "Title is required.")
            return render(request, "filecomplaint.html", {"complaint_types": complaint_types})
 
        if not description:
            messages.error(request, "Description is required.")
            return render(request, "filecomplaint.html", {"complaint_types": complaint_types})
 
        try:
            complaint_type = ComplaintType.objects.get(ctid=complaint_type_id)
        except ComplaintType.DoesNotExist:
            messages.error(request, "Invalid complaint type selected.")
            return render(request, "filecomplaint.html", {"complaint_types": complaint_types})
 
        current_user = get_current_user(request)
 
        #FILE VALIDATION & SAVE
        file_path = None
        if evidence:
            ok, err = validate_upload(evidence)
            if not ok:
                messages.error(request, err)
                return render(request, "filecomplaint.html", {"complaint_types": complaint_types})
 
            file_path = default_storage.save(
                "complaints/" + evidence.name,
                ContentFile(evidence.read())
            )
 
        #CONTENT MODERATION
        text_check = moderate_text(f"{title} {description} {complainee}")
 
        #CONTENT MODERATION — image (ONLY if file is an image)
        image_check = {"flagged": False, "reason": None}
        if evidence and evidence.content_type.startswith("image/"):
            evidence.seek(0)
            image_check = moderate_image(evidence)
 
        is_flagged  = text_check["flagged"] or image_check["flagged"]
        flag_reason = text_check["reason"] or image_check["reason"]
 
        if is_flagged:
            messages.error(
                request,
                "Your complaint contains inappropriate content and could not be submitted. "
                "Please revise and try again."
            )
            return render(request, "filecomplaint.html", {"complaint_types": complaint_types})
 
        # SAVE — only reaches here if clean
        Complaints.objects.create(
            complaint_type=complaint_type,
            complainant_user=current_user,
            complainee=complainee,
            complainee_address=complainee_address,
            title=title,
            description=description,
            incident_date=incident_date or None,
            file_path=file_path,
            status="Pending",
            is_flagged=False,
            flagged_reason=None,
        )
 
        #NOTE: SLA for Complaints is ON HOLD! NEED TO CLARFIY TO BARANGAY
 
        messages.success(
            request,
            "Complaint submitted successfully. You can track its status through Track Submissions."
        )
        return redirect("tracksub")
 
    return render(request, "filecomplaint.html", {"complaint_types": complaint_types})


def aboutus(request):
    return render(request, 'aboutus.html')

def documents(request):
    document_types = DocumentTypes.objects.filter(is_active=True)
    return render(request, 'documents.html', {"document_types": document_types})

def faqs(request):
    return render(request, 'faqs.html')

def contactus(request):
    if request.method == "POST":
        firstname = request.POST.get("firstname", "").strip()
        lastname  = request.POST.get("lastname", "").strip()
        contactno = request.POST.get("contactno", "").strip()
        address   = request.POST.get("address", "").strip()
        subject   = request.POST.get("messagesubject", "").strip()
        message   = request.POST.get("message", "").strip()
 
        if not firstname or not lastname or not contactno or not message:
            messages.error(request, "Please fill in all required fields.")
            return render(request, "contactus.html")
 
        # CONTENT MODERATION — check before saving
        check = moderate_text(f"{subject} {message}")
        if check["flagged"]:
            messages.error(
                request,
                "Your message contains inappropriate content and could not be submitted. "
                "Please revise and try again."
            )
            return render(request, "contactus.html")
 
        # SAVE
        current_user = get_current_user(request)
        inquiry = Inquiry.objects.create(
            user=current_user,
            firstname=firstname,
            lastname=lastname,
            contactno=contactno,
            address=address,
            messagesubject=subject,
            message=message,
            status="New",
            created_at=timezone.now(),
        )
 
        # SLA — start the 24-hour clock
        create_sla("Inquiry", inquiry.cuid, priority="Medium")
 
        messages.success(
            request,
            "Your inquiry has been submitted. We will get back to you within 24 hours."
        )
        return redirect("contactus")
 
    return render(request, "contactus.html")

def announcements_view(request):
    announcements = Announcements.objects.all().order_by("-announcement_id")

    current_user = get_current_user(request)
    feedback_map = {}
    if current_user and hasattr(current_user, 'user_type') and current_user.user_type.type_name == "Resident":
        for fb in AnnouncementFeedback.objects.filter(user=current_user):
            feedback_map[fb.announcement_id] = fb.rating

    for ann in announcements:
        ann.my_rating = feedback_map.get(ann.announcement_id)  # None if not rated, 1-5 if rated

    return render(request, "public/announcements.html", {
    "announcements":  announcements,
    "is_resident":    bool(current_user and current_user.user_type.type_name == "Resident"),
    })

def profile(request):
    return render(request, 'residentprofile.html')

@login_required
@resident_required
def submit_announcement_feedback(request, announcement_id):
    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)

    try:
        announcement = Announcements.objects.get(announcement_id=announcement_id)
    except Announcements.DoesNotExist:
        return JsonResponse({"error": "Announcement not found."}, status=404)

    current_user = get_current_user(request)

    try:
        data   = json.loads(request.body)
        rating = int(data.get("rating", 0))
    except (ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid data."}, status=400)

    if rating < 1 or rating > 5:
        return JsonResponse({"error": "Rating must be between 1 and 5."}, status=400)

    feedback, created = AnnouncementFeedback.objects.update_or_create(
        announcement=announcement,
        user=current_user,
        defaults={
            "rating":     rating,
            "created_at": timezone.now(),
        }
    )

    AuditLogs.objects.create(
        user=current_user,
        action="Submit Announcement Feedback" if created else "Update Announcement Feedback",
        module_name="Announcements",
        table_name="AnnouncementFeedback",
        record_id=feedback.afid,
        new_value=f"Rating: {rating} for Announcement #{announcement_id}",
        created_at=timezone.now(),
    )

    return JsonResponse({
        "success": True,
        "message": "Feedback submitted!" if created else "Feedback updated!",
        "rating":  rating,
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

def _send_admin_login_otp(request, user, otp):
    try:
        send_sms(
            user.contactno,
            f"KaugnayPH OTP: {otp.code}. Valid for 5 minutes."
        )
        request.session["otp_method"] = "sms"
    except Exception:
        send_email_otp(user.email, otp.code)
        request.session["otp_method"] = "email"


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
    return redirect("landing")


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
        messages.error(
            request,
            f"Please wait {cooldown} before requesting another OTP."
        )
        return render(request, "auth/login_admin.html")

    sms_sent = send_sms(
        user.contactno,
        f"KaugnayPH OTP: {otp.code}. Valid for 5 minutes."
    )

    if sms_sent:
        request.session["otp_method"] = "sms"
    else:
        send_email_otp(user.email, otp.code)
        request.session["otp_method"] = "email"

        messages.warning(
            request,
            "SMS delivery failed. OTP has been sent to your registered email address instead."
        )

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
        sms_sent = send_sms(
            user.contactno,
            f"KaugnayPH OTP: {otp.code}. Valid for 5 minutes."
        )

        if sms_sent:
            request.session["otp_method"] = "sms"
        else:
            send_email_otp(user.email, otp.code)
            request.session["otp_method"] = "email"

            messages.warning(
                request,
                "SMS delivery failed. OTP has been sent to your registered email address instead."
            )

    else:
        send_sms(
            user.contactno,
            f"KaugnayPH OTP: {otp.code}. Valid for 5 minutes."
        )

        request.session["otp_method"] = "sms"

    messages.success(request, "New OTP sent.")
    return redirect("otp_verify")

# IF EMAIL OTP
def send_email_otp_view(request):
    pending_id = request.session.get("pending_user_id")

    if not pending_id:
        return redirect("admin_login")

    try:
        user = Users.objects.get(userid=pending_id)
    except Users.DoesNotExist:
        return redirect("admin_login")

    if not user.email:
        messages.error(
            request,
            "No email address is registered for this account."
        )
        return redirect("otp_verify")

    purpose = "first_login" if request.session.get("from_first_login") else "login"

    otp = OTP.objects.filter(
        user=user,
        purpose=purpose,
        is_used=False,
        expires_at__gt=timezone.now()
    ).order_by("-created_at").first()

    if not otp:
        otp, cooldown = generate_otp(
            user,
            purpose=purpose
        )

        if cooldown:
            mins = cooldown // 60
            secs = cooldown % 60

            messages.error(
                request,
                f"Please wait {mins}m {secs}s before requesting another OTP."
            )
            return redirect("otp_verify")

    send_email_otp(
        user.email,
        otp.code
    )

    request.session["otp_method"] = "email"

    messages.success(
        request,
        "OTP has been sent to your registered email address."
    )

    return redirect("otp_verify")


# RESIDENT REGISTER

def _validate_register_form(data, files):
    errors = []

    if not data['firstname'] or not data['lastname']:
        errors.append("First name and last name are required.")

    if not data['email']:
        errors.append("Email address is required.")
    elif Users.objects.filter(email=data['email']).exists():
        errors.append("Email address is already registered.")

    if not data['contact_no'].startswith("09") or len(data['contact_no']) != 11:
        errors.append("Enter a valid 11-digit PH mobile number.")
    elif Users.objects.filter(contactno=data['contact_no']).exists():
        errors.append("Mobile number is already registered.")
    elif Users.objects.filter(username=data['contact_no']).exists():
        errors.append("An account with this mobile number already exists.")

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
        'email': request.POST.get("email_address", "").strip(),
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
        email=data['email'],
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
    from django.core.paginator import Paginator

    status_filter = request.GET.get("status", "All").strip()
    search_query = request.GET.get("search", "").strip()

    residents = Users.objects.filter(
        user_type__type_name="Resident"
    ).order_by("lastname", "firstname")

    if search_query:
        residents = residents.filter(
            Q(firstname__icontains=search_query) |
            Q(lastname__icontains=search_query) |
            Q(contactno__icontains=search_query) |
            Q(username__icontains=search_query)
        )

    records = []

    for u in residents:
        rv = ResidentVerification.objects.filter(user=u).first()
        s = Settings.objects.filter(user=u).first()
        status = rv.status if rv else "No Submission"

        if status_filter != "All" and status != status_filter:
            continue

        records.append({
            "user": u,
            "rv": rv,
            "status": status,
            "sms_sub": s.receive_sms if s else False,
        })

    paginator = Paginator(records, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    total_residents = Users.objects.filter(
        user_type__type_name="Resident"
    ).count()

    return render(request, "adminpanel/resident_records.html", {
        "records": page_obj,
        "page_obj": page_obj,
        "user": get_current_user(request),
        "status_filter": status_filter,
        "search_query": search_query,
        "total_residents": total_residents,
        "pending_count": ResidentVerification.objects.filter(status="Pending").count(),
        "verified_count": ResidentVerification.objects.filter(status="Approved").count(),
        "sms_count": Settings.objects.filter(receive_sms=True).count(),
    })

# RESIDENT PROFILE
@login_required
@resident_required
def residentprofile(request):
    current_user = get_current_user(request)

    recent_complaints = Complaints.objects.filter(
        complainant_user=current_user
    ).order_by('-dateadded')[:3]

    active_complaints = Complaints.objects.filter(
        complainant_user=current_user
    ).exclude(
        status__in=['Resolved', 'Dismissed']
    ).order_by('-dateadded')[:3]

    recent_requests = DocumentRequests.objects.filter(
        user=current_user
    ).select_related('document_type').order_by('-requested_at')[:3]

    latest_announcement = Announcements.objects.order_by('-announcement_id').first()

    return render(request, 'residentprofile.html', {
        'recent_complaints': recent_complaints,
        'active_complaints': active_complaints,
        'recent_requests': recent_requests,
        'latest_announcement': latest_announcement,
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
        
        if action in ("approve", "reject"):
            if not has_permission(admin, 'verify_residents'):
                messages.error(request, "You do not have permission to verify residents.")
                return redirect("resident_record_view", user_id=user_id)
        if action == "approve" and rv:
            rv.status = "Approved"
            rv.reviewed_by = admin
            rv.reviewed_at = timezone.now()
            rv.save()
            resident.is_verified = True
            resident.save()
            s = Settings.objects.filter(user=resident).first()

            if s and s.receive_sms:
                SMSSubscriptions.objects.update_or_create(
                    user=resident,
                    defaults={"is_active": True}
                )
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
            remarks = request.POST.get("remarks", "").strip() 
            rv.status = "Rejected"
            rv.remarks = remarks                                
            rv.reviewed_by = admin
            rv.reviewed_at = timezone.now()
            rv.save()
            resident.is_verified = False
            resident.save()
            SMSSubscriptions.objects.filter(user=resident).update(is_active=False)
            send_sms(resident.contactno,
                "KaugnayPH: Your registration was not approved. "
                "Please visit the barangay office.",
                sent_by=admin)
            AuditLogs.objects.create(
                user=admin, action="Reject Resident",
                module_name="Verification", table_name="ResidentVerification",
                record_id=rv.rv_id,
                new_value=f"Resident {resident.username} rejected. Remarks: {remarks or 'None'}",  # ← UPDATED
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
        }

        resident.firstname = request.POST.get("firstname", resident.firstname).strip()
        resident.lastname  = request.POST.get("lastname",  resident.lastname).strip()

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
    from django.core.paginator import Paginator

    search = request.GET.get("search", "").strip()
    category = request.GET.get("category", "").strip()

    announcements = Announcements.objects.select_related(
        "category",
        "posted_by"
    ).all()

    if search:
        announcements = announcements.filter(title__icontains=search)

    if category and category != "all":
        announcements = announcements.filter(category__name__iexact=category)

    announcements = announcements.order_by("-announcement_id")

    paginator = Paginator(announcements, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "adminpanel/announcements_list.html", {
        "announcements": page_obj,
        "page_obj": page_obj,
        "user": get_current_user(request),
        "search": search,
        "selected_category": category,
        "total_announcements": announcements.count(),
    })

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
        announcement.send_sms = (request.POST.get("send_sms") == "on")

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

        # FILE UPLOAD
        uploaded_file = request.FILES.get("attachment")

        if uploaded_file:
            ok, err = validate_upload(uploaded_file)

            if not ok:
                messages.error(request, err)
                return render(request, "adminpanel/announcement_edit.html", {
                    "announcement": announcement,
                    "user": get_current_user(request),
                })

            file_path = default_storage.save(
                "announcements/" + uploaded_file.name,
                ContentFile(uploaded_file.read())
            )
            announcement.file_path = file_path

        # --- CONTENT MODERATION ---
        text_check = moderate_text(f"{announcement.title} {announcement.content}")
        if text_check["flagged"]:
            messages.error(
                request,
                f"Announcement content was flagged for: {text_check['reason']}. "
                "Please review and revise before saving."
            )
            return render(request, "adminpanel/announcement_edit.html", {
                "announcement": announcement,
                "user": get_current_user(request),
            })

        announcement.save()

        messages.success(request, "Announcement updated successfully.")
        return redirect(
            "admin_announcement_detail",
            announcement_id=announcement.announcement_id
        )

    return render(
        request,
        "adminpanel/announcement_edit.html",
        {
            "announcement": announcement,
            "user": get_current_user(request),
        }
    )

# ADMIN ANNOUNCEMENT DELETE

@admin_login_required
def admin_announcement_delete_view(request, announcement_id):

    try:
        announcement = Announcements.objects.get(
            announcement_id=announcement_id
        )

    except Announcements.DoesNotExist:
        messages.error(request, "Announcement not found.")
        return redirect("announcements")

    if request.method == "POST":
        announcement.delete()
        messages.success(request, "Announcement deleted successfully.")
        return redirect("announcements")

    return redirect("admin_announcement_detail", announcement_id=announcement_id)

# ADMIN ANNOUNCEMENT CREATE

@admin_login_required
def admin_announcement_create_view(request):

    current_admin = get_current_user(request)

    if request.method == "POST":

        title = request.POST.get("title", "").strip()
        content = request.POST.get("content", "").strip()
        send_sms_flag = request.POST.get("send_sms") == "on"
        category_id = request.POST.get("category_id", 1)

        if send_sms_flag:
            category_id = 2

        if not title:
            messages.error(request, "Title is required.")

            return render(
                request,
                "adminpanel/announcement_create.html",
                {
                    "user": current_admin,
                }
            )

        if not content:
            messages.error(request, "Content is required.")

            return render(
                request,
                "adminpanel/announcement_create.html",
                {
                    "user": current_admin,
                }
            )

        # FILE UPLOAD
        file_path = None
        uploaded_file = request.FILES.get("attachment")

        if uploaded_file:

            ok, err = validate_upload(uploaded_file)

            if not ok:

                messages.error(request, err)

                return render(
                    request,
                    "adminpanel/announcement_create.html",
                    {
                        "user": current_admin,
                    }
                )

            file_path = default_storage.save(
                "announcements/" + uploaded_file.name,
                ContentFile(uploaded_file.read())
            )

        #CONTENT MODERATION
        text_check = moderate_text(f"{title} {content}")
        if text_check["flagged"]:
            messages.error(
                request,
                f"Announcement content was flagged for: {text_check['reason']}. "
                "Please review and revise before posting."
            )
            return render(request, "adminpanel/announcement_create.html", {"user": current_admin})

        announcement = Announcements.objects.create(
            title=title,
            content=content,
            file_path=file_path,
            send_sms=1 if send_sms_flag else 0,
            category_id=category_id,
            posted_by=current_admin,
            created_at=timezone.now()
)

        # OPTIONAL SMS SEND
        if send_sms_flag:

            for sub in SMSSubscriptions.objects.select_related(
                "user"
            ).filter(is_active=True):

                send_sms(
                    sub.user.contactno,
                    f"KaugnayPH: {announcement.title}",
                    sent_by=current_admin
                )

        # AUDIT LOG
        AuditLogs.objects.create(
            user=current_admin,
            action="Create Announcement",
            module_name="Announcements",
            table_name="Announcements",
            record_id=announcement.announcement_id,
            new_value=f"Announcement '{title}' created.",
            created_at=timezone.now()
        )

        messages.success(request, "Announcement created successfully.")
        return redirect("announcements")   # ← ADD THIS, it's missing

    return render(request, "adminpanel/announcement_create.html", {"user": current_admin})

#ADMIN: Feedback View (rating)
@admin_login_required
def admin_feedback_view(request):
    from django.db.models import Avg, Count, Q

    announcements = Announcements.objects.annotate(
        avg_rating    = Avg("announcementfeedback__rating"),
        feedback_count= Count("announcementfeedback"),
        r1 = Count("announcementfeedback", filter=Q(announcementfeedback__rating=1)),
        r2 = Count("announcementfeedback", filter=Q(announcementfeedback__rating=2)),
        r3 = Count("announcementfeedback", filter=Q(announcementfeedback__rating=3)),
        r4 = Count("announcementfeedback", filter=Q(announcementfeedback__rating=4)),
        r5 = Count("announcementfeedback", filter=Q(announcementfeedback__rating=5)),
    ).order_by("-announcement_id")

    return render(request, "adminpanel/feedback_monitoring.html", {
        "announcements": announcements,
        "user":          get_current_user(request),
    })


@admin_login_required
def admin_feedback_detail_view(request, announcement_id):
    from django.db.models import Avg, Count

    try:
        announcement = Announcements.objects.get(announcement_id=announcement_id)
    except Announcements.DoesNotExist:
        messages.error(request, "Announcement not found.")
        return redirect("admin_feedback")

    feedbacks = AnnouncementFeedback.objects.filter(
        announcement=announcement
    ).select_related("user").order_by("-created_at")

    stats = feedbacks.aggregate(
        avg_rating=Avg("rating"),
        total=Count("afid"),
    )

    distribution = {}
    for i in range(1, 6):
        distribution[i] = feedbacks.filter(rating=i).count()

    return render(request, "adminpanel/feedback_detail.html", {
        "announcement": announcement,
        "feedbacks":    feedbacks,
        "stats":        stats,
        "distribution": distribution,
        "user":         get_current_user(request),
    })


# ADMIN CASE RECORDS
@admin_login_required
def case_records_view(request):
    from django.core.paginator import Paginator
    import re

    search_query = request.GET.get("search", "").strip()

    complaints = Complaints.objects.select_related(
        "complaint_type",
        "complainant_user"
    ).all()

    if search_query:
        case_id_match = re.search(r"(\d+)$", search_query)
        case_id_number = int(case_id_match.group(1)) if case_id_match else None

        search_filter = (
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(complainee__icontains=search_query) |
            Q(status__icontains=search_query) |
            Q(complaint_type__type__icontains=search_query)
        )

        if case_id_number is not None:
            search_filter |= Q(complaintsid=case_id_number)

        complaints = complaints.filter(search_filter)

    complaints = complaints.order_by("-dateadded")

    case_records = []

    for complaint in complaints:
        status = complaint.status or "Pending"

        case_records.append({
            "complaint_id": complaint.complaintsid,
            "case_id": f"CMP-2026-{complaint.complaintsid:04d}",
            "case_type": complaint.complaint_type.type if complaint.complaint_type else "Complaint",
            "type_class": "complaint",
            "title": complaint.title,
            "date_submitted": complaint.dateadded.strftime("%b %d, %Y") if complaint.dateadded else "",
            "status": status,
            "status_class": status.lower().replace(" ", "-"),
        })

    paginator = Paginator(case_records, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    total_cases = complaints.count()
    pending_cases = complaints.filter(status="Pending").count()
    under_review_cases = complaints.filter(status="Under Review").count()
    completed_cases = complaints.filter(status="Resolved").count()

    return render(request, "adminpanel/case_records.html", {
        "cases": page_obj,
        "page_obj": page_obj,
        "user": get_current_user(request),
        "search_query": search_query,
        "total_cases": total_cases,
        "pending_cases": pending_cases,
        "under_review_cases": under_review_cases,
        "completed_cases": completed_cases,
        "avg_processing_time": "0%",
    })

# ADMIN CASE DETAIL
@admin_login_required
def case_detail_view(request, complaint_id):
    complaint = Complaints.objects.select_related(
        "complaint_type",
        "complainant_user",
        "handled_by"
    ).get(complaintsid=complaint_id)

    current_admin = get_current_user(request)

    if request.method == "POST":
        action = request.POST.get("action")
        old_status = complaint.status

        if action == "resolve":
            complaint.status = "Resolved"
            log_action = "Resolve Case"

        elif action == "review":
            complaint.status = "Under Review"
            log_action = "Mark Case Under Review"

        elif action == "dismiss":
            complaint.status = "Dismissed"
            log_action = "Dismiss Case"

        else:
            messages.error(request, "Invalid action.")
            return redirect("case_detail", complaint_id=complaint.complaintsid)

        complaint.handled_by = current_admin
        complaint.save()

        case_number = f"CMP-2026-{complaint.complaintsid:04d}"

        if complaint.complainant_user and complaint.complainant_user.contactno:
            if complaint.status == "Under Review":
                sms_message = (
                    f"KaugnayPH: Your complaint {case_number} is now Under Review."
                )

            elif complaint.status == "Resolved":
                sms_message = (
                    f"KaugnayPH: Your complaint {case_number} has been resolved."
                )

            elif complaint.status == "Dismissed":
                sms_message = (
                    f"KaugnayPH: Your complaint {case_number} has been dismissed. "
                    "Please contact the barangay office for more information."
                )

            else:
                sms_message = None

            if sms_message:
                send_sms(
                    complaint.complainant_user.contactno,
                    sms_message,
                    sent_by=current_admin
                )

        AuditLogs.objects.create(
            user=current_admin,
            action=log_action,
            module_name="Cases",
            table_name="Complaints",
            record_id=complaint.complaintsid,
            old_value=f"Status: {old_status}",
            new_value=f"Status: {complaint.status}",
            created_at=timezone.now()
        )

        messages.success(request, "Case status updated successfully.")

        return redirect("case_detail", complaint_id=complaint.complaintsid)

    return render(request, "adminpanel/case_detail.html", {
        "complaint": complaint,
        "user": current_admin,
        "case_id": f"CMP-2026-{complaint.complaintsid:04d}",
    })


#DOCUMENT REQUEST FOR RESIDENT 
@login_required
@resident_required
def document_request_view(request):
    document_types = DocumentTypes.objects.filter(is_active=True)
 
    if request.method == "POST":
        document_type_id = request.POST.get("document_type_id", "").strip()
        purpose          = request.POST.get("purpose", "").strip()
        uploaded_file    = request.FILES.get("uploaded_file")
 
        if not document_type_id:
            messages.error(request, "Please select a document type.")
            return render(request, "documents.html", {"document_types": document_types})
 
        try:
            document_type = DocumentTypes.objects.get(dtid=document_type_id, is_active=True)
        except DocumentTypes.DoesNotExist:
            messages.error(request, "Invalid document type selected.")
            return render(request, "documents.html", {"document_types": document_types})
 
        fields = DocumentFields.objects.filter(document_type=document_type)
        field_errors = []
        for field in fields:
            if field.is_required:
                value = request.POST.get(f"field_{field.dfid}", "").strip()
                if not value:
                    field_errors.append(f"'{field.field_label}' is required.")
 
        if field_errors:
            for err in field_errors:
                messages.error(request, err)
            return render(request, "documents.html", {
                "document_types": document_types,
                "selected_type": document_type,
                "fields": fields,
            })
 
        current_user = get_current_user(request)
 
        file_path = None
        if uploaded_file:
            ok, err = validate_upload(uploaded_file)
            if not ok:
                messages.error(request, err)
                return render(request, "documents.html", {"document_types": document_types})
            file_path = default_storage.save(
                f"document_requests/{uploaded_file.name}",
                ContentFile(uploaded_file.read())
            )
 
        # CONTENT MODERATION
        text_check = moderate_text(purpose)
        if text_check["flagged"]:
            messages.error(request, "Your request contains inappropriate content and could not be submitted.")
            return render(request, "documents.html", {"document_types": document_types})
 
        # SAVE
        doc_request = DocumentRequests.objects.create(
            user=current_user, document_type=document_type,
            purpose=purpose, uploaded_file=file_path,
            request_mode="Online", status="Pending",
        )
 
        for field in fields:
            value = request.POST.get(f"field_{field.dfid}", "").strip()
            DocumentRequestFieldValues.objects.create(
                document_request=doc_request, document_field=field,
                field_value=value, created_at=timezone.now(),
            )
 
        AuditLogs.objects.create(
            user=current_user, action="Submit Document Request",
            module_name="DocumentRequests", table_name="DocumentRequests",
            record_id=doc_request.drid,
            new_value=f"Request for '{document_type.name}' submitted.",
            created_at=timezone.now(),
        )
 
        # SLA — start the 3-day clock
        create_sla("DocumentRequest", doc_request.drid, priority="Medium")
 
        messages.success(request, "Document request submitted successfully. You can track its status under Track Submissions.")
        return redirect("tracksub")
 
    return render(request, "documents.html", {"document_types": document_types})


# DOCUMENT FIELDS API: returns fields for a selected doc type
def get_document_fields(request, dtid):
    """
    AJAX endpoint: GET /documents/fields/<dtid>/
    Returns JSON list of fields for a given DocumentType.
    Used by the frontend to render dynamic form fields.
    """
    try:
        document_type = DocumentTypes.objects.get(dtid=dtid, is_active=True)
    except DocumentTypes.DoesNotExist:
        return JsonResponse({"error": "Document type not found."}, status=404)

    fields = DocumentFields.objects.filter(document_type=document_type).values(
        "dfid", "field_label", "field_type", "is_required"
    )

    return JsonResponse({
        "document_type": document_type.name,
        "fields": list(fields),
    })


#TRACK SUBMISSIONS: updated to include document requests
@login_required
@resident_required
def tracksub(request):
    current_user = get_current_user(request)

    complaints = Complaints.objects.filter(
        complainant_user=current_user
    ).order_by("-dateadded")

    document_requests = DocumentRequests.objects.filter(
        user=current_user
    ).select_related("document_type").order_by("-requested_at")

    hearings = ComplaintHearing.objects.select_related(
        "complaint",
        "hearing_level",
        "status"
    ).filter(
        complaint__complainant_user=current_user
    ).order_by("-hearing_date")

    print("CURRENT USER:", current_user.userid)
    print("HEARINGS FOUND:", hearings.count())

    return render(request, "tracksub.html", {
        "complaints": complaints,
        "document_requests": document_requests,
        "hearings": hearings,
    })


# ADMIN: DOCUMENT REQUESTS LIST
@admin_login_required
def admin_document_requests_view(request):
    from django.core.paginator import Paginator
 
    search_query  = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "All").strip()
 
    doc_requests = DocumentRequests.objects.select_related("user", "document_type", "processed_by").all()
 
    if search_query:
        doc_requests = doc_requests.filter(
            Q(user__firstname__icontains=search_query) |
            Q(user__lastname__icontains=search_query)  |
            Q(document_type__name__icontains=search_query) |
            Q(drid__icontains=search_query)
        )
 
    if status_filter != "All":
        doc_requests = doc_requests.filter(status=status_filter)
 
    doc_requests = doc_requests.order_by("-requested_at")
 
    records = []
    for dr in doc_requests:
        from core.utils import generate_document_id
        sla        = get_sla_for_record("DocumentRequest", dr.drid)
        records.append({
            "obj":        dr,
            "doc_id":     generate_document_id(dr.drid),
            "status":     dr.status or "Pending",
            "sla":        sla,
            "sla_status": get_sla_status_live(sla),
        })
 
    paginator   = Paginator(records, 10)
    page_obj    = paginator.get_page(request.GET.get("page"))
 
    return render(request, "adminpanel/document_requests.html", {
        "records":       page_obj,
        "page_obj":      page_obj,
        "user":          get_current_user(request),
        "search_query":  search_query,
        "status_filter": status_filter,
        "total":         doc_requests.count(),
        "pending":       doc_requests.filter(status="Pending").count(),
        "processing":    doc_requests.filter(status="Processing").count(),
        "completed":     doc_requests.filter(status="Completed").count(),
    })


# ADMIN: DOCUMENT REQUEST DETAILS
@admin_login_required
def admin_document_request_detail_view(request, drid):
    try:
        doc_request = DocumentRequests.objects.select_related(
            "user", "document_type", "processed_by"
        ).get(drid=drid)
    except DocumentRequests.DoesNotExist:
        messages.error(request, "Document request not found.")
        return redirect("admin_document_requests")
 
    current_admin = get_current_user(request)
    field_values  = DocumentRequestFieldValues.objects.filter(
        document_request=doc_request
    ).select_related("document_field")
    resident = doc_request.user
 
    if request.method == "POST":
        action = request.POST.get("action")
 
        if action == "complete":
            old_status            = doc_request.status
            doc_request.status    = "Completed"
            doc_request.processed_by = current_admin
            doc_request.processed_at = timezone.now()
            doc_request.save()
 
            # SLA — mark first response + resolve
            record_first_response("DocumentRequest", doc_request.drid)
            resolve_sla("DocumentRequest", doc_request.drid)
 
            if resident and resident.contactno:
                from core.utils import generate_document_id
                doc_id = generate_document_id(doc_request.drid)
                send_sms(
                    resident.contactno,
                    f"KaugnayPH: Your document request {doc_id} ({doc_request.document_type.name}) "
                    "has been completed. Please visit the barangay office to claim it.",
                    sent_by=current_admin,
                )
 
            AuditLogs.objects.create(
                user=current_admin, action="Complete Document Request",
                module_name="DocumentRequests", table_name="DocumentRequests",
                record_id=doc_request.drid,
                old_value=f"Status: {old_status}", new_value="Status: Completed",
                created_at=timezone.now(),
            )
            messages.success(request, "Document request marked as Completed.")
 
        elif action == "processing":
            old_status            = doc_request.status
            doc_request.status    = "Processing"
            doc_request.processed_by = current_admin
            doc_request.save()
 
            # SLA — mark first touch only (not resolved yet)
            record_first_response("DocumentRequest", doc_request.drid)
 
            AuditLogs.objects.create(
                user=current_admin, action="Set Document Request Processing",
                module_name="DocumentRequests", table_name="DocumentRequests",
                record_id=doc_request.drid,
                old_value=f"Status: {old_status}", new_value="Status: Processing",
                created_at=timezone.now(),
            )
            messages.success(request, "Document request marked as Processing.")
 
        elif action == "reject":
            old_status            = doc_request.status
            doc_request.status    = "Rejected"
            doc_request.processed_by = current_admin
            doc_request.processed_at = timezone.now()
            doc_request.save()
 
            # SLA — mark first response + resolve
            record_first_response("DocumentRequest", doc_request.drid)
            resolve_sla("DocumentRequest", doc_request.drid)
 
            AuditLogs.objects.create(
                user=current_admin, action="Reject Document Request",
                module_name="DocumentRequests", table_name="DocumentRequests",
                record_id=doc_request.drid,
                old_value=f"Status: {old_status}", new_value="Status: Rejected",
                created_at=timezone.now(),
            )
            messages.success(request, "Document request rejected.")
 
        return redirect("admin_document_request_detail", drid=doc_request.drid)
 
    from core.utils import generate_document_id
    sla = get_sla_for_record("DocumentRequest", drid)
 
    return render(request, "adminpanel/document_request_detail.html", {
        "doc_request":  doc_request,
        "doc_id":       generate_document_id(doc_request.drid),
        "field_values": field_values,
        "resident":     resident,
        "user":         current_admin,
        "sla":          sla,
        "sla_status":   get_sla_status_live(sla),
    })


#COMPLAINT UPDATES 
@admin_login_required
def case_detail_view(request, complaint_id):
    """
    Replaces the existing case_detail_view.
    Now writes to ComplaintUpdates table on every status change.
    Also handles hearing level updates and assigned official.
    """
    try:
        complaint = Complaints.objects.select_related(
            "complaint_type",
            "complainant_user",
            "handled_by"
        ).get(complaintsid=complaint_id)
    except Complaints.DoesNotExist:
        messages.error(request, "Complaint not found.")
        return redirect("case_records")

    current_admin = get_current_user(request)

    #Get/Fetch hearing levels and existing hearing record (if any)
    hearing_levels   = HearingLevel.objects.all()
    hearing_statuses = HearingStatus.objects.all()
    existing_hearing = ComplaintHearing.objects.filter(
        complaint=complaint
    ).select_related("hearing_level", "status").first()

    # Get/Fetch all update history for this complaint
    complaint_updates = ComplaintUpdates.objects.filter(
        complaint=complaint
    ).select_related("updated_by").order_by("-updated_at")

    #GetFetch assigned officials
    assigned_officials = HearingOfficials.objects.filter(
        complaint=complaint
    ).select_related("user_officials")

    #Get/Fetch all admin users for the "assign official" dropdown
    admin_users = Users.objects.filter(
        user_type__type_name="Admin",
        is_active=True
    ).select_related("position")

    if request.method == "POST":
        action = request.POST.get("action")

        #CHANGE Status
        if action in ("resolve", "review", "dismiss"):
            old_status = complaint.status
            remarks    = request.POST.get("remarks", "").strip()

            status_map = {
                "resolve": "Resolved",
                "review":  "Under Review",
                "dismiss": "Dismissed",
            }
            log_action_map = {
                "resolve": "Resolve Case",
                "review":  "Mark Case Under Review",
                "dismiss": "Dismiss Case",
            }

            new_status = status_map[action]
            log_action = log_action_map[action]

            complaint.status     = new_status
            complaint.handled_by = current_admin
            complaint.save()

            # Write to ComplaintUpdates table
            ComplaintUpdates.objects.create(
                complaint=complaint,
                updated_by=current_admin,
                status=new_status,
                remarks=remarks or None,
                updated_at=timezone.now(),
            )

            #SMS notification (PLS CHECKK AND VERIFY THE LOGIC HERE, WE DONT WANT TO SEND SMS ON EVERY UPDATE, ONLY ON STATUS CHANGE TO UNDER REVIEW, RESOLVED, OR DISMISSED)
            case_number = f"CMP-2026-{complaint.complaintsid:04d}"
            sms_map = {
                "Under Review": f"KaugnayPH: Your complaint {case_number} is now Under Review.",
                "Resolved":     f"KaugnayPH: Your complaint {case_number} has been resolved.",
                "Dismissed":    (
                    f"KaugnayPH: Your complaint {case_number} has been dismissed. "
                    "Please contact the barangay office for more information."
                ),
            }
            sms_body = sms_map.get(new_status)
            if sms_body and complaint.complainant_user and complaint.complainant_user.contactno:
                send_sms(
                    complaint.complainant_user.contactno,
                    sms_body,
                    sent_by=current_admin,
                )

            AuditLogs.objects.create(
                user=current_admin,
                action=log_action,
                module_name="Cases",
                table_name="Complaints",
                record_id=complaint.complaintsid,
                old_value=f"Status: {old_status}",
                new_value=f"Status: {new_status}",
                created_at=timezone.now(),
            )

            messages.success(request, "Case status updated successfully.")

        #Hearing Level Update
        elif action == "update_hearing":
            hearing_level_id = request.POST.get("hearing_level_id", "").strip()
            hearing_date     = request.POST.get("hearing_date", "").strip()
            hearing_status_id = request.POST.get("hearing_status_id", "").strip()

            if not hearing_level_id:
                messages.error(request, "Please select a hearing level.")
                return redirect("case_detail", complaint_id=complaint.complaintsid)

            try:
                hearing_level = HearingLevel.objects.get(hearinglevelid=hearing_level_id)
            except HearingLevel.DoesNotExist:
                messages.error(request, "Invalid hearing level.")
                return redirect("case_detail", complaint_id=complaint.complaintsid)

            try:
                hearing_status = HearingStatus.objects.get(statusid=hearing_status_id)
            except HearingStatus.DoesNotExist:
                messages.error(request, "Invalid hearing status.")
                return redirect("case_detail", complaint_id=complaint.complaintsid)

            if existing_hearing:
                # Update existing record
                existing_hearing.hearing_level = hearing_level
                existing_hearing.status        = hearing_status
                if hearing_date:
                    existing_hearing.hearing_date = hearing_date
                existing_hearing.save()
            else:
                # Create new hearing record
                ComplaintHearing.objects.create(
                    complaint=complaint,
                    hearing_level=hearing_level,
                    hearing_date=hearing_date or timezone.now(),
                    status=hearing_status,
                    created_at=timezone.now(),
                )

            AuditLogs.objects.create(
                user=current_admin,
                action="Update Hearing Level",
                module_name="Cases",
                table_name="ComplaintHearing",
                record_id=complaint.complaintsid,
                new_value=f"Hearing level set to '{hearing_level.level_type}'.",
                created_at=timezone.now(),
            )

            messages.success(request, "Hearing level updated.")

        #ASSIGN OFFICIAL
        elif action == "assign_official":
            official_user_id = request.POST.get("official_user_id", "").strip()
            official_role    = request.POST.get("official_role", "Mediator").strip()

            if not official_user_id:
                messages.error(request, "Please select an official to assign.")
                return redirect("case_detail", complaint_id=complaint.complaintsid)

            try:
                official_user = Users.objects.get(userid=official_user_id)
            except Users.DoesNotExist:
                messages.error(request, "Selected official not found.")
                return redirect("case_detail", complaint_id=complaint.complaintsid)

            # Prevent duplicate assignment
            already_assigned = HearingOfficials.objects.filter(
                complaint=complaint,
                user_officials=official_user
            ).exists()

            if already_assigned:
                messages.warning(request, "This official is already assigned to this case.")
            else:
                HearingOfficials.objects.create(
                    complaint=complaint,
                    user_officials=official_user,
                    role=official_role,
                )
                AuditLogs.objects.create(
                    user=current_admin,
                    action="Assign Official",
                    module_name="Cases",
                    table_name="HearingOfficials",
                    record_id=complaint.complaintsid,
                    new_value=f"Official '{official_user.firstname} {official_user.lastname}' assigned.",
                    created_at=timezone.now(),
                )
                messages.success(request, "Official assigned successfully.")

        # ---- REMOVE OFFICIAL ----
        elif action == "remove_official":
            hoid = request.POST.get("hoid", "").strip()
            try:
                ho = HearingOfficials.objects.get(hoid=hoid, complaint=complaint)
                ho.delete()
                messages.success(request, "Official removed.")
            except HearingOfficials.DoesNotExist:
                messages.error(request, "Official record not found.")

        else:
            messages.error(request, "Invalid action.")

        return redirect("case_detail", complaint_id=complaint.complaintsid)

    return render(request, "adminpanel/case_detail.html", {
        "complaint":          complaint,
        "user":               current_admin,
        "case_id":            f"CMP-2026-{complaint.complaintsid:04d}",
        "complaint_updates":  complaint_updates,
        "hearing_levels":     hearing_levels,
        "hearing_statuses":   hearing_statuses,
        "existing_hearing":   existing_hearing,
        "assigned_officials": assigned_officials,
        "admin_users":        admin_users,
    })

#admin inquiry view
@admin_login_required
def admin_inquiries_view(request):
    from django.core.paginator import Paginator
 
    search_query  = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "All").strip()
 
    inquiries = Inquiry.objects.all()
 
    if search_query:
        inquiries = inquiries.filter(
            Q(firstname__icontains=search_query) |
            Q(lastname__icontains=search_query)  |
            Q(messagesubject__icontains=search_query) |
            Q(contactno__icontains=search_query)
        )
 
    if status_filter != "All":
        inquiries = inquiries.filter(status=status_filter)
 
    inquiries = inquiries.order_by("-created_at")
 
    records = []
    for inq in inquiries:
        sla = get_sla_for_record("Inquiry", inq.cuid)
        records.append({
            "obj":        inq,
            "sla":        sla,
            "sla_status": get_sla_status_live(sla),
        })
 
    paginator = Paginator(records, 10)
    page_obj  = paginator.get_page(request.GET.get("page"))
 
    return render(request, "adminpanel/inquiries_list.html", {
        "records":       page_obj,
        "page_obj":      page_obj,
        "user":          get_current_user(request),
        "search_query":  search_query,
        "status_filter": status_filter,
        "total":         inquiries.count(),
        "new_count":     Inquiry.objects.filter(status="New").count(),
        "pending_count": Inquiry.objects.filter(status="Pending").count(),
        "replied_count": Inquiry.objects.filter(status="Replied").count(),
    })

#admin inquiry detail
@admin_login_required
def admin_inquiry_detail_view(request, cuid):
    try:
        inquiry = Inquiry.objects.select_related("user", "replied_byuser").get(cuid=cuid)
    except Inquiry.DoesNotExist:
        messages.error(request, "Inquiry not found.")
        return redirect("admin_inquiries")
 
    current_admin = get_current_user(request)
    sla           = get_sla_for_record("Inquiry", cuid)

    if request.method == "GET" and inquiry.status == "New":
        inquiry.status = "Pending"
        inquiry.save()
 
    if request.method == "POST":
        action      = request.POST.get("action")
        admin_reply = request.POST.get("admin_reply", "").strip()
 
        if action == "reply":
            if not admin_reply:
                messages.error(request, "Reply cannot be empty.")
                return redirect("admin_inquiry_detail", cuid=inquiry.cuid)
 
            inquiry.admin_reply    = admin_reply
            inquiry.replied_at     = timezone.now()
            inquiry.replied_byuser = current_admin
            inquiry.status         = "Replied"
            inquiry.save()
 
            # SLA — mark first response + resolve
            record_first_response("Inquiry", inquiry.cuid)
            resolve_sla("Inquiry", inquiry.cuid)
 
            # Notify resident via SMS
            sms_reply = f"KaugnayPH Reply: {admin_reply}"

            send_sms(
                inquiry.contactno,
                sms_reply,
                sent_by=current_admin,
            )
            
            AuditLogs.objects.create(
                user=current_admin, action="Reply to Inquiry",
                module_name="Inquiry", table_name="Inquiry",
                record_id=inquiry.cuid,
                new_value=f"Replied by {current_admin.username}.",
                created_at=timezone.now(),
            )
 
            messages.success(request, "Reply sent successfully.")
 
        elif action == "close":
            inquiry.status = "Closed"
            inquiry.save()
            resolve_sla("Inquiry", inquiry.cuid)
            messages.success(request, "Inquiry closed.")
 
        elif action == "pending":
            inquiry.status = "Pending"
            inquiry.save()
            messages.success(request, "Inquiry marked as Pending.")
 
        return redirect("admin_inquiry_detail", cuid=inquiry.cuid)
 
    return render(request, "adminpanel/inquiry_detail.html", {
        "inquiry":    inquiry,
        "sla":        sla,
        "sla_status": get_sla_status_live(sla),
        "user":       current_admin,
    })