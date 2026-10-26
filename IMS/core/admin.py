from django.contrib import admin

from .models import (
    Asset,
    AssetAssignment,
    AssetType,
    AuditLog,
    Department,
    Employee,
    Location,
    SystemUser,
    AssetRepair,
)


@admin.register(AssetRepair)
class AssetRepairAdmin(admin.ModelAdmin):
    list_display = (
        "asset",
        "reported_date",
        "completed_date",
        "repaired_condition",
        "repaired_by",
        "repair_provider",
        "repair_cost",
    )

    search_fields = (
        "asset__asset_tag",
        "asset__serial_number",
        "repaired_by",
        "repair_provider",
        "repair_notes",
    )

    list_filter = (
        "repaired_condition",
        "reported_date",
        "completed_date",
    )

    ordering = (
        "-completed_date",
        "-created_at",
    )

    autocomplete_fields = (
        "asset",
    )

    fieldsets = (
        (
            "Repair Information",
            {
                "fields": (
                    "asset",
                    "reported_date",
                    "completed_date",
                    "repaired_condition",
                    "repaired_by",
                    "repair_provider",
                    "repair_cost",
                    "repair_notes",
                )
            },
        ),
    )


@admin.register(AssetType)
class AssetTypeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "icon",
        "is_active",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "name",
        "slug",
        "icon",
    )

    prepopulated_fields = {
        "slug": ("name",),
    }

    ordering = (
        "name",
    )


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "employee_count",
        "asset_count",
    )

    search_fields = (
        "name",
    )

    ordering = (
        "name",
    )

    @admin.display(description="Employees")
    def employee_count(self, obj):
        return obj.employees.count()

    @admin.display(description="Assets")
    def asset_count(self, obj):
        return obj.assets.count()


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "address",
        "employee_count",
        "asset_count",
    )

    search_fields = (
        "name",
        "address",
    )

    ordering = (
        "name",
    )

    @admin.display(description="Employees")
    def employee_count(self, obj):
        return obj.employees.count()

    @admin.display(description="Assets")
    def asset_count(self, obj):
        return obj.assets.count()


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "employee_id",
        "name",
        "email",
        "department",
        "location",
        "role",
        "status",
        "assigned_asset_count",
    )

    list_filter = (
        "status",
        "department",
        "location",
    )

    search_fields = (
        "employee_id",
        "name",
        "email",
        "role",
    )

    ordering = (
        "name",
    )

    autocomplete_fields = (
        "department",
        "location",
    )

    fieldsets = (
        (
            "Employee information",
            {
                "fields": (
                    "employee_id",
                    "name",
                    "email",
                    "role",
                )
            },
        ),
        (
            "Organization",
            {
                "fields": (
                    "department",
                    "location",
                    "status",
                )
            },
        ),
    )

    @admin.display(description="Assigned assets")
    def assigned_asset_count(self, obj):
        return obj.assignments.filter(
            end_date__isnull=True
        ).count()


class AssetAssignmentInline(admin.TabularInline):
    model = AssetAssignment
    extra = 0
    ordering = (
        "-start_date",
    )

    fields = (
        "employee",
        "assigned_by",
        "start_date",
        "end_date",
        "returned_by",
        "returned_condition",
        "remarks",
    )

    autocomplete_fields = (
        "employee",
    )


