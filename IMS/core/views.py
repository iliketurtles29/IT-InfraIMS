from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.db import models
from django.db.models import Count, Q, Prefetch, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.core.exceptions import ValidationError
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView


from .models import (
    Asset,
    AssetAssignment,
    AssetType,
    AuditLog,
    ComputerQualityInspection,
    Department,
    Employee,
    Location,
    SystemUser,
    AssetRepair,
    ConsumableItem,
    ConsumableMovement,
    
 )

class GemsLoginView(LoginView):
    template_name = "login.html"
    redirect_authenticated_user = True

def dashboard_context():
    assets = Asset.objects.select_related(
        "asset_type",
        "department",
        "location",
    )

    asset_types = (
        AssetType.objects
        .filter(is_active=True)
        .annotate(asset_count=Count("assets"))
    )

    departments = (
        Department.objects
        .annotate(asset_count=Count("assets"))
    )

    locations = (
        Location.objects
        .annotate(
            asset_count=Count(
                "assets",
                distinct=True,
            )
        )
        .order_by("name")
    )

    return {
        "total_assets": assets.count(),

        "assigned_assets": assets.filter(
            status=Asset.Status.ASSIGNED
        ).count(),

        "available_assets": assets.filter(
            status=Asset.Status.AVAILABLE
        ).count(),

        "repair_assets": assets.filter(
            status=Asset.Status.IN_REPAIR
        ).count(),

        "lost_assets": assets.filter(
            status=Asset.Status.LOST
        ).count(),

        "retired_assets": assets.filter(
            status=Asset.Status.RETIRED
        ).count(),

        "asset_types": asset_types,
        "departments": departments,
        "locations": locations,

        "recent_logs": (
            AuditLog.objects
            .select_related(
                "user",
                "asset",
                "employee",
            )
            .order_by("-created_at")[:5]
        ),
    }

@login_required
def index(request):
    return render(
        request,
        "index.html",
        dashboard_context(),
    )

@login_required
def assets(request):
    selected_type = request.GET.get(
        "type",
        "",
    ).strip()

    selected_status = request.GET.get(
        "status",
        "",
    ).strip()

    search_query = request.GET.get(
        "q",
        "",
    ).strip()

    current_assignments = (
        AssetAssignment.objects
        .filter(end_date__isnull=True)
        .select_related("employee")
        .order_by("-start_date")
    )

    asset_queryset = (
        Asset.objects
        .select_related(
            "asset_type",
            "department",
            "location",
        )
        .prefetch_related(
            __import__("django.db.models", fromlist=["Prefetch"]).Prefetch(
                "assignments",
                queryset=current_assignments,
                to_attr="current_assignments",
            )
        )
        .order_by("asset_tag")
    )

    if selected_type:
        asset_queryset = asset_queryset.filter(
            asset_type__name__iexact=selected_type,
        )

    if selected_status:
        asset_queryset = asset_queryset.filter(
            status__iexact=selected_status,
        )

    if search_query:
        asset_queryset = asset_queryset.filter(
            Q(asset_tag__icontains=search_query)
            | Q(brand__icontains=search_query)
            | Q(model__icontains=search_query)
            | Q(serial_number__icontains=search_query)
            | Q(department__name__icontains=search_query)
            | Q(location__name__icontains=search_query)
            | Q(assignments__employee__name__icontains=search_query)
        ).distinct()

    return render(
        request,
        "assets.html",
        {
            "assets": asset_queryset,

            "asset_types": (
                AssetType.objects
                .filter(is_active=True)
                .order_by("name")
            ),

            "asset_statuses": Asset.Status.choices,

            "departments": (
                Department.objects
                .order_by("name")
            ),

            "locations": (
                Location.objects
                .order_by("name")
            ),

            "selected_type": selected_type,
            "selected_status": selected_status,
            "search_query": search_query,

            "employees": (
                Employee.objects
                .filter(status=Employee.Status.ACTIVE)
                .order_by("name")
            ),
        },
    )


def _get_or_create_audit_system_user(request):
    """
    Gets the SystemUser matching the logged-in Django user.

    If the matching SystemUser does not exist, it creates one.
    """

    username = getattr(
        request.user,
        "username",
        "",
    ).strip()

    if not username:
        return None

    display_name = (
        request.user.get_full_name()
        or username
    )[:160]

    system_user, created = SystemUser.objects.get_or_create(
        username=username,
        defaults={
            "display_name": display_name,
            "role": SystemUser.Role.IT_STAFF,
            "is_active": True,
        },
    )

    return system_user


def _create_asset_audit_log(request, asset):
    """
    Creates an audit-log entry for a newly added asset.
    """

    system_user = _get_or_create_audit_system_user(request)

    # Keep this return as requested.
    if not system_user:
        return

    # Do not create logs for inactive system users.
    if not system_user.is_active:
        return

    AuditLog.objects.create(
        action=AuditLog.Action.CREATE,
        description=(
            f"Added asset {asset.asset_tag}: "
            f"{asset.asset_type.name}, "
            f"{asset.brand} {asset.model} "
            f"at {asset.location.name}."
        ),
        user=system_user,
        asset=asset,
    )


@require_POST
@transaction.atomic
def asset_create(request):
    """
    Creates a new asset and records the action in the audit logs.
    """

    asset_tag = request.POST.get(
        "asset_tag",
        "",
    ).strip()

    asset_type_name = request.POST.get(
        "asset_type",
        "",
    ).strip()

    department_name = request.POST.get(
        "department",
        "",
    ).strip()

    location_name = request.POST.get(
        "location",
        "",
    ).strip()

    serial_number = request.POST.get(
        "serial_number",
        "",
    ).strip()

    errors = []

    if not asset_tag:
        errors.append(
            "Asset tag is required."
        )

    elif Asset.objects.filter(
        pk=asset_tag,
    ).exists():
        errors.append(
            "An asset with this tag already exists."
        )

    asset_type = (
        AssetType.objects
        .filter(name=asset_type_name)
        .first()
    )

    if not asset_type:
        errors.append(
            "Select a valid asset type."
        )

    department = (
        Department.objects
        .filter(name=department_name)
        .first()
    )

    if not department:
        errors.append(
            "Select a valid department."
        )

    location = (
        Location.objects
        .filter(name=location_name)
        .first()
    )

    if not location:
        errors.append(
            "Select a valid location."
        )

    if (
        serial_number
        and Asset.objects.filter(
            serial_number=serial_number,
        ).exists()
    ):
        errors.append(
            "This serial number is already on file."
        )

    if errors:
        for message in errors:
            messages.error(
                request,
                message,
            )

        return redirect("assets")

    asset = Asset.objects.create(
        asset_tag=asset_tag,
        asset_type=asset_type,
        brand=request.POST.get(
            "brand",
            "",
        ).strip(),
        model=request.POST.get(
            "model",
            "",
        ).strip(),
        serial_number=serial_number,
        condition=request.POST.get(
            "condition",
        ) or Asset.Condition.NEW,
        purchase_date=request.POST.get(
            "purchase_date",
        ) or None,
        warranty_expiration=request.POST.get(
            "warranty_expiration",
        ) or None,
        department=department,
        location=location,
    )

    # This creates the CREATE audit log.
    _create_asset_audit_log(
        request,
        asset,
    )

    messages.success(
        request,
        f"Asset {asset.asset_tag} created.",
    )

    return redirect("assets")

