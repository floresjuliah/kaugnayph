from django.utils import timezone
from .models import ComplaintUpdates, AuditLogs

VALID_OFFICIAL_ROLES = ["Lupon Member", "Chairman"]

# SMS copy per status. None = no SMS sent for that status.
SMS_COPY = {
    "Referred to Proper Barangay": (
        "KaugnayPH: Your complaint {case_number} falls under another barangay's "
        "jurisdiction ({jurisdiction}). Please proceed to that barangay."
    ),
    "Recorded": (
        "KaugnayPH: Your complaint {case_number} has been recorded. "
        "You will be notified regarding the mediation schedule."
    ),
    "Mediation Scheduled": (
        "KaugnayPH: You are requested to appear at the Barangay Hall on "
        "{hearing_date} regarding Complaint {case_number}."
    ),
    "Settled": (
        "KaugnayPH: Your complaint {case_number} has been successfully settled. "
        "Case Closed."
    ),
    "For 1st Hearing": (
        "KaugnayPH: Complaint {case_number} is scheduled for Hearing 1 on {hearing_date}."
    ),
    "For 2nd Hearing": (
        "KaugnayPH: Complaint {case_number} is scheduled for Hearing 2 on {hearing_date}."
    ),
    "For 3rd Hearing": (
        "KaugnayPH: Complaint {case_number} is scheduled for Hearing 3 on {hearing_date}."
    ),
    "Eligible for Certificate to File Action": None,  # internal status, no SMS
    "Certificate Issued": (
        "KaugnayPH: A Certificate to File Action has been issued for complaint "
        "{case_number}. You may proceed with filing the case before the proper authority."
    ),
    "Under Review": "KaugnayPH: Your complaint {case_number} is now Under Review.",
    "Resolved": "KaugnayPH: Your complaint {case_number} has been resolved.",
    "Dismissed": (
        "KaugnayPH: Your complaint {case_number} has been dismissed. "
        "Please contact the barangay office for more information."
    ),
}


def build_sms_for_status(status, case_number, jurisdiction=None, hearing_date=None):
    """Returns the SMS body for a status, or None if no SMS should be sent."""
    template = SMS_COPY.get(status)
    if not template:
        return None
    return template.format(
        case_number=case_number,
        jurisdiction=jurisdiction or "the proper barangay",
        hearing_date=hearing_date.strftime("%B %d, %Y at %I:%M %p") if hearing_date else "a date to be announced",
    )


def apply_status_change(complaint, new_status, admin_user, remarks=None, log_action=None):
    """
    Single entry point for changing a complaint's status.
    Writes to ComplaintUpdates (the timeline source for Item 1) and AuditLogs.
    Does NOT send SMS — caller decides that using build_sms_for_status,
    since some callers need hearing_date/jurisdiction context this function doesn't have.
    """
    old_status = complaint.status
    complaint.status = new_status
    complaint.handled_by = admin_user
    complaint.save()

    ComplaintUpdates.objects.create(
        complaint=complaint,
        updated_by=admin_user,
        status=new_status,
        remarks=remarks or None,
        updated_at=timezone.now(),
    )

    AuditLogs.objects.create(
        user=admin_user,
        action=log_action or f"Status changed to {new_status}",
        module_name="Cases",
        table_name="Complaints",
        record_id=complaint.complaintsid,
        old_value=f"Status: {old_status}",
        new_value=f"Status: {new_status}",
        created_at=timezone.now(),
    )

    return old_status