from decimal import Decimal

from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

from django.conf import settings
from django.db import models
from django.utils import timezone


class QualityApprovalRole(models.TextChoices):
    TECHNICAL_SUPERVISOR = "technical_supervisor", "Technical Supervisor"
    SERVER_SUPERVISOR = "server_supervisor", "Server Supervisor"
    NAV_SAP_SUPERVISOR = "nav_sap_supervisor", "NAV/SAP Supervisor"
    IT_MANAGER = "it_manager", "IT Manager"


class QualityApprovalStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class QualityInspectionApproval(models.Model):
    inspection = models.ForeignKey(
        "ComputerQualityInspection",
        on_delete=models.CASCADE,
        related_name="approvals",
    )
    role = models.CharField(
        max_length=40,
        choices=QualityApprovalRole.choices,
    )
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="quality_inspection_approvals",
    )
    status = models.CharField(
        max_length=20,
        choices=QualityApprovalStatus.choices,
        default=QualityApprovalStatus.PENDING,
    )
    remarks = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["role"]
        constraints = [
            models.UniqueConstraint(
                fields=["inspection", "role"],
                name="unique_quality_approval_per_role",
            )
        ]
        indexes = [
            models.Index(fields=["inspection", "status"]),
            models.Index(fields=["role", "status"]),
        ]

    def approve(self, user, remarks=""):
        self.approver = user
        self.status = QualityApprovalStatus.APPROVED
        self.remarks = (remarks or "").strip()
        self.decided_at = timezone.now()
        self.save(update_fields=[
            "approver",
            "status",
            "remarks",
            "decided_at",
            "updated_at",
        ])

    def reject(self, user, remarks=""):
        self.approver = user
        self.status = QualityApprovalStatus.REJECTED
        self.remarks = (remarks or "").strip()
        self.decided_at = timezone.now()
        self.save(update_fields=[
            "approver",
            "status",
            "remarks",
            "decided_at",
            "updated_at",
        ])

    def __str__(self):
        return (
            f"Inspection #{self.inspection_id} - "
            f"{self.get_role_display()} - {self.get_status_display()}"
        )


QUALITY_APPROVAL_GROUPS = {
    QualityApprovalRole.TECHNICAL_SUPERVISOR: "Technical Supervisor",
    QualityApprovalRole.SERVER_SUPERVISOR: "Server Supervisor",
    QualityApprovalRole.NAV_SAP_SUPERVISOR: "NAV/SAP Supervisor",
    QualityApprovalRole.IT_MANAGER: "IT Manager",
}


def ensure_quality_approvals(inspection):
    """Create the four approval rows for an inspection if missing."""
    for role, _label in QualityApprovalRole.choices:
        QualityInspectionApproval.objects.get_or_create(
            inspection=inspection,
            role=role,
            defaults={"status": QualityApprovalStatus.PENDING},
        )


def user_can_approve_quality_inspection(user, role):
    """Check approval permission on the server."""
    if not user or not user.is_authenticated or not user.is_active:
        return False

    if user.is_superuser:
        return True

    group_name = QUALITY_APPROVAL_GROUPS.get(role)
    if not group_name:
        return False

    return user.groups.filter(name=group_name).exists()


def get_quality_approval_context(inspection, user):
    """Return approval records, counts, and roles available to the user."""
    ensure_quality_approvals(inspection)

    approvals = list(
        inspection.approvals
        .select_related("approver")
        .order_by("role")
    )

    approved_count = sum(
        approval.status == QualityApprovalStatus.APPROVED
        for approval in approvals
    )
    rejected_count = sum(
        approval.status == QualityApprovalStatus.REJECTED
        for approval in approvals
    )

    approval_can_act = [
        role
        for role, _label in QualityApprovalRole.choices
        if user_can_approve_quality_inspection(user, role)
    ]

    return {
        "approval_records": approvals,
        "approval_can_act": approval_can_act,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "pending_count": max(4 - approved_count - rejected_count, 0),
        "is_fully_approved": (
            len(approvals) == 4 and approved_count == 4
        ),
    }

class AssetType(models.Model):
    """
    One row per equipment category shown in the sidebar.
    Kept as a table (not hardcoded choices) so Settings can add a
    new category without a migration.
    """
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=80, unique=True)    
    icon = models.CharField(max_length=50, blank=True)    
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Department(models.Model):
    name = models.CharField(max_length=120, unique=True)

    def __str__(self):
        return self.name


class Location(models.Model):
    name = models.CharField(max_length=120, unique=True)
    address = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.name