@require_POST
@transaction.atomic
def asset_update(request, asset_tag):
    """Update an asset and record the change in the audit log."""
    asset = get_object_or_404(
        Asset.objects.select_for_update(),
        asset_tag=asset_tag,
    )

    asset_type_name = request.POST.get("asset_type", "").strip()
    department_name = request.POST.get("department", "").strip()
    location_name = request.POST.get("location", "").strip()
    serial_number = request.POST.get("serial_number", "").strip()

    asset_type = AssetType.objects.filter(
        name=asset_type_name,
        is_active=True,
    ).first()
    department = Department.objects.filter(name=department_name).first()
    location = Location.objects.filter(name=location_name).first()

    errors = []

    if not asset_type:
        errors.append("Select a valid asset type.")
    if not department:
        errors.append("Select a valid department.")
    if not location:
        errors.append("Select a valid location.")

    if not serial_number:
        errors.append("Serial number is required.")
    elif Asset.objects.filter(
        serial_number=serial_number,
    ).exclude(
        asset_tag=asset.asset_tag,
    ).exists():
        errors.append("This serial number is already on file.")

    purchase_date_value = request.POST.get("purchase_date", "").strip()
    warranty_expiration_value = request.POST.get(
        "warranty_expiration",
        "",
    ).strip()

    def parse_date(value, label):
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            errors.append(f"Enter a valid {label}.")
            return None

    purchase_date = parse_date(purchase_date_value, "purchase date")
    warranty_expiration = parse_date(
        warranty_expiration_value,
        "warranty expiration",
    )

    if (
        purchase_date
        and warranty_expiration
        and warranty_expiration < purchase_date
    ):
        errors.append(
            "Warranty expiration cannot be before the purchase date."
        )

    condition = request.POST.get("condition", "").strip()
    valid_conditions = {
        value for value, _label in Asset.Condition.choices
    }
    if condition not in valid_conditions:
        errors.append("Select a valid asset condition.")

    if errors:
        for message in errors:
            messages.error(request, message)
        return redirect("assets")

    old_values = {
        "asset_type": asset.asset_type.name,
        "brand": asset.brand,
        "model": asset.model,
        "serial_number": asset.serial_number,
        "condition": asset.condition,
        "purchase_date": asset.purchase_date,
        "warranty_expiration": asset.warranty_expiration,
        "department": asset.department.name,
        "location": asset.location.name,
    }

    asset.asset_type = asset_type
    asset.brand = request.POST.get("brand", "").strip()
    asset.model = request.POST.get("model", "").strip()
    asset.serial_number = serial_number
    asset.condition = condition
    asset.purchase_date = purchase_date
    asset.warranty_expiration = warranty_expiration
    asset.department = department
    asset.location = location
    asset.save()

    system_user = _get_or_create_audit_system_user(request)
    if system_user and system_user.is_active:
        AuditLog.objects.create(
            action=AuditLog.Action.UPDATE,
            description=(
                f"Updated asset {asset.asset_tag}. "
                f"Previous values: {old_values}."
            ),
            user=system_user,
            asset=asset,
        )

    messages.success(request, f"Asset {asset.asset_tag} updated.")
    return redirect("assets")


@login_required
@require_POST
@transaction.atomic
def asset_return(request, asset_tag):
    asset = get_object_or_404(
        Asset.objects.select_for_update(),
        asset_tag=asset_tag,
    )

    assignment = (
        asset.assignments
        .select_for_update()
        .select_related("employee")
        .filter(end_date__isnull=True)
        .first()
    )

    if not assignment:
        messages.error(
            request,
            "This asset has no active assignment to return.",
        )
        return redirect("assets")

    end_date_value = request.POST.get(
        "end_date",
        "",
    ).strip()

    returned_condition = request.POST.get(
        "returned_condition",
        "",
    ).strip()

    remarks = request.POST.get(
        "remarks",
        "",
    ).strip()

    if not end_date_value:
        messages.error(request, "Please enter a return date.")
        return redirect("assets")

    try:
        end_date = date.fromisoformat(end_date_value)
    except ValueError:
        messages.error(request, "Please enter a valid return date.")
        return redirect("assets")

    if end_date < assignment.start_date:
        messages.error(
            request,
            "Return date cannot be before the assignment start date.",
        )
        return redirect("assets")

    valid_conditions = {
        value
        for value, _label in Asset.Condition.choices
    }

    if returned_condition not in valid_conditions:
        messages.error(
            request,
            "Please select the returned condition.",
        )
        return redirect("assets")

    if returned_condition == Asset.Condition.DAMAGED:
        next_status = Asset.Status.IN_REPAIR
        result_message = (
            f"{asset.asset_tag} was returned damaged "
            "and moved to In Repair."
        )

    elif returned_condition == Asset.Condition.FOR_DISPOSAL:
        next_status = Asset.Status.RETIRED
        result_message = (
            f"{asset.asset_tag} was returned as scrap/disposal "
            "and moved to Retired."
        )

    else:
        next_status = Asset.Status.AVAILABLE
        result_message = (
            f"{asset.asset_tag} was returned "
            "and is now Available."
        )

    actor_name = (
        request.user.get_full_name()
        or getattr(request.user, "username", "")
        or "System"
    )[:160]

    assignment.end_date = end_date
    assignment.returned_by = actor_name
    assignment.returned_condition = returned_condition
    assignment.remarks = remarks

    assignment.save(
        update_fields=[
            "end_date",
            "returned_by",
            "returned_condition",
            "remarks",
        ]
    )

    # Store physical condition separately from lifecycle status.
    asset.condition = returned_condition
    asset.status = next_status

    asset.save(
        update_fields=[
            "condition",
            "status",
            "updated_at",
        ]
    )

    # Keep this block if your project uses SystemUser and AuditLog.
    system_user = _get_or_create_audit_system_user(request)

    if system_user and system_user.is_active:
        AuditLog.objects.create(
            action=AuditLog.Action.RETURN,
            description=(
                f"Returned {asset.asset_tag} from "
                f"{assignment.employee.name} on {end_date}. "
                f"Condition: {returned_condition}. "
                f"New status: {next_status}."
            ),
            user=system_user,
            asset=asset,
            employee=assignment.employee,
        )

    messages.success(request, result_message)
    return redirect("assets")

