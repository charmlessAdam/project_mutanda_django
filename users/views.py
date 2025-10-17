from rest_framework import generics, permissions, status, filters
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.viewsets import ModelViewSet
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.db.models import Q
from .models import UserActivity, Department, Section, SectionPermission
from .serializers import (
    UserSerializer, 
    RegisterSerializer, 
    LoginSerializer,
    UserUpdateSerializer,
    ChangePasswordSerializer,
    UserCreateSerializer,
    UserManagementSerializer,
    UserActivitySerializer,
    DepartmentSerializer,
    SectionSerializer,
    SectionPermissionSerializer
)

User = get_user_model()

# Login API
class LoginApi(generics.GenericAPIView):
    serializer_class = LoginSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'success': True,
            'user': UserSerializer(user).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        })

# Register API
class RegisterApi(generics.GenericAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        refresh = RefreshToken.for_user(user)
        
        return Response({
            "success": True,
            "user": UserSerializer(user).data,
            "tokens": {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            },
            "message": "User created successfully.",
        }, status=status.HTTP_201_CREATED)

# Current User API
class CurrentUserApi(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user
    
    def get_serializer_class(self):
        if self.request.method == 'PUT' or self.request.method == 'PATCH':
            return UserUpdateSerializer
        return UserSerializer

# Change Password API
class ChangePasswordApi(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response({
            'success': True,
            'message': 'Password changed successfully.'
        })

# Logout API (Optional - for blacklisting tokens)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def logout_api(request):
    try:
        refresh_token = request.data.get("refresh_token")
        token = RefreshToken(refresh_token)
        token.blacklist()
        return Response({
            'success': True,
            'message': 'Successfully logged out.'
        })
    except Exception as e:
        return Response({
            'success': False,
            'message': 'Error logging out.'
        }, status=status.HTTP_400_BAD_REQUEST)


class UserManagementViewSet(ModelViewSet):
    """ViewSet for hierarchical user management"""
    serializer_class = UserManagementSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['username', 'first_name', 'last_name', 'email', 'department']
    ordering_fields = ['username', 'role', 'date_joined', 'last_login']
    ordering = ['role', 'username']
    
    def get_queryset(self):
        """Return only users that the current user can manage (excluding soft-deleted users)"""
        user = self.request.user
        if user.role == 'super_admin':
            # Super admin can see all users (excluding soft-deleted)
            return User.objects.filter(is_deleted=False).select_related('manager', 'created_by')
        else:
            # Other users can only see users they can manage (excluding soft-deleted)
            manageable_users = user.get_manageable_users()
            return manageable_users.select_related('manager', 'created_by')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserManagementSerializer
    
    def perform_create(self, serializer):
        """Create user with activity logging"""
        user = serializer.save()
        
        # Log activity
        UserActivity.objects.create(
            performed_by=self.request.user,
            target_user=user,
            action='created',
            description=f"Created user {user.username} with role {user.role}",
            new_values={
                'username': user.username,
                'role': user.role,
                'email': user.email
            },
            ip_address=self.request.META.get('REMOTE_ADDR')
        )
    
    def perform_update(self, serializer):
        """Update user with activity logging"""
        old_instance = self.get_object()
        old_values = {
            'first_name': old_instance.first_name,
            'last_name': old_instance.last_name,
            'email': old_instance.email,
            'role': old_instance.role,
            'is_active': old_instance.is_active
        }
        
        user = serializer.save()
        
        new_values = {
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'role': user.role,
            'is_active': user.is_active
        }
        
        # Log activity
        UserActivity.objects.create(
            performed_by=self.request.user,
            target_user=user,
            action='updated',
            description=f"Updated user {user.username}",
            old_values=old_values,
            new_values=new_values,
            ip_address=self.request.META.get('REMOTE_ADDR')
        )
    
    def perform_destroy(self, instance):
        """Soft delete - mark user as deleted instead of removing from database"""
        if not self.request.user.can_deactivate_users:
            raise permissions.PermissionDenied("You don't have permission to delete users.")

        if not self.request.user.can_manage_user(instance):
            raise permissions.PermissionDenied("You cannot manage this user.")

        # Soft delete: mark as deleted and deactivate
        from django.utils import timezone
        instance.is_deleted = True
        instance.is_active = False
        instance.deleted_at = timezone.now()
        instance.save()

        # Log activity
        UserActivity.objects.create(
            performed_by=self.request.user,
            target_user=instance,
            action='deleted',
            description=f"Deleted user {instance.username}",
            old_values={'is_deleted': False, 'is_active': instance.is_active},
            new_values={'is_deleted': True, 'is_active': False},
            ip_address=self.request.META.get('REMOTE_ADDR')
        )
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a deactivated user"""
        user = self.get_object()

        if not request.user.can_manage_user(user):
            return Response({
                'success': False,
                'error': 'You cannot manage this user.'
            }, status=status.HTTP_403_FORBIDDEN)

        user.is_active = True
        user.save()

        # Log activity
        UserActivity.objects.create(
            performed_by=request.user,
            target_user=user,
            action='activated',
            description=f"Activated user {user.username}",
            old_values={'is_active': False},
            new_values={'is_active': True},
            ip_address=request.META.get('REMOTE_ADDR')
        )

        return Response({
            'success': True,
            'message': f'User {user.username} has been activated.'
        })

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate a user (temporary disable without soft delete)"""
        user = self.get_object()

        if not request.user.can_manage_user(user):
            return Response({
                'success': False,
                'error': 'You cannot manage this user.'
            }, status=status.HTTP_403_FORBIDDEN)

        user.is_active = False
        user.save()

        # Log activity
        UserActivity.objects.create(
            performed_by=request.user,
            target_user=user,
            action='deactivated',
            description=f"Deactivated user {user.username}",
            old_values={'is_active': True},
            new_values={'is_active': False},
            ip_address=request.META.get('REMOTE_ADDR')
        )

        return Response({
            'success': True,
            'message': f'User {user.username} has been deactivated.'
        })

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        """Restore a soft-deleted user"""
        # Need to get the user even if deleted
        try:
            user = User.objects.get(pk=pk, is_deleted=True)
        except User.DoesNotExist:
            return Response({
                'success': False,
                'error': 'User not found or not deleted.'
            }, status=status.HTTP_404_NOT_FOUND)

        if not request.user.can_manage_user(user):
            return Response({
                'success': False,
                'error': 'You cannot manage this user.'
            }, status=status.HTTP_403_FORBIDDEN)

        user.is_deleted = False
        user.deleted_at = None
        user.is_active = True  # Also reactivate
        user.save()

        # Log activity
        UserActivity.objects.create(
            performed_by=request.user,
            target_user=user,
            action='restored',
            description=f"Restored deleted user {user.username}",
            old_values={'is_deleted': True, 'is_active': False},
            new_values={'is_deleted': False, 'is_active': True},
            ip_address=request.META.get('REMOTE_ADDR')
        )

        return Response({
            'success': True,
            'message': f'User {user.username} has been restored.'
        })
    
    @action(detail=True, methods=['post'])
    def reset_password(self, request, pk=None):
        """Reset user password"""
        user = self.get_object()
        
        if not request.user.can_manage_user(user):
            return Response({
                'success': False,
                'error': 'You cannot manage this user.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Generate temporary password
        import secrets
        import string
        temp_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for i in range(12))
        
        user.set_password(temp_password)
        user.save()
        
        # Log activity
        UserActivity.objects.create(
            performed_by=request.user,
            target_user=user,
            action='password_reset',
            description=f"Reset password for user {user.username}",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return Response({
            'success': True,
            'message': f'Password reset for {user.username}.',
            'temporary_password': temp_password
        })
    
    @action(detail=False, methods=['get'])
    def deleted_users(self, request):
        """Get list of soft-deleted users (super admin only)"""
        if request.user.role != 'super_admin':
            return Response({
                'success': False,
                'error': 'Only super admins can view deleted users.'
            }, status=status.HTTP_403_FORBIDDEN)

        deleted_users = User.objects.filter(is_deleted=True).select_related('manager', 'created_by')
        serializer = UserManagementSerializer(deleted_users, many=True, context={'request': request})

        return Response({
            'success': True,
            'deleted_users': serializer.data
        })

    @action(detail=False, methods=['get'])
    def hierarchy(self, request):
        """Get user hierarchy tree"""
        user = request.user

        # Get the hierarchy starting from the current user
        hierarchy_data = {
            'user': UserManagementSerializer(user, context={'request': request}).data,
            'subordinates': user.get_hierarchy_tree()
        }

        return Response(hierarchy_data)
    
    @action(detail=False, methods=['get'])
    def creatable_roles(self, request):
        """Get roles that the current user can create"""
        user = request.user
        creatable_roles = user.get_creatable_roles()
        
        # Convert to choices format
        role_choices = []
        for role_code in creatable_roles:
            role_display = dict(User.ROLE_CHOICES).get(role_code, role_code)
            role_choices.append({'value': role_code, 'label': role_display})
        
        return Response({'roles': role_choices})


class UserActivityViewSet(generics.ListAPIView):
    """View user management activities"""
    serializer_class = UserActivitySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['target_user__username', 'description']
    ordering = ['-timestamp']
    
    def get_queryset(self):
        """Return activities related to users the current user can manage"""
        user = self.request.user
        
        if user.role == 'super_admin':
            return UserActivity.objects.all().select_related('performed_by', 'target_user')
        else:
            # Show activities for users they can manage, plus their own activities
            manageable_user_ids = user.get_manageable_users().values_list('id', flat=True)
            return UserActivity.objects.filter(
                Q(target_user_id__in=manageable_user_ids) | Q(performed_by=user)
            ).select_related('performed_by', 'target_user')


class SectionViewSet(ModelViewSet):
    """List all available system sections"""
    serializer_class = SectionSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Section.objects.filter(is_active=True).order_by('display_name')
    http_method_names = ['get']  # Only allow GET methods
    

class SectionPermissionViewSet(ModelViewSet):
    """Manage section permissions for users (Super Admin only)"""
    serializer_class = SectionPermissionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Only super admins can manage section permissions"""
        if self.request.user.role != 'super_admin':
            return SectionPermission.objects.none()
        
        # Optional filtering by user or section
        queryset = SectionPermission.objects.select_related('user', 'section', 'granted_by')
        
        user_id = self.request.query_params.get('user_id')
        section_id = self.request.query_params.get('section_id')
        
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if section_id:
            queryset = queryset.filter(section_id=section_id)
            
        return queryset.order_by('user__username', 'section__display_name')
    
    def perform_create(self, serializer):
        """Create section permission with activity logging"""
        if self.request.user.role != 'super_admin':
            raise permissions.PermissionDenied("Only super admins can manage section permissions.")
        
        permission = serializer.save(granted_by=self.request.user)
        
        # Log activity
        UserActivity.objects.create(
            performed_by=self.request.user,
            target_user=permission.user,
            action='updated',
            description=f"Granted {permission.get_permission_level_display()} access to {permission.section.display_name}",
            new_values={
                'section': permission.section.name,
                'permission_level': permission.permission_level
            },
            ip_address=self.request.META.get('REMOTE_ADDR')
        )
    
    def perform_update(self, serializer):
        """Update section permission with activity logging"""
        if self.request.user.role != 'super_admin':
            raise permissions.PermissionDenied("Only super admins can manage section permissions.")
        
        old_permission = self.get_object()
        old_level = old_permission.permission_level
        
        permission = serializer.save()
        
        # Log activity
        UserActivity.objects.create(
            performed_by=self.request.user,
            target_user=permission.user,
            action='updated',
            description=f"Changed {permission.section.display_name} access from {old_permission.get_permission_level_display()} to {permission.get_permission_level_display()}",
            old_values={
                'section': permission.section.name,
                'permission_level': old_level
            },
            new_values={
                'section': permission.section.name,
                'permission_level': permission.permission_level
            },
            ip_address=self.request.META.get('REMOTE_ADDR')
        )
    
    def perform_destroy(self, instance):
        """Remove section permission with activity logging"""
        if self.request.user.role != 'super_admin':
            raise permissions.PermissionDenied("Only super admins can manage section permissions.")
        
        # Log activity before deletion
        UserActivity.objects.create(
            performed_by=self.request.user,
            target_user=instance.user,
            action='updated',
            description=f"Removed access to {instance.section.display_name}",
            old_values={
                'section': instance.section.name,
                'permission_level': instance.permission_level
            },
            ip_address=self.request.META.get('REMOTE_ADDR')
        )
        
        super().perform_destroy(instance)
    
    @action(detail=False, methods=['post'])
    def bulk_update(self, request):
        """Bulk update permissions for a user across all sections"""
        if request.user.role != 'super_admin':
            return Response({
                'success': False,
                'error': 'Only super admins can manage section permissions.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        user_id = request.data.get('user_id')
        permissions_data = request.data.get('permissions', [])
        
        if not user_id:
            return Response({
                'success': False,
                'error': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({
                'success': False,
                'error': 'User not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        updated_permissions = []
        
        for perm_data in permissions_data:
            section_id = perm_data.get('section_id')
            permission_level = perm_data.get('permission_level')
            
            if not section_id or not permission_level:
                continue
                
            try:
                section = Section.objects.get(id=section_id)
                
                # Update or create permission
                permission, created = SectionPermission.objects.update_or_create(
                    user=target_user,
                    section=section,
                    defaults={
                        'permission_level': permission_level,
                        'granted_by': request.user
                    }
                )
                
                updated_permissions.append({
                    'section': section.display_name,
                    'permission_level': permission.get_permission_level_display(),
                    'created': created
                })
                
                # Log activity
                action_desc = f"{'Granted' if created else 'Updated'} {permission.get_permission_level_display()} access to {section.display_name}"
                UserActivity.objects.create(
                    performed_by=request.user,
                    target_user=target_user,
                    action='updated',
                    description=action_desc,
                    new_values={
                        'section': section.name,
                        'permission_level': permission_level
                    },
                    ip_address=request.META.get('REMOTE_ADDR')
                )
                
            except Section.DoesNotExist:
                continue
        
        return Response({
            'success': True,
            'message': f'Updated permissions for {target_user.username}',
            'updated_permissions': updated_permissions
        })
    
    @action(detail=False, methods=['get'])
    def user_permissions_matrix(self, request):
        """Get permission matrix for all users and sections"""
        if request.user.role != 'super_admin':
            return Response({
                'success': False,
                'error': 'Only super admins can view the permission matrix.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get all users (excluding soft-deleted) and sections
        users = User.objects.filter(is_deleted=False).order_by('username')
        sections = Section.objects.filter(is_active=True).order_by('display_name')
        
        # Build permission matrix
        matrix = []
        for user in users:
            user_permissions = {}
            for section in sections:
                try:
                    perm = SectionPermission.objects.get(user=user, section=section)
                    user_permissions[section.name] = {
                        'level': perm.permission_level,
                        'display': perm.get_permission_level_display(),
                        'granted_by': perm.granted_by.username if perm.granted_by else None,
                        'granted_at': perm.granted_at
                    }
                except SectionPermission.DoesNotExist:
                    user_permissions[section.name] = {
                        'level': 'no_access',
                        'display': 'No Access',
                        'granted_by': None,
                        'granted_at': None
                    }
            
            matrix.append({
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'full_name': user.full_name,
                    'role': user.role,
                    'role_display': user.get_role_display()
                },
                'permissions': user_permissions
            })
        
        return Response({
            'sections': [{'id': s.id, 'name': s.name, 'display_name': s.display_name} for s in sections],
            'matrix': matrix
        })


class DepartmentViewSet(ModelViewSet):
    """Manage departments (Super Admin only)"""
    serializer_class = DepartmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return all departments"""
        return Department.objects.all().select_related('head').order_by('name')
    
    def get_permissions(self):
        """Only super admins can create, update, or delete departments"""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [permissions.IsAuthenticated]
            if not self.request.user.role == 'super_admin':
                raise permissions.PermissionDenied("Only super admins can manage departments.")
        else:
            permission_classes = [permissions.IsAuthenticated]
        
        return [permission() for permission in permission_classes]
    
    def create(self, request, *args, **kwargs):
        """Create a new department"""
        if request.user.role != 'super_admin':
            return Response({
                'success': False,
                'error': 'Only super admins can create departments.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            department = serializer.save()
            
            # Log activity if there's a head assigned
            if department.head:
                UserActivity.objects.create(
                    performed_by=request.user,
                    target_user=department.head,
                    action='updated',
                    description=f"Assigned as head of department: {department.name}",
                    new_values={'department_head': department.name},
                    ip_address=request.META.get('REMOTE_ADDR')
                )
            
            return Response({
                'success': True,
                'message': f'Department "{department.name}" created successfully.',
                'department': serializer.data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    def update(self, request, *args, **kwargs):
        """Update a department"""
        if request.user.role != 'super_admin':
            return Response({
                'success': False,
                'error': 'Only super admins can update departments.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        department = self.get_object()
        old_head = department.head
        
        serializer = self.get_serializer(department, data=request.data, partial=kwargs.get('partial', False))
        if serializer.is_valid():
            updated_department = serializer.save()
            
            # Log activity if head changed
            if old_head != updated_department.head:
                if old_head:
                    UserActivity.objects.create(
                        performed_by=request.user,
                        target_user=old_head,
                        action='updated',
                        description=f"Removed as head of department: {updated_department.name}",
                        old_values={'department_head': updated_department.name},
                        ip_address=request.META.get('REMOTE_ADDR')
                    )
                
                if updated_department.head:
                    UserActivity.objects.create(
                        performed_by=request.user,
                        target_user=updated_department.head,
                        action='updated',
                        description=f"Assigned as head of department: {updated_department.name}",
                        new_values={'department_head': updated_department.name},
                        ip_address=request.META.get('REMOTE_ADDR')
                    )
            
            return Response({
                'success': True,
                'message': f'Department "{updated_department.name}" updated successfully.',
                'department': serializer.data
            })
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    def destroy(self, request, *args, **kwargs):
        """Delete a department"""
        if request.user.role != 'super_admin':
            return Response({
                'success': False,
                'error': 'Only super admins can delete departments.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        department = self.get_object()
        department_name = department.name
        
        # Check if any users are assigned to this department
        users_count = User.objects.filter(department=department_name).count()
        if users_count > 0:
            return Response({
                'success': False,
                'error': f'Cannot delete department "{department_name}" because it has {users_count} user(s) assigned to it. Please reassign users first.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Log activity if there was a head
        if department.head:
            UserActivity.objects.create(
                performed_by=request.user,
                target_user=department.head,
                action='updated',
                description=f"Department deleted: {department.name} (was department head)",
                old_values={'department_head': department.name},
                ip_address=request.META.get('REMOTE_ADDR')
            )
        
        department.delete()
        
        return Response({
            'success': True,
            'message': f'Department "{department_name}" deleted successfully.'
        }, status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=False, methods=['get'])
    def list_with_users(self, request):
        """Get departments with their users count"""
        departments = self.get_queryset()
        
        department_data = []
        for dept in departments:
            users_count = User.objects.filter(department=dept.name).count()
            dept_serializer = self.get_serializer(dept)
            dept_data = dept_serializer.data
            dept_data['users_count'] = users_count
            department_data.append(dept_data)
        
        return Response({
            'success': True,
            'departments': department_data
        })