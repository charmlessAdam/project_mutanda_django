from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model
from .models import UserActivity, Department

User = get_user_model()

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'full_name', 'role', 'manager', 'department', 'is_active', 'can_create_users')
    list_filter = ('role', 'is_staff', 'is_active', 'can_create_users', 'can_edit_users', 'department', 'date_joined')
    search_fields = ('username', 'first_name', 'last_name', 'email', 'department')
    ordering = ('role', 'username')
    raw_id_fields = ('manager', 'created_by')
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Profile Info', {
            'fields': ('role', 'phone', 'location', 'bio', 'department'),
        }),
        ('Hierarchy', {
            'fields': ('manager', 'created_by'),
        }),
        ('Permissions', {
            'fields': ('can_create_users', 'can_edit_users', 'can_deactivate_users'),
            'description': 'These are automatically set based on role but can be overridden'
        }),
        ('Important Dates', {
            'fields': ('last_password_change',),
        }),
    )
    
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Profile Info', {
            'fields': ('email', 'first_name', 'last_name', 'role', 'department', 'manager'),
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('manager', 'created_by')

        

@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'performed_by', 'action', 'target_user', 'description')
    list_filter = ('action', 'timestamp')
    search_fields = ('performed_by__username', 'target_user__username', 'description')
    ordering = ('-timestamp',)
    readonly_fields = ('timestamp', 'ip_address')
    raw_id_fields = ('performed_by', 'target_user')
    
    def has_add_permission(self, request):
        return False  # Activities are created programmatically
    
    def has_change_permission(self, request, obj=None):
        return False  # Activities shouldn't be modified

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'head', 'created_at')
    search_fields = ('name', 'description')
    raw_id_fields = ('head',)
    ordering = ('name',)