def asset_details(request, asset_tag):
    asset = get_object_or_404(
        (
            Asset.objects
            .select_related(
                "asset_type",
                "department",
                "location",
            )
            .prefetch_related(
                "assignments__employee",
            )
        ),
        asset_tag=asset_tag,
    )

    return render(
        request,
        "asset-details.html",
        {
            "asset": asset,

            "assignment_history": (
                asset.assignments
                .select_related("employee")
                .order_by("-start_date")
            ),

            "employees": (
                Employee.objects
                .filter(status=Employee.Status.ACTIVE)
                .order_by("name")
            ),

            "asset_types": (
                AssetType.objects
                .filter(is_active=True)
                .order_by("name")
            ),

            "departments": Department.objects.order_by("name"),
            "locations": Location.objects.order_by("name"),
        },
    )

def _asset_assignment_block_reason(asset):
    """Return a user-facing reason when an asset cannot be issued."""
    if asset.condition == Asset.Condition.DAMAGED:
        return (
            f"{asset.asset_tag} is marked Damaged and cannot be assigned "
            "until it has been repaired."
        )

    if asset.condition == Asset.Condition.FOR_DISPOSAL:
        return (
            f"{asset.asset_tag} is marked For Disposal and cannot be "
            "assigned."
        )

    if asset.status == Asset.Status.IN_REPAIR:
        return (
            f"{asset.asset_tag} is still In Repair and cannot be assigned "
            "until it has been repaired."
        )

    if asset.status == Asset.Status.RETIRED:
        return f"{asset.asset_tag} is retired and cannot be assigned."

    if asset.status == Asset.Status.LOST:
        return f"{asset.asset_tag} is lost or stolen and cannot be assigned."

    return ""

@login_required
@require_POST
@transaction.atomic
def asset_assign(request, asset_tag):
    asset = get_object_or_404(
        Asset.objects.select_for_update(),
        asset_tag=asset_tag,
    )

    blocked_reason = _asset_assignment_block_reason(asset)
    if blocked_reason:
        messages.error(request, blocked_reason)
        return redirect("assets")

    # Accept the new multi-select field, and keep compatibility with
    # an older single-select form named "employee".
    employee_ids = (
        request.POST.getlist("employee_ids")
        or request.POST.getlist("employee")
    )
    employee_ids = list(dict.fromkeys(
        employee_id.strip()
        for employee_id in employee_ids
        if employee_id.strip()
    ))

    if not employee_ids:
        messages.error(request, "Please select at least one employee.")
        return redirect("assets")

    employees = list(
        Employee.objects.filter(
            employee_id__in=employee_ids,
            status=Employee.Status.ACTIVE,
        ).order_by("name")
    )

    found_ids = {str(employee.employee_id) for employee in employees}
    missing_ids = set(employee_ids) - found_ids
    if missing_ids:
        messages.error(
            request,
            "One or more selected employees are invalid or inactive.",
        )
        return redirect("assets")

    active_employee_ids = set(
        asset.assignments.filter(
            end_date__isnull=True,
        ).values_list("employee_id", flat=True)
    )

    new_employees = [
        employee
        for employee in employees
        if employee.employee_id not in active_employee_ids
    ]

    if not new_employees:
        messages.warning(
            request,
            "All selected employees already have an active assignment "
            "for this asset.",
        )
        return redirect("assets")

    start_date_value = request.POST.get("start_date", "").strip()
    if start_date_value:
        try:
            start_date = date.fromisoformat(start_date_value)
        except ValueError:
            messages.error(request, "Please enter a valid start date.")
            return redirect("assets")
    else:
        start_date = date.today()

    remarks = request.POST.get("remarks", "").strip()
    assigned_by = _assignment_actor_name(request)

    assignments = []
    for employee in new_employees:
        assignment = AssetAssignment.objects.create(
            asset=asset,
            employee=employee,
            assigned_by=assigned_by,
            start_date=start_date,
            remarks=remarks,
        )
        assignments.append(assignment)
        _create_assignment_audit_log(
            request,
            asset,
            employee,
            assignment,
        )

    asset.status = Asset.Status.ASSIGNED
    asset.save(update_fields=["status", "updated_at"])

    names = ", ".join(employee.name for employee in new_employees)
    messages.success(request, f"{asset.asset_tag} assigned to: {names}.")

    return redirect("assets")



def _assignment_actor_name(request):
    user = request.user

    return (
        user.get_full_name()
        or getattr(user, "username", "")
        or "System"
    )[:160]


def _create_assignment_audit_log(
    request,
    asset,
    employee,
    assignment,
):
    """
    Creates an audit entry for an asset assignment.
    """

    system_user = _get_or_create_audit_system_user(
        request,
    )

    if not system_user:
        return

    if not system_user.is_active:
        return

    AuditLog.objects.create(
        action=AuditLog.Action.ASSIGN,
        description=(
            f"Assigned {asset.asset_tag} to "
            f"{employee.name} starting "
            f"{assignment.start_date}."
        ),
        user=system_user,
        asset=asset,
        employee=employee,
    )

