import json
import random
import string as _string
import requests
import os
import re
 
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.hashers import check_password
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from datetime import datetime
from datetime import datetime, time
from datetime import datetime, time, timedelta
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db.models import Q, Value
from django.db.models.functions import Concat
from zoneinfo import ZoneInfo

from .forms import CaptchaOnlyForm
from core.complaint_workflow import apply_status_change, build_sms_for_status, _complaint_contact_numbers
from .models import AvatarOptions, HearingAttendance, CertificateToFileAction
from core.utils import (
    validate_upload,
    generate_case_number,
    generate_certificate_number,
    format_full_name,
    mask_contact,
    mask_email,
)
from datetime import date, datetime, timedelta
import uuid
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
    FAQs,
    FAQCategories,
    AvatarOptions, 
)

from django.utils.dateparse import parse_datetime 
from django.utils.dateparse import parse_date
from django.urls import reverse
from urllib.parse import urlencode

from .auth_utils import (
    hash_password, check_password, generate_otp,
    verify_otp, send_sms, send_email_otp,
    set_user_session, get_current_user,
    has_permission, queue_sms
)
 
from .decorators import (
    login_required,
    admin_login_required,
    resident_required,
    permission_required,
    chairman_required,
)

from django.shortcuts import render, get_object_or_404
from datetime import timedelta
from django.utils import timezone
from django.core.paginator import Paginator

from .utils import format_full_name, mask_contact, mask_email

from django.db.models import Sum, Avg, Count, F, ExpressionWrapper, fields, Max


# PUBLIC PAGES

def landing_page(request):
    announcements = Announcements.objects.select_related(
        "category",
        "posted_by"
    ).order_by("-created_at")[:4]

    return render(request, "public/landing.html", {
        "announcements": announcements
    })



def announcement_detail(request, announcement_id):
    announcement = get_object_or_404(
        Announcements,
        announcement_id=announcement_id
    )
    viewed_announcements = request.session.get(
        "viewed_announcements",
        []
    )

    if announcement_id not in viewed_announcements:
        announcement.view_count += 1
        announcement.save()
        viewed_announcements.append(announcement_id)
        request.session["viewed_announcements"] = viewed_announcements

    return render(
        request,
        'public/announcement_detail.html',
        {
            'announcement': announcement,
            'is_resident': request.session.get('user_type') == 'Resident',
        }
    )


@login_required
@resident_required
def filecomplaint(request):


    incident_date = None
    current_user = get_current_user(request)

    today = date.today()
    min_incident_date = today
    max_incident_date = today

    def complaint_context(captcha_form=None, form_data=None):
        initial_data = {
            "firstname": current_user.firstname,
            "lastname": current_user.lastname,
            "contactno": current_user.contactno,
        } if current_user else {}

        return {
            "initial_data": initial_data,
            "captcha_form": captcha_form or CaptchaOnlyForm(),
            "min_incident_date": min_incident_date,
            "max_incident_date": max_incident_date,
            "form_data": form_data or {},
        }

    if request.method == "POST":
        captcha_form = CaptchaOnlyForm(request.POST)

        if not captcha_form.is_valid():
            return render(
                request,
                "filecomplaint.html",
                complaint_context(captcha_form, request.POST)
            )

        incident_date_raw    = request.POST.get("incident_date", "").strip()
        complainee          = request.POST.get("complainee", "").strip()
        complainee_address  = request.POST.get("complainee_address", "").strip()
        jurisdiction_barangay = request.POST.get("jurisdiction_barangay", "").strip()
        title               = request.POST.get("title", "").strip()
        description         = request.POST.get("description", "").strip()
        evidence             = request.FILES.get("evidence")

        if not complainee:
            messages.error(request, "Name of complainee is required.")
            return render(request, "filecomplaint.html", complaint_context())

        if not title:
            messages.error(request, "Title is required.")
            return render(request, "filecomplaint.html", complaint_context())

        if not description:
            messages.error(request, "Description is required.")
            return render(request, "filecomplaint.html", complaint_context())

        incident_date = None
        if incident_date_raw:
            try:
                incident_date = datetime.fromisoformat(incident_date_raw)
            except ValueError:
                messages.error(request, "Invalid incident date format.")
                return render(request, "filecomplaint.html", complaint_context())

            if incident_date.date() > max_incident_date:
                messages.error(request, "Incident date cannot be in the future.")
                return render(request, "filecomplaint.html", complaint_context())

            if incident_date.date() != today:
                messages.error(
                    request,
                    "Incident date must be today's date. "
                    "For older incidents, please visit the barangay office directly."
                )
                return render(request, "filecomplaint.html", complaint_context())

        # FILE VALIDATION & SAVE
        file_path = None
        if evidence:
            ok, err = validate_upload(evidence)
            if not ok:
                messages.error(request, err)
                return render(request, "filecomplaint.html", complaint_context())

            filename = f"complaints/{uuid.uuid4()}_{evidence.name}"

            file_path = default_storage.save(
                filename,
                ContentFile(evidence.read())
            )

        # CONTENT MODERATION
        text_check = moderate_text(f"{title} {description} {complainee}")

        image_check = {"flagged": False, "reason": None}
        if evidence and evidence.content_type.startswith("image/"):
            evidence.seek(0)
            image_check = moderate_image(evidence)

        is_flagged  = text_check["flagged"] or image_check["flagged"]
        flag_reason = text_check["reason"] or image_check["reason"]

        complaint = Complaints.objects.create(
            complaint_type=None,
            complainant_user=current_user,
            complainee=complainee,
            complainee_address=complainee_address,
            jurisdiction_barangay=jurisdiction_barangay or None,
            title=title,
            description=description,
            incident_date=incident_date,
            file_path=file_path,
            status="For Chairman Review",
            is_flagged=is_flagged,
            flagged_reason=flag_reason,
        )

        complaint.case_number = generate_case_number(
            complaint.complaintsid
        )
        complaint.save(update_fields=["case_number"])

        ComplaintUpdates.objects.create(
            complaint=complaint,
            updated_by=current_user,
            status="For Chairman Review",
            remarks="Complaint submitted and forwarded for Chairman review." if not is_flagged
                    else f"Complaint submitted by resident. Flagged for review: {flag_reason}",
            updated_at=timezone.now(),
        )

        AuditLogs.objects.create(
            user=current_user,
            action="Submit Complaint",
            module_name="Cases",
            table_name="Complaints",
            record_id=complaint.complaintsid,
            new_value=f"Complaint '{complaint.title}' submitted.",
            created_at=timezone.now(),
        )

        sms_body = (
            f"KaugnayPH: Your complaint {complaint.case_number} "
            "has been submitted successfully. "
            "Please wait for updates from Barangay 761."
        )

        if current_user.contactno:
            queue_sms(
                current_user.contactno,
                sms_body,
                sent_by=current_user
            )

        if is_flagged:
            messages.warning(
                request,
                "Your complaint was submitted and is pending admin review due to "
                "flagged content. You can track its status through Track Submissions."
            )
        else:
            messages.success(
                request,
                "Complaint submitted successfully. You can track its status through Track Submissions."
            )

        return redirect("tracksub")

    return render(request, "filecomplaint.html", complaint_context())


def aboutus(request):
    return render(request, 'aboutus.html')

def privacypolicy(request):
    return render(request, 'privacypolicy.html')

def documents(request):
    document_types = DocumentTypes.objects.filter(is_active=True)
    current_user = get_current_user(request)

    return render(request, 'documents.html', {
        "document_types": document_types,
        "resident": current_user,
        "captcha_form": CaptchaOnlyForm(),
    })

def faqs(request):
    faqs = FAQs.objects.filter(is_active=True)

    return render(
        request,
        'faqs.html',
        {
            'faqs': faqs
        }
    )

def admin_faqs(request):
    faqs = FAQs.objects.select_related('faq_category').order_by('-created_at')

    return render(request, 'adminpanel/admin_faqs.html', {
    'faqs': faqs
})

#submit inquiry
def contactus(request):
    current_user = get_current_user(request)
    
    initial_data = {}
    if current_user:
        initial_data = {
            "firstname": current_user.firstname,
            "lastname": current_user.lastname,
            "contactno": current_user.contactno,
        }

    def contact_context(captcha_form=None, form_data=None):
        return {
            "initial_data": initial_data,
            "captcha_form": captcha_form or CaptchaOnlyForm(),
            "form_data": form_data or {},
        }

    if request.method == "POST":
        captcha_form = CaptchaOnlyForm(request.POST)

        if not captcha_form.is_valid():
            return render(
                request,
                "contactus.html",
                contact_context(captcha_form, request.POST)
            )

        firstname = request.POST.get("firstname", "").strip()
        lastname  = request.POST.get("lastname", "").strip()
        contactno = request.POST.get("contactno", "").strip()
        address   = request.POST.get("address", "").strip()
        subject   = request.POST.get("messagesubject", "").strip()
        message   = request.POST.get("message", "").strip()
 
        if not firstname or not lastname or not contactno or not message:
            messages.error(request, "Please fill in all required fields.")
            return render(
                request,
                "contactus.html",
                contact_context(form_data=request.POST)
            )
 
        # CONTENT MODERATION — check before saving
        check = moderate_text(f"{subject} {message}")
        if check["flagged"]:
            messages.error(
                request,
                "Your message contains inappropriate content and could not be submitted. "
                "Please revise and try again."
            )
            return render(
                request,
                "contactus.html",
                contact_context(form_data=request.POST)
            )
 
        # SAVE
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

        AuditLogs.objects.create(
            user=current_user,
            action="Submit Inquiry",
            module_name="Inquiry",
            table_name="Inquiry",
            record_id=inquiry.cuid,
            new_value=f"Inquiry '{subject}' submitted.",
            created_at=timezone.now(),
        )

        messages.success(
            request,
            "Your inquiry has been submitted. We will get back to you within 24 hours."
        )
        return redirect("contactus")
 
    return render(request, "contactus.html", contact_context())

#view announcements public
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
    sms_failed = 0
    sms_sent = 0

    if send_sms_flag == 1:
        for sub in SMSSubscriptions.objects.select_related("user").filter(is_active=True):
            if sub.user and sub.user.contactno:
                sms_success = queue_sms(
                    sub.user.contactno,
                    f"KaugnayPH: {announcement.title}",
                    sent_by=current_user
                )

                if sms_success:
                    sms_sent += 1
                else:
                    sms_failed += 1
    AuditLogs.objects.create(
        user=current_user, action="Create Announcement",
        module_name="Announcements", table_name="Announcements",
        record_id=announcement.announcement_id,
        new_value=f"'{title}' created.", created_at=timezone.now()
    )
    return JsonResponse({
        "message": "Created",
        "announcement_id": announcement.announcement_id,
        "sms_sent": sms_sent,
        "sms_failed": sms_failed,
    })

#UPDATE ANNOUNCEMENT
@csrf_exempt
def update_announcement(request, announcement_id):
    if request.method != "PUT":
        return JsonResponse({"error": "PUT required"}, status=400)

    data = json.loads(request.body)
    current_user = get_current_user(request)

    try:
        a = Announcements.objects.get(announcement_id=announcement_id)
    except Announcements.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)

    old_value = f"Title: {a.title}; Category: {a.category_id}; Send SMS: {a.send_sms}"

    a.title       = data.get("title",       a.title)
    a.content     = data.get("content",     a.content)
    a.send_sms    = data.get("send_sms",    a.send_sms)
    a.category_id = data.get("category_id", a.category_id)
    a.save()

    new_value = f"Title: {a.title}; Category: {a.category_id}; Send SMS: {a.send_sms}"

    AuditLogs.objects.create(
        user=current_user,
        action="Update Announcement",
        module_name="Announcements",
        table_name="Announcements",
        record_id=a.announcement_id,
        old_value=old_value,
        new_value=new_value,
        created_at=timezone.now(),
    )

    return JsonResponse({"message": "Updated"})

#DELETE ANNOUNCEMENT
@csrf_exempt
def delete_announcement(request, announcement_id):
    if request.method != "DELETE":
        return JsonResponse({"error": "DELETE required"}, status=400)

    current_user = get_current_user(request)

    try:
        a = Announcements.objects.get(announcement_id=announcement_id)
    except Announcements.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)

    old_title = a.title
    a.delete()

    AuditLogs.objects.create(
        user=current_user,
        action="Delete Announcement",
        module_name="Announcements",
        table_name="Announcements",
        record_id=announcement_id,
        old_value=f"Announcement '{old_title}' deleted.",
        created_at=timezone.now(),
    )

    return JsonResponse({"message": "Deleted"})

#incoming sms api / remote sms posting
@csrf_exempt
def incoming_sms_webhook(request):
    if request.content_type == "application/json":
        try:
            data = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            data = {}
    else:
        data = request.POST if request.method == "POST" else request.GET

    phone = (
        data.get("phone")
        or data.get("mobile")
        or data.get("sender")
        or data.get("number")
        or ""
    ).strip()

    message = (
        data.get("message")
        or data.get("Memo")
        or data.get("content")
        or ""
    ).strip()

    port = (
        data.get("port")
        or data.get("name")
        or ""
    ).strip()

    received_at = data.get("received_at")

    if phone.startswith("+63"):
        phone = "0" + phone[3:]

    if not phone or not message:
        return JsonResponse({
            "status": "error",
            "message": "phone and message are required"
        }, status=400)

    authorized_admin = Users.objects.filter(
        contactno=phone,
        is_active=True,
        role__rolename__in=["Barangay Chairman", "Barangay Secretary"]
    ).first()

    if not authorized_admin:
        return JsonResponse({
            "status": "error",
            "message": "Unauthorized sender"
        }, status=403)

    if not message.startswith("#ANNOUNCE#"):
        return JsonResponse({
            "status": "error",
            "message": "Invalid command. Use #ANNOUNCE#Category#Message"
        }, status=400)

    parts = message.split("#", 3)

    if len(parts) < 4:
        return JsonResponse({
            "status": "error",
            "message": "Invalid format. Use #ANNOUNCE#Category#Message"
        }, status=400)

    category_name = parts[2].strip()
    announcement_content = parts[3].strip()

    if not category_name or not announcement_content:
        return JsonResponse({
            "status": "error",
            "message": "Category and message are required"
        }, status=400)

    category = AnnouncementCategories.objects.filter(
        name__iexact=category_name
    ).first()

    if not category:
        return JsonResponse({
            "status": "error",
            "message": f"Announcement category '{category_name}' not found"
        }, status=400)

    title = f"{category.name} Announcement"

    text_check = moderate_text(f"{title} {announcement_content}")
    if text_check["flagged"]:
        return JsonResponse({
            "status": "error",
            "message": f"Announcement content was flagged for: {text_check['reason']}"
        }, status=400)

    announcement = Announcements.objects.create(
        title=title,
        content=announcement_content,
        file_path=None,
        send_sms=True,
        category=category,
        posted_by=authorized_admin,
        created_at=timezone.now()
    )

    sent_count = 0
    failed_count = 0

    for sub in SMSSubscriptions.objects.select_related("user").filter(is_active=True):
        if sub.user and sub.user.contactno:
            sms_success = queue_sms(
                sub.user.contactno,
                f"KaugnayPH: {announcement.title}\n{announcement.content}",
                sent_by=authorized_admin
            )

            if sms_success:
                sent_count += 1
            else:
                failed_count += 1

    AuditLogs.objects.create(
        user=authorized_admin,
        action="Remote SMS Announcement",
        module_name="Announcements",
        table_name="Announcements",
        record_id=announcement.announcement_id,
        old_value="",
        new_value=(
            f"Remote SMS via GOIP port {port or 'N/A'}; "
            f"Phone: {phone}; "
            f"Message: {message}; "
            f"Received At: {received_at or 'N/A'}"
        ),
        ip_address=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        created_at=timezone.now()
    )

    return JsonResponse({
        "status": "success",
        "message": "Remote SMS announcement created",
        "announcement_id": announcement.announcement_id,
        "sms_sent": sent_count,
        "sms_failed": failed_count
    })