class Employee(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        OFFBOARDED = "offboarded", "Offboarded"

    employee_id = models.CharField(max_length=30, primary_key=True)
    name = models.CharField(max_length=160)
    email = models.EmailField(unique=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="employees")
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="employees")
    role = models.CharField(max_length=120)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        indexes = [
            models.Index(fields=["department"]),
            models.Index(fields=["location"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.employee_id})"

class Asset(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        ASSIGNED = "assigned", "Assigned"
        IN_REPAIR = "in_repair", "In Repair"
        RETIRED = "retired", "Retired"
        LOST = "lost", "Lost/Stolen"

    class Condition(models.TextChoices):
        NEW = "new", "New"
        GOOD = "good", "Good"
        FAIR = "fair", "Fair"
        DAMAGED = "damaged", "Damaged"
        FOR_DISPOSAL = "for_disposal", "For Disposal"

    asset_tag = models.CharField(
        max_length=50,
        primary_key=True,
    )

    asset_type = models.ForeignKey(
        AssetType,
        on_delete=models.PROTECT,
        related_name="assets",
    )

    brand = models.CharField(max_length=100)
    model = models.CharField(max_length=120)

    serial_number = models.CharField(
        max_length=120,
        unique=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AVAILABLE,
    )

    condition = models.CharField(
        max_length=20,
        choices=Condition.choices,
        default=Condition.NEW,
    )

    purchase_date = models.DateField(
        null=True,
        blank=True,
    )

    warranty_expiration = models.DateField(
        null=True,
        blank=True,
    )

    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="assets",
    )

    location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name="assets",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["asset_tag"]
        indexes = [
            models.Index(fields=["asset_type"]),
            models.Index(fields=["status"]),
            models.Index(fields=["department"]),
            models.Index(fields=["location"]),
            models.Index(fields=["warranty_expiration"]),
        ]

    def __str__(self):
        return f"{self.asset_tag} - {self.brand} {self.model}"

    @property
    def current_assignment(self):
        """
        Returns the currently open assignment.

        The view prefetched current assignments into
        `current_assignments` to avoid one query per asset.
        """
        if hasattr(self, "current_assignments"):
            return (
                self.current_assignments[0]
                if self.current_assignments
                else None
            )

        return (
            self.assignments
            .filter(end_date__isnull=True)
            .select_related("employee")
            .first()
        )

    @property
    def current_holder(self):
        assignment = self.current_assignment
        return assignment.employee if assignment else None

    def is_warranty_expiring_soon(self, days=30):
        if not self.warranty_expiration:
            return False

        remaining_days = (
            self.warranty_expiration - timezone.now().date()
        ).days

        return 0 <= remaining_days <= days


class AssetAssignment(models.Model):
    """
    Every row here is one entry in an asset's assignment history.
    An open row (end_date is null) means the asset is currently
    with that employee.
    """
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="assignments")
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="assignments")
    assigned_by = models.CharField(max_length=160)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    returned_by = models.CharField(max_length=160, blank=True)
    returned_condition = models.CharField(max_length=20, choices=Asset.Condition.choices, blank=True)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["asset", "end_date"]),
            models.Index(fields=["employee"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "employee"],
                condition=models.Q(end_date__isnull=True),
                name="unique_open_assignment_per_asset_employee",
            )
        ]

    def clean(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError("End date cannot be before start date.")

    def __str__(self):
        return f"{self.asset_id} -> {self.employee_id} ({self.start_date} - {self.end_date or 'present'})"


class SystemUser(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrator"
        IT_STAFF = "it_staff", "IT Staff"
        VIEWER = "viewer", "Viewer"

    username = models.CharField(max_length=80, unique=True)
    display_name = models.CharField(max_length=160)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.IT_STAFF)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.display_name


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        ASSIGN = "assign", "Assign"
        REPAIR = "repair", "Repair"
        RETURN = "return", "Return"
        RETIRE = "retire", "Retire"
        DELETE = "delete", "Delete"

    action = models.CharField(max_length=20, choices=Action.choices)
    description = models.TextField()
    user = models.ForeignKey(SystemUser, on_delete=models.PROTECT, related_name="audit_logs")
    asset = models.ForeignKey(Asset, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs")
    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"[{self.created_at}] {self.action} by {self.user}"

class AssetRepair(models.Model):
    class RepairedCondition(models.TextChoices):
        GOOD = Asset.Condition.GOOD, "Good"
        FAIR = Asset.Condition.FAIR, "Fair"

    asset = models.ForeignKey(
        Asset,
        on_delete=models.PROTECT,
        related_name="repairs",
    )

    reported_date = models.DateField(
        default=timezone.localdate,
    )

    completed_date = models.DateField()

    repair_notes = models.TextField()

    repair_provider = models.CharField(
        max_length=160,
        blank=True,
    )

    repair_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    repaired_condition = models.CharField(
        max_length=20,
        choices=RepairedCondition.choices,
        default=RepairedCondition.GOOD,
    )

    repaired_by = models.CharField(
        max_length=160,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-completed_date", "-created_at"]
        indexes = [
            models.Index(fields=["asset", "completed_date"]),
        ]

    def __str__(self):
        return f"Repair: {self.asset_id} on {self.completed_date}"

    

class ComputerQualityInspection(models.Model):
    class Result(models.TextChoices):
        PENDING = "pending", "Pending review"
        PASSED = "passed", "Passed"
        FAILED = "failed", "Failed"
        CONDITIONAL = "conditional", "Conditional pass"

    asset = models.ForeignKey(
        Asset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quality_inspections",
    )
    user_name = models.CharField(max_length=160, blank=True)
    position = models.CharField(max_length=160, blank=True)
    inspection_date = models.DateField(default=timezone.localdate)
    supplier = models.CharField(max_length=160, blank=True)
    purchased_date = models.DateField(null=True, blank=True)

    computer_type = models.CharField(max_length=80, blank=True)
    brand = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=120, blank=True)
    processor = models.CharField(max_length=160, blank=True)
    memory = models.CharField(max_length=80, blank=True)
    storage = models.CharField(max_length=120, blank=True)
    optical_drive = models.CharField(max_length=80, blank=True)
    serial_number = models.CharField(max_length=120, blank=True)
    asset_no = models.CharField(max_length=50, blank=True)

    # Each JSON object stores the item key, selected status, and optional notes.
    hardware_checks = models.JSONField(default=dict, blank=True)
    software_checks = models.JSONField(default=dict, blank=True)
    access_checks = models.JSONField(default=dict, blank=True)

    verified_by = models.CharField(max_length=160, blank=True)
    approved_by = models.CharField(max_length=160, blank=True)
    remarks = models.TextField(blank=True)
    result = models.CharField(
        max_length=20,
        choices=Result.choices,
        default=Result.PENDING,
    )

    created_by = models.ForeignKey(
        SystemUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quality_inspections_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["inspection_date"]),
            models.Index(fields=["serial_number"]),
            models.Index(fields=["asset_no"]),
            models.Index(fields=["result"]),
        ]

    def clean(self):
        if (
            self.purchased_date
            and self.inspection_date
            and self.purchased_date > self.inspection_date
        ):
            raise ValidationError(
                "Purchased date cannot be after the inspection date."
            )

    def __str__(self):
        subject = self.asset_no or self.serial_number or self.model or "Computer"
        return f"Quality inspection — {subject} — {self.inspection_date}"



class ConsumableItem(models.Model):
    class Category(models.TextChoices):
        BATTERY = "battery", "Battery / Power"
        CABLE = "cable", "Cables / Connectors"
        ADAPTER = "adapter", "Adapters / Chargers"
        TOOL = "tool", "Tools"
        PERIPHERAL = "peripheral", "Peripherals"
        NETWORK = "network", "Network Supplies"
        STORAGE = "storage", "Storage Media"
        SAFETY = "safety", "Safety / ESD"
        OTHER = "other", "Other IT Supply"

    item_code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=160)
    category = models.CharField(max_length=20, choices=Category.choices)
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=30, default="piece")
    quantity_on_hand = models.PositiveIntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=1)
    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    supplier = models.CharField(max_length=160, blank=True)
    storage_location = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "SystemUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consumable_items_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "name"]
        indexes = [
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["item_code"]),
            models.Index(fields=["quantity_on_hand"]),
        ]

    def clean(self):
        if self.reorder_level < 0:
            raise ValidationError("Reorder level cannot be negative.")

    @property
    def is_low_stock(self):
        return self.quantity_on_hand <= self.reorder_level

    @property
    def stock_value(self):
        return self.quantity_on_hand * self.unit_cost

    def __str__(self):
        return f"{self.item_code} · {self.name}"


class ConsumableMovement(models.Model):
    class MovementType(models.TextChoices):
        RECEIVED = "received", "Stock in"
        ISSUED = "issued", "Stock out"
        ADJUSTED = "adjusted", "Adjustment"

    item = models.ForeignKey(
        ConsumableItem,
        on_delete=models.CASCADE,
        related_name="movements",
    )
    movement_type = models.CharField(max_length=12, choices=MovementType.choices)
    quantity = models.PositiveIntegerField()
    balance_after = models.PositiveIntegerField(default=0)
    recipient = models.ForeignKey(
        "Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consumable_movements",
    )
    reference = models.CharField(max_length=120, blank=True)
    remarks = models.TextField(blank=True)
    performed_by = models.ForeignKey(
        "SystemUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consumable_movements_performed",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["item", "created_at"]),
            models.Index(fields=["movement_type"]),
        ]

    def clean(self):
        if self.quantity < 1:
            raise ValidationError("Movement quantity must be at least 1.")

    def __str__(self):
        return f"{self.item.item_code} · {self.get_movement_type_display()} · {self.quantity}"