@login_required
@require_POST
@transaction.atomic
def asset_transfer(request, asset_tag):
    asset = get_object_or_404(
        Asset.objects.select_for_update(),
        asset_tag=asset_tag,
    )

    transfer_action = request.POST.get(
        "transfer_action",
        "transfer",
    ).strip()

    if transfer_action not in {"transfer", "remove"}:
        messages.error(request, "Select a valid assignment action.")
        return redirect("assets")

    # Removing an assignee only closes that employee's assignment. It does
    # not issue the asset to anyone, so it remains available even if the
    # asset is currently damaged, lost, or retired.
    if transfer_action == "transfer":
        blocked_reason = _asset_assignment_block_reason(asset)
        if blocked_reason:
            messages.error(
                request,
                blocked_reason.replace("assigned", "transferred"),
            )
            return redirect("assets")

    assignment_id = request.POST.get("assignment_id", "").strip()
    if not assignment_id:
        messages.error(request, "Select which employee's assignment to transfer.")
        return redirect("assets")

    current_assignment = (
        AssetAssignment.objects
        .select_for_update()
        .select_related("employee")
        .filter(
            asset=asset,
            pk=assignment_id,
            end_date__isnull=True,
        )
        .first()
    )

    if not current_assignment:
        messages.error(
            request,
            "That employee no longer has an active assignment for this asset.",
        )
        return redirect("assets")

    if transfer_action == "remove":
        effective_date_value = request.POST.get("start_date", "").strip()
        if effective_date_value:
            try:
                effective_date = date.fromisoformat(effective_date_value)
            except ValueError:
                messages.error(request, "Please enter a valid effective date.")
                return redirect("assets")
        else:
            effective_date = date.today()

        if effective_date < current_assignment.start_date:
            messages.error(
                request,
                "The removal date cannot be before the assignment start date.",
            )
            return redirect("assets")

        actor_name = _assignment_actor_name(request)
        removed_employee = current_assignment.employee
        removal_note = request.POST.get("remarks", "").strip()

        current_assignment.end_date = effective_date
        current_assignment.returned_by = actor_name
        if removal_note:
            prior_remarks = (current_assignment.remarks or "").strip()
            removal_entry = (
                f"Assignee removed effective {effective_date}: {removal_note}"
            )
            current_assignment.remarks = "\n".join(
                value for value in (prior_remarks, removal_entry) if value
            )
        current_assignment.save(
            update_fields=["end_date", "returned_by", "remarks"]
        )

        remaining_assignments = AssetAssignment.objects.filter(
            asset=asset,
            end_date__isnull=True,
        ).count()

        if remaining_assignments:
            if asset.status not in {
                Asset.Status.LOST,
                Asset.Status.RETIRED,
                Asset.Status.IN_REPAIR,
            }:
                asset.status = Asset.Status.ASSIGNED
            status_message = (
                f"{remaining_assignments} other employee"
                f"{'s' if remaining_assignments != 1 else ''} remain assigned."
            )
        elif asset.condition == Asset.Condition.DAMAGED:
            asset.status = Asset.Status.IN_REPAIR
            status_message = "The asset is now In Repair."
        elif asset.condition == Asset.Condition.FOR_DISPOSAL:
            asset.status = Asset.Status.RETIRED
            status_message = "The asset is now Retired."
        elif asset.status not in {Asset.Status.LOST, Asset.Status.RETIRED}:
            asset.status = Asset.Status.AVAILABLE
            status_message = "The asset is now Available."
        else:
            status_message = f"The asset remains {asset.get_status_display()}."

        asset.save(update_fields=["status", "updated_at"])

        system_user = _get_or_create_audit_system_user(request)
        if system_user and system_user.is_active:
            AuditLog.objects.create(
                action=AuditLog.Action.RETURN,
                description=(
                    f"Removed {removed_employee.name} from the active "
                    f"assignment for {asset.asset_tag} effective "
                    f"{effective_date}. {status_message}"
                ),
                user=system_user,
                asset=asset,
                employee=removed_employee,
            )

        messages.success(
            request,
            f"Removed {removed_employee.name} from {asset.asset_tag}. "
            f"{status_message}",
        )
        return redirect("assets")

    employee_id = request.POST.get("employee", "").strip()
    if not employee_id:
        messages.error(request, "Please select the receiving employee.")
        return redirect("assets")

    employee = Employee.objects.filter(employee_id=employee_id).first()
    if not employee or employee.status != Employee.Status.ACTIVE:
        messages.error(request, "Only active employees can receive assets.")
        return redirect("assets")

    if employee.employee_id == current_assignment.employee_id:
        messages.error(
            request,
            "The asset is already assigned to this employee.",
        )
        return redirect("assets")

    if asset.assignments.filter(
        end_date__isnull=True,
        employee=employee,
    ).exclude(pk=current_assignment.pk).exists():
        messages.error(
            request,
            "The receiving employee already has an active assignment "
            "for this asset.",
        )
        return redirect("assets")

    start_date_value = request.POST.get("start_date", "").strip()
    if start_date_value:
        try:
            start_date = date.fromisoformat(start_date_value)
        except ValueError:
            messages.error(request, "Please enter a valid transfer date.")
            return redirect("assets")
    else:
        start_date = date.today()

    if start_date < current_assignment.start_date:
        messages.error(
            request,
            "Transfer date cannot be before the current assignment date.",
        )
        return redirect("assets")

    actor_name = _assignment_actor_name(request)
    previous_employee = current_assignment.employee

    current_assignment.end_date = start_date
    current_assignment.returned_by = actor_name
    current_assignment.save(update_fields=["end_date", "returned_by"])

    new_assignment = AssetAssignment.objects.create(
        asset=asset,
        employee=employee,
        assigned_by=actor_name,
        start_date=start_date,
        remarks=request.POST.get("remarks", "").strip(),
    )

    # Other employees may still have this asset assigned.
    asset.status = Asset.Status.ASSIGNED
    asset.save(update_fields=["status", "updated_at"])

    system_user = _get_or_create_audit_system_user(request)
    if system_user and system_user.is_active:
        AuditLog.objects.create(
            action=AuditLog.Action.ASSIGN,
            description=(
                f"Transferred {asset.asset_tag} from "
                f"{previous_employee.name} to {employee.name} "
                f"starting {new_assignment.start_date}."
            ),
            user=system_user,
            asset=asset,
            employee=employee,
        )

    messages.success(
        request,
        f"{asset.asset_tag} transferred from "
        f"{previous_employee.name} to {employee.name}.",
    )
    return redirect("assets")




def employees(request):
    employees_queryset = (
        Employee.objects
        .select_related(
            "department",
            "location",
        )
        .prefetch_related("assignments")
        .order_by("name")
    )

    return render(
        request,
        "employees.html",
        {
            "employees": employees_queryset,
        },
    )


def employee_details(request, employee_id=None):
    employee_id = (
        employee_id
        or request.GET.get("id")
    )

    employee = get_object_or_404(
        (
            Employee.objects
            .select_related(
                "department",
                "location",
            )
        ),
        employee_id=employee_id,
    )

    assignments = (
        employee.assignments
        .select_related(
            "asset",
            "asset__asset_type",
        )
        .order_by("-start_date")
    )

    return render(
        request,
        "employee-details.html",
        {
            "employee": employee,
            "assignments": assignments,
        },
    )


def reports(request):
    context = dashboard_context()

    context["assets_by_status"] = [
        {
            "label": label,
            "value": Asset.objects.filter(
                status=value,
            ).count(),
        }
        for value, label in Asset.Status.choices
    ]

    return render(
        request,
        "reports.html",
        context,
    )


def audit_logs(request):
    logs = (
        AuditLog.objects
        .select_related(
            "user",
            "asset",
            "employee",
        )
        .order_by("-created_at")
    )

    return render(
        request,
        "audit-logs.html",
        {
            "logs": logs,
        },
    )


def settings(request):
    return render(
        request,
        "settings.html",
        {
            "asset_types": (
                AssetType.objects
                .order_by("name")
            ),

            "departments": (
                Department.objects
                .order_by("name")
            ),

            "locations": (
                Location.objects
                .order_by("name")
            ),
        },
    )

