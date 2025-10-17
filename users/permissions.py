from functools import wraps
from django.http import JsonResponse
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework import status


def require_section_permission(section_name, required_level='read_only'):
    """
    Decorator to require specific section permission for view functions
    
    Args:
        section_name (str): The section name to check permission for
        required_level (str): Minimum permission level required
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({
                    'success': False,
                    'error': 'Authentication required'
                }, status=401)
            
            if not request.user.has_section_permission(section_name, required_level):
                return JsonResponse({
                    'success': False,
                    'error': f'Insufficient permissions. {required_level.replace("_", " ").title()} access required for {section_name.replace("_", " ").title()}'
                }, status=403)
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


class SectionPermissionMixin:
    """
    Mixin for DRF ViewSets to check section permissions
    """
    section_name = None  # Must be set in subclass
    
    def get_required_permission_level(self):
        """
        Get the required permission level based on the action
        Override this method to customize permission requirements
        """
        permission_map = {
            'list': 'read_only',
            'retrieve': 'read_only',
            'create': 'add_records',
            'update': 'edit_records',
            'partial_update': 'edit_records',
            'destroy': 'full_access',
        }
        return permission_map.get(self.action, 'read_only')
    
    def check_section_permission(self):
        """Check if user has required section permission"""
        if not self.section_name:
            raise ValueError("section_name must be set in the ViewSet")
        
        user = self.request.user
        if not user.is_authenticated:
            return False
        
        required_level = self.get_required_permission_level()
        return user.has_section_permission(self.section_name, required_level)
    
    def dispatch(self, request, *args, **kwargs):
        """Override dispatch to check permissions"""
        response = super().dispatch(request, *args, **kwargs)
        
        # Skip permission check for OPTIONS requests
        if request.method == 'OPTIONS':
            return response
            
        if not self.check_section_permission():
            required_level = self.get_required_permission_level()
            return Response({
                'success': False,
                'error': f'Insufficient permissions. {required_level.replace("_", " ").title()} access required for {self.section_name.replace("_", " ").title()}'
            }, status=status.HTTP_403_FORBIDDEN)
        
        return response


class SectionPermission(permissions.BasePermission):
    """
    DRF Permission class for section-based permissions
    """
    section_name = None
    required_level = 'read_only'
    
    def __init__(self, section_name, required_level='read_only'):
        self.section_name = section_name
        self.required_level = required_level
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        return request.user.has_section_permission(self.section_name, self.required_level)
    
    def has_object_permission(self, request, view, obj):
        # Default to the same permission as has_permission
        return self.has_permission(request, view)


class MedicineManagementPermission(permissions.BasePermission):
    """Permission class for Medicine Management section"""

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        # Map HTTP methods to permission levels
        method_permission_map = {
            'GET': 'read_only',
            'HEAD': 'read_only',
            'OPTIONS': 'read_only',
            'POST': 'add_records',
            'PUT': 'edit_records',
            'PATCH': 'edit_records',
            'DELETE': 'full_access',
        }

        required_level = method_permission_map.get(request.method, 'read_only')
        return request.user.has_section_permission('medicine_management', required_level)


class MedicineStoragePermission(permissions.BasePermission):
    """Permission class for Medicine Storage section"""

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        method_permission_map = {
            'GET': 'read_only',
            'HEAD': 'read_only',
            'OPTIONS': 'read_only',
            'POST': 'add_records',
            'PUT': 'edit_records',
            'PATCH': 'edit_records',
            'DELETE': 'full_access',
        }

        required_level = method_permission_map.get(request.method, 'read_only')
        return request.user.has_section_permission('medicine_storage', required_level)


class StorageInventoryPermission(permissions.BasePermission):
    """Permission class for Storage Inventory section"""

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        method_permission_map = {
            'GET': 'read_only',
            'HEAD': 'read_only',
            'OPTIONS': 'read_only',
            'POST': 'add_records',
            'PUT': 'edit_records',
            'PATCH': 'edit_records',
            'DELETE': 'full_access',
        }

        required_level = method_permission_map.get(request.method, 'read_only')
        return request.user.has_section_permission('storage_inventory', required_level)


class CattleManagementPermission(permissions.BasePermission):
    """Permission class for Cattle Management section"""
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        method_permission_map = {
            'GET': 'read_only',
            'HEAD': 'read_only', 
            'OPTIONS': 'read_only',
            'POST': 'add_records',
            'PUT': 'edit_records',
            'PATCH': 'edit_records',
            'DELETE': 'full_access',
        }
        
        required_level = method_permission_map.get(request.method, 'read_only')
        return request.user.has_section_permission('cattle_management', required_level)


class WarehouseStoragePermission(permissions.BasePermission):
    """Permission class for Warehouse Storage section"""
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        method_permission_map = {
            'GET': 'read_only',
            'HEAD': 'read_only',
            'OPTIONS': 'read_only', 
            'POST': 'add_records',
            'PUT': 'edit_records',
            'PATCH': 'edit_records',
            'DELETE': 'full_access',
        }
        
        required_level = method_permission_map.get(request.method, 'read_only')
        return request.user.has_section_permission('warehouse_storage', required_level)


class UserManagementPermission(permissions.BasePermission):
    """Permission class for User Management section"""
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        # User management has additional role-based restrictions
        if request.user.role not in ['super_admin', 'admin']:
            return False
        
        method_permission_map = {
            'GET': 'read_only',
            'HEAD': 'read_only',
            'OPTIONS': 'read_only',
            'POST': 'add_records', 
            'PUT': 'edit_records',
            'PATCH': 'edit_records',
            'DELETE': 'full_access',
        }
        
        required_level = method_permission_map.get(request.method, 'read_only')
        return request.user.has_section_permission('user_management', required_level)


class ReportsPermission(permissions.BasePermission):
    """Permission class for Reports section"""
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        # Reports are typically read-only, but may have export functionality
        method_permission_map = {
            'GET': 'read_only',
            'HEAD': 'read_only',
            'OPTIONS': 'read_only',
            'POST': 'read_only',  # For generating/exporting reports
        }
        
        required_level = method_permission_map.get(request.method, 'read_only')
        return request.user.has_section_permission('reports', required_level)


class SettingsPermission(permissions.BasePermission):
    """Permission class for Settings section"""
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        # Settings typically require higher permissions
        method_permission_map = {
            'GET': 'read_only',
            'HEAD': 'read_only',
            'OPTIONS': 'read_only',
            'POST': 'edit_records',
            'PUT': 'edit_records',
            'PATCH': 'edit_records',
            'DELETE': 'full_access',
        }
        
        required_level = method_permission_map.get(request.method, 'read_only')
        return request.user.has_section_permission('settings', required_level)