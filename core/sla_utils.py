from django.utils import timezone
from datetime import timedelta
from .models import SLATracking, SLAModules


# SLA deadlines by module and priority (in hours)
SLA_DEADLINES = {
    "Complaint": {
        "Low":    72,
        "Medium": 48,
        "High":   24,
        "Urgent": 8,
    },
    "DocumentRequest": {
        "Low":    48,
        "Medium": 24,
        "High":   12,
        "Urgent": 4,
    },
    "Inquiry": {
        "Low":    48,
        "Medium": 24,
        "High":   12,
        "Urgent": 4,
    },
}


def get_or_create_module(module_name: str) -> SLAModules:
    module, _ = SLAModules.objects.get_or_create(module_name=module_name)
    return module


def create_sla(module_name: str, record_id: int, priority: str = "Medium") -> SLATracking:
    """
    Create a new SLA tracking record for any module.
    Called immediately after a record is created.
    """
    module = get_or_create_module(module_name)
    hours = SLA_DEADLINES.get(module_name, {}).get(priority, 48)
    now = timezone.now()

    sla = SLATracking.objects.create(
        module=module,
        record_id=record_id,
        priority_level=priority,
        sla_deadline=now + timedelta(hours=hours),
        sla_status="Pending",
        created_at=now,
    )
    return sla


def record_first_response(module_name: str, record_id: int) -> None:
    """
    Call this when an admin first acts on a record (e.g., status changes from Pending).
    Sets first_response_at and calculates response_time_minutes.
    """
    try:
        sla = SLATracking.objects.filter(
            module__module_name=module_name,
            record_id=record_id,
            first_response_at__isnull=True,
        ).latest("created_at")
    except SLATracking.DoesNotExist:
        return

    now = timezone.now()
    sla.first_response_at = now
    sla.sla_status = "In Progress"

    if sla.created_at:
        delta = now - sla.created_at
        sla.response_time_minutes = int(delta.total_seconds() / 60)

    # Check if already breached
    if sla.sla_deadline and now > sla.sla_deadline:
        sla.sla_status = "Breached"

    sla.save()


def resolve_sla(module_name: str, record_id: int) -> None:
    """
    Call this when a record is fully resolved/completed.
    Sets resolved_at, resolution_time_minutes, and final sla_status.
    """
    try:
        sla = SLATracking.objects.filter(
            module__module_name=module_name,
            record_id=record_id,
        ).latest("created_at")
    except SLATracking.DoesNotExist:
        return

    now = timezone.now()
    sla.resolved_at = now
    sla.completed_at = now

    if sla.created_at:
        delta = now - sla.created_at
        sla.resolution_time_minutes = int(delta.total_seconds() / 60)

    # Breached if resolved after deadline
    if sla.sla_deadline and now > sla.sla_deadline:
        sla.sla_status = "Breached"
    else:
        sla.sla_status = "Resolved"

    sla.save()


def get_sla_for_record(module_name: str, record_id: int) -> SLATracking | None:
    """
    Retrieve the latest SLA record for a given module + record_id.
    Returns None if not found.
    """
    return SLATracking.objects.filter(
        module__module_name=module_name,
        record_id=record_id,
    ).order_by("-created_at").first()