@login_required
@require_POST
@transaction.atomic
def asset_repair(request, asset_tag ):
    asset = get_object_or_404(
        Asset.objects.select_for_update(),
        asset_tag=asset_tag,
    )

    if asset.status == Asset.Status.ASSIGNED:
        messages.error(
            request,
            "Return the asset before marking it as repaired.",
        )
        return redirect("assets")

    if asset.status not in {
        Asset.Status.IN_REPAIR,
        Asset.Status.AVAILABLE,
    } and asset.condition != Asset.Condition.DAMAGED:
        messages.error(
            request,
            "Only damaged or in-repair assets can be repaired.",
        )
        return redirect("assets")

    completed_date_value = request.POST.get(
        "completed_date",
        "",
    ).strip()

    repaired_condition = request.POST.get(
        "repaired_condition",
        "",
    ).strip()

    repair_notes = request.POST.get(
        "repair_notes",
        "",
    ).strip()

    repair_provider = request.POST.get(
        "repair_provider",
        "",
    ).strip()

    repair_cost_value = request.POST.get(
        "repair_cost",
        "",
    ).strip()

    if not completed_date_value:
        messages.error(
            request,
            "Please enter the repair completion date.",
        )
        return redirect("assets")

    try:
        completed_date = date.fromisoformat(completed_date_value)
    except ValueError:
        messages.error(
            request,
            "Please enter a valid repair completion date.",
        )
        return redirect("assets")

    if not repaired_condition:
        messages.error(
            request,
            "Please select the condition after repair.",
        )
        return redirect("assets")

    valid_repaired_conditions = {
        AssetRepair.RepairedCondition.GOOD,
        AssetRepair.RepairedCondition.FAIR,
    }

    if repaired_condition not in valid_repaired_conditions:
        messages.error(
            request,
            "The repaired condition must be Good or Fair.",
        )
        return redirect("assets")

    if not repair_notes:
        messages.error(
            request,
            "Please describe the repair performed.",
        )
        return redirect("assets")

    repair_cost = None

    if repair_cost_value:
        try:
            repair_cost = Decimal(repair_cost_value)
        except InvalidOperation:
            messages.error(
                request,
                "Please enter a valid repair cost.",
            )
            return redirect("assets")

        if repair_cost < 0:
            messages.error(
                request,
                "Repair cost cannot be negative.",
            )
            return redirect("assets")

    repaired_by = (
        request.user.get_full_name()
        or getattr(request.user, "username", "")
        or "System"
    )[:160]

    repair = AssetRepair.objects.create(
        asset=asset,
        completed_date=completed_date,
        repair_notes=repair_notes,
        repair_provider=repair_provider,
        repair_cost=repair_cost,
        repaired_condition=repaired_condition,
        repaired_by=repaired_by,
    )

    asset.condition = repaired_condition
    asset.status = Asset.Status.AVAILABLE
    asset.save(
        update_fields=[
            "condition",
            "status",
            "updated_at",
        ]
    )

    system_user = _get_or_create_audit_system_user(request)

    if system_user and system_user.is_active:
        AuditLog.objects.create(
            action=AuditLog.Action.REPAIR,
            description=(
                f"Repaired {asset.asset_tag} on "
                f"{repair.completed_date}. "
                f"Condition: {repair.repaired_condition}."
            ),
            user=system_user,
            asset=asset,
        )

    messages.success(
        request,
        (
            f"{asset.asset_tag} was repaired and is now "
            f"Available ({asset.get_condition_display()})."
        ),
    )

    return redirect("assets")





QUALITY_HARDWARE_CHECKS = [
    ("casing", "Casing / System Unit"),
    ("display", "Display / Monitor"),
    ("keyboard", "Keyboard / Button"),
    ("touchpad", "Touchpad / Mouse"),
    ("charger", "Charger / Power Cord"),
    ("webcam", "Webcam / Speaker"),
    ("usb", "USB / SDCARD"),
    ("ports", "VGA / HDMI / Disp Port"),
    ("battery", "Battery / Power Supply"),
    ("storage", "HDD / SDD"),
    ("odd", "ODD / FDD"),
    ("addon", "Add-on Card"),
]

QUALITY_SOFTWARE_CHECKS = [
    ("operating_system", "Operating System"),
    ("office_application", "Office Application"),
    ("antivirus", "Anti-Virus"),
    ("other_software", "Other Software"),
]

QUALITY_ACCESS_CHECKS = [
    ("profile", "Profile / Domain Profile"),
    ("email", "Email"),
    ("bitlocker", "Bitlocker"),
    ("nav", "NAV"),
    ("fileserver", "Fileserver"),
    ("network", "Network"),
]


SOFTWARE_STATUS_FIELDS = {
    "operating_system": "os_status",
    "office_application": "office_status",
    "antivirus": "antivirus_status",
    "other_software": "other_software_status",
}

ACCESS_STATUS_FIELDS = {
    "profile": "profile_status",
    "email": "email_status",
    "bitlocker": "bitlocker_status",
    "nav": "nav_status",
    "fileserver": "fileserver_status",
    "network": "network_status",
}


def _inspection_actor(request):
    """Return a safe display name for the person creating the record."""
    return (
        request.user.get_full_name()
        or getattr(request.user, "username", "")
        or "System"
    )[:160]


def _inspection_system_user(request):
    """Reuse the project's SystemUser audit identity helper."""
    username = getattr(request.user, "username", "").strip()
    if not username:
        return None

    display_name = (
        request.user.get_full_name()
        or username
    )[:160]

    system_user, _created = SystemUser.objects.get_or_create(
        username=username,
        defaults={
            "display_name": display_name,
            "role": SystemUser.Role.IT_STAFF,
            "is_active": True,
        },
    )
    return system_user


def _parse_inspection_date(raw_value, label, errors, default=None):
    value = (raw_value or "").strip()
    if not value:
        return default

    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"Enter a valid {label}.")
        return default


def _inspection_checks(request, prefix, definitions):
    """Store each check as {value, status} JSON."""
    checks = {}

    for key, _label in definitions:
        if prefix == "hardware":
            value = request.POST.get(f"hardware_{key}_function", "").strip()
            appearance = request.POST.get(f"hardware_{key}_appearance", "").strip()
            signature = _inspection_actor(request) if (appearance or value) else ""
            status_field = None
        elif prefix == "software":
            value = request.POST.get(key, "").strip()
            status_field = SOFTWARE_STATUS_FIELDS[key]
        else:
            value = request.POST.get(key, "").strip()
            status_field = ACCESS_STATUS_FIELDS[key]

        checks[key] = {
            "value": value,
        }
        if prefix == "hardware":
            checks[key].update({
                "appearance": appearance,
                "function": value,
                "signature": signature,
            })
        else:
            checks[key].update({
                "status": request.POST.get(status_field, "").strip(),
                "remark": request.POST.get(f"{key}_remark", "").strip(),
                "signature": _inspection_actor(request) if (value or request.POST.get(status_field, "").strip() or request.POST.get(f"{key}_remark", "").strip()) else "",
            })

    return checks


def _inspection_assets():
    """Return assets prepared for the browser-side asset-tag lookup."""
    assignment_history = (
        AssetAssignment.objects
        .select_related("employee")
        .order_by("-start_date", "-pk")
    )

    assets = (
        Asset.objects
        .select_related(
            "asset_type",
            "department",
            "location",
        )
        .prefetch_related(
            Prefetch(
                "assignments",
                queryset=assignment_history,
                to_attr="inspection_assignments",
            )
        )
        .order_by("asset_tag")
    )

    for asset in assets:
        active_assignments = [
            assignment
            for assignment in asset.inspection_assignments
            if assignment.end_date is None
        ]
        asset.current_holder_name = ", ".join(
            assignment.employee.name
            for assignment in active_assignments
        )
        # Use the latest assignment history date, even when the assignment
        # has ended, so the Assigned date always reflects the asset history.
        asset.current_assignment_date = (
            asset.inspection_assignments[0].start_date
            if asset.inspection_assignments
            else None
        )

    return assets


