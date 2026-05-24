import json
import random
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
    Users,
    UserTypes,
    Settings,
    Announcements,
    SMSOutbox,
    SMSSubscriptions,
    AuditLogs,
)

from .auth_utils import (
    hash_password, check_password, generate_otp,
    verify_otp, send_sms, set_user_session, get_current_user
)

from .decorators import (
    login_required,
    admin_login_required,
    admin_required,
    resident_required,
    role_required,
    permission_required,
    chairman_required,
)



# FOR RESIDENTS:
def landing_page(request):
    return render(request, 'public/landing.html')

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




#FOR ADMIN:

#@csrf_exempt
@admin_login_required
@permission_required('create_announcements')
def create_announcement(request):
    if request.method == "POST":
        data = json.loads(request.body)

        current_user = get_current_user(request) or Users.objects.get(userid=1)

        title = data.get("title", "").strip()
        content = data.get("content", "").strip()

        if not title:
            return JsonResponse({
                "error": "Title is required."
            }, status=400)

        if not content:
            return JsonResponse({
                "error": "Content is required."
            }, status=400)

        send_sms_value = int(data.get("send_sms", 0))
        gateway_response = None

        announcement = Announcements.objects.create(
            title=title,
            content=content,
            send_sms=send_sms_value,
            category_id=data.get("category_id", 1),
            posted_by=current_user,
            created_at=timezone.now()
        )

        if send_sms_value == 1:
            subscribers = SMSSubscriptions.objects.select_related("user").filter(is_active=True)
            gateway_response = []

            for sub in subscribers:
                response = send_sms(
                    contact_number=sub.user.contactno,
                    message=f"New announcement: {announcement.title}",
                    sent_by=current_user
                )

                gateway_response.append({
                    "user_id": sub.user.userid,
                    "contact_number": sub.user.contactno,
                    "response": response
                })

            AuditLogs.objects.create(
                user=current_user,
                action="Create Announcement",
                module_name="Announcements",
                table_name="Announcements",
                record_id=announcement.announcement_id,
                new_value=f"Announcement '{announcement.title}' was created.",
                created_at=timezone.now()
                )

        return JsonResponse({
            "message": "Announcement created successfully",
            "announcement_id": announcement.announcement_id,
            "send_sms_value": send_sms_value,
            "gateway_response": gateway_response
        })

    return JsonResponse({"error": "POST request required"}, status=400)

#@csrf_exempt
def update_announcement(request, announcement_id):
    if request.method == "PUT":
        data = json.loads(request.body)
        current_user = get_current_user(request) or Users.objects.get(userid=1)

        try:
            announcement = Announcements.objects.get(announcement_id=announcement_id)

            announcement.title = data.get("title", announcement.title)
            announcement.content = data.get("content", announcement.content)
            announcement.send_sms = data.get("send_sms", announcement.send_sms)
            announcement.category_id = data.get("category_id", announcement.category_id)
            announcement.save()

            AuditLogs.objects.create(
                user=current_user,
                action="Update Announcement",
                module_name="Announcements",
                table_name="Announcements",
                record_id=announcement.announcement_id,
                new_value=f"Announcement '{announcement.title}' was updated.",
                created_at=timezone.now()
            )

            return JsonResponse({"message": "Announcement updated successfully"})

        except Announcements.DoesNotExist:
            return JsonResponse({"error": "Announcement not found"}, status=404)

    return JsonResponse({"error": "PUT request required"}, status=400)