class AssetAuditLogInline(admin.TabularInline):
    model = AuditLog
    extra = 0
    can_delete = False
    ordering = (
        "-created_at",
    )

    fields = (
        "action",
        "description",
        "user",
        "employee",
        "created_at",
    )

    readonly_fields = (
        "action",
        "description",
        "user",
        "employee",
        "created_at",
    )

    autocomplete_fields = (
        "user",
        "employee",
    )


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = (
        "asset_tag",
        "asset_type",
        "brand",
        "model",
        "serial_number",
        "status",
        "condition",
        "department",
        "location",
        "current_holder_display",
        "warranty_expiration",
        "updated_at",
    )

    list_filter = (
        "asset_type",
        "status",
        "condition",
        "department",
        "location",
        "purchase_date",
        "warranty_expiration",
    )

    search_fields = (
        "asset_tag",
        "brand",
        "model",
        "serial_number",
        "department__name",
        "location__name",
    )

    ordering = (
        "asset_tag",
    )

    autocomplete_fields = (
        "asset_type",
        "department",
        "location",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "current_holder_display",
        "warranty_status",
    )

    fieldsets = (
        (
            "Asset identification",
            {
                "fields": (
                    "asset_tag",
                    "asset_type",
                    "brand",
                    "model",
                    "serial_number",
                )
            },
        ),
        (
            "Current status",
            {
                "fields": (
                    "status",
                    "condition",
                    "current_holder_display",
                )
            },
        ),
        (
            "Purchase and warranty",
            {
                "fields": (
                    "purchase_date",
                    "warranty_expiration",
                    "warranty_status",
                )
            },
        ),
        (
            "Organization and location",
            {
                "fields": (
                    "department",
                    "location",
                )
            },
        ),
        (
            "System information",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    inlines = (
        AssetAssignmentInline,
        AssetAuditLogInline,
    )

    @admin.display(description="Current holder")
    def current_holder_display(self, obj):
        holder = obj.current_holder

        if holder:
            return f"{holder.name} ({holder.employee_id})"

        return "Unassigned"

    @admin.display(description="Warranty status")
    def warranty_status(self, obj):
        if not obj.warranty_expiration:
            return "No warranty date"

        if obj.is_warranty_expiring_soon():
            return "Expiring within 30 days"

        if obj.warranty_expiration < obj.updated_at.date():
            return "Expired"

        return "Active"


@admin.register(AssetAssignment)
class AssetAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "asset",
        "employee",
        "assigned_by",
        "start_date",
        "end_date",
        "assignment_status",
        "returned_by",
        "returned_condition",
    )

    list_filter = (
        "start_date",
        "end_date",
        "returned_condition",
    )

    search_fields = (
        "asset__asset_tag",
        "asset__serial_number",
        "employee__employee_id",
        "employee__name",
        "assigned_by",
        "returned_by",
    )

    ordering = (
        "-start_date",
    )

    autocomplete_fields = (
        "asset",
        "employee",
    )

    fieldsets = (
        (
            "Assignment",
            {
                "fields": (
                    "asset",
                    "employee",
                    "assigned_by",
                    "start_date",
                    "end_date",
                )
            },
        ),
        (
            "Return information",
            {
                "fields": (
                    "returned_by",
                    "returned_condition",
                    "remarks",
                )
            },
        ),
    )

    @admin.display(description="Status")
    def assignment_status(self, obj):
        if obj.end_date is None:
            return "Active"

        return "Returned"


@admin.register(SystemUser)
class SystemUserAdmin(admin.ModelAdmin):
    list_display = (
        "username",
        "display_name",
        "role",
        "is_active",
    )

    list_filter = (
        "role",
        "is_active",
    )

    search_fields = (
        "username",
        "display_name",
    )

    ordering = (
        "display_name",
    )

    fieldsets = (
        (
            "User information",
            {
                "fields": (
                    "username",
                    "display_name",
                    "role",
                    "is_active",
                )
            },
        ),
    )


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "action",
        "description_short",
        "user",
        "asset",
        "employee",
    )

    list_filter = (
        "action",
        "created_at",
    )

    search_fields = (
        "description",
        "user__username",
        "user__display_name",
        "asset__asset_tag",
        "employee__employee_id",
        "employee__name",
    )

    ordering = (
        "-created_at",
    )

    autocomplete_fields = (
        "user",
        "asset",
        "employee",
    )

    readonly_fields = (
        "created_at",
    )

    fieldsets = (
        (
            "Event",
            {
                "fields": (
                    "action",
                    "description",
                    "created_at",
                )
            },
        ),
        (
            "Related records",
            {
                "fields": (
                    "user",
                    "asset",
                    "employee",
                )
            },
        ),
    )

    @admin.display(description="Description")
    def description_short(self, obj):
        if len(obj.description) > 80:
            return f"{obj.description[:80]}..."

        return obj.description