def _quality_inspection_context():
    return {
        "hardware_checks": QUALITY_HARDWARE_CHECKS,
        "software_checks": QUALITY_SOFTWARE_CHECKS,
        "access_checks": QUALITY_ACCESS_CHECKS,
        "inspection_results": ComputerQualityInspection.Result.choices,
        "inspection_assets": _inspection_assets(),
    }


@login_required
def quality_inspection(request):
    """
    Display and save the computer quality inspection form.

    GET:
        Shows the inspection page and provides existing assets for the
        asset-tag autocomplete and automatic field population.

    POST:
        Validates the asset tag against the Asset table, stores the
        inspection, and writes an audit-log entry.
    """
    if request.method == "GET":
        return render(
            request,
            "computer_quality_inspection.html",
            _quality_inspection_context(),
        )

    errors = []
    asset_tag = request.POST.get("asset_tag", "").strip()

    asset = (
        Asset.objects
        .select_related("asset_type", "department", "location")
        .filter(asset_tag=asset_tag)
        .first()
    )

    if not asset:
        errors.append(
            "Enter an existing asset tag before saving the inspection."
        )

    inspection_date = _parse_inspection_date(
        request.POST.get("inspection_date"),
        "inspection date",
        errors,
        default=date.today(),
    )
    purchased_date = _parse_inspection_date(
        request.POST.get("purchased_date"),
        "purchased date",
        errors,
    )

    if (
        purchased_date
        and inspection_date
        and purchased_date > inspection_date
    ):
        errors.append(
            "Purchased date cannot be after the inspection date."
        )

    result = request.POST.get(
        "result",
        ComputerQualityInspection.Result.PENDING,
    ).strip()
    valid_results = {
        value
        for value, _label in ComputerQualityInspection.Result.choices
    }

    if result not in valid_results:
        errors.append("Select a valid inspection result.")

    if errors:
        for error in errors:
            messages.error(request, error)
        return redirect("quality-inspection")

    with transaction.atomic():
        system_user = _inspection_system_user(request)

        inspection = ComputerQualityInspection.objects.create(
            asset=asset,
            asset_no=asset.asset_tag,
            user_name=request.POST.get("user_name", "").strip(),
            position=request.POST.get("position", "").strip(),
            inspection_date=inspection_date,
            supplier=request.POST.get("supplier", "").strip(),
            purchased_date=purchased_date,
            computer_type=request.POST.get("computer_type", "").strip(),
            brand=request.POST.get("brand", "").strip(),
            model=request.POST.get("model", "").strip(),
            processor=request.POST.get("processor", "").strip(),
            memory=request.POST.get("memory", "").strip(),
            storage=request.POST.get("hdd", "").strip(),
            optical_drive=request.POST.get("odd", "").strip(),
            serial_number=request.POST.get("serial_number", "").strip(),
            hardware_checks=_inspection_checks(
                request,
                "hardware",
                QUALITY_HARDWARE_CHECKS,
            ),
            software_checks=_inspection_checks(
                request,
                "software",
                QUALITY_SOFTWARE_CHECKS,
            ),
            access_checks=_inspection_checks(
                request,
                "access",
                QUALITY_ACCESS_CHECKS,
            ),
            verified_by=request.POST.get("verified_by", "").strip(),
            approved_by=request.POST.get("approved_by", "").strip(),
            remarks=request.POST.get("remarks", "").strip(),
            result=result,
            created_by=system_user,
        )

        if system_user and system_user.is_active:
            AuditLog.objects.create(
                action=AuditLog.Action.CREATE,
                description=(
                    f"Created computer quality inspection #{inspection.pk} "
                    f"for asset {asset.asset_tag}."
                ),
                user=system_user,
                asset=asset,
            )

    messages.success(
        request,
        f"Computer quality inspection #{inspection.pk} saved.",
    )
    # Return to the inspection page after saving. This keeps the view
    # independent of an optional detail URL pattern.
    return redirect("quality-inspection")


@login_required
def quality_inspections(request):
    """List saved inspections with asset-tag and text search."""
    query = request.GET.get("q", "").strip()
    result = request.GET.get("result", "").strip()

    inspections = (
        ComputerQualityInspection.objects
        .select_related("asset", "created_by")
        .order_by("-created_at")
    )

    if query:
        inspections = inspections.filter(
            asset__asset_tag__icontains=query
        ) | inspections.filter(
            serial_number__icontains=query
        ) | inspections.filter(
            user_name__icontains=query
        )

    if result:
        inspections = inspections.filter(result=result)

    return render(
        request,
        "quality_inspections.html",
        {
            "inspections": inspections.distinct(),
            "search_query": query,
            "selected_result": result,
            "inspection_results": ComputerQualityInspection.Result.choices,
        },
    )


def _can_edit_quality_inspection(request):
    """Allow the technical teams to update inspection records."""
    user = request.user
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True

    normalize = lambda value: str(value).strip().lower().replace("_", " ").replace("-", " ")
    group_names = {normalize(group.name) for group in user.groups.all()}
    user_roles = {normalize(getattr(user, "role", ""))}
    allowed_groups = {"it technical", "it staff", "network team"}
    if group_names.intersection(allowed_groups) or user_roles.intersection(allowed_groups):
        return True

    username = getattr(user, "username", "").strip()
    system_user = SystemUser.objects.filter(username=username).first()
    return bool(system_user and system_user.is_active and system_user.role == SystemUser.Role.IT_STAFF)


def _preserve_empty_signatures(existing, updated):
    """Keep previous signatures on untouched rows during an edit."""
    for key, old_check in (existing or {}).items():
        new_check = updated.get(key, {})
        tracked_fields = ("value", "appearance", "function", "status", "remark")
        has_value = any(str(new_check.get(field, "") or "").strip() for field in tracked_fields)
        unchanged = all(
            str(new_check.get(field, "") or "").strip()
            == str(old_check.get(field, "") or "").strip()
            for field in tracked_fields
        )
        if old_check.get("signature") and (not has_value or unchanged):
            new_check["signature"] = old_check["signature"]
    return updated