#CREATE SMS LOG
@admin_login_required
@permission_required("send_sms")
def create_sms_log(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)
    data = json.loads(request.body)
    queue_sms(data.get("recipient_number"), data.get("message"))
    return JsonResponse({"message": "SMS logged"})

# GET SMS LOG
@admin_login_required
@permission_required("view_sms_outbox")
def get_sms_logs(request):
    return JsonResponse(
        list(SMSOutbox.objects.all().values()),
        safe=False
    )


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
        messages.error(
            request,
            f"Please wait {mins}m {secs}s before requesting a new OTP."
        )
        return render(request, template, context or {})

    send_sms(
        user.contactno,
        f"KaugnayPH OTP: {otp.code}. Valid for 5 minutes. Do not share this OTP with anyone."
    )

    return None

def _send_admin_login_otp(request, user, otp):
    try:
        send_sms(
            user.contactno,
            f"KaugnayPH OTP: {otp.code}. Valid for 5 minutes. Do not share this OTP with anyone."
        )
        request.session["otp_method"] = "sms"
    except Exception:
        send_email_otp(user.email, otp.code)
        request.session["otp_method"] = "email"

def get_role_for_position(position):
    if not position:
        return None

    mapping = {
        "Barangay Chairman": "Barangay Chairman",
        "Kagawad": "Barangay Kagawad",
        "Barangay Secretary": "Barangay Secretary",
        "Barangay Treasurer": "Barangay Treasurer",
        "Barangay Tanod": "Barangay Tanod",
        "Lupon Tagapamayapa": "Lupong Tagapamayapa",
        "SK Chairman": "SK Chairman",
    }

    role_name = mapping.get(position.name)

    if not role_name:
        return None

    try:
        return Roles.objects.get(rolename=role_name)
    except Roles.DoesNotExist:
        return None

def send_sms_with_warning(request, contact_number, message, sent_by=None):
    queue_sms(
        contact_number,
        message,
        sent_by=sent_by
    )

    messages.info(
        request,
        "The action was completed, and the SMS notification has been queued for sending."
    )

    return True

def mask_sms_message(message):
    if not message:
        return message

    return re.sub(
        r'(?i)(OTP:\s*)\d{6}',
        r'\1******',
        message
    )


