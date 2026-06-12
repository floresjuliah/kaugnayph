# core/sla_utils.py
from django.utils import timezone
from datetime import timedelta
from .models import SLATracking, SLAModules


# SLA deadlines by module and priority (in hours)
SLA_DEADLINES = {
    "Inquiry": {
        "Low":    48,
        "Medium": 24,
        "High":   12,
        "Urgent": 4,
    },
    "DocumentRequest": {
        "Low":    72,
        "Medium": 48,
        "High":   24,
        "Urgent": 8,
    },
}


def get_or_create_module(module_name: str) -> SLAModules:
    module, _ = SLAModules.objects.get_or_create(module_name=module_name)
    return module


def create_sla(module_name: str, record_id: int, priority: str = "Medium") -> SLATracking:
    """
    Create a new SLA tracking record.
    Call immediately after saving a new Inquiry or DocumentRequest.
    """
    module = get_or_create_module(module_name)
    hours  = SLA_DEADLINES.get(module_name, {}).get(priority, 24)
    now    = timezone.now()

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
    Call on the first admin action on a record.
    Sets first_response_at and response_time_minutes.
    Only applies once — ignored if already set.
    """
    try:
        sla = SLATracking.objects.filter(
            module__module_name=module_name,
            record_id=record_id,
            first_response_at__isnull=True,
        ).latest("created_at")
    except SLATracking.DoesNotExist:
        return

    now                   = timezone.now()
    sla.first_response_at = now
    sla.sla_status        = "In Progress"

    if sla.created_at:
        delta = now - sla.created_at
        sla.response_time_minutes = int(delta.total_seconds() / 60)

    if sla.sla_deadline and now > sla.sla_deadline:
        sla.sla_status = "Breached"

    sla.save()


def resolve_sla(module_name: str, record_id: int) -> None:
    """
    Call when a record is fully resolved/completed/replied.
    Sets resolved_at, resolution_time_minutes, and final sla_status.
    """
    try:
        sla = SLATracking.objects.filter(
            module__module_name=module_name,
            record_id=record_id,
        ).latest("created_at")
    except SLATracking.DoesNotExist:
        return

    now              = timezone.now()
    sla.resolved_at  = now
    sla.completed_at = now

    if sla.created_at:
        delta = now - sla.created_at
        sla.resolution_time_minutes = int(delta.total_seconds() / 60)

    sla.sla_status = (
        "Breached" if sla.sla_deadline and now > sla.sla_deadline
        else "Resolved"
    )

    sla.save()


def get_sla_for_record(module_name: str, record_id: int):
    """
    Fetch the latest SLA record for a module + record.
    Returns SLATracking or None.
    """
    return SLATracking.objects.filter(
        module__module_name=module_name,
        record_id=record_id,
    ).order_by("-created_at").first()


def get_sla_status_live(sla) -> str:
    """
    Returns a live-calculated status string.
    Use this in templates instead of sla.sla_status directly,
    because sla_status in the DB only updates when an action is taken.
    """
    if not sla:
        return "No SLA"
    if sla.resolved_at:
        return sla.sla_status  # Already finalized
    if sla.sla_deadline and timezone.now() > sla.sla_deadline:
        return "Breached"
    if sla.first_response_at:
        return "In Progress"
    return "Pending"