@login_required
def quality_inspection_detail(request, inspection_id):
    """View or edit a saved inspection."""
    inspection = get_object_or_404(
        ComputerQualityInspection.objects.select_related(
            "asset",
            "asset__asset_type",
            "asset__department",
            "asset__location",
            "created_by",
        ),
        pk=inspection_id,
    )
    can_edit = _can_edit_quality_inspection(request)

    if request.method == "POST":
        if not can_edit:
            messages.error(request, "Only IT Technical and Network Team users can update inspections.")
            return redirect("quality-inspection-detail", inspection_id=inspection.pk)

        errors = []
        inspection_date = _parse_inspection_date(
            request.POST.get("inspection_date"), "inspection date", errors, inspection.inspection_date
        )
        purchased_date = _parse_inspection_date(
            request.POST.get("purchased_date"), "purchased date", errors, inspection.purchased_date
        )
        if purchased_date and inspection_date and purchased_date > inspection_date:
            errors.append("Purchased date cannot be after the inspection date.")

        result = request.POST.get("result", inspection.result).strip()
        valid_results = {value for value, _label in ComputerQualityInspection.Result.choices}
        if result not in valid_results:
            errors.append("Select a valid inspection result.")

        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect("quality-inspection-detail", inspection_id=inspection.pk)

        with transaction.atomic():
            inspection.user_name = request.POST.get("user_name", "").strip()
            inspection.position = request.POST.get("position", "").strip()
            inspection.inspection_date = inspection_date
            inspection.supplier = request.POST.get("supplier", "").strip()
            inspection.purchased_date = purchased_date
            inspection.computer_type = request.POST.get("computer_type", "").strip()
            inspection.brand = request.POST.get("brand", "").strip()
            inspection.model = request.POST.get("model", "").strip()
            inspection.processor = request.POST.get("processor", "").strip()
            inspection.memory = request.POST.get("memory", "").strip()
            inspection.storage = request.POST.get("hdd", "").strip()
            inspection.optical_drive = request.POST.get("odd", "").strip()
            inspection.serial_number = request.POST.get("serial_number", "").strip()
            inspection.hardware_checks = _preserve_empty_signatures(
                inspection.hardware_checks,
                _inspection_checks(request, "hardware", QUALITY_HARDWARE_CHECKS),
            )
            inspection.software_checks = _preserve_empty_signatures(
                inspection.software_checks,
                _inspection_checks(request, "software", QUALITY_SOFTWARE_CHECKS),
            )
            inspection.access_checks = _preserve_empty_signatures(
                inspection.access_checks,
                _inspection_checks(request, "access", QUALITY_ACCESS_CHECKS),
            )
            inspection.verified_by = request.POST.get("verified_by", "").strip()
            inspection.approved_by = request.POST.get("approved_by", "").strip()
            inspection.remarks = request.POST.get("remarks", "").strip()
            inspection.result = result
            inspection.save()

            system_user = _inspection_system_user(request)
            if system_user and system_user.is_active:
                AuditLog.objects.create(
                    action=AuditLog.Action.UPDATE,
                    description=(
                        f"Updated computer quality inspection #{inspection.pk} "
                        f"for asset {inspection.asset_id}."
                    ),
                    user=system_user,
                    asset=inspection.asset,
                )

        messages.success(request, f"Computer quality inspection #{inspection.pk} updated.")
        return redirect("quality-inspection-detail", inspection_id=inspection.pk)

    return render(
        request,
        "quality_inspection_detail.html",
        {
            "inspection": inspection,
            "can_edit_inspection": can_edit,
            "inspection_results": ComputerQualityInspection.Result.choices,
        },
    )




def _non_negative_int(raw_value, default=0):
    try:
        return max(int(raw_value or default), 0)
    except (TypeError, ValueError):
        return default

def _system_user_for_request(request):
    username = getattr(request.user, "username", "").strip()
    if not username:
        return None

    display_name = (request.user.get_full_name() or username)[:160]
    system_user, _created = SystemUser.objects.get_or_create(
        username=username,
        defaults={
            "display_name": display_name,
            "role": SystemUser.Role.IT_STAFF,
            "is_active": True,
        },
    )
    return system_user


def _consumable_context(query="", category="", stock_filter=""):
    items = ConsumableItem.objects.filter(is_active=True).order_by("category", "name")

    if query:
        items = items.filter(
            Q(item_code__icontains=query)
            | Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(supplier__icontains=query)
            | Q(storage_location__icontains=query)
        )
    if category:
        items = items.filter(category=category)
    if stock_filter == "low":
        items = items.filter(quantity_on_hand__lte=models.F("reorder_level"))

    all_items = ConsumableItem.objects.filter(is_active=True)
    stats = {
        "total_items": all_items.count(),
        "low_stock": sum(item.is_low_stock for item in all_items),
        "total_units": all_items.aggregate(total=Sum("quantity_on_hand"))["total"] or 0,
        "stock_value": sum(item.stock_value for item in all_items),
    }

    return {
        "items": items,
        "categories": ConsumableItem.Category.choices,
        "category_choices": ConsumableItem.Category.choices,
        # Employee uses `status` in this project rather than `is_active`.
        "employees": Employee.objects.all().order_by("name"),
        "movement_types": ConsumableMovement.MovementType.choices,
        "search_query": query,
        "selected_category": category,
        "selected_stock_filter": stock_filter,
        "stats": stats,
    }


@login_required
def consumables(request):
    """List, search, and create IT infrastructure consumables."""
    if request.method == "POST":
        item_code = request.POST.get("item_code", "").strip().upper()
        name = request.POST.get("name", "").strip()
        category = request.POST.get("category", "").strip()

        valid_categories = {value for value, _label in ConsumableItem.Category.choices}
        errors = []
        if not item_code:
            errors.append("Item code is required.")
        if not name:
            errors.append("Item name is required.")
        if category not in valid_categories:
            errors.append("Select a valid category.")
        if ConsumableItem.objects.filter(item_code=item_code).exists():
            errors.append("That item code already exists.")

        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect("consumables")

        item = ConsumableItem.objects.create(
            item_code=item_code,
            name=name,
            category=category,
            description=request.POST.get("description", "").strip(),
            unit=request.POST.get("unit", "piece").strip() or "piece",
            quantity_on_hand=_non_negative_int(request.POST.get("quantity_on_hand")),
            reorder_level=_non_negative_int(request.POST.get("reorder_level"), default=1),
            unit_cost=request.POST.get("unit_cost", "0") or "0",
            supplier=request.POST.get("supplier", "").strip(),
            storage_location=request.POST.get("storage_location", "").strip(),
            created_by=_system_user_for_request(request),
        )
        messages.success(request, f"{item.name} was added to consumables.")
        return redirect("consumables")

    return render(
        request,
        "consumables.html",
        _consumable_context(
            request.GET.get("q", "").strip(),
            request.GET.get("category", "").strip(),
            request.GET.get("stock", "").strip(),
        ),
    )