#@csrf_exempt
def delete_announcement(request, announcement_id):
    if request.method == "DELETE":

        current_user = get_current_user(request) or Users.objects.get(userid=1)

        try:
            announcement = Announcements.objects.get(
                announcement_id=announcement_id
            )

            announcement_title = announcement.title
            announcement_record_id = announcement.announcement_id

            announcement.delete()

            AuditLogs.objects.create(
                user=current_user,
                action="Delete Announcement",
                module_name="Announcements",
                table_name="Announcements",
                record_id=announcement_record_id,
                new_value=f"Announcement '{announcement_title}' was deleted.",
                created_at=timezone.now()
            )

            return JsonResponse({
                "message": "Announcement deleted successfully"
            })

        except Announcements.DoesNotExist:

            return JsonResponse({
                "error": "Announcement not found"
            }, status=404)

    return JsonResponse({
        "error": "DELETE request required"
    }, status=400)

#Commented Out cuz IDK if this should be deleted or not. Please check. TY!
##def send_sms(recipient_number, message, sent_by):

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

#    return sms ##


@admin_login_required
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

@admin_login_required
def get_sms_logs(request):
    data = list(SMSOutbox.objects.all().values())
    return JsonResponse(data, safe=False)

def admin_dashboard(request):
    return render(request, 'admin_dashboard.html')


@admin_login_required
@permission_required('verify_residents')
def serve_verification_file(request, rv_id, file_type):
    """Serve verification images only to authorized admins."""
    from .models import ResidentVerification
    import mimetypes
    from django.http import FileResponse, Http404

    try:
        rv = ResidentVerification.objects.get(rv_id=rv_id)
    except ResidentVerification.DoesNotExist:
        raise Http404

    if file_type == "id":
        path = rv.id_image_path
    elif file_type == "selfie":
        path = rv.selfie_image_path
    else:
        raise Http404

    full_path = settings.MEDIA_ROOT / path
    if not full_path.exists():
        raise Http404

    mime_type, _ = mimetypes.guess_type(str(full_path))
    return FileResponse(open(full_path, 'rb'), content_type=mime_type or 'image/jpeg')

#New - Auth - Tam (Below this)
# FOR AUTHENTICATION SYSTEM

def login_view(request):

    # Already logged in
    if request.session.get("user_id"):
        return _redirect_by_type(request)

    if request.method == "POST":

        contact_no = request.POST.get("contact_no", "").strip()
        password   = request.POST.get("password", "").strip()

        try:
            user = Users.objects.select_related(
                "user_type", "role", "position"
            ).get(contactno=contact_no, is_active=True)

        except Users.DoesNotExist:
            messages.error(request, "Invalid credentials.")
            return render(request, "auth/login.html")

        if not check_password(password, user.password):
            messages.error(request, "Invalid credentials.")
            return render(request, "auth/login.html")

        # ADMIN FLOW
        if user.user_type.type_name == "Admin":
            request.session["pending_user_id"] = user.userid
            if user.is_first_login:
                return redirect("admin_first_login")
            otp = generate_otp(user, purpose="login")
            send_sms(user.contactno, f"KaugnayPH OTP: {otp.code}. Valid for 5 minutes.")
            return redirect("otp_verify")

        # RESIDENT FLOW
        if user.user_type.type_name == "Resident":
            if not user.is_verified:
                messages.warning(request, "Your account is pending verification.")
                return render(request, "auth/login.html")
            set_user_session(request, user)
            return redirect("resident_dashboard")

        messages.error(request, "Invalid credentials.")

    # GET request — just render the form, nothing else
    return render(request, "auth/login.html")

# ADMIN LOGIN PAGE

def admin_login_view(request):

    # Already logged in
    if request.session.get('user_id'):
        return redirect('admin_dashboard')

    if request.method == "POST":

        username = request.POST.get(
            "username",
            ""
        ).strip()

        password = request.POST.get(
            "password",
            ""
        ).strip()

        try:
            user = Users.objects.select_related(
                "user_type",
                "role",
                "position"
            ).get(
                username=username,
                is_active=True
            )

        except Users.DoesNotExist:

            messages.error(
                request,
                "Invalid credentials."
            )

            return render(
                request,
                "auth/login_admin.html"
            )

        # ADMIN ONLY
        if user.user_type.type_name != "Admin":

            messages.error(
                request,
                "Admin access only."
            )

            return render(
                request,
                "auth/login_admin.html"
            )

        # PASSWORD CHECK
        if not check_password(
            password,
            user.password
        ):

            messages.error(
                request,
                "Invalid credentials."
            )

            return render(
                request,
                "auth/login_admin.html"
            )

        # TEMP SESSION
        request.session[
            "pending_user_id"
        ] = user.userid

        # FIRST LOGIN FLOW
        if user.is_first_login:

            return redirect(
                "admin_first_login"
            )

        # NORMAL LOGIN FLOW
        otp = generate_otp(
            user,
            purpose="login"
        )

        send_sms(
            user.contactno,
            f"KaugnayPH OTP: {otp.code}"
        )

        return redirect(
            "otp_verify"
        )

    return render(
        request,
        "auth/login_admin.html"
    )


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

    from .models import Positions

    if request.method == "POST":
        firstname        = request.POST.get("firstname", "").strip()
        lastname         = request.POST.get("lastname", "").strip()
        username         = request.POST.get("username", "").strip()
        contact_no       = request.POST.get("contact_no", "").strip()
        position_id      = request.POST.get("position_id", "").strip()
        new_password     = request.POST.get("new_password", "").strip()
        confirm_password = request.POST.get("confirm_password", "").strip()

        positions = Positions.objects.all()
        errors = []

        # --- Validation ---
        if not firstname or not lastname:
            errors.append("First name and last name are required.")

        if not username or len(username) < 4:
            errors.append("Username must be at least 4 characters.")

        if Users.objects.filter(username=username).exclude(userid=user.userid).exists():
            errors.append("Username is already taken.")

        if not contact_no.startswith("09") or len(contact_no) != 11:
            errors.append("Enter a valid 11-digit PH mobile number (e.g. 09XXXXXXXXX).")

        if Users.objects.filter(contactno=contact_no).exclude(userid=user.userid).exists():
            errors.append("Contact number is already in use.")

        if len(new_password) < 8:
            errors.append("Password must be at least 8 characters.")

        if not any(c.isdigit() for c in new_password):
            errors.append("Password must contain at least one number.")

        if not any(c.isalpha() for c in new_password):
            errors.append("Password must contain at least one letter.")

        if new_password != confirm_password:
            errors.append("Passwords do not match.")

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, "auth/admin_first_login.html", {
                "positions": positions,
                "user": user,
            })

        # --- Save everything ---
        user.firstname         = firstname
        user.lastname          = lastname
        user.username          = username
        user.contactno         = contact_no
        user.password          = hash_password(new_password)
        user.is_first_login    = False
        user.is_password_changed = True

        if position_id:
            try:
                user.position = Positions.objects.get(positionid=position_id)
            except Positions.DoesNotExist:
                pass

        user.save()

        # --- Send OTP to the new contact number ---
        otp = generate_otp(user, purpose="login")
        send_sms(
            user.contactno,
            f"KaugnayPH OTP: {otp.code}. Valid for 5 minutes."
        )

        messages.success(request, "Profile updated! Enter the OTP sent to your number.")
        return redirect("otp_verify")

    positions = Positions.objects.all()
    return render(request, "auth/admin_first_login.html", {
        "positions": positions,
        "user": user,
    })


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

    if request.method == "POST":
        code = request.POST.get("otp_code", "").strip()

        if not code or len(code) != 6 or not code.isdigit():
            messages.error(request, "Please enter a valid 6-digit OTP.")
            return render(request, "auth/otp_verify.html")

        if verify_otp(user, code, purpose="login"):
            # Clear the pending session
            del request.session["pending_user_id"]

            # Mark OTP verified — send them back to login to do a clean login
            request.session["otp_verified_user_id"] = user.userid
            messages.success(request,
                "OTP verified! Your account is ready. Please log in."
            )
            return redirect("admin_login")

        else:
            messages.error(request, "Invalid or expired OTP. Please try again or resend.")

    return render(request, "auth/otp_verify.html")


# RESEND OTP

def resend_otp_view(request):

    pending_id = request.session.get(
        "pending_user_id"
    )

    if not pending_id:
        return redirect("login")

    try:
        user = Users.objects.get(
            userid=pending_id
        )

    except Users.DoesNotExist:
        return redirect("login")

    otp = generate_otp(
        user,
        purpose="login"
    )

    send_sms(
        user.contactno,
        f"KaugnayPH NEW OTP: {otp.code}"
    )

    messages.success(
        request,
        "New OTP sent."
    )

    return redirect("otp_verify")


# REGISTER

def resident_register_view(request):

    if request.method == "POST":
        lastname    = request.POST.get("lastname", "").strip()
        firstname   = request.POST.get("firstname", "").strip()
        contact_no  = request.POST.get("contact_no", "").strip()
        password    = request.POST.get("password", "").strip()
        receive_sms = request.POST.get("receive_sms") == "on"
        toid        = request.POST.get("type_of_id", "").strip()
        id_image    = request.FILES.get("id_image")
        selfie      = request.FILES.get("selfie_image")

        # --- Validations ---
        errors = []
        if not contact_no.startswith("09") or len(contact_no) != 11:
            errors.append("Enter a valid 11-digit PH mobile number.")
        if Users.objects.filter(contactno=contact_no).exists():
            errors.append("Mobile number is already registered.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if not firstname or not lastname:
            errors.append("First name and last name are required.")
        if not toid:
            errors.append("Please select a type of ID.")
        if not id_image:
            errors.append("Please upload a photo of your ID.")
        if not selfie:
            errors.append("Please upload a selfie with your ID.")

        from .utils import validate_upload
            
        ok, err = validate_upload(id_image)
        if not ok:
            messages.error(request, f"ID Photo: {err}")

        ok, err = validate_upload(selfie)
        if not ok:
            messages.error(request, f"Selfie: {err}")
        
        
        # File type validation
        allowed_types = ['image/jpeg', 'image/png', 'image/jpg'] #Iphone file type not YET integrated
        if id_image and id_image.content_type not in allowed_types:
            errors.append("ID image must be JPG or PNG.")
        if selfie and selfie.content_type not in allowed_types:
            errors.append("Selfie must be JPG or PNG.")

        # File size validation (max 5MB)
        if id_image and id_image.size > 5 * 1024 * 1024:
            errors.append("ID image must be less than 5MB.")
        if selfie and selfie.size > 5 * 1024 * 1024:
            errors.append("Selfie must be less than 5MB.")

        if errors:
            for e in errors:
                messages.error(request, e)
            from .models import TypeOfID
            return render(request, "auth/register.html", {
                "id_types": TypeOfID.objects.all()
            })

        try:
            resident_type = UserTypes.objects.get(type_name="Resident")
        except UserTypes.DoesNotExist:
            messages.error(request, "System error. Please contact admin.")
            return render(request, "auth/register.html")

        # DUPLICATE NUMBER
        if Users.objects.filter(
            contactno=contact_no
        ).exists():

            messages.error(
                request,
                "Mobile number already exists."
            )

            return render(
                request,
                "auth/register.html"
            )
        
        
        # PASSWORD VALIDATION
        if len(password) < 8:
            messages.error(request, "Password must be at least 8 characters.")
            return render(request, "auth/register.html")

        try:
            resident_type = UserTypes.objects.get(
                type_name="Resident"
            )

        except UserTypes.DoesNotExist:

            messages.error(
                request,
                "Resident user type missing."
            )

            return render(
                request,
                "auth/register.html"
            )

        # USER - Resident
        if not firstname or not lastname:
            messages.error(request, "First name and last name are required.")
            return render(request, "auth/register.html")

        try:
            resident_type = UserTypes.objects.get(type_name="Resident")
        except UserTypes.DoesNotExist:
            messages.error(request, "System error: Resident type missing. Contact admin.")
            return render(request, "auth/register.html")

        #Save uploaded files
        upload_dir = f"uploads/verification/{new_user.userid}/"
        id_path = default_storage.save(
            upload_dir + "id_" + id_image.name,
            ContentFile(id_image.read())
        )
        selfie_path = default_storage.save(
            upload_dir + "selfie_" + selfie.name,
            ContentFile(selfie.read())
        )


        #CREATE New User
        new_user = Users.objects.create(
            username=contact_no,
            password=hash_password(password),
            firstname=firstname,
            lastname=lastname,
            contactno=contact_no,
            user_type=resident_type,
            is_verified=False,
            is_active=True,
            is_first_login=False,
            is_password_changed=True,
        )

            # Create ResidentVerification record
        from .models import ResidentVerification, TypeOfID
        try:
            id_type = TypeOfID.objects.get(toid=toid)
        except TypeOfID.DoesNotExist:
            id_type = None

        ResidentVerification.objects.create(
            user=new_user,
            toid=id_type,
            id_image_path=id_path,
            selfie_image_path=selfie_path,
            status="Pending",
        )

        #Setting
        Settings.objects.create(
            user=new_user,
            receive_sms=receive_sms,
            notifications_enabled=True,
            dark_mode=False,
            updated_at=timezone.now(),
        )

        messages.success(request,
            "Account created successfully! "
            "Please wait for admin verification before you can log in."
        )
        return redirect("login")
    
    from .models import TypeOfID
    return render(request, "auth/register.html", {
        "id_types": TypeOfID.objects.all()
    })



@admin_login_required
def admin_dashboard_view(request):

    user = get_current_user(request)

    return render(
        request,
        "adminpanel/dashboard.html",
        {
            "user": user
        }
    )


@login_required
@resident_required
def resident_dashboard_view(request):

    user = get_current_user(request)

    return render(
        request,
        "resident/dashboard.html",
        {
            "user": user
        }
    )


def pending_verification_view(request):

    return render(
        request,
        "resident/pending_verification.html"
    )


def logout_view(request):
    user_type = request.session.get("user_type", "Resident")
    request.session.flush()
    messages.success(request, "You have been logged out successfully.")
    if user_type == "Admin":
        return redirect("admin_login")
    return redirect("login")

 
def _redirect_by_type(request):
    user_type = request.session.get("user_type")
    if user_type == "Admin": return redirect("admin_dashboard")
    return redirect("resident_dashboard")

from .decorators import admin_login_required, permission_required

@admin_login_required
@permission_required('create_users')
def admin_register(request):
    """
    Chairman-only: Create a new staff account.
    GET  → render the create staff form
    POST → create staff user with temp credentials
    """
    if request.method == "POST":
        firstname  = request.POST.get("firstname", "").strip()
        lastname   = request.POST.get("lastname", "").strip()
        contact_no = request.POST.get("contact_no", "").strip()
        role_id    = request.POST.get("role_id", "").strip()
        position_id= request.POST.get("position_id", "").strip()

        # --- basic validation ---
        if not all([firstname, lastname, contact_no, role_id]):
            messages.error(request, "All required fields must be filled.")
            return redirect("admin_register")

        if Users.objects.filter(contactno=contact_no).exists():
            messages.error(request, "Contact number already exists.")
            return redirect("admin_register")

        # --- build username from lastname + random digits ---
        import random, string as _string
        suffix   = ''.join(random.choices(_string.digits, k=4))
        username = (lastname.lower().replace(" ", "") + suffix)[:20]
        while Users.objects.filter(username=username).exists():
            suffix   = ''.join(random.choices(_string.digits, k=4))
            username = (lastname.lower().replace(" ", "") + suffix)[:20]

        # --- temp password ---
        temp_password = ''.join(random.choices(
            _string.ascii_letters + _string.digits, k=10
        ))

        from .models import UserTypes, Roles, Positions
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
            is_first_login=True,       # forces first-login flow
            is_password_changed=False,
        )

        # --- SMS the temp credentials ---
        send_sms(
            contact_no,
            f"KaugnayPH: Your account has been created.\n"
            f"Username: {username}\n"
            f"Temp Password: {temp_password}\n"
            f"Please log in and change your password immediately.",
            sent_by=get_current_user(request)
        )

        # --- Audit log ---
        from .models import AuditLogs
        AuditLogs.objects.create(
            user=get_current_user(request),
            action="Create Staff Account",
            module_name="UserManagement",
            table_name="Users",
            record_id=new_user.userid,
            new_value=f"Staff '{username}' created by chairman.",
            created_at=timezone.now()
        )

        messages.success(
            request,
            f"Staff account created! Username: {username} | "
            f"Temp Password: {temp_password}  (also sent via SMS)"
        )
        return redirect("admin_register")

    # GET — load roles and positions for the dropdown
    from .models import Roles, Positions
    roles     = Roles.objects.all()
    positions = Positions.objects.all()
    return render(request, "auth/admin_register.html", {
        "roles": roles,
        "positions": positions,
    })

