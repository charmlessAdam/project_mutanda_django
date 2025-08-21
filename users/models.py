from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.exceptions import ValidationError

class User(AbstractUser):
    ROLE_CHOICES = [
        ('super_admin', 'Super Admin'),
        ('admin', 'Admin'),
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
        'manager': 4,
        'admin': 5,
        'super_admin': 6,
    }
    
    # Define which roles can manage which roles
    MANAGEMENT_PERMISSIONS = {
        'super_admin': ['admin', 'manager', 'operator', 'warehouse_worker', 'viewer'],
        'admin': ['manager', 'operator', 'warehouse_worker', 'viewer'],
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
    can_create_users = models.BooleanField(default=False)
    can_edit_users = models.BooleanField(default=False)
    can_deactivate_users = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_password_change = models.DateTimeField(null=True, blank=True)
    
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
        """Get all users this user can manage"""
        manageable_roles = self.MANAGEMENT_PERMISSIONS.get(self.role, [])
        return User.objects.filter(role__in=manageable_roles)
    
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


class UserActivity(models.Model):
    """Track user management activities"""
    ACTION_CHOICES = [
        ('created', 'User Created'),
        ('updated', 'User Updated'),
        ('deactivated', 'User Deactivated'),
        ('activated', 'User Activated'),
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