# SHARED RESIDENT AND PERSONNEL LOGIN
def login_view(request):
    if request.session.get("user_id"):
        if request.session.get("user_type") == "Admin":
            return redirect("admin_dashboard")
        return redirect("landing")

    if request.method != "POST":
        return render(request, "auth/login.html")

    identifier = (
        request.POST.get("identifier")
        or request.POST.get("contact_no")
        or ""
    ).strip()

    password = request.POST.get("password", "").strip()

    if not identifier or not password:
        messages.error(request, "Please enter your username or mobile number and password.")
        return render(request, "auth/login.html")

    # Residents log in using their mobile number.
    user = Users.objects.select_related(
        "user_type", "role", "position"
    ).filter(
        contactno=identifier,
        user_type__type_name="Resident",
        is_active=True,
    ).first()

    # Barangay personnel log in using their username.
    if user is None:
        user = Users.objects.select_related(
            "user_type", "role", "position"
        ).filter(
            username=identifier,
            user_type__type_name="Admin",
            is_active=True,
        ).first()

    if user is None or not check_password(password, user.password):
        messages.error(request, "Invalid credentials.")
        return render(request, "auth/login.html")

    # RESIDENT LOGIN FLOW
    if user.user_type.type_name == "Resident":
        if not user.is_verified:
            rv = ResidentVerification.objects.filter(user=user).first()

            if rv and rv.status == "Rejected":
                messages.error(
                    request,
                    "Your registration was rejected. Please contact the barangay office."
                )
            else:
                messages.warning(
                    request,
                    "Your account is pending verification. You will be notified via SMS."
                )

            return render(request, "auth/login.html")

        set_user_session(request, user)

        AuditLogs.objects.create(
            user=user,
            action="Resident Login",
            module_name="Authentication",
            table_name="Users",
            record_id=user.userid,
            new_value=f"Resident '{user.username}' logged in.",
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
            created_at=timezone.now(),
        )

        return redirect("landing")

    # BARANGAY PERSONNEL LOGIN FLOW

    # Clear stale authentication-flow values from previous attempts.
    request.session.pop("from_forgot_password", None)
    request.session.pop("forgot_password_verified", None)
    request.session.pop("forgot_password_user_type", None)
    request.session.pop("from_first_login", None)
    request.session.pop("pending_first_login_data", None)
    request.session.pop("otp_method", None)

    request.session["pending_user_id"] = user.userid

    if user.is_first_login:
        return redirect("admin_first_login")

    otp, cooldown = generate_otp(user, purpose="login")

    if cooldown:
        mins = cooldown // 60
        secs = cooldown % 60

        messages.error(
            request,
            f"Please wait {mins}m {secs}s before requesting another OTP."
        )

        return render(request, "auth/login.html")

    sms_sent = send_sms(
        user.contactno,
        (
            f"KaugnayPH OTP: {otp.code}. Valid for 5 minutes. "
            "Do not share this OTP with anyone."
        )
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

# SHARED RESIDENT AND PERSONNEL FORGOT PASSWORD
def forgot_password_view(request):
    if request.method != "POST":
        return render(request, "auth/forgot_password.html")

    identifier = request.POST.get("identifier", "").strip()

    if not identifier:
        messages.error(
            request,
            "Please enter your username or registered mobile number."
        )
        return render(request, "auth/forgot_password.html")

    # Residents use their registered mobile number.
    user = Users.objects.select_related(
        "user_type", "role", "position"
    ).filter(
        contactno=identifier,
        user_type__type_name="Resident",
        is_active=True,
    ).first()

    account_type = "resident"

    # Barangay personnel use their username.
    if user is None:
        user = Users.objects.select_related(
            "user_type", "role", "position"
        ).filter(
            username=identifier,
            user_type__type_name="Admin",
            is_active=True,
        ).first()

        account_type = "admin"

    if user is None:
        messages.error(
            request,
            "No active account was found with that username or mobile number."
        )
        return render(request, "auth/forgot_password.html")

    if not user.email:
        messages.error(
            request,
            "No email address is registered for this account."
        )
        return render(request, "auth/forgot_password.html")

    # Clear any stale authentication-flow session values.
    request.session.pop("forgot_password_verified", None)
    request.session.pop("from_first_login", None)
    request.session.pop("pending_first_login_data", None)

    request.session["pending_user_id"] = user.userid
    request.session["from_forgot_password"] = True
    request.session["forgot_password_user_type"] = account_type

    otp, cooldown = generate_otp(
        user,
        purpose="forgot_password"
    )

    if cooldown:
        mins = cooldown // 60
        secs = cooldown % 60

        messages.error(
            request,
            f"Please wait {mins}m {secs}s before requesting another OTP."
        )
        return render(request, "auth/forgot_password.html")

    send_email_otp(user.email, otp.code)
    request.session["otp_method"] = "email"

    messages.success(
        request,
        "OTP has been sent to your registered email address."
    )

    return redirect("otp_verify")

# RESIDENT RESET PASSWORD
def reset_password_view(request):
    pending_id = request.session.get("pending_user_id")

    if not pending_id or not request.session.get("forgot_password_verified"):
        messages.error(request, "Please verify your OTP first.")
        return redirect("forgot_password")

    try:
        user = Users.objects.get(userid=pending_id, is_active=True)
    except Users.DoesNotExist:
        messages.error(request, "Account not found.")
        return redirect("forgot_password")

    if user.user_type.type_name != "Resident":
        messages.error(request, "Invalid account type.")
        return redirect("forgot_password")

    if request.method != "POST":
        return render(request, "auth/reset_password.html")

    new_password = request.POST.get("new_password", "").strip()
    confirm_password = request.POST.get("confirm_password", "").strip()

    if not new_password or not confirm_password:
        messages.error(request, "Please complete all password fields.")
        return render(request, "auth/reset_password.html")

    if len(new_password) < 8:
        messages.error(request, "Password must be at least 8 characters long.")
        return render(request, "auth/reset_password.html")

    if new_password != confirm_password:
        messages.error(request, "New password and confirm password do not match.")
        return render(request, "auth/reset_password.html")

    if check_password(new_password, user.password):
        messages.error(request, "Your new password must be different from your current password.")
        return render(request, "auth/reset_password.html")

    user.password = hash_password(new_password)
    user.is_password_changed = True
    user.save()

    AuditLogs.objects.create(
        user=user,
        action="Changed Password",
        module_name="Authentication",
        table_name="Users",
        record_id=user.userid,
        old_value="Password reset",
        new_value="Password updated",
        ip_address=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT"),
        created_at=timezone.now(),
    )

    request.session.pop("pending_user_id", None)
    request.session.pop("from_forgot_password", None)
    request.session.pop("forgot_password_verified", None)
    request.session.pop("forgot_password_user_type", None)
    request.session.pop("otp_method", None)

    messages.success(request, "Password reset successful. Please log in.")
    return redirect("login")


# OLD PERSONNEL LOGIN URL
def admin_login_view(request):
    return redirect("login")

#ADMIN FORGOT PASSWORD
def admin_forgot_password_view(request):
    if request.method != "POST":
        return render(request, "auth/admin_forgot_password.html")

    username = request.POST.get("username", "").strip()

    try:
        user = Users.objects.select_related(
            "user_type", "role", "position"
        ).get(username=username, is_active=True)
    except Users.DoesNotExist:
        messages.error(request, "No active admin account found with that username.")
        return render(request, "auth/admin_forgot_password.html")

    if user.user_type.type_name != "Admin":
        messages.error(request, "No active admin account found with that username.")
        return render(request, "auth/admin_forgot_password.html")

    if not user.email:
        messages.error(request, "No email address is registered for this account.")
        return render(request, "auth/admin_forgot_password.html")

    request.session["pending_user_id"] = user.userid
    request.session["from_forgot_password"] = True

    otp, cooldown = generate_otp(user, purpose="forgot_password")

    if cooldown:
        mins = cooldown // 60
        secs = cooldown % 60
        messages.error(request, f"Please wait {mins}m {secs}s before requesting another OTP.")
        return render(request, "auth/admin_forgot_password.html")

    send_email_otp(user.email, otp.code)
    request.session["otp_method"] = "email"

    messages.success(request, "OTP has been sent to your registered email address.")
    return redirect("otp_verify")


#ADMIN RESET PASSWORD
def admin_reset_password_view(request):
    pending_id = request.session.get("pending_user_id")

    if not pending_id or not request.session.get("forgot_password_verified"):
        messages.error(request, "Please verify your OTP first.")
        return redirect("admin_forgot_password")

    try:
        user = Users.objects.get(userid=pending_id, is_active=True)
    except Users.DoesNotExist:
        messages.error(request, "Account not found.")
        return redirect("admin_forgot_password")

    if request.method != "POST":
        return render(request, "auth/admin_reset_password.html")

    new_password = request.POST.get("new_password", "").strip()
    confirm_password = request.POST.get("confirm_password", "").strip()

    if len(new_password) < 8:
        messages.error(request, "Password must be at least 8 characters.")
        return render(request, "auth/admin_reset_password.html")

    if new_password != confirm_password:
        messages.error(request, "Passwords do not match.")
        return render(request, "auth/admin_reset_password.html")

    user.password = hash_password(new_password)
    user.is_password_changed = True
    user.save()

    AuditLogs.objects.create(
        user=user,
        action="Changed Password",
        module_name="Authentication",
        table_name="Users",
        record_id=user.userid,
        old_value="Password reset via forgot-password flow",
        new_value="Password updated",
        ip_address=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT"),
        created_at=timezone.now(),
    )
    
    request.session.pop("forgot_password_user_type", None)
    request.session.pop("pending_user_id", None)
    request.session.pop("from_forgot_password", None)
    request.session.pop("forgot_password_verified", None)
    request.session.pop("otp_method", None)

    messages.success(request, "Password reset successful. Please log in.")
    return redirect("admin_login")


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
        f"KaugnayPH OTP: {otp.code}. Valid for 5 minutes. Do not share this OTP with anyone."
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

    if request.session.get("from_first_login"):
        purpose = "first_login"
    elif request.session.get("from_forgot_password"):
        purpose = "forgot_password"
    else:
        purpose = "login"

    result = verify_otp(user, code, purpose=purpose)

    if result == 'ok':

        # FORGOT PASSWORD FLOW
        if request.session.get("from_forgot_password"):
            request.session["forgot_password_verified"] = True
            messages.success(request, "OTP verified. Please set your new password.")

            if request.session.get("forgot_password_user_type") == "resident":
                return redirect("reset_password")

            return redirect("admin_reset_password")

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

        AuditLogs.objects.create(
            user=fresh_user,
            action="Admin Login",
            module_name="Authentication",
            table_name="Users",
            record_id=fresh_user.userid,
            new_value=f"Admin '{fresh_user.username}' logged in.",
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
            created_at=timezone.now(),
        )

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

    if request.session.get("from_first_login"):
        purpose = "first_login"
    elif request.session.get("from_forgot_password"):
        purpose = "forgot_password"
    else:
        purpose = "login"
    otp, cooldown = generate_otp(user, purpose=purpose)

    if cooldown:
        mins = cooldown // 60
        secs = cooldown % 60

        messages.error(
            request,
            f"Please wait {mins}m {secs}s before requesting a new OTP."
        )

        return render(request, "auth/otp_verify.html")

    otp_method = request.session.get("otp_method", "sms")

    if otp_method == "email":
        send_email_otp(user.email, otp.code)
        request.session["otp_method"] = "email"
    else:
        sms_sent = send_sms(
            user.contactno,
            f"KaugnayPH OTP: {otp.code}. Valid for 5 minutes. Do not share this OTP with anyone."
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

    if request.session.get("from_first_login"):
        purpose = "first_login"
    elif request.session.get("from_forgot_password"):
        purpose = "forgot_password"
    else:
        purpose = "login"

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

    MAX_UPLOAD_SIZE_MB = 10
    MAX_UPLOAD_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024

    for label, f in [("ID Photo", files['id_image']), ("Selfie", files['selfie'])]:
        if not f:
            errors.append(f"Please upload a {label}.")
        else:
            ok, err = validate_upload(f)

            if not ok:
                errors.append(f"{label}: {err}")
            elif f.content_type not in allowed_types:
                errors.append(f"{label} must be JPG or PNG.")
            elif f.size > MAX_UPLOAD_SIZE:
                errors.append(f"{label} must be less than {MAX_UPLOAD_SIZE_MB}MB or below.")

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
        'address': request.POST.get("address", "").strip(),
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
        address=data['address'],
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

    AuditLogs.objects.create(
        user=new_user,
        action="Register Resident Account",
        module_name="Authentication",
        table_name="Users",
        record_id=new_user.userid,
        new_value=f"Resident account '{new_user.username}' registered and pending verification.",
        created_at=timezone.now(),
    )

    messages.success(request,
        "Account created! Please wait for admin verification before logging in.")
    return redirect("login")


# DASHBOARDS

@admin_login_required
@permission_required("view_dashboard")
def admin_dashboard_view(request):
    from django.db.models import Avg, Count, F, ExpressionWrapper, fields
    from django.core.serializers.json import DjangoJSONEncoder
    import json

    user = get_current_user(request)

    period = request.GET.get("period", "daily")

    today = timezone.now()

    if period == "daily":
        start_date = today - timedelta(days=1)

    elif period == "weekly":
        start_date = today - timedelta(days=7)

    else:
        start_date = today - timedelta(days=30)

    #TOP STAT CARDS
    total_residents = Users.objects.filter(
        user_type__type_name="Resident"
    ).count()

    pending_verifications = ResidentVerification.objects.filter(
        status="Pending"
    ).count()

    total_requests = DocumentRequests.objects.filter(
        requested_at__gte=start_date
    ).count()

    total_cases = Complaints.objects.filter(
        dateadded__gte=start_date
    ).count()

    total_inquiries = Inquiry.objects.filter(
        created_at__gte=start_date
    ).count()
    total_sms = SMSOutbox.objects.count()

    #ANNOUNCEMENT ANALYTICS

    total_announcements = Announcements.objects.count()

    announcement_stats = Announcements.objects.aggregate(
        total_views=Sum("view_count"),
        avg_views=Avg("view_count"),
    )

    total_views = announcement_stats["total_views"] or 0
    avg_views_per_post = round(announcement_stats["avg_views"] or 0, 1)

    most_viewed_announcement = (
        Announcements.objects
        .order_by("-view_count", "-created_at")
        .first()
    )

    #for Google Analyticss
    unique_visitors = 0


    #CASE ANALYTICS (in pie chart data)
    cases_pending = Complaints.objects.filter(
        status="For Chairman Review",
        dateadded__gte=start_date
    ).count()
    cases_ongoing = Complaints.objects.exclude(
        status__in=[
            "For Chairman Review",
            "Resolved",
            "Dismissed",
            "Settled",
            "Certificate Issued",
            "Resolved Outside Barangay",
            "Settled in Court",
        ],
    ).filter(
        dateadded__gte=start_date
    ).count()
    cases_resolved = Complaints.objects.filter(
        status__in=[
            "Resolved", "Dismissed", "Settled",
            "Certificate Issued", "Resolved Outside Barangay",
            "Settled in Court",
        ],
        dateadded__gte=start_date
    ).count()

    #Average resolution time for cases that have a datefinish
    resolved_cases = Complaints.objects.filter(
        datefinish__isnull=False,
        dateadded__isnull=False,
        datefinish__gte=start_date
    ).annotate(
        resolution_duration=ExpressionWrapper(
            F("datefinish") - F("dateadded"),
            output_field=fields.DurationField(),
        )
    )
    avg_case_resolution = resolved_cases.aggregate(
        avg=Avg("resolution_duration")
    )["avg"]
    avg_resolution_days = (
        round(avg_case_resolution.total_seconds() / 86400, 1)
        if avg_case_resolution else 0
    )

    # ---- DOCUMENT REQUEST ANALYTICS (bar chart data) ----
    docreq_pending = DocumentRequests.objects.filter(
        status="Pending",
        requested_at__gte=start_date
    ).count()

    docreq_processing = DocumentRequests.objects.filter(
        status="Processing",
        requested_at__gte=start_date
    ).count()

    docreq_completed = DocumentRequests.objects.filter(
        status="Completed",
        requested_at__gte=start_date
    ).count()

    docreq_rejected = DocumentRequests.objects.filter(
        status="Rejected",
        requested_at__gte=start_date
    ).count()

    completed_requests = DocumentRequests.objects.filter(
        processed_at__isnull=False,
        requested_at__isnull=False,
        processed_at__gte=start_date
    ).annotate(
        processing_duration=ExpressionWrapper(
            F("processed_at") - F("requested_at"),
            output_field=fields.DurationField(),
        )
    )

    avg_docreq_duration = completed_requests.aggregate(
        avg=Avg("processing_duration")
    )["avg"]

    avg_processing_days = (
        round(avg_docreq_duration.total_seconds() / 86400, 1)
        if avg_docreq_duration else 0
    )

    completed_period = DocumentRequests.objects.filter(
        status="Completed",
        requested_at__gte=start_date
    ).count()

    total_period = DocumentRequests.objects.filter(
        requested_at__gte=start_date
    ).count()

    completion_rate = (
        round((completed_period / total_period) * 100)
        if total_period else 0
    )
    
    import json

    case_chart_data = json.dumps({
        "labels": [
            "Pending",
            "Ongoing",
            "Resolved"
        ],
        "values": [
            cases_pending,
            cases_ongoing,
            cases_resolved
        ]
    })

    docreq_chart_data = json.dumps({
        "labels": [
            "Pending",
            "Processing",
            "Completed",
            "Rejected"
        ],
        "values": [
            docreq_pending,
            docreq_processing,
            docreq_completed,
            docreq_rejected
        ]
    })

    return render(request, "adminpanel/dashboard.html", {

        "user": user,
        "case_chart_data": case_chart_data,
        "docreq_chart_data": docreq_chart_data,
        "period": period,

        # Top cards
        "total_residents": total_residents,
        "pending_verifications": pending_verifications,
        "total_requests": total_requests,
        "total_cases": total_cases,
        "total_inquiries": total_inquiries,
        "total_sms_sent": total_sms,

        # Announcement Analytics
        "total_announcements": total_announcements,
        "total_views": total_views,
        "avg_views_per_post": avg_views_per_post,
        "most_viewed_announcement": most_viewed_announcement,

        # Case Analytics
        "cases_pending": cases_pending,
        "cases_ongoing": cases_ongoing,
        "cases_resolved": cases_resolved,
        "avg_resolution_time": avg_resolution_days,

        # Document Requests
        "docreq_pending": docreq_pending,
        "docreq_processing": docreq_processing,
        "docreq_completed": docreq_completed,
        "docreq_rejected": docreq_rejected,
        "avg_processing_time": avg_processing_days,
        "completion_rate": completion_rate,

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
    current_user = get_current_user(request)
    user_type = request.session.get("user_type", "Resident")

    if current_user:
        AuditLogs.objects.create(
            user=current_user,
            action=f"{user_type} Logout",
            module_name="Authentication",
            table_name="Users",
            record_id=current_user.userid,
            new_value=f"{user_type} '{current_user.username}' logged out.",
            created_at=timezone.now(),
        )

    request.session.flush()
    messages.success(request, "You have been logged out successfully.")

    if user_type == "Admin":
        return redirect("admin_login")

    return redirect("landing")


# ADMIN — CREATE STAFF (Chairman only)

@admin_login_required
@permission_required('create_users')
def admin_register(request):
    if request.method != "POST":
        return render(request, "auth/admin_register.html", {
            "positions": Positions.objects.all(),
        })

    firstname   = request.POST.get("firstname", "").strip()
    lastname    = request.POST.get("lastname", "").strip()
    contact_no  = request.POST.get("contact_no", "").strip()
    email       = request.POST.get("email", "").strip()
    position_id = request.POST.get("position_id", "").strip()

    if not all([firstname, lastname, contact_no, email, position_id]):
        messages.error(request, "All required fields must be filled.")
        return redirect("admin_register")

    if not contact_no.startswith("09") or len(contact_no) != 11:
        messages.error(request, "Enter a valid 11-digit PH mobile number.")
        return redirect("admin_register")

    if Users.objects.filter(contactno=contact_no).exists():
        messages.error(request, "Contact number already exists.")
        return redirect("admin_register")

    if Users.objects.filter(email=email).exists():
        messages.error(request, "Email already exists.")
        return redirect("admin_register")

    try:
        admin_type = UserTypes.objects.get(type_name="Admin")
    except UserTypes.DoesNotExist:
        messages.error(request, "Personnel user type not found.")
        return redirect("admin_register")

    try:
        position = Positions.objects.get(positionid=position_id)
    except Positions.DoesNotExist:
        messages.error(request, "Invalid position selected.")
        return redirect("admin_register")

    role = get_role_for_position(position)

    if not role:
        messages.error(
            request,
            "No matching system role found for the selected position."
        )
        return redirect("admin_register")

    suffix   = ''.join(random.choices(_string.digits, k=4))
    username = (lastname.lower().replace(" ", "") + suffix)[:20]

    while Users.objects.filter(username=username).exists():
        suffix   = ''.join(random.choices(_string.digits, k=4))
        username = (lastname.lower().replace(" ", "") + suffix)[:20]

    temp_password = ''.join(random.choices(
        _string.ascii_letters + _string.digits, k=10
    ))

    current_admin = get_current_user(request)

    new_user = Users.objects.create(
        username=username,
        email=email,
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

    sms_success = queue_sms(
        contact_no,
        f"KaugnayPH: Account created. "
        f"Username: {username} | Temp Password: {temp_password} "
        f"Log in and change your password immediately.",
        sent_by=current_admin
    )

    AuditLogs.objects.create(
        user=current_admin,
        action="Create Personnel Account",
        module_name="UserManagement",
        table_name="Users",
        record_id=new_user.userid,
        new_value=(
            f"Personnel '{username}' created by {current_admin.username}. "
            f"Position: {position.name}. System Role: {role.rolename}."
        ),
        created_at=timezone.now()
    )

    if sms_success:
        messages.success(
            request,
            f"Staff account created! Username: {username} | "
            f"Temp Password: {temp_password} (also sent via SMS)"
        )
    else:
        messages.warning(
            request,
            f"Staff account created! Username: {username} | "
            f"Temp Password: {temp_password}. SMS notification failed. Please check the SMS Outbox."
        )

    return redirect("admins_list")

#ADMIN DETAILS VIEW
@admin_login_required
@permission_required(
    "create_users", 
    "edit_users",
    "deactivate_users"
)
def admin_detail_view(request, user_id):
    try:
        admin_user = Users.objects.select_related(
            "role",
            "position",
            "user_type"
        ).get(
            userid=user_id,
            user_type__type_name="Admin"
        )
    except Users.DoesNotExist:
        messages.error(request, "Personnel account not found.")
        return redirect("admins_list")

    return render(request, "adminpanel/admin_detail.html", {
        "admin_user": admin_user,
        "user": get_current_user(request),
    })

# ADMIN DEACTIVATE ADMIN
@admin_login_required
@permission_required(
    "create_users", 
    "edit_users",
    "deactivate_users"
)
def admin_deactivate_view(request, user_id):
    current_admin = get_current_user(request)

    try:
        admin_user = Users.objects.select_related(
            "role",
            "position",
            "user_type"
        ).get(
            userid=user_id,
            user_type__type_name="Admin",
            is_active=True
        )
    except Users.DoesNotExist:
        messages.error(request, "Personnel account not found.")
        return redirect("admins_list")

    # Prevent current admin from deactivating their own account
    if admin_user.userid == current_admin.userid:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect("admins_list")

    # Prevent deactivating the last active Barangay Chairman account
    if (
        admin_user.position
        and admin_user.position.name == "Barangay Chairman"
    ):
        active_chairmen_count = Users.objects.filter(
            user_type__type_name="Admin",
            position__name="Barangay Chairman",
            is_active=True
        ).count()

        if active_chairmen_count <= 1:
            messages.error(
                request,
                "You cannot deactivate the last active Barangay Chairman account."
            )
            return redirect("admins_list")

    if request.method == "POST":
        admin_user.is_active = False
        admin_user.save(update_fields=["is_active"])

        AuditLogs.objects.create(
            user=current_admin,
            action="Deactivate Admin Account",
            module_name="UserManagement",
            table_name="Users",
            record_id=admin_user.userid,
            old_value="is_active=True",
            new_value="is_active=False",
            created_at=timezone.now()
        )

        messages.success(
            request,
            f"Personnel account for {admin_user.firstname} {admin_user.lastname} has been deactivated."
        )
        return redirect("admins_list")

    return render(request, "adminpanel/admin_deactivate_confirm.html", {
        "admin_user": admin_user,
        "user": current_admin,
    })

# ADMIN EDIT ADMIN
@admin_login_required
@permission_required(
    "create_users",
    "edit_users",
    "deactivate_users"
)
def admin_edit_view(request, user_id):
    try:
        admin_user = Users.objects.select_related(
            "role",
            "position",
            "user_type"
        ).get(
            userid=user_id,
            user_type__type_name="Admin"
        )
    except Users.DoesNotExist:
        messages.error(request, "Personnel account not found.")
        return redirect("admins_list")

    positions = Positions.objects.all()
    current_admin = get_current_user(request)

    if request.method != "POST":
        return render(request, "adminpanel/admin_edit.html", {
            "admin_user": admin_user,
            "positions": positions,
            "user": current_admin,
        })

    firstname   = request.POST.get("firstname", "").strip()
    lastname    = request.POST.get("lastname", "").strip()
    email       = request.POST.get("email", "").strip()
    contact_no  = request.POST.get("contact_no", "").strip()
    position_id = request.POST.get("position_id", "").strip()

    if not all([firstname, lastname, email, contact_no, position_id]):
        messages.error(request, "All required fields must be filled.")
        return redirect("admin_edit", user_id=user_id)

    if not contact_no.startswith("09") or len(contact_no) != 11:
        messages.error(request, "Enter a valid 11-digit PH mobile number.")
        return redirect("admin_edit", user_id=user_id)

    if Users.objects.filter(email=email).exclude(userid=user_id).exists():
        messages.error(request, "Email is already in use.")
        return redirect("admin_edit", user_id=user_id)

    if Users.objects.filter(contactno=contact_no).exclude(userid=user_id).exists():
        messages.error(request, "Contact number is already in use.")
        return redirect("admin_edit", user_id=user_id)

    try:
        position = Positions.objects.get(positionid=position_id)
    except Positions.DoesNotExist:
        messages.error(request, "Invalid position selected.")
        return redirect("admin_edit", user_id=user_id)

    role = get_role_for_position(position)

    if not role:
        messages.error(
            request,
            "No matching system role found for the selected position."
        )
        return redirect("admin_edit", user_id=user_id)

    old_value = (
        f"Name: {admin_user.firstname} {admin_user.lastname}, "
        f"Email: {admin_user.email}, "
        f"Contact: {admin_user.contactno}, "
        f"Position: {admin_user.position.name if admin_user.position else 'None'}, "
        f"System Role: {admin_user.role.rolename if admin_user.role else 'None'}"
    )

    admin_user.firstname = firstname
    admin_user.lastname = lastname
    admin_user.email = email
    admin_user.contactno = contact_no
    admin_user.position = position
    admin_user.role = role
    admin_user.save()

    new_value = (
        f"Name: {admin_user.firstname} {admin_user.lastname}, "
        f"Email: {admin_user.email}, "
        f"Contact: {admin_user.contactno}, "
        f"Position: {admin_user.position.name if admin_user.position else 'None'}, "
        f"System Role: {admin_user.role.rolename if admin_user.role else 'None'}"
    )

    AuditLogs.objects.create(
        user=current_admin,
        action="Edit Admin Account",
        module_name="UserManagement",
        table_name="Users",
        record_id=admin_user.userid,
        old_value=old_value,
        new_value=new_value,
        created_at=timezone.now()
    )

    messages.success(
        request,
        f"Personnel account for {admin_user.firstname} {admin_user.lastname} has been updated."
    )

    return redirect("admins_list")

#ADMIN REACTIVATE ADMIN
@admin_login_required
@permission_required(
    "create_users", 
    "edit_users",
    "deactivate_users"
)
def admin_reactivate_view(request, user_id):
    current_admin = get_current_user(request)

    try:
        admin_user = Users.objects.select_related(
            "role",
            "position",
            "user_type"
        ).get(
            userid=user_id,
            user_type__type_name="Admin",
            is_active=False
        )
    except Users.DoesNotExist:
        messages.error(request, "Inactive admin account not found.")
        return redirect("admins_list")

    admin_user.is_active = True
    admin_user.save(update_fields=["is_active"])

    AuditLogs.objects.create(
        user=current_admin,
        action="Reactivate Admin Account",
        module_name="UserManagement",
        table_name="Users",
        record_id=admin_user.userid,
        old_value="is_active=False",
        new_value="is_active=True",
        created_at=timezone.now()
    )

    messages.success(
        request,
        f"Personnel account for {admin_user.firstname} {admin_user.lastname} has been reactivated."
    )

    return redirect("admins_list")

# RESIDENT RECORDS

@admin_login_required
@permission_required('view_residents')
def resident_records_view(request):
    from django.core.paginator import Paginator

    status_filter = request.GET.get("status", "All").strip()
    sms_filter = request.GET.get("sms", "All").strip()
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
        sub = SMSSubscriptions.objects.filter(user=u).first()

        status = rv.status if rv else "No Submission"
        sms_sub = sub.is_active if sub else False

        if status_filter != "All" and status != status_filter:
            continue

        if sms_filter == "Subscribed" and not sms_sub:
            continue

        if sms_filter == "Not Subscribed" and sms_sub:
            continue

        records.append({
            "user": u,
            "rv": rv,
            "status": status,
            "sms_sub": sms_sub,
            "display_name": format_full_name(u.lastname, u.firstname),
            "masked_contact": mask_contact(u.contactno),
            "masked_email": mask_email(u.email)
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
        "sms_filter": sms_filter,
        "search_query": search_query,
        "total_residents": total_residents,
        "pending_count": ResidentVerification.objects.filter(status="Pending").count(),
        "verified_count": ResidentVerification.objects.filter(status="Approved").count(),
        "sms_subscribers": SMSSubscriptions.objects.filter(is_active=True).count(),
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

    latest_announcements = Announcements.objects.order_by('-announcement_id')[:3]

    return render(request, 'residentprofile.html', {
        'user': current_user,
        'recent_complaints': recent_complaints,
        'active_complaints': active_complaints,
        'recent_requests': recent_requests,
        'latest_announcements': latest_announcements,
    })

# RESIDENT CHANGE SMS SUBSCRIPTION
@login_required
@require_POST
def toggle_sms_subscription(request):
    resident = get_current_user(request)

    subscription, created = SMSSubscriptions.objects.get_or_create(
        user=resident,
        defaults={"is_active": False}
    )

    subscription.is_active = not subscription.is_active
    subscription.save(update_fields=["is_active"])

    AuditLogs.objects.create(
        user=resident,
        action="Updated SMS Subscription",
        module_name="Settings",
        table_name="SMSSubscriptions",
        record_id=subscription.id,
        new_value=f"SMS subscription {'enabled' if subscription.is_active else 'disabled'}.",
        created_at=timezone.now(),
    )

    return JsonResponse({
        "success": True,
        "is_active": subscription.is_active
    })

#RESIDENT EDIT PROFILE + CHANGE PASSWORD
@login_required
@resident_required
def editprofile_view(request):
    user = get_current_user(request)

    if request.method == "POST":
        form_type = request.POST.get("form_type")

        if form_type == "avatar":
            avatar_id = request.POST.get("avatar_id", "").strip()
            if avatar_id:
                try:
                    user.avatar = AvatarOptions.objects.get(avatarid=avatar_id, is_active=True)
                except AvatarOptions.DoesNotExist:
                    messages.error(request, "Invalid avatar selected.")
                    return render(request, "editprofile.html", {
                        "user": user,
                        "avatars": AvatarOptions.objects.filter(is_active=True).order_by("avatarid"),
                    })
            else:
                user.avatar = None

            user.save()
            request.session['avatar_path'] = user.avatar.image_path if user.avatar else None

            messages.success(request, "Avatar updated successfully!")
            return redirect("editprofile")

        elif form_type == "password":
            current_password = request.POST.get("current_password", "").strip()
            new_password = request.POST.get("new_password", "").strip()
            confirm_password = request.POST.get("confirm_password", "").strip()

            if not current_password or not new_password or not confirm_password:
                messages.error(request, "Please complete all password fields.")
                return redirect("editprofile")

            if not check_password(current_password, user.password):
                messages.error(request, "Current password is incorrect.")
                return redirect("editprofile")

            if new_password != confirm_password:
                messages.error(request, "New password and confirm password do not match.")
                return redirect("editprofile")

            if len(new_password) < 8:
                messages.error(request, "Password must be at least 8 characters long.")
                return redirect("editprofile")

            if check_password(new_password, user.password):
                messages.error(request, "Your new password must be different from your current password.")
                return redirect("editprofile")

            user.password = hash_password(new_password)
            user.is_password_changed = True
            user.save()

            AuditLogs.objects.create(
                user=user,
                action="Changed Password",
                module_name="Profile",
                table_name="Users",
                record_id=user.userid,
                old_value="Password changed",
                new_value="Password updated",
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT"),
                created_at=timezone.now(),
            )

            request.session.flush()

            messages.success(request, "Password changed successfully. Please log in again.")
            return redirect("login")

    return render(request, "editprofile.html", {
        "user": user,
        "avatars": AvatarOptions.objects.filter(is_active=True).order_by("avatarid"),
    })

#ADMIN VIEW RESIDENT
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
    sub     = SMSSubscriptions.objects.filter(user=resident).first()
    sms_sub = sub.is_active if sub else False
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
            send_sms_with_warning(
                request,
                resident.contactno,
                "KaugnayPH: Your account has been verified! You can now log in.",
                sent_by=admin
            )
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
            send_sms_with_warning(
                request,
                resident.contactno,
                "KaugnayPH: Your registration was not approved. "
                "Please visit the barangay office.",
                sent_by=admin
            )
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
@permission_required("view_announcements")
def admin_announcements_view(request):
    from django.core.paginator import Paginator

    search = request.GET.get("search", "").strip()
    category = request.GET.get("category", "all").strip()
    date_filter = request.GET.get("date", "").strip()

    all_announcements = Announcements.objects.select_related(
        "category",
        "posted_by"
    ).all()

    announcements = all_announcements

    if search:
        announcements = announcements.filter(
            title__icontains=search
        )

    if category and category != "all":
        announcements = announcements.filter(
            category__name__iexact=category
        )

    if date_filter:
        selected_date = parse_date(date_filter)

        if selected_date:
            start = timezone.make_aware(datetime.combine(selected_date, time.min))
            end = timezone.make_aware(datetime.combine(selected_date, time.max))

            announcements = announcements.filter(
                created_at__range=(start, end)
            )

    announcements = announcements.order_by("-announcement_id")

    total_announcements = all_announcements.count()
    announcement_stats = all_announcements.aggregate(
    total_views=Sum("view_count"),
    avg_views=Avg("view_count"),
    )

    total_views = announcement_stats["total_views"] or 0
    avg_views_per_post = round(announcement_stats["avg_views"] or 0, 1)

    most_viewed = (
        all_announcements
        .order_by("-view_count", "-created_at")
        .first()
    )

    general_count = all_announcements.filter(
        category__name__iexact="General"
    ).count()

    emergency_count = all_announcements.filter(
        category__name__iexact="Emergency"
    ).count()

    paginator = Paginator(announcements, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "adminpanel/announcements_list.html", {
        "announcements": page_obj,
        "page_obj": page_obj,
        "user": get_current_user(request),

        "search": search,
        "selected_category": category,
        "date_filter": date_filter,

        "total_announcements": total_announcements,
       
       "total_views": total_views,
        "most_viewed": most_viewed,
        "avg_views_per_post": avg_views_per_post,
    })

# ADMIN ANNOUNCEMENT DETAIL
@admin_login_required
@permission_required("view_announcements")
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
@permission_required("edit_announcements")
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
@permission_required("delete_announcements")
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
@permission_required("create_announcements")
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

                queue_sms(
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
@permission_required("view_announcements")
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
@permission_required("view_announcements")
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
@permission_required(
    "view_complaints", 
    "manage_complaints"
)
def case_records_view(request):
    from django.core.paginator import Paginator
    import re

    search_query = request.GET.get("search", "").strip()
    flagged_only = request.GET.get("flagged", "") == "1"
    status_filter = request.GET.get("status", "").strip()
    type_filter = request.GET.get("type", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    complaints = Complaints.objects.select_related(
        "complaint_type",
        "complainant_user",
        "handled_by"
    )

    if flagged_only:
        complaints = complaints.filter(is_flagged=True)

    if status_filter:
        complaints = complaints.filter(status=status_filter)

    if type_filter:
        complaints = complaints.filter(complaint_type__ctid=type_filter)

    if date_from:
        complaints = complaints.filter(incident_date__gte=date_from)
    if date_to:
        selected_date = parse_date(date_to)

        if selected_date:
            start = timezone.make_aware(datetime.combine(selected_date, time.min))
            end = timezone.make_aware(datetime.combine(selected_date, time.max))

            complaints = complaints.filter(
                incident_date__range=(start, end)
            )

    if search_query:
        case_id_match = re.search(r"(\d+)$", search_query)
        case_id_number = int(case_id_match.group(1)) if case_id_match else None

        search_filter = (
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(complainee__icontains=search_query) |
            Q(status__icontains=search_query) |
            Q(case_number__icontains=search_query) |
            Q(complaint_type__type__icontains=search_query) |
            Q(complainant_user__firstname__icontains=search_query) |
            Q(complainant_user__lastname__icontains=search_query)
        )

        if case_id_number is not None:
            search_filter |= Q(complaintsid=case_id_number)

        complaints = complaints.filter(search_filter)

    complaints = complaints.order_by("-dateadded")

    case_records = []

    for complaint in complaints:
        status = complaint.status or "For Chairman Review"

        case_records.append({
            "complaint_id": complaint.complaintsid,
            "case_id": complaint.case_number or f"CMP-{complaint.dateadded.year}-{complaint.complaintsid:04d}",
            "case_type": complaint.complaint_type.type if complaint.complaint_type else "Unclassified",
            "type_class": "complaint",
            "title": complaint.title,
            "complainant_name": (
                f"{complaint.complainant_user.firstname} {complaint.complainant_user.lastname}"
                if complaint.complainant_user else "—"
            ),
            "complainee_name": complaint.complainee or "—",
            "incident_date": complaint.incident_date.strftime("%b %d, %Y") if complaint.incident_date else "—",
            "date_submitted": complaint.dateadded.strftime("%b %d, %Y %I:%M %p") if complaint.dateadded else "",
            "status": status,
            "status_class": status.lower().replace(" ", "-"),
            "is_flagged": complaint.is_flagged,
            "flagged_reason": complaint.flagged_reason,
        })

    paginator = Paginator(case_records, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Base queryset (unfiltered by search/status/etc) for the top stat cards,
    # so the cards always reflect totals, not the current filtered view.
    all_complaints = Complaints.objects.all()

    total_cases = all_complaints.count()
    for_review_cases = all_complaints.filter(status="For Chairman Review").count()
    ongoing_cases = all_complaints.filter(
        status__in=[
            "Ongoing",
            "Mediation Scheduled",
            "Mediation Ongoing",
            "For 1st Hearing",
            "For 2nd Hearing",
            "For 3rd Hearing",
            "Eligible for Certificate to File Action",
        ]
    ).count()
    resolved_cases = all_complaints.filter(
        status__in=["Settled", "Resolved Outside Barangay", "Settled in Court"]
    ).count()
    certificates_issued_count = all_complaints.filter(status="Certificate Issued").count()
    flagged_count = all_complaints.filter(is_flagged=True).count()

    complaint_types = ComplaintType.objects.all()

    return render(request, "adminpanel/case_records.html", {
        "cases": page_obj,
        "page_obj": page_obj,
        "user": get_current_user(request),
        "search_query": search_query,
        "flagged_only": flagged_only,
        "flagged_count": flagged_count,
        "status_filter": status_filter,
        "type_filter": type_filter,
        "date_from": date_from,
        "date_to": date_to,
        "complaint_types": complaint_types,
        "status_choices": Complaints.STATUS_CHOICES,
        "total_cases": total_cases,
        "for_review_cases": for_review_cases,
        "ongoing_cases": ongoing_cases,
        "resolved_cases": resolved_cases,
        "certificates_issued_count": certificates_issued_count,
    })


# DOCUMENT REQUEST FOR RESIDENT 
@login_required
@resident_required
def document_request_view(request):
    document_types = DocumentTypes.objects.filter(is_active=True)
    current_user = get_current_user(request)

    def documents_context(
        captcha_form=None,
        selected_type=None,
        fields=None,
        form_data=None,
    ):
        context = {
            "document_types": document_types,
            "resident": current_user,
            "captcha_form": captcha_form or CaptchaOnlyForm(),
            "form_data": form_data or {},
        }

        if selected_type:
            context["selected_type"] = selected_type

        if fields is not None:
            context["fields"] = fields

        return context

    if request.method == "POST":
        captcha_form = CaptchaOnlyForm(request.POST)

        document_type_id = request.POST.get("document_type_id", "").strip()
        purpose = request.POST.get("purpose", "").strip()

        if not captcha_form.is_valid():
            selected_type = None
            fields = None

            if document_type_id:
                try:
                    selected_type = DocumentTypes.objects.get(
                        dtid=document_type_id,
                        is_active=True
                    )
                    fields = DocumentFields.objects.filter(
                        document_type=selected_type
                    )
                except DocumentTypes.DoesNotExist:
                    pass

            return render(
                request,
                "documents.html",
                documents_context(
                    captcha_form=captcha_form,
                    selected_type=selected_type,
                    fields=fields,
                    form_data=request.POST,
                )
            )

        if not document_type_id:
            messages.error(request, "Please select a document type.")
            return render(request, "documents.html", documents_context())

        try:
            document_type = DocumentTypes.objects.get(dtid=document_type_id, is_active=True)
        except DocumentTypes.DoesNotExist:
            messages.error(request, "Invalid document type selected.")
            return render(request, "documents.html", documents_context())

        fields = DocumentFields.objects.filter(document_type=document_type)

        field_errors = []

        for field in fields:
            if field.is_required:
                input_name = f"field_{field.dfid}"

                if field.field_type == "file":
                    uploaded_file = request.FILES.get(input_name)

                    if not uploaded_file:
                        field_errors.append(f"'{field.field_label}' is required.")
                else:
                    value = request.POST.get(input_name, "").strip()

                    if not value:
                        field_errors.append(f"'{field.field_label}' is required.")

        if field_errors:
            for err in field_errors:
                messages.error(request, err)

            return render(
                request,
                "documents.html",
                documents_context(
                    selected_type=document_type,
                    fields=fields,
                    form_data=request.POST,
                )
            )

        # CONTENT MODERATION
        text_check = moderate_text(purpose)

        if text_check["flagged"]:
            messages.error(request, "Your request contains inappropriate content and could not be submitted.")
            return render(request, "documents.html", documents_context())

        # SAVE MAIN REQUEST
        doc_request = DocumentRequests.objects.create(
            user=current_user,
            document_type=document_type,
            purpose=purpose,
            request_mode="Online",
            status="Pending",
        )

        # SAVE FIELD VALUES / FILES
        for field in fields:
            input_name = f"field_{field.dfid}"

            field_value = None
            file_path = None

            if field.field_type == "file":
                uploaded_file = request.FILES.get(input_name)

                if uploaded_file:
                    ok, err = validate_upload(uploaded_file)

                    if not ok:
                        messages.error(request, err)
                        doc_request.delete()
                        return render(
                            request,
                            "documents.html",
                            documents_context(selected_type=document_type, fields=fields)
                        )

                    file_path = default_storage.save(
                        f"document_requests/{uploaded_file.name}",
                        ContentFile(uploaded_file.read())
                    )
            else:
                field_value = request.POST.get(input_name, "").strip()

            DocumentRequestFieldValues.objects.create(
                document_request=doc_request,
                document_field=field,
                field_value=field_value,
                uploaded_file=file_path,
                created_at=timezone.now(),
            )

        from core.utils import generate_document_id
        doc_id = generate_document_id(doc_request.drid)

        if current_user and current_user.contactno:
            queue_sms(
                current_user.contactno,
                f"KaugnayPH: Your document request {doc_id} ({document_type.name}) has been submitted and is now pending review.",
                sent_by=current_user,
            )

        AuditLogs.objects.create(
            user=current_user,
            action="Submit Document Request",
            module_name="DocumentRequests",
            table_name="DocumentRequests",
            record_id=doc_request.drid,
            new_value=f"Request for '{document_type.name}' submitted.",
            created_at=timezone.now(),
        )

        # SLA — start the 3-day clock
        create_sla("DocumentRequest", doc_request.drid, priority="Medium")

        messages.success(request, "Document request submitted successfully. You can track its status under Track Submissions.")
        return redirect("tracksub")

    return render(request, "documents.html", documents_context())


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
    ).select_related("complaint_type").order_by("-dateadded")

    document_requests = DocumentRequests.objects.filter(
        user=current_user
    ).select_related("document_type").order_by("-requested_at")

    # Build a hearing summary per complaint so the template doesn't need
    # nested queries per row.
    hearing_by_complaint = {}
    hearings = ComplaintHearing.objects.select_related(
        "complaint", "hearing_level", "status"
    ).filter(
        complaint__complainant_user=current_user
    ).order_by("-hearing_date")

    officials_map = {}

    all_officials = HearingOfficials.objects.select_related(
        "user_officials"
    )

    for official in all_officials:
        officials_map.setdefault(
            official.complaint_id,
            []
        ).append(official)

    for hearing in hearings:
        cid = hearing.complaint_id

        if cid not in hearing_by_complaint:
            hearing_by_complaint[cid] = {
                "latest_hearing": hearing,
                "officials": officials_map.get(cid, [])
            }

    return render(request, "tracksub.html", {
        "complaints": complaints,
        "document_requests": document_requests,
        "hearing_by_complaint": hearing_by_complaint,
        "hearings": hearings,
        "status_choices": Complaints.STATUS_CHOICES,
    })

@login_required
@resident_required
def complaint_timeline_view(request, complaint_id):
    """
    Resident-facing read-only timeline for a single complaint they own.
    Used by Track Submissions (Item 2/3) when a resident clicks into a complaint.
    """
    current_user = get_current_user(request)

    try:
        complaint = Complaints.objects.select_related("complaint_type", "handled_by").get(
            complaintsid=complaint_id,
            complainant_user=current_user,  # ownership check — residents can't view others' complaints
        )
    except Complaints.DoesNotExist:
        messages.error(request, "Complaint not found.")
        return redirect("tracksub")

    complaint_updates = ComplaintUpdates.objects.filter(
        complaint=complaint
    ).select_related("updated_by").order_by("-updated_at")

    all_hearings = ComplaintHearing.objects.filter(
        complaint=complaint
    ).select_related("hearing_level", "status").order_by("hearing_date")

    assigned_officials = HearingOfficials.objects.filter(
        complaint=complaint
    ).select_related("user_officials")

    certificate = CertificateToFileAction.objects.filter(complaint=complaint).first()

    return render(request, "complaint_timeline.html", {
        "complaint": complaint,
        "case_id": complaint.case_number or generate_case_number(complaint.complaintsid),
        "complaint_updates": complaint_updates,
        "all_hearings": all_hearings,
        "assigned_officials": assigned_officials,
        "certificate": certificate,
    })

# ADMIN: DOCUMENT REQUESTS LIST
@admin_login_required
@permission_required(
    "view_document_requests",
    "process_document_requests"
)
def admin_document_requests_view(request):
    from django.core.paginator import Paginator

    search_query         = request.GET.get("search", "").strip()
    status_filter        = request.GET.get("status", "All").strip()
    document_type_filter = request.GET.get("document_type", "All").strip()
    date_filter          = request.GET.get("date", "").strip()

    doc_requests = DocumentRequests.objects.select_related(
        "user",
        "document_type",
        "processed_by"
    ).all()

    if search_query:
        doc_requests = doc_requests.filter(
            Q(user__firstname__icontains=search_query) |
            Q(user__lastname__icontains=search_query) |
            Q(document_type__name__icontains=search_query) |
            Q(drid__icontains=search_query)
        )

    if status_filter != "All":
        doc_requests = doc_requests.filter(status=status_filter)

    if document_type_filter != "All":
        doc_requests = doc_requests.filter(document_type_id=document_type_filter)

    if date_filter:
        selected_date = parse_date(date_filter)

        if selected_date:
            start = timezone.make_aware(datetime.combine(selected_date, time.min))
            end = timezone.make_aware(datetime.combine(selected_date, time.max))

            doc_requests = doc_requests.filter(
                requested_at__range=(start, end)
            )

    doc_requests = doc_requests.order_by("-requested_at")

    records = []

    for dr in doc_requests:
        from core.utils import generate_document_id

        sla = get_sla_for_record("DocumentRequest", dr.drid)

        records.append({
            "obj": dr,
            "doc_id": generate_document_id(dr.drid),
            "status": dr.status or "Pending",
            "sla": sla,
            "sla_status": get_sla_status_live(sla),
        })

    paginator = Paginator(records, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "adminpanel/document_requests.html", {
        "records": page_obj,
        "page_obj": page_obj,
        "user": get_current_user(request),

        "search_query": search_query,
        "status_filter": status_filter,
        "document_type_filter": document_type_filter,
        "date_filter": date_filter,

        "document_types": DocumentTypes.objects.all(),

        "total": DocumentRequests.objects.count(),
        "pending": DocumentRequests.objects.filter(status="Pending").count(),
        "processing": DocumentRequests.objects.filter(status="Processing").count(),
        "completed": DocumentRequests.objects.filter(status="Completed").count(),
    })


# ADMIN: DOCUMENT REQUEST DETAILS
@admin_login_required
@permission_required(
    "view_document_requests",
    "process_document_requests"
)
def admin_document_request_detail_view(request, drid):
    try:
        doc_request = DocumentRequests.objects.select_related(
            "user", "document_type", "processed_by"
        ).get(drid=drid)
    except DocumentRequests.DoesNotExist:
        messages.error(request, "Document request not found.")
        return redirect("admin_document_requests")

    current_admin = get_current_user(request)

    field_values = DocumentRequestFieldValues.objects.filter(
        document_request=doc_request
    ).select_related("document_field")

    resident = doc_request.user

    if request.method == "POST":
        action = request.POST.get("action")

        remarks = request.POST.get("admin_remarks")
        if remarks is not None:
            remarks = remarks.strip()
        else:
            remarks = doc_request.admin_remarks

        from core.utils import generate_document_id
        doc_id = generate_document_id(doc_request.drid)

        if action == "save_remarks":
            old_remarks = doc_request.admin_remarks
            send_remark_sms = request.POST.get("send_remark_sms") == "1"

            if remarks:
                doc_request.admin_remarks = remarks
                doc_request.processed_by = current_admin
                doc_request.save()

                if send_remark_sms and resident and resident.contactno:
                    send_sms_with_warning(
                        request,
                        resident.contactno,
                        f"KaugnayPH: A remark has been added to your document request {doc_id} "
                        f"({doc_request.document_type.name}): {remarks}",
                        sent_by=current_admin,
                    )

                AuditLogs.objects.create(
                    user=current_admin,
                    action="Update Document Request Remarks",
                    module_name="DocumentRequests",
                    table_name="DocumentRequests",
                    record_id=doc_request.drid,
                    old_value=f"Remarks: {old_remarks or 'None'}",
                    new_value=f"Remarks: {remarks or 'None'}",
                    created_at=timezone.now(),
                )

                messages.success(request, "Admin remarks saved.")
            else:
                messages.warning(request, "Please enter a remark before saving.")

        elif action == "complete":
            old_status = doc_request.status
            old_remarks = doc_request.admin_remarks
            completed_remark = "Document completed. Ready for pickup."

            doc_request.status = "Completed"
            doc_request.admin_remarks = completed_remark
            doc_request.processed_by = current_admin
            doc_request.processed_at = timezone.now()
            doc_request.save()

            record_first_response("DocumentRequest", doc_request.drid)
            resolve_sla("DocumentRequest", doc_request.drid)

            if resident and resident.contactno:
                send_sms_with_warning(
                    request,
                    resident.contactno,
                    f"KaugnayPH: Your document request {doc_id} ({doc_request.document_type.name}) "
                    "has been completed. Please visit the barangay office to claim it.",
                    sent_by=current_admin,
                )

            AuditLogs.objects.create(
                user=current_admin,
                action="Complete Document Request",
                module_name="DocumentRequests",
                table_name="DocumentRequests",
                record_id=doc_request.drid,
                old_value=f"Status: {old_status}; Remarks: {old_remarks or 'None'}",
                new_value=f"Status: Completed; Remarks: {completed_remark}",
                created_at=timezone.now(),
            )

            messages.success(request, "Document request marked as Completed.")

        elif action == "processing":
            old_status = doc_request.status
            old_remarks = doc_request.admin_remarks

            doc_request.status = "Processing"
            doc_request.admin_remarks = remarks
            doc_request.processed_by = current_admin
            doc_request.save()

            record_first_response("DocumentRequest", doc_request.drid)

            if resident and resident.contactno:
                send_sms_with_warning(
                    request,
                    resident.contactno,
                    f"KaugnayPH: Your document request {doc_id} ({doc_request.document_type.name}) "
                    "is now being processed.",
                    sent_by=current_admin,
                )

            AuditLogs.objects.create(
                user=current_admin,
                action="Set Document Request Processing",
                module_name="DocumentRequests",
                table_name="DocumentRequests",
                record_id=doc_request.drid,
                old_value=f"Status: {old_status}; Remarks: {old_remarks or 'None'}",
                new_value=f"Status: Processing; Remarks: {remarks or 'None'}",
                created_at=timezone.now(),
            )

            messages.success(request, "Document request marked as Processing.")

        elif action == "reject":
            if not remarks:
                messages.error(request, "Rejection remarks are required before rejecting a document request.")
                return redirect("admin_document_request_detail", drid=doc_request.drid)

            old_status = doc_request.status
            old_remarks = doc_request.admin_remarks

            doc_request.status = "Rejected"
            doc_request.admin_remarks = remarks
            doc_request.processed_by = current_admin
            doc_request.processed_at = timezone.now()
            doc_request.save()

            record_first_response("DocumentRequest", doc_request.drid)
            resolve_sla("DocumentRequest", doc_request.drid)

            if resident and resident.contactno:
                send_sms_with_warning(
                    request,
                    resident.contactno,
                    f"KaugnayPH: Your document request {doc_id} ({doc_request.document_type.name}) "
                    "has been rejected. Please contact the barangay office for more details.",
                    sent_by=current_admin,
                )

            AuditLogs.objects.create(
                user=current_admin,
                action="Reject Document Request",
                module_name="DocumentRequests",
                table_name="DocumentRequests",
                record_id=doc_request.drid,
                old_value=f"Status: {old_status}; Remarks: {old_remarks or 'None'}",
                new_value=f"Status: Rejected; Remarks: {remarks or 'None'}",
                created_at=timezone.now(),
            )

            messages.success(request, "Document request rejected.")

        return redirect("admin_document_request_detail", drid=doc_request.drid)

    from core.utils import generate_document_id
    sla = get_sla_for_record("DocumentRequest", drid)

    return render(request, "adminpanel/document_request_detail.html", {
        "doc_request": doc_request,
        "doc_id": generate_document_id(doc_request.drid),
        "field_values": field_values,
        "resident": resident,
        "user": current_admin,
        "sla": sla,
        "sla_status": get_sla_status_live(sla),
    })

#COMPLAINT UPDATES 
# ADMIN CASE DETAIL
@admin_login_required
@permission_required(
    "view_complaints", 
    "manage_complaints"
)
def case_detail_view(request, complaint_id):
    """
    Full complaint lifecycle management per the barangay complaint process:
    Submitted -> Chairman Review -> Decision -> Mediation -> Hearings 1-3 ->
    Certificate -> Closed (or External Resolution).
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
    complaint_types = ComplaintType.objects.all()
    hearing_levels   = HearingLevel.objects.all()
    hearing_statuses = HearingStatus.objects.all()
    all_hearings = ComplaintHearing.objects.filter(
        complaint=complaint
    ).select_related("hearing_level", "status").order_by("hearing_date")
    existing_hearing = all_hearings.last()

    complaint_updates = ComplaintUpdates.objects.filter(
        complaint=complaint
    ).select_related("updated_by").order_by("-updated_at")

    assigned_officials = HearingOfficials.objects.filter(
        complaint=complaint
    ).select_related("user_officials")

    admin_users = Users.objects.filter(
        user_type__type_name="Admin",
        is_active=True
    ).select_related("position")

    certificate = CertificateToFileAction.objects.filter(complaint=complaint).first()

    attendance_records = HearingAttendance.objects.filter(
        hearing__complaint=complaint
    ).select_related("hearing")

    hearings_completed = all_hearings.filter(status__statustype="Completed").count()

    if request.method == "POST":
        action = request.POST.get("action")
        case_number = complaint.case_number or generate_case_number(complaint.complaintsid)

        # STEP 2: Initial Review outcome
        if action == "refer_jurisdiction":
            target_barangay = request.POST.get("target_barangay", "").strip()
            if not target_barangay:
                messages.error(request, "Please specify the proper barangay.")
                return redirect("case_detail", complaint_id=complaint.complaintsid)

            complaint.jurisdiction_barangay = target_barangay
            apply_status_change(
                complaint, "Referred to Proper Barangay", current_admin,
                remarks=f"Referred to {target_barangay}.",
                log_action="Refer Complaint to Proper Barangay",
            )
            sms_body = build_sms_for_status(
                "Referred to Proper Barangay", case_number, jurisdiction=target_barangay
            )
            if sms_body and complaint.complainant_user and complaint.complainant_user.contactno:
                queue_sms(complaint.complainant_user.contactno, sms_body, sent_by=current_admin)
            messages.success(request, "Complaint referred to proper barangay.")

        elif action == "mark_recorded":
            if complaint.status == "Ongoing":
                messages.warning(request, "Complaint is already marked as Ongoing.")
                return redirect("case_detail", complaint_id=complaint.complaintsid)

            complaint_type_id = request.POST.get("complaint_type", "").strip()
            if not complaint_type_id:
                messages.error(request, "Please classify the complaint as Incident or Blotter before proceeding.")
                return redirect("case_detail", complaint_id=complaint.complaintsid)

            try:
                chosen_type = ComplaintType.objects.get(ctid=complaint_type_id)
            except ComplaintType.DoesNotExist:
                messages.error(request, "Invalid complaint type selected.")
                return redirect("case_detail", complaint_id=complaint.complaintsid)

            complaint.complaint_type = chosen_type
            complaint.save(update_fields=["complaint_type"])

            apply_status_change(
                complaint, "Ongoing", current_admin,
                remarks=f"Classified as {chosen_type.type} and recorded by Chairman.",
                log_action="Classify Complaint and Record (Chairman Review)",
            )

            sms_body = build_sms_for_status("Ongoing", case_number)

            if sms_body and complaint.complainant_user and complaint.complainant_user.contactno:
                queue_sms(
                    complaint.complainant_user.contactno,
                    sms_body,
                    sent_by=current_admin
                )

            messages.success(request, f"Complaint classified as {chosen_type.type} and marked as Ongoing.")

        # STEP 4: Schedule Mediation
        elif action == "schedule_mediation":
            hearing_date_raw = request.POST.get("hearing_date", "").strip()
            lupon_user_id = request.POST.get("lupon_user_id", "").strip()

            if not hearing_date_raw:
                messages.error(request, "Please provide a mediation date/time.")
                return redirect("case_detail", complaint_id=complaint.complaintsid)

            hearing_date = parse_datetime(hearing_date_raw)
            if hearing_date and timezone.is_naive(hearing_date):
                hearing_date = timezone.make_aware(hearing_date)
            if not hearing_date:
                messages.error(request, "Invalid mediation date/time format.")
                return redirect("case_detail", complaint_id=complaint.complaintsid)

            mediation_level = HearingLevel.objects.filter(level_type="Mediation").first()
            scheduled_status = HearingStatus.objects.filter(statustype="Scheduled").first()

            if not mediation_level or not scheduled_status:
                messages.error(
                    request,
                    "HearingLevel 'Mediation' or HearingStatus 'Scheduled' not found. "
                    "Run the lookup table inserts from Section 9.1 first."
                )
                return redirect("case_detail", complaint_id=complaint.complaintsid)

            hearing = ComplaintHearing.objects.create(
                complaint=complaint,
                hearing_level=mediation_level,
                hearing_date=hearing_date,
                status=scheduled_status,
                created_at=timezone.now(),
            )

            if lupon_user_id:
                lupon_user = Users.objects.filter(userid=lupon_user_id).first()
                if lupon_user:
                    HearingOfficials.objects.get_or_create(
                        complaint=complaint,
                        user_officials=lupon_user,
                        defaults={"role": "Lupon Member"},
                    )

            apply_status_change(
                complaint, "Mediation Scheduled", current_admin,
                remarks=f"Mediation scheduled for {hearing.hearing_date}.",
                log_action="Schedule Mediation",
            )

            sms_body = build_sms_for_status(
                "Mediation Scheduled", case_number, hearing_date=hearing.hearing_date
            )
            for party_contact in _complaint_contact_numbers(complaint):
                queue_sms(party_contact, sms_body, sent_by=current_admin)

            messages.success(request, "Mediation scheduled.")

        # STEP 5: First Mediation Session outcome
        elif action == "record_mediation_outcome":
            outcome = request.POST.get("outcome", "").strip()  # "Settled" or "Not Settled"

            mediation_hearing = all_hearings.filter(hearing_level__level_type="Mediation").last()
            completed_status = HearingStatus.objects.filter(statustype="Completed").first()
            if mediation_hearing and completed_status:
                mediation_hearing.status = completed_status
                mediation_hearing.outcome = outcome
                mediation_hearing.save()

            if outcome == "Settled":
                complaint.settlement_date = timezone.now()
                apply_status_change(
                    complaint, "Settled", current_admin,
                    remarks="Settled during mediation.",
                    log_action="Record Mediation Settlement",
                )
                sms_body = build_sms_for_status("Settled", case_number)
            else:
                apply_status_change(
                    complaint, "For 1st Hearing", current_admin,
                    remarks="No agreement reached in mediation. Proceeding to Hearing 1.",
                    log_action="Mediation Failed - Escalate to Hearing 1",
                )
                sms_body = build_sms_for_status("For 1st Hearing", case_number)

            if sms_body:
                for party_contact in _complaint_contact_numbers(complaint):
                    queue_sms(party_contact, sms_body, sent_by=current_admin)

            messages.success(request, f"Mediation outcome recorded: {outcome}.")

        # STEP 6: Schedule a numbered hearing (1, 2, or 3)
        elif action == "schedule_hearing":
            hearing_number = request.POST.get("hearing_number", "").strip()  # "1", "2", "3"
            hearing_date_raw = request.POST.get("hearing_date", "").strip()

            # The lookup table stores full descriptive labels rather than
            # plain "Hearing N", map the number to the exact level_type
            # text instead of building the string from hearing_number.
            HEARING_LEVEL_BY_NUMBER = {
                "1": "1st Hearing - Lupong Tagapamayapa (Chairman Present)",
                "2": "2nd Hearing - Lupong Tagapamayapa (Same Lupons, Chairman Present)",
                "3": "3rd Hearing - Pangkat ng Tagapagkasundo (Lupon Chairman Appointed, No Chairman)",
            }
            status_label = f"For {hearing_number}{'st' if hearing_number == '1' else 'nd' if hearing_number == '2' else 'rd'} Hearing"

            if not hearing_date_raw or hearing_number not in ("1", "2", "3"):
                messages.error(request, "Please provide a valid hearing number (1-3) and date.")
                return redirect("case_detail", complaint_id=complaint.complaintsid)

            hearing_date = parse_datetime(hearing_date_raw)
            if hearing_date and timezone.is_naive(hearing_date):
                hearing_date = timezone.make_aware(hearing_date)
            if not hearing_date:
                messages.error(request, "Invalid hearing date/time format.")
                return redirect("case_detail", complaint_id=complaint.complaintsid)

            level_name = HEARING_LEVEL_BY_NUMBER[hearing_number]
            hearing_level = HearingLevel.objects.filter(level_type=level_name).first()
            scheduled_status = HearingStatus.objects.filter(statustype="Scheduled").first()

            if not hearing_level or not scheduled_status:
                messages.error(request, f"HearingLevel '{level_name}' not found in lookup table.")
                return redirect("case_detail", complaint_id=complaint.complaintsid)

            hearing = ComplaintHearing.objects.create(
                complaint=complaint,
                hearing_level=hearing_level,
                hearing_date=hearing_date,
                status=scheduled_status,
                created_at=timezone.now(),
            )

            apply_status_change(
                complaint, status_label, current_admin,
                remarks=f"{level_name} scheduled for {hearing.hearing_date}.",
                log_action=f"Schedule {level_name}",
            )

            sms_body = build_sms_for_status(status_label, case_number, hearing_date=hearing.hearing_date)
            for party_contact in _complaint_contact_numbers(complaint):
                queue_sms(party_contact, sms_body, sent_by=current_admin)

            messages.success(request, f"{level_name} scheduled.")

        # Record attendance + outcome for a specific hearing
        elif action == "record_hearing_outcome":
            hearing_id = request.POST.get("hearing_id", "").strip()
            outcome = request.POST.get("outcome", "").strip()
            complainant_attendance = request.POST.get("complainant_attendance", "").strip()
            respondent_attendance = request.POST.get("respondent_attendance", "").strip()

            try:
                hearing = ComplaintHearing.objects.get(chid=hearing_id, complaint=complaint)
            except ComplaintHearing.DoesNotExist:
                messages.error(request, "Hearing record not found.")
                return redirect("case_detail", complaint_id=complaint.complaintsid)

            # "Rescheduled" (postponement): keep the hearing's status as Scheduled
            # rather than Completed, since the hearing itself didn't happen yet.
            # This does NOT advance the case past the current "For Nth Hearing"
            # status and does NOT count toward the 3-hearing limit, per the
            # documented process ("Possible postponements" is a distinct outcome
            # from a hearing actually occurring and failing).
            if outcome == "Rescheduled":
                hearing.outcome = "Rescheduled"
                hearing.save()

                ComplaintUpdates.objects.create(
                    complaint=complaint, updated_by=current_admin,
                    status=complaint.status,
                    remarks=f"{hearing.hearing_level.level_type} postponed/rescheduled. {remarks}".strip(),
                    updated_at=timezone.now(),
                )
                messages.success(request, "Hearing marked as rescheduled. Please set a new date.")
                return redirect("case_detail", complaint_id=complaint.complaintsid)

            completed_status = HearingStatus.objects.filter(statustype="Completed").first()
            hearing.status = completed_status or hearing.status
            hearing.outcome = outcome
            hearing.save()

            if complainant_attendance:
                HearingAttendance.objects.create(
                    hearing=hearing, participant_type="Complainant",
                    attendance_status=complainant_attendance,
                )
            if respondent_attendance:
                HearingAttendance.objects.create(
                    hearing=hearing, participant_type="Respondent",
                    attendance_status=respondent_attendance,
                )

            # Failed Attendance Tracking — flag non-cooperative party
            unexcused_count = HearingAttendance.objects.filter(
                hearing__complaint=complaint,
                participant_type="Respondent",
                attendance_status="Refused",
            ).count()
            if unexcused_count >= 2 and not complaint.non_cooperative_party:
                complaint.non_cooperative_party = "Respondent"
                complaint.non_cooperative_flagged_at = timezone.now()
                complaint.save(update_fields=["non_cooperative_party", "non_cooperative_flagged_at"])
                AuditLogs.objects.create(
                    user=current_admin, action="Flag Non-Cooperative Party",
                    module_name="Cases", table_name="Complaints",
                    record_id=complaint.complaintsid,
                    new_value="Respondent flagged as non-cooperative after repeated unexcused absences.",
                    created_at=timezone.now(),
                )
                messages.warning(
                    request,
                    "Respondent flagged as Non-Cooperative Party due to repeated absences. "
                    "A Certificate to File Action may now be justified."
                )

            if outcome == "Settled":
                complaint.settlement_date = timezone.now()
                apply_status_change(
                    complaint, "Settled", current_admin,
                    remarks=f"Settled at {hearing.hearing_level.level_type}.",
                    log_action="Record Hearing Settlement",
                )
                sms_body = build_sms_for_status("Settled", case_number)
                if sms_body:
                    for party_contact in _complaint_contact_numbers(complaint):
                        queue_sms(party_contact, sms_body, sent_by=current_admin)

            elif outcome == "Not Settled":

                level = hearing.hearing_level.level_type

            # Hearing 1 → Hearing 2
            if level == "1st Hearing - Lupong Tagapamayapa (Chairman Present)":

                apply_status_change(
                    complaint,
                    "For 2nd Hearing",
                    current_admin,
                    remarks="No settlement reached during Hearing 1. Proceeding to Hearing 2.",
                    log_action="Advance to Hearing 2",
                )

                sms_body = build_sms_for_status("For 2nd Hearing", case_number)

            # Hearing 2 → Hearing 3
            elif level == "2nd Hearing - Lupong Tagapamayapa (Same Lupons, Chairman Present)":

                apply_status_change(
                    complaint,
                    "For 3rd Hearing",
                    current_admin,
                    remarks="No settlement reached during Hearing 2. Proceeding to Hearing 3.",
                    log_action="Advance to Hearing 3",
                )

                sms_body = build_sms_for_status("For 3rd Hearing", case_number)

            # Hearing 3 → Certificate
            elif level == "3rd Hearing - Pangkat ng Tagapagkasundo (Lupon Chairman Appointed, No Chairman)":

                apply_status_change(
                    complaint,
                    "Eligible for Certificate to File Action",
                    current_admin,
                    remarks="No settlement reached after the 3rd hearing.",
                    log_action="Eligible for Certificate to File Action",
                )

                sms_body = build_sms_for_status(
                    "Eligible for Certificate to File Action",
                    case_number,
                )

            if sms_body:
                for party_contact in _complaint_contact_numbers(complaint):
                    queue_sms(
                        party_contact,
                        sms_body,
                        sent_by=current_admin,
                    )

            messages.success(request, "Hearing outcome recorded.")

        # Issue Certificate to File Action
        elif action == "issue_certificate":
            remarks = request.POST.get("remarks", "").strip()

            if complaint.status != "Eligible for Certificate to File Action":
                messages.error(
                    request,
                    "Certificate can only be issued when status is 'Eligible for Certificate to File Action'."
                )
                return redirect("case_detail", complaint_id=complaint.complaintsid)

            if CertificateToFileAction.objects.filter(complaint=complaint).exists():
                messages.warning(request, "A certificate was already issued for this complaint.")
                return redirect("case_detail", complaint_id=complaint.complaintsid)

            cert = CertificateToFileAction.objects.create(
                complaint=complaint,
                certificate_no="TEMP",
                issued_by=current_admin,
                issued_at=timezone.now(),
            )
            cert.certificate_no = generate_certificate_number(cert.cfaid)
            cert.save(update_fields=["certificate_no"])

            apply_status_change(
                complaint, "Certificate Issued", current_admin,
                remarks=f"Certificate {cert.certificate_no} issued.",
                log_action="Issue Certificate to File Action",
            )

            sms_body = build_sms_for_status("Certificate Issued", case_number)
            if sms_body and complaint.complainant_user and complaint.complainant_user.contactno:
                queue_sms(complaint.complainant_user.contactno, sms_body, sent_by=current_admin)

            messages.success(request, f"Certificate {cert.certificate_no} issued.")

        # External Resolution (either "Resolved Outside Barangay" or "Settled in Court")
        elif action == "record_external_resolution":
            ext_status = request.POST.get("external_status", "").strip()  # "Resolved Outside Barangay" or "Settled in Court"
            ext_notes = request.POST.get("external_notes", "").strip()
            ext_date = request.POST.get("external_date", "").strip()

            if ext_status not in ("Resolved Outside Barangay", "Settled in Court"):
                messages.error(request, "Invalid external resolution status.")
                return redirect("case_detail", complaint_id=complaint.complaintsid)

            complaint.external_resolution_notes = ext_notes or None
            complaint.external_resolution_date = ext_date or None
            complaint.save(update_fields=["external_resolution_notes", "external_resolution_date"])

            apply_status_change(
                complaint, ext_status, current_admin,
                remarks=ext_notes or "Resolved outside the barangay process.",
                log_action="Record External Resolution",
            )

            messages.success(request, "External resolution recorded.")

        # Existing simple status changes (kept for flexibility)
        elif action in ("resolve", "review", "dismiss"):
            remarks = request.POST.get("remarks", "").strip()
            status_map = {
                "resolve": "Settled",
                "review": "Under Review",
                "dismiss": "Dismissed",
            }
            log_action_map = {
                "resolve": "Settle Case", "review": "Mark Case Under Review", "dismiss": "Dismiss Case"
            }
            new_status = status_map[action]
            apply_status_change(
                complaint, new_status, current_admin, remarks=remarks, log_action=log_action_map[action]
            )
            sms_body = build_sms_for_status(new_status, case_number)
            if sms_body and complaint.complainant_user and complaint.complainant_user.contactno:
                queue_sms(complaint.complainant_user.contactno, sms_body, sent_by=current_admin)
            messages.success(request, "Case status updated successfully.")

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

            already_assigned = HearingOfficials.objects.filter(
                complaint=complaint, user_officials=official_user
            ).exists()

            sms_body = None

            if already_assigned:
                messages.warning(request, "This official is already assigned to this case.")
            else:
                HearingOfficials.objects.create(
                    complaint=complaint, user_officials=official_user, role=official_role,
                )
                AuditLogs.objects.create(
                    user=current_admin, action="Assign Official",
                    module_name="Cases", table_name="HearingOfficials",
                    record_id=complaint.complaintsid,
                    new_value=f"Official '{official_user.firstname} {official_user.lastname}' assigned.",
                    created_at=timezone.now(),
                )

                sms_body = (
                    f"KaugnayPH: A barangay official has been assigned "
                    f"to your complaint {case_number}. "
                    "Please check your account for updates."
                )
                messages.success(request, "Official assigned successfully.")

            if sms_body and complaint.complainant_user and complaint.complainant_user.contactno:
                queue_sms(
                    complaint.complainant_user.contactno,
                    sms_body,
                    sent_by=current_admin
                )

        elif action == "remove_official":
            hoid = request.POST.get("hoid", "").strip()
            try:
                ho = HearingOfficials.objects.get(hoid=hoid, complaint=complaint)
                ho.delete()
                messages.success(request, "Official removed.")
            except HearingOfficials.DoesNotExist:
                messages.error(request, "Official record not found.")

        # Add a free-text case note (admin-side log entry, no status change)
        elif action == "add_note":
            note_text = request.POST.get("note_text", "").strip()
            if not note_text:
                messages.error(request, "Note cannot be empty.")
                return redirect("case_detail", complaint_id=complaint.complaintsid)

            ComplaintUpdates.objects.create(
                complaint=complaint, updated_by=current_admin,
                status=complaint.status,
                remarks=note_text,
                updated_at=timezone.now(),
            )
            messages.success(request, "Note added.")

        else:
            messages.error(request, "Invalid action.")

        return redirect("case_detail", complaint_id=complaint.complaintsid)

    # Complainee has no linked Users FK (free-text only on Complaints model),
    # so there is no contact number to display -- the detail template shows
    # an explicit "Not on file" fallback instead of leaving the field blank.
    complainee_contact = "Not on file"

    return render(request, "adminpanel/case_detail.html", {
        "complaint":           complaint,
        "user":                current_admin,
        "case_id":             complaint.case_number or generate_case_number(complaint.complaintsid),
        "complaint_updates":   complaint_updates,
        "hearing_levels":      hearing_levels,
        "hearing_statuses":    hearing_statuses,
        "existing_hearing":    existing_hearing,
        "all_hearings":        all_hearings,
        "attendance_records":  attendance_records,
        "assigned_officials":  assigned_officials,
        "admin_users":         admin_users,
        "certificate":         certificate,
        "hearings_completed":  hearings_completed,
        "complaint_types":     complaint_types,
        "complainee_contact":  complainee_contact,
    })


def _complaint_contact_numbers(complaint):
    """
    Returns a list of contact numbers to SMS for case-wide notifications
    (mediation/hearing schedules, settlements). Currently only the
    complainant has a linked Users record with a phone number — the
    respondent (complainee) is stored as a free-text name/address on
    Complaints.complainee, not a Users FK, so there's no number to
    message on their side yet.
    """
    numbers = []
    if complaint.complainant_user and complaint.complainant_user.contactno:
        numbers.append(complaint.complainant_user.contactno)
    return numbers

#admin inquiry view
@admin_login_required
@permission_required("view_inquiries")
def admin_inquiries_view(request):
    from django.core.paginator import Paginator

    search_query = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "All").strip()
    category_filter = request.GET.get("category", "All").strip()
    date_to = request.GET.get("date_to", "").strip()

    inquiries = Inquiry.objects.all()

    if search_query:
        inquiries = inquiries.filter(
            Q(firstname__icontains=search_query) |
            Q(lastname__icontains=search_query) |
            Q(messagesubject__icontains=search_query) |
            Q(contactno__icontains=search_query)
        )

    if status_filter != "All":
        inquiries = inquiries.filter(status=status_filter)

    if category_filter != "All":
        if category_filter == "Uncategorized":
            inquiries = inquiries.filter(faq_category__isnull=True)
        else:
            inquiries = inquiries.filter(faq_category_id=category_filter)

    if date_to:
        selected_date = parse_date(date_to)

        if selected_date:
            start = timezone.make_aware(datetime.combine(selected_date, time.min))
            end = timezone.make_aware(datetime.combine(selected_date, time.max))

            inquiries = inquiries.filter(
                created_at__range=(start, end)
            )

    inquiries = inquiries.order_by("-created_at")

    records = []
    for inq in inquiries:
        sla = get_sla_for_record("Inquiry", inq.cuid)
        records.append({
            "obj": inq,
            "sla": sla,
            "sla_status": get_sla_status_live(sla),
        })

    paginator = Paginator(records, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "adminpanel/inquiries_list.html", {
        "records": page_obj,
        "page_obj": page_obj,
        "user": get_current_user(request),

        "search_query": search_query,
        "status_filter": status_filter,
        "category_filter": category_filter,
        "date_to": date_to,

        "categories": FAQCategories.objects.all(),

        "total": inquiries.count(),
        "new_count": Inquiry.objects.filter(status="New").count(),
        "pending_count": Inquiry.objects.filter(status="Pending").count(),
        "replied_count": Inquiry.objects.filter(status="Replied").count(),
    })

# admin inquiry detail
@admin_login_required
@permission_required("view_inquiries")
def admin_inquiry_detail_view(request, cuid):
    try:
        inquiry = Inquiry.objects.select_related(
            "user",
            "replied_byuser",
            "faq_category"
        ).get(cuid=cuid)
    except Inquiry.DoesNotExist:
        messages.error(request, "Inquiry not found.")
        return redirect("admin_inquiries")

    current_admin = get_current_user(request)
    sla = get_sla_for_record("Inquiry", cuid)
    categories = FAQCategories.objects.all()

    if request.method == "GET" and inquiry.status == "New":
        inquiry.status = "Pending"
        inquiry.save()

    if request.method == "POST":
        action = request.POST.get("action")
        admin_reply = request.POST.get("admin_reply", "").strip()
        category_id = request.POST.get("faq_category")

        if action == "reply":
            if not category_id:
                messages.error(request, "Please select an inquiry category before sending a reply.")
                return redirect("admin_inquiry_detail", cuid=inquiry.cuid)

            if not admin_reply:
                messages.error(request, "Reply cannot be empty.")
                return redirect("admin_inquiry_detail", cuid=inquiry.cuid)

            inquiry.faq_category_id = category_id
            inquiry.admin_reply = admin_reply
            inquiry.replied_at = timezone.now()
            inquiry.replied_byuser = current_admin
            inquiry.status = "Replied"
            inquiry.save()

            record_first_response("Inquiry", inquiry.cuid)
            resolve_sla("Inquiry", inquiry.cuid)

            sms_reply = f"KaugnayPH Reply: {admin_reply}"

            send_sms_with_warning(
                request,
                inquiry.contactno,
                sms_reply,
                sent_by=current_admin,
            )

            AuditLogs.objects.create(
                user=current_admin,
                action="Reply to Inquiry",
                module_name="Inquiry",
                table_name="Inquiry",
                record_id=inquiry.cuid,
                new_value=f"Replied by {current_admin.username}; Category: {inquiry.faq_category}",
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
        "inquiry": inquiry,
        "sla": sla,
        "sla_status": get_sla_status_live(sla),
        "user": current_admin,
        "categories": categories,
    })

#admin add inquiry to faq
@admin_login_required
@permission_required(
    "view_inquiries",
    "reply_inquiries"    
)
def add_inquiry_to_faq(request, inquiry_id):
    inquiry = get_object_or_404(Inquiry, cuid=inquiry_id)

    if not inquiry.admin_reply or not inquiry.admin_reply.strip():
        messages.error(request, "Please send a reply first before adding this inquiry to FAQs.")
        return redirect("admin_inquiry_detail", cuid=inquiry.cuid)

    query_params = {
        "question": inquiry.messagesubject or "",
        "answer": inquiry.admin_reply or "",
    }

    if inquiry.faq_category_id:
        query_params["category"] = inquiry.faq_category_id

    url = reverse("admin_add_faq") + "?" + urlencode(query_params)

    return redirect(url)

@admin_login_required
@permission_required("view_audit_logs")
def audit_logs_view(request):
    from django.core.paginator import Paginator

    current_user = get_current_user(request)

    search_query = request.GET.get("search", "").strip()
    module_filter = request.GET.get("module", "All").strip()
    action_filter = request.GET.get("action", "All").strip()
    date_filter = request.GET.get("date", "").strip()

    logs = AuditLogs.objects.select_related("user").filter(
        user__user_type__type_name="Admin"
    )

    if search_query:
        logs = logs.filter(
            Q(action__icontains=search_query) |
            Q(module_name__icontains=search_query) |
            Q(table_name__icontains=search_query) |
            Q(new_value__icontains=search_query) |
            Q(old_value__icontains=search_query) |
            Q(user__firstname__icontains=search_query) |
            Q(user__lastname__icontains=search_query) |
            Q(user__username__icontains=search_query)
        )

    if module_filter != "All":
        logs = logs.filter(module_name=module_filter)

    if action_filter != "All":
        logs = logs.filter(action=action_filter)

    if date_filter:
        selected_date = parse_date(date_filter)

        if selected_date:
            start = timezone.make_aware(datetime.combine(selected_date, time.min))
            end = timezone.make_aware(datetime.combine(selected_date, time.max))

            logs = logs.filter(
                created_at__range=(start, end)
            )

    logs = logs.order_by("-created_at")

    base_logs = AuditLogs.objects.filter(
        user__user_type__type_name="Admin"
    )

    modules = base_logs.exclude(
        module_name__isnull=True
    ).exclude(
        module_name=""
    ).values_list("module_name", flat=True).distinct().order_by("module_name")

    actions = base_logs.exclude(
        action__isnull=True
    ).exclude(
        action=""
    ).values_list("action", flat=True).distinct().order_by("action")

    paginator = Paginator(logs, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "adminpanel/audit_logs.html", {
        "logs": page_obj,
        "page_obj": page_obj,
        "user": current_user,
        "search_query": search_query,
        "module_filter": module_filter,
        "action_filter": action_filter,
        "date_filter": date_filter,
        "modules": modules,
        "actions": actions,
        "total": logs.count(),
    })

# ADMIN FAQS VIEW
@admin_login_required
@permission_required("view_inquiries")
def admin_faqs(request):
    from django.core.paginator import Paginator

    search = request.GET.get("search", "").strip()
    category_filter = request.GET.get("category", "All").strip()
    status_filter = request.GET.get("status", "All").strip()

    faqs = FAQs.objects.select_related(
        "faq_category",
        "created_by"
    ).all()

    if search:
        faqs = faqs.filter(
            Q(question__icontains=search) |
            Q(answer__icontains=search) |
            Q(faq_category__category_name__icontains=search)
        )

    if category_filter != "All":
        faqs = faqs.filter(faq_category_id=category_filter)

    if status_filter == "Active":
        faqs = faqs.filter(is_active=True)
    elif status_filter == "Inactive":
        faqs = faqs.filter(is_active=False)

    faqs = faqs.order_by("-updated_at")

    all_faqs = FAQs.objects.all()

    paginator = Paginator(faqs, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "adminpanel/admin_faqs.html", {
        "faqs": page_obj,
        "page_obj": page_obj,
        "search": search,
        "category_filter": category_filter,
        "status_filter": status_filter,
        "categories": FAQCategories.objects.all(),
        "total_faqs": all_faqs.count(),
        "active_faqs": all_faqs.filter(is_active=True).count(),
        "inactive_faqs": all_faqs.filter(is_active=False).count(),
        "user": get_current_user(request),
    })

#ADMIN ADD FAQ
@admin_login_required
@permission_required("reply_inquiries")
def admin_add_faq(request):
    categories = FAQCategories.objects.all()

    if request.method == 'POST':
        current_user = get_current_user(request)

        faq = FAQs.objects.create(
            faq_category_id=request.POST.get('category'),
            question=request.POST.get('question'),
            answer=request.POST.get('answer'),
            created_by=current_user,
            created_at=timezone.now(),
            updated_at=timezone.now(),
            is_active=True
        )

        AuditLogs.objects.create(
            user=current_user,
            action="Create FAQ",
            module_name="FAQs",
            table_name="FAQs",
            record_id=faq.faq_id,
            new_value=f"Question: {faq.question}",
            created_at=timezone.now(),
        )

        messages.success(request, 'FAQ added successfully.')
        return redirect('admin_faqs')

    prefill_question = request.GET.get('question', '')
    prefill_answer = request.GET.get('answer', '')
    prefill_category = request.GET.get('category', '')

    return render(request, 'adminpanel/admin_faq_form.html', {
        'categories': categories,
        'faq': None,
        'prefill_question': prefill_question,
        'prefill_answer': prefill_answer,
        'prefill_category': prefill_category,
    })

#ADMIN EDIT FAQ
@admin_login_required
@permission_required("reply_inquiries")
def admin_edit_faq(request, faq_id):
    faq = get_object_or_404(FAQs, faq_id=faq_id)
    categories = FAQCategories.objects.all()

    if request.method == 'POST':
        current_user = get_current_user(request)

        faq.faq_category_id = request.POST.get('category')
        faq.question = request.POST.get('question')
        faq.answer = request.POST.get('answer')
        faq.updated_at = timezone.now()
        faq.save()

        AuditLogs.objects.create(
            user=current_user,
            action="Update FAQ",
            module_name="FAQs",
            table_name="FAQs",
            record_id=faq.faq_id,
            new_value=f"Question: {faq.question}",
            created_at=timezone.now(),
        )

        messages.success(request, 'FAQ updated successfully.')
        return redirect('admin_faqs')

    return render(request, 'adminpanel/admin_faq_form.html', {
        'categories': categories,
        'faq': faq
    })


@admin_login_required
@permission_required("reply_inquiries")
def admin_toggle_faq(request, faq_id):
    faq = get_object_or_404(FAQs, faq_id=faq_id)

    current_user = get_current_user(request)

    faq.is_active = not faq.is_active
    faq.updated_at = timezone.now()
    faq.save()

    AuditLogs.objects.create(
        user=current_user,
        action="Activate FAQ" if faq.is_active else "Deactivate FAQ",
        module_name="FAQs",
        table_name="FAQs",
        record_id=faq.faq_id,
        new_value=f"Question: {faq.question}",
        created_at=timezone.now(),
    )

    if faq.is_active:
        messages.success(request, 'FAQ activated successfully.')
    else:
        messages.success(request, 'FAQ deactivated successfully.')

    return redirect('admin_faqs')

# ADMIN REGISTER / ADMIN LIST
@admin_login_required
@permission_required('create_users')
def admins_list_view(request):
    from django.core.paginator import Paginator

    search_query = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "All").strip()
    position_filter = request.GET.get("position", "All").strip()

    admins = Users.objects.filter(
        user_type__type_name="Admin"
    ).select_related(
        "role",
        "position"
    )

    if search_query:
        admins = admins.filter(
            Q(firstname__icontains=search_query) |
            Q(lastname__icontains=search_query) |
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(position__name__icontains=search_query)
        )

    if status_filter == "Active":
        admins = admins.filter(is_active=True)
    elif status_filter == "Inactive":
        admins = admins.filter(is_active=False)

    if position_filter != "All":
        admins = admins.filter(position__name=position_filter)

    admins = admins.order_by(
        "role__roleid",
        "lastname",
        "firstname"
    )

    all_admins = Users.objects.filter(user_type__type_name="Admin")

    positions = all_admins.exclude(
        position__isnull=True
    ).values_list(
        "position__name", flat=True
    ).distinct().order_by("position__name")

    paginator = Paginator(admins, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    for a in page_obj:
        a.display_name = format_full_name(a.lastname, a.firstname)
        a.masked_contact = mask_contact(a.contactno)
        a.masked_email = mask_email(a.email)

    context = {
        "admins": page_obj,
        "page_obj": page_obj,
        "search_query": search_query,
        "status_filter": status_filter,
        "position_filter": position_filter,
        "positions": positions,
        "total_admins": all_admins.count(),
        "active_admins": all_admins.filter(is_active=True).count(),
        "inactive_admins": all_admins.filter(is_active=False).count(),
        "user": get_current_user(request),
    }

    return render(request, "adminpanel/admins_list.html", context)

#ADMIN SMS OUTBOX 
@admin_login_required
@permission_required("view_sms_outbox")
def sms_outbox_view(request):

    search_query = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "All")
    date_filter = request.GET.get("date", "").strip()

    sms_list = SMSOutbox.objects.select_related(
        "sent_by"
    ).order_by("-sent_at")

    if search_query:
        sms_list = sms_list.annotate(
            sender_full_name=Concat(
                "sent_by__firstname",
                Value(" "),
                "sent_by__lastname"
            )
        )

        search_filter = (
            Q(recipient_number__icontains=search_query) |
            Q(message__icontains=search_query) |
            Q(sent_by__firstname__icontains=search_query) |
            Q(sent_by__lastname__icontains=search_query) |
            Q(sent_by__username__icontains=search_query) |
            Q(sender_full_name__icontains=search_query)
        )

        if "system" in search_query.lower():
            search_filter |= Q(sent_by__isnull=True)

        sms_list = sms_list.filter(search_filter)

    if status_filter != "All":
        sms_list = sms_list.filter(status__iexact=status_filter)

    if date_filter:
        try:
            selected_date = datetime.strptime(
                date_filter,
                "%Y-%m-%d"
            ).date()

            manila_timezone = ZoneInfo("Asia/Manila")

            start_of_day = datetime.combine(
                selected_date,
                time.min,
                tzinfo=manila_timezone
            )

            end_of_day = start_of_day + timedelta(days=1)

            sms_list = sms_list.filter(
                sent_at__gte=start_of_day,
                sent_at__lt=end_of_day
            )

        except ValueError:
            pass

    paginator = Paginator(sms_list, 10)

    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    
    for sms in page_obj:
        sms.masked_recipient = mask_contact(sms.recipient_number)
        sms.masked_message = mask_sms_message(sms.message)

    return render(
        request,
        "adminpanel/SMS_outbox.html",
        {
            "page_obj": page_obj,
            "search_query": search_query,
            "status_filter": status_filter,
            "date_filter": date_filter,
            "statuses": [
                "Pending",
                "Processing",
                "Sent",
                "Failed",
            ],
        },
    )


# ADMIN SETTINGS PAGE
@admin_login_required
def settings_page(request):
    current_user = get_current_user(request)

    recent_login_activity = AuditLogs.objects.filter(
        user=current_user,
        module_name="Authentication",
        action__in=["Admin Login", "Failed Admin Login"]
    ).order_by("-created_at")[:10]

    last_password_change = AuditLogs.objects.filter(
        user=current_user,
        action="Changed Password"
    ).order_by("-created_at").first()

    return render(request, "adminpanel/settings_page.html", {
        "current_user": current_user,
        "recent_login_activity": recent_login_activity,
        "last_password_change": last_password_change,
        "avatars": AvatarOptions.objects.filter(
            is_active=True
        ).order_by("avatarid"),

        "display_name": format_full_name(
        current_user.lastname,
        current_user.firstname
        ),
        "masked_contact": mask_contact(current_user.contactno),
        "masked_email": mask_email(current_user.email),
    })

#ADMIN CHANGE PASSWORD
@admin_login_required
def admin_change_password(request):
    if request.method != "POST":
        return redirect("settings_page")

    current_user = get_current_user(request)

    current_password = request.POST.get("current_password", "").strip()
    new_password = request.POST.get("new_password", "").strip()
    confirm_password = request.POST.get("confirm_password", "").strip()

    if not check_password(current_password, current_user.password):
        messages.error(request, "Current password is incorrect.")
        return redirect("settings_page")

    if new_password != confirm_password:
        messages.error(request, "New password and confirm password do not match.")
        return redirect("settings_page")

    if len(new_password) < 8:
        messages.error(request, "Password must be at least 8 characters long.")
        return redirect("settings_page")

    if check_password(new_password, current_user.password):
        messages.error(request, "Your new password must be different from your current password.")
        return redirect("settings_page")

    current_user.password = hash_password(new_password)
    current_user.is_password_changed = True
    current_user.save()

    AuditLogs.objects.create(
        user=current_user,
        action="Changed Password",
        module_name="Settings",
        table_name="Users",
        record_id=current_user.userid,
        old_value="Password changed",
        new_value="Password updated",
        ip_address=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT"),
        created_at=timezone.now(),
    )

    messages.success(request, "Password changed successfully.")
    return redirect("settings_page")

#ADMIN UPDATE CONTACT START
@admin_login_required
def admin_update_contact_start(request):
    if request.method != "POST":
        return redirect("settings_page")

    current_user = get_current_user(request)

    password = request.POST.get("password", "").strip()
    new_contact = request.POST.get("new_contact", "").strip()

    if not check_password(password, current_user.password):
        messages.error(request, "Password is incorrect.")
        return redirect("settings_page")

    if not new_contact.isdigit() or len(new_contact) != 11 or not new_contact.startswith("09"):
        messages.error(request, "Please enter a valid 11-digit contact number starting with 09.")
        return redirect("settings_page")

    if new_contact == current_user.contactno:
        messages.error(request, "New contact number must be different from your current contact number.")
        return redirect("settings_page")

    request.session["pending_new_contact"] = new_contact

    otp, cooldown = generate_otp(current_user, purpose="change_contact")

    if cooldown:
        mins = cooldown // 60
        secs = cooldown % 60
        messages.error(request, f"Please wait {mins}m {secs}s before requesting another OTP.")
        return redirect("settings_page")

    sms_sent = send_sms(
        new_contact,
        f"KaugnayPH OTP: {otp.code}. Use this to verify your new contact number. Valid for 5 minutes.",
        sent_by=current_user
    )

    if not sms_sent:
        messages.error(request, "Failed to send OTP to the new contact number. Please try again.")
        return redirect("settings_page")

    request.session.pop("show_email_otp_modal", None)
    request.session["show_contact_otp_modal"] = True
    messages.success(request, "OTP has been sent to your new contact number.")
    return redirect("settings_page")

#ADMIN UPDATE CONTACT VERIFY
@admin_login_required
def admin_update_contact_verify(request):
    if request.method != "POST":
        return redirect("settings_page")

    current_user = get_current_user(request)

    pending_new_contact = request.session.get("pending_new_contact")
    otp_code = request.POST.get("otp_code", "").strip()

    if not pending_new_contact:
        messages.error(request, "No pending contact number update found.")
        return redirect("settings_page")

    if not otp_code or len(otp_code) != 6 or not otp_code.isdigit():
        request.session["show_contact_otp_modal"] = True
        messages.error(request, "Please enter a valid 6-digit OTP.")
        return redirect("settings_page")

    result = verify_otp(current_user, otp_code, purpose="change_contact")

    if result == "ok":
        old_contact = current_user.contactno

        current_user.contactno = pending_new_contact
        current_user.save()

        AuditLogs.objects.create(
            user=current_user,
            action="Updated Contact Number",
            module_name="Settings",
            table_name="Users",
            record_id=current_user.userid,
            old_value=old_contact,
            new_value=pending_new_contact,
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
            created_at=timezone.now(),
        )

        request.session.pop("pending_new_contact", None)
        request.session.pop("show_contact_otp_modal", None)

        messages.success(request, "Contact number updated successfully.")
        return redirect("settings_page")

    request.session["show_contact_otp_modal"] = True

    if result.startswith("locked:"):
        minutes = result.split(":")[1]
        messages.error(request, f"Too many incorrect attempts. Please wait {minutes} minute(s).")
    elif result.startswith("wrong:"):
        remaining = result.split(":")[1]
        messages.error(request, f"Incorrect OTP. {remaining} attempt(s) remaining.")
    else:
        messages.error(request, "OTP has expired. Please request a new one.")

    return redirect("settings_page")

#ADMIN UPDATE EMAIL START
@admin_login_required
def admin_update_email_start(request):
    if request.method != "POST":
        return redirect("settings_page")

    current_user = get_current_user(request)

    password = request.POST.get("password", "").strip()
    new_email = request.POST.get("new_email", "").strip().lower()

    if not check_password(password, current_user.password):
        messages.error(request, "Password is incorrect.")
        return redirect("settings_page")

    if not new_email:
        messages.error(request, "Please enter an email address.")
        return redirect("settings_page")

    if "@" not in new_email or "." not in new_email:
        messages.error(request, "Please enter a valid email address.")
        return redirect("settings_page")

    if new_email == current_user.email:
        messages.error(request, "New email address must be different from your current email address.")
        return redirect("settings_page")

    if Users.objects.filter(email=new_email).exclude(userid=current_user.userid).exists():
        messages.error(request, "This email address is already used by another account.")
        return redirect("settings_page")

    request.session["pending_new_email"] = new_email

    otp, cooldown = generate_otp(current_user, purpose="change_email")

    if cooldown:
        mins = cooldown // 60
        secs = cooldown % 60
        messages.error(request, f"Please wait {mins}m {secs}s before requesting another OTP.")
        return redirect("settings_page")

    send_email_otp(new_email, otp.code)

    request.session.pop("show_contact_otp_modal", None)
    request.session["show_email_otp_modal"] = True

    messages.success(request, "OTP has been sent to your new email address.")
    return redirect("settings_page")

#ADMIN UPDATE EMAIL VERIFY
@admin_login_required
def admin_update_email_verify(request):
    if request.method != "POST":
        return redirect("settings_page")

    current_user = get_current_user(request)

    pending_new_email = request.session.get("pending_new_email")
    otp_code = request.POST.get("otp_code", "").strip()

    if not pending_new_email:
        messages.error(request, "No pending email update found.")
        return redirect("settings_page")

    if not otp_code or len(otp_code) != 6 or not otp_code.isdigit():
        request.session["show_email_otp_modal"] = True
        messages.error(request, "Please enter a valid 6-digit OTP.")
        return redirect("settings_page")

    result = verify_otp(current_user, otp_code, purpose="change_email")

    if result == "ok":
        old_email = current_user.email

        current_user.email = pending_new_email
        current_user.save()

        AuditLogs.objects.create(
            user=current_user,
            action="Updated Email Address",
            module_name="Settings",
            table_name="Users",
            record_id=current_user.userid,
            old_value=old_email,
            new_value=pending_new_email,
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
            created_at=timezone.now(),
        )

        request.session.pop("pending_new_email", None)
        request.session.pop("show_email_otp_modal", None)

        messages.success(request, "Email address updated successfully.")
        return redirect("settings_page")

    request.session["show_email_otp_modal"] = True

    if result.startswith("locked:"):
        minutes = result.split(":")[1]
        messages.error(request, f"Too many incorrect attempts. Please wait {minutes} minute(s).")
    elif result.startswith("wrong:"):
        remaining = result.split(":")[1]
        messages.error(request, f"Incorrect OTP. {remaining} attempt(s) remaining.")
    else:
        messages.error(request, "OTP has expired. Please request a new one.")

    return redirect("settings_page")

#ADMIN CHANGE AVATAR
@admin_login_required
def admin_change_avatar(request):
    if request.method != "POST":
        return redirect("settings_page")

    current_user = get_current_user(request)
    avatar_id = request.POST.get("avatar_id", "").strip()

    if avatar_id:
        try:
            current_user.avatar = AvatarOptions.objects.get(
                avatarid=avatar_id,
                is_active=True
            )
        except AvatarOptions.DoesNotExist:
            messages.error(request, "Invalid avatar selected.")
            return redirect("settings_page")
    else:
        current_user.avatar = None

    current_user.save()

    request.session["avatar_path"] = (
        current_user.avatar.image_path
        if current_user.avatar else None
    )

    messages.success(request, "Avatar updated successfully.")
    return redirect("settings_page")

# ADMIN UPDATE USERNAME
@admin_login_required
def admin_change_username(request):
    if request.method != "POST":
        return redirect("settings_page")

    current_user = get_current_user(request)

    password = request.POST.get("password", "").strip()
    new_username = request.POST.get("new_username", "").strip().lower()

    if not check_password(password, current_user.password):
        messages.error(request, "Password is incorrect.")
        return redirect("settings_page")

    if not new_username:
        messages.error(request, "Please enter a username.")
        return redirect("settings_page")

    if len(new_username) < 4:
        messages.error(request, "Username must be at least 4 characters long.")
        return redirect("settings_page")

    if len(new_username) > 50:
        messages.error(request, "Username cannot exceed 50 characters.")
        return redirect("settings_page")

    if " " in new_username:
        messages.error(request, "Username cannot contain spaces.")
        return redirect("settings_page")

    if new_username == current_user.username:
        messages.error(request, "New username must be different from your current username.")
        return redirect("settings_page")

    if Users.objects.filter(username=new_username).exclude(userid=current_user.userid).exists():
        messages.error(request, "This username is already used by another account.")
        return redirect("settings_page")

    old_username = current_user.username

    current_user.username = new_username
    current_user.save()

    AuditLogs.objects.create(
        user=current_user,
        action="Updated Username",
        module_name="Settings",
        table_name="Users",
        record_id=current_user.userid,
        old_value=old_username,
        new_value=new_username,
        ip_address=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT"),
        created_at=timezone.now(),
    )

    messages.success(request, "Username updated successfully.")
    return redirect("settings_page")