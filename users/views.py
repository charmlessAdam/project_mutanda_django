from rest_framework import generics, permissions, status, filters
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.viewsets import ModelViewSet
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.db.models import Q
from .models import UserActivity, Department
from .serializers import (
    UserSerializer, 
    RegisterSerializer, 
    LoginSerializer,
    UserUpdateSerializer,
    ChangePasswordSerializer,
    UserCreateSerializer,
    UserManagementSerializer,
    UserActivitySerializer,
    DepartmentSerializer
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
        """Return only users that the current user can manage"""
        user = self.request.user
        if user.role == 'super_admin':
            # Super admin can see all users
            return User.objects.all().select_related('manager', 'created_by')
        else:
            # Other users can only see users they can manage
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
        """Don't actually delete, just deactivate"""
        if not self.request.user.can_deactivate_users:
            raise permissions.PermissionDenied("You don't have permission to deactivate users.")
        
        if not self.request.user.can_manage_user(instance):
            raise permissions.PermissionDenied("You cannot manage this user.")
        
        instance.is_active = False
        instance.save()
        
        # Log activity
        UserActivity.objects.create(
            performed_by=self.request.user,
            target_user=instance,
            action='deactivated',
            description=f"Deactivated user {instance.username}",
            old_values={'is_active': True},
            new_values={'is_active': False},
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