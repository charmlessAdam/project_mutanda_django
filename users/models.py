from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.exceptions import ValidationError

class User(AbstractUser):
    ROLE_CHOICES = [
        ('super_admin', 'Super Admin'),
        ('admin', 'Admin'),
        ('finance_manager', 'Finance Manager'),
        ('procurement', 'Procurement'),
        ('head_veterinary', 'Head Veterinary'),
        ('manager', 'Manager'),
        ('operator', 'Operator'),
        ('warehouse_worker', 'Warehouse Worker'),
        ('viewer', 'Viewer'),
    ]
    
    # Role hierarchy levels (higher number = more permissions)
    ROLE_HIERARCHY = {
        'viewer': 1,
        'warehouse_worker': 2,
        'operator': 3,
        'head_veterinary': 4,
        'finance_manager': 4,
        'procurement': 4,
        'manager': 4,
        'admin': 5,
        'super_admin': 6,
    }
    
    # Define which roles can manage which roles
    MANAGEMENT_PERMISSIONS = {
        'super_admin': ['admin', 'finance_manager', 'procurement', 'head_veterinary', 'manager', 'operator', 'warehouse_worker', 'viewer'],
        'admin': ['finance_manager', 'procurement', 'head_veterinary', 'manager', 'operator', 'warehouse_worker', 'viewer'],
        'finance_manager': ['operator', 'warehouse_worker', 'viewer'],
        'procurement': ['operator', 'warehouse_worker', 'viewer'],
        'head_veterinary': ['operator', 'warehouse_worker', 'viewer'],
        'manager': ['operator', 'warehouse_worker', 'viewer'],
        'operator': ['warehouse_worker', 'viewer'],
        'warehouse_worker': [],
        'viewer': [],
    }
    
    role = models.CharField(
        max_length=20, 
        choices=ROLE_CHOICES, 
        default='viewer'
    )
    phone = models.CharField(max_length=20, blank=True, null=True)
    location = models.CharField(max_length=100, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    
    # Hierarchy relationships
    created_by = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='created_users',
        help_text="User who created this account"
    )
    manager = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_users',
        help_text="Direct manager/supervisor"
    )
    
    # Status and permissions
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False, help_text="Soft delete - user is hidden but not removed from database")
    can_create_users = models.BooleanField(default=False)
    can_edit_users = models.BooleanField(default=False)
    can_deactivate_users = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_password_change = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when user was soft deleted")
    
    class Meta:
        ordering = ['role', 'username']
    
    def save(self, *args, **kwargs):
        # Auto-assign permissions based on role
        self._set_permissions_by_role()
        
        # Validate manager relationship
        if self.manager:
            if not self._can_be_managed_by(self.manager):
                raise ValidationError(f"A {self.get_role_display()} cannot be managed by a {self.manager.get_role_display()}")
        
        super().save(*args, **kwargs)
    
    def _set_permissions_by_role(self):
        """Automatically set permissions based on role"""
        permissions_map = {
            'super_admin': {'can_create_users': True, 'can_edit_users': True, 'can_deactivate_users': True, 'is_staff': True, 'is_superuser': True},
            'admin': {'can_create_users': True, 'can_edit_users': True, 'can_deactivate_users': True, 'is_staff': True},
            'manager': {'can_create_users': True, 'can_edit_users': True, 'can_deactivate_users': False, 'is_staff': False},
            'operator': {'can_create_users': False, 'can_edit_users': True, 'can_deactivate_users': False, 'is_staff': False},
            'warehouse_worker': {'can_create_users': False, 'can_edit_users': False, 'can_deactivate_users': False, 'is_staff': False},
            'viewer': {'can_create_users': False, 'can_edit_users': False, 'can_deactivate_users': False, 'is_staff': False},
        }
        
        role_perms = permissions_map.get(self.role, {})
        for perm, value in role_perms.items():
            setattr(self, perm, value)
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username
    
    @property
    def role_level(self):
        """Get numeric level for role hierarchy"""
        return self.ROLE_HIERARCHY.get(self.role, 0)
    
    def can_manage_role(self, target_role):
        """Check if this user can manage users with the target role"""
        manageable_roles = self.MANAGEMENT_PERMISSIONS.get(self.role, [])
        return target_role in manageable_roles
    
    def can_manage_user(self, target_user):
        """Check if this user can manage the target user"""
        if not isinstance(target_user, User):
            return False
        return self.can_manage_role(target_user.role)
    
    def _can_be_managed_by(self, manager_user):
        """Check if this user can be managed by the manager_user"""
        if not isinstance(manager_user, User):
            return False
        return manager_user.can_manage_role(self.role)
    
    def get_manageable_users(self):
        """Get all users this user can manage (excluding soft-deleted users)"""
        manageable_roles = self.MANAGEMENT_PERMISSIONS.get(self.role, [])
        return User.objects.filter(role__in=manageable_roles, is_deleted=False)
    
    def get_creatable_roles(self):
        """Get list of roles this user can create"""
        return self.MANAGEMENT_PERMISSIONS.get(self.role, [])
    
    def get_subordinates(self):
        """Get all direct subordinates"""
        return self.managed_users.all()
    
    def get_hierarchy_tree(self):
        """Get the full hierarchy tree under this user"""
        def get_children(user):
            children = []
            for subordinate in user.get_subordinates():
                children.append({
                    'user': subordinate,
                    'children': get_children(subordinate)
                })
            return children
        
        return get_children(self)
    
    def get_section_permission(self, section_name):
        """Get user's permission for a specific section"""
        try:
            section_perm = self.section_permissions.get(section__name=section_name)
            return section_perm.permission_level
        except:
            return 'no_access'
    
    def has_section_permission(self, section_name, required_level='read_only'):
        """Check if user has required permission level for a section"""
        if self.role == 'super_admin':
            return True
            
        try:
            section_perm = self.section_permissions.get(section__name=section_name)
            return section_perm.has_permission(required_level)
        except:
            return False
    
    def can_access_section(self, section_name):
        """Check if user can access a section at all"""
        return self.has_section_permission(section_name, 'read_only')
    
    def get_accessible_sections(self):
        """Get all sections this user can access"""
        if self.role == 'super_admin':
            from .models import Section
            return Section.objects.filter(is_active=True)
        
        return [perm.section for perm in self.section_permissions.filter(
            section__is_active=True
        ).exclude(permission_level='no_access')]


class UserActivity(models.Model):
    """Track user management activities"""
    ACTION_CHOICES = [
        ('created', 'User Created'),
        ('updated', 'User Updated'),
        ('deactivated', 'User Deactivated'),
        ('activated', 'User Activated'),
        ('deleted', 'User Deleted'),
        ('restored', 'User Restored'),
        ('role_changed', 'Role Changed'),
        ('password_reset', 'Password Reset'),
    ]
    
    performed_by = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='performed_activities'
    )
    target_user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='received_activities'
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    description = models.TextField(blank=True)
    old_values = models.JSONField(blank=True, null=True, help_text="Previous values before change")
    new_values = models.JSONField(blank=True, null=True, help_text="New values after change")
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.performed_by.username} {self.action} {self.target_user.username}"


class Department(models.Model):
    """Departments for organizational structure"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    head = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='headed_departments'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name


class Section(models.Model):
    """System sections/modules that can have permissions assigned"""
    SECTION_CHOICES = [
        ('medicine_management', 'Medicine Management'),
        ('medicine_storage', 'Medicine Storage'),
        ('cattle_management', 'Cattle Management'),
        ('user_management', 'User Management'),
        ('warehouse_storage', 'Warehouse Storage'),
        ('storage_inventory', 'Storage Inventory'),
        ('finance_management', 'Finance Management'),
        ('procurement', 'Procurement'),
        ('feed_management', 'Feed Management'),
        ('operations', 'Operations'),
        ('reports', 'Reports'),
        ('settings', 'Settings'),
    ]
    
    name = models.CharField(max_length=50, choices=SECTION_CHOICES, unique=True)
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.display_name
    
    class Meta:
        ordering = ['display_name']


class SectionPermission(models.Model):
    """User permissions for specific system sections"""
    PERMISSION_CHOICES = [
        ('no_access', 'No Access'),
        ('read_only', 'Read Only'),
        ('add_records', 'Add Records'),
        ('edit_records', 'Edit Records'), 
        ('full_access', 'Full Access'),
    ]
    
    # Permission hierarchy levels (higher number = more permissions)
    PERMISSION_HIERARCHY = {
        'no_access': 0,
        'read_only': 1,
        'add_records': 2,
        'edit_records': 3,
        'full_access': 4,
    }
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='section_permissions')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='user_permissions')
    permission_level = models.CharField(max_length=20, choices=PERMISSION_CHOICES, default='no_access')
    granted_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='granted_permissions',
        help_text="User who granted this permission"
    )
    granted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, help_text="Optional notes about this permission")
    
    class Meta:
        unique_together = ['user', 'section']
        ordering = ['section__display_name', 'user__username']
    
    def __str__(self):
        return f"{self.user.username} - {self.section.display_name} ({self.get_permission_level_display()})"
    
    @property
    def permission_level_numeric(self):
        """Get numeric level for permission hierarchy"""
        return self.PERMISSION_HIERARCHY.get(self.permission_level, 0)
    
    def has_permission(self, required_level):
        """Check if user has at least the required permission level"""
        required_numeric = self.PERMISSION_HIERARCHY.get(required_level, 0)
        return self.permission_level_numeric >= required_numeric
    
    def can_read(self):
        """Check if user can read data in this section"""
        return self.has_permission('read_only')
    
    def can_add(self):
        """Check if user can add records in this section"""
        return self.has_permission('add_records')
    
    def can_edit(self):
        """Check if user can edit records in this section"""
        return self.has_permission('edit_records')
    
    def can_delete(self):
        """Check if user can delete records in this section"""
        return self.has_permission('full_access')
