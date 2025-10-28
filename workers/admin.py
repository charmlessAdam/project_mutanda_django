from django.contrib import admin
from .models import Worker, EquipmentAssignment, WorkerActivity


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ['employee_id', 'full_name', 'department', 'position', 'status', 'hire_date']
    list_filter = ['status', 'department', 'position']
    search_fields = ['employee_id', 'first_name', 'last_name', 'email']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'last_updated_by']
    fieldsets = (
        ('Identification', {
            'fields': ('employee_id', 'first_name', 'last_name')
        }),
        ('Contact Information', {
            'fields': ('email', 'phone', 'emergency_contact', 'emergency_phone')
        }),
        ('Employment Details', {
            'fields': ('department', 'position', 'hire_date', 'termination_date', 'status', 'supervisor')
        }),
        ('System Account', {
            'fields': ('user_account',),
            'classes': ('collapse',)
        }),
        ('Additional Information', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('Tracking', {
            'fields': ('created_at', 'updated_at', 'created_by', 'last_updated_by'),
            'classes': ('collapse',)
        }),
    )


@admin.register(EquipmentAssignment)
class EquipmentAssignmentAdmin(admin.ModelAdmin):
    list_display = ['worker', 'item_name', 'quantity', 'assigned_date', 'is_active', 'condition_at_assignment']
    list_filter = ['is_active', 'item_type', 'assigned_date']
    search_fields = ['worker__first_name', 'worker__last_name', 'worker__employee_id', 'item_name']
    readonly_fields = ['assigned_date', 'created_at', 'updated_at', 'assigned_by', 'returned_by']
    fieldsets = (
        ('Assignment Details', {
            'fields': ('worker', 'inventory_item', 'item_name', 'item_type', 'quantity')
        }),
        ('Dates', {
            'fields': ('assigned_date', 'expected_return_date', 'returned_date', 'is_active')
        }),
        ('Condition', {
            'fields': ('condition_at_assignment', 'condition_at_return')
        }),
        ('Notes', {
            'fields': ('assignment_notes', 'return_notes', 'damage_notes'),
            'classes': ('collapse',)
        }),
        ('Tracking', {
            'fields': ('assigned_by', 'returned_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(WorkerActivity)
class WorkerActivityAdmin(admin.ModelAdmin):
    list_display = ['worker', 'action', 'performed_by', 'timestamp']
    list_filter = ['action', 'timestamp']
    search_fields = ['worker__first_name', 'worker__last_name', 'worker__employee_id', 'description']
    readonly_fields = ['worker', 'action', 'description', 'assignment', 'performed_by', 'timestamp', 'old_values', 'new_values']

    def has_add_permission(self, request):
        # Activities are created automatically, not manually
        return False

    def has_change_permission(self, request, obj=None):
        # Activities should not be edited
        return False