@login_required
@require_POST
def consumable_stock_move(request, item_id):
    """Receive, issue, or adjust stock using a locked inventory row."""
    movement_type = request.POST.get("movement_type", "").strip()
    try:
        quantity = int(request.POST.get("quantity", "0"))
    except (TypeError, ValueError):
        quantity = 0

    valid_types = {value for value, _label in ConsumableMovement.MovementType.choices}
    if movement_type not in valid_types or quantity < 1:
        messages.error(request, "Choose a valid movement and quantity.")
        return redirect("consumables")

    with transaction.atomic():
        item = get_object_or_404(
            ConsumableItem.objects.select_for_update(),
            pk=item_id,
            is_active=True,
        )
        if movement_type == ConsumableMovement.MovementType.RECEIVED:
            new_balance = item.quantity_on_hand + quantity
        elif movement_type == ConsumableMovement.MovementType.ISSUED:
            if quantity > item.quantity_on_hand:
                messages.error(request, "Cannot issue more stock than is available.")
                return redirect("consumables")
            new_balance = item.quantity_on_hand - quantity
        else:
            # Adjustment quantity is the new absolute stock balance.
            new_balance = quantity

        item.quantity_on_hand = new_balance
        item.save(update_fields=["quantity_on_hand", "updated_at"])
        ConsumableMovement.objects.create(
            item=item,
            movement_type=movement_type,
            quantity=quantity,
            balance_after=new_balance,
            recipient_id=request.POST.get("recipient") or None,
            reference=request.POST.get("reference", "").strip(),
            remarks=request.POST.get("remarks", "").strip(),
            performed_by=_system_user_for_request(request),
        )

    messages.success(request, f"Stock updated: {item.name} now has {new_balance} {item.unit}(s).")
    return redirect("consumables")


@login_required
def consumable_detail(request, item_id):
    item = get_object_or_404(
        ConsumableItem.objects.prefetch_related("movements__recipient", "movements__performed_by"),
        pk=item_id,
    )
    return render(
        request,
        "consumable_detail.html",
        {
            "item": item,
            "movements": item.movements.all()[:100],
        },
    )



def _activity_sort_key(event):
    """Sort date-only and datetime activity records consistently."""
    obj = event.get("object")
    created_at = getattr(obj, "created_at", None)
    created_key = created_at.timestamp() if created_at else 0
    return event["date"], created_key


def build_asset_activity(asset):
    """Build a unified activity timeline for one asset."""
    activities = []

    assignments = (
        AssetAssignment.objects
        .filter(asset=asset)
        .select_related("employee")
        .order_by("-start_date", "-pk")
    )
    for assignment in assignments:
        employee_name = assignment.employee.name if assignment.employee else "Unassigned"
        activities.append({
            "kind": "assignment",
            "icon": "bi-person-badge",
            "tone": "blue",
            "date": assignment.start_date,
            "date_label": (
                f"{assignment.start_date:%b %d, %Y} – "
                f"{assignment.end_date:%b %d, %Y}"
                if assignment.end_date
                else f"{assignment.start_date:%b %d, %Y} – Present"
            ),
            "title": "Asset assignment",
            "description": f"Assigned to {employee_name}.",
            "actor": assignment.assigned_by or "System",
            "meta": assignment.remarks or "No assignment remarks.",
            "object": assignment,
        })

        if assignment.end_date:
            activities.append({
                "kind": "return",
                "icon": "bi-box-arrow-in-left",
                "tone": "amber",
                "date": assignment.end_date,
                "date_label": f"{assignment.end_date:%b %d, %Y}",
                "title": "Asset returned",
                "description": f"Returned by {employee_name}.",
                "actor": assignment.returned_by or "System",
                "meta": (
                    f"Condition: {assignment.returned_condition or 'Not recorded'}"
                    + (f" · {assignment.remarks}" if assignment.remarks else "")
                ),
                "object": assignment,
            })

    repairs = (
        AssetRepair.objects
        .filter(asset=asset)
        .order_by("-completed_date", "-pk")
    )
    for repair in repairs:
        activities.append({
            "kind": "repair",
            "icon": "bi-wrench-adjustable-circle",
            "tone": "orange",
            "date": repair.completed_date,
            "date_label": f"{repair.completed_date:%b %d, %Y}",
            "title": "Repair completed",
            "description": repair.repair_notes or "Repair activity recorded.",
            "actor": repair.repaired_by or "System",
            "meta": (
                f"Provider: {repair.repair_provider or 'Not recorded'} · "
                f"Condition: {repair.get_repaired_condition_display()}"
                + (f" · Cost: {repair.repair_cost}" if repair.repair_cost is not None else "")
            ),
            "object": repair,
        })

    inspections = (
        ComputerQualityInspection.objects
        .filter(asset=asset)
        .select_related("created_by")
        .order_by("-created_at", "-pk")
    )
    for inspection in inspections:
        inspection_date = inspection.inspection_date or inspection.created_at.date()
        actor = getattr(inspection.created_by, "display_name", None) or "System"
        activities.append({
            "kind": "quality inspection",
            "icon": "bi-clipboard2-pulse",
            "tone": "teal",
            "date": inspection_date,
            "date_label": f"{inspection_date:%b %d, %Y}",
            "title": "Computer quality inspection",
            "description": (
                f"Inspection recorded with result: {inspection.get_result_display()}."
            ),
            "actor": actor,
            "meta": inspection.remarks or "No inspection remarks.",
            "object": inspection,
            "url": reverse("quality-inspection-detail", args=[inspection.pk]),
        })

    audit_logs = (
        AuditLog.objects
        .filter(asset=asset)
        .select_related("user", "employee")
        .order_by("-created_at", "-pk")
    )
    for log in audit_logs:
        activities.append({
            "kind": "audit log",
            "icon": "bi-journal-text",
            "tone": "slate",
            "date": log.created_at.date(),
            "date_label": f"{log.created_at:%b %d, %Y %H:%M}",
            "title": log.get_action_display(),
            "description": log.description,
            "actor": getattr(log.user, "display_name", None) or str(log.user),
            "meta": "Audit log event",
            "object": log,
        })

    activities.sort(key=_activity_sort_key, reverse=True)
    return activities


@login_required
def asset_details(request, asset_tag):
    """Display an asset and every activity recorded against it."""
    asset = get_object_or_404(
        Asset.objects
        .select_related("asset_type", "department", "location")
        .prefetch_related("assignments__employee"),
        asset_tag=asset_tag,
    )
    current_holders = (
        AssetAssignment.objects
        .filter(asset=asset, end_date__isnull=True)
        .select_related("employee", "employee__department", "employee__location")
        .order_by("employee__name")
    )

    return render(
        request,
        "asset-details.html",
        {
            "asset": asset,
            "asset_activity": build_asset_activity(asset),
            "current_holders": current_holders,
            "assignment_history": (
                asset.assignments
                .select_related("employee")
                .order_by("-start_date", "-pk")
            ),
            "employees": (
                Employee.objects
                .filter(status=Employee.Status.ACTIVE)
                .order_by("name")
            ),
            "asset_types": (
                AssetType.objects
                .filter(is_active=True)
                .order_by("name")
            ),
            "departments": Department.objects.order_by("name"),
            "locations": Location.objects.order_by("name"),
        },
    )