# FOR RESIDENT VERIFICATION:
@admin_login_required
@permission_required('verify_residents')
def resident_verification_list(request):
    """List all pending verification requests."""
    from .models import ResidentVerification
    pending = ResidentVerification.objects.select_related(
        'user', 'toid'
    ).filter(status="Pending").order_by('-rv_id')

    return render(request, "adminpanel/verification_list.html", {
        "verifications": pending,
        "user": get_current_user(request),
    })


@admin_login_required
@permission_required('verify_residents')
def resident_verification_detail(request, rv_id):
    """View detail and approve/reject a verification request."""
    from .models import ResidentVerification
    try:
        rv = ResidentVerification.objects.select_related(
            'user', 'toid'
        ).get(rv_id=rv_id)
    except ResidentVerification.DoesNotExist:
        messages.error(request, "Verification record not found.")
        return redirect("verification_list")

    if request.method == "POST":
        action = request.POST.get("action")  # "approve" or "reject"
        admin = get_current_user(request)

        if action == "approve":
            rv.status = "Approved"
            rv.reviewed_by = admin
            rv.reviewed_at = timezone.now()
            rv.save()

            rv.user.is_verified = True
            rv.user.save()

            # Notify resident via SMS
            send_sms(
                rv.user.contactno,
                "KaugnayPH: Your account has been verified! You can now log in.",
                sent_by=admin
            )

            AuditLogs.objects.create(
                user=admin,
                action="Approve Resident",
                module_name="Verification",
                table_name="ResidentVerification",
                record_id=rv.rv_id,
                new_value=f"Resident {rv.user.username} approved.",
                created_at=timezone.now()
            )

            messages.success(request, f"Resident {rv.user.firstname} {rv.user.lastname} approved.")

        elif action == "reject":
            rv.status = "Rejected"
            rv.reviewed_by = admin
            rv.reviewed_at = timezone.now()
            rv.save()

            send_sms(
                rv.user.contactno,
                "KaugnayPH: Your registration was not approved. "
                "Please visit the barangay office for assistance.",
                sent_by=admin
            )

            AuditLogs.objects.create(
                user=admin,
                action="Reject Resident",
                module_name="Verification",
                table_name="ResidentVerification",
                record_id=rv.rv_id,
                new_value=f"Resident {rv.user.username} rejected.",
                created_at=timezone.now()
            )

            messages.warning(request, f"Resident {rv.user.firstname} {rv.user.lastname} rejected.")

        return redirect("verification_list")

    return render(request, "adminpanel/verification_detail.html", {
        "rv": rv,
        "user": get_current_user(request),
    })
