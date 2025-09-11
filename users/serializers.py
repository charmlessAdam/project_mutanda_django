from django.contrib.auth import get_user_model, authenticate
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from .models import UserActivity, Department, Section, SectionPermission

User = get_user_model()

class UserBasicSerializer(serializers.ModelSerializer):
    """Basic user info for references"""
    full_name = serializers.CharField(read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    
    class Meta:
        model = User
        fields = ('id', 'username', 'full_name', 'role', 'role_display', 'email')

class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    role_level = serializers.IntegerField(read_only=True)
    manager = UserBasicSerializer(read_only=True)
    created_by = UserBasicSerializer(read_only=True)
    creatable_roles = serializers.ListField(read_only=True)
    manageable_users_count = serializers.SerializerMethodField()
    subordinates_count = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'first_name', 'last_name', 
            'full_name', 'role', 'role_display', 'role_level', 'phone', 'location', 
            'bio', 'department', 'manager', 'created_by', 'is_active', 'is_superuser',
            'can_create_users', 'can_edit_users', 'can_deactivate_users',
            'date_joined', 'last_login', 'last_password_change',
            'creatable_roles', 'manageable_users_count', 'subordinates_count'
        )
        read_only_fields = (
            'id', 'date_joined', 'last_login', 'last_password_change', 
            'role_level', 'can_create_users', 'can_edit_users', 'can_deactivate_users'
        )
    
    def get_manageable_users_count(self, obj):
        return obj.get_manageable_users().count()
    
    def get_subordinates_count(self, obj):
        return obj.get_subordinates().count()
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['creatable_roles'] = instance.get_creatable_roles()
        return data

class UserUpdateSerializer(serializers.ModelSerializer):
    manager_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'phone', 'location', 'bio', 'department', 'manager_id')
    
    def validate_manager_id(self, value):
        if value is not None:
            try:
                manager = User.objects.get(id=value)
                # Check if the requesting user can assign this manager
                request_user = self.context['request'].user
                if not request_user.can_manage_user(manager):
                    raise serializers.ValidationError("You cannot assign this user as a manager.")
                return manager.id
            except User.DoesNotExist:
                raise serializers.ValidationError("Manager not found.")
        return None
    
    def update(self, instance, validated_data):
        manager_id = validated_data.pop('manager_id', None)
        if manager_id is not None:
            validated_data['manager'] = User.objects.get(id=manager_id) if manager_id else None
        
        return super().update(instance, validated_data)

class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    manager_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    
    class Meta:
        model = User
        fields = (
            'username', 'email', 'first_name', 'last_name', 'password', 
            'password_confirm', 'role', 'phone', 'location', 'bio', 
            'department', 'manager_id'
        )
    
    def validate(self, data):
        # Check password confirmation
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError("Passwords don't match.")
        
        # Check if requesting user can create this role
        request_user = self.context['request'].user
        target_role = data['role']
        if not request_user.can_manage_role(target_role):
            raise serializers.ValidationError(f"You cannot create users with the role '{target_role}'.")
        
        return data
    
    def validate_manager_id(self, value):
        if value is not None:
            try:
                manager = User.objects.get(id=value)
                # Check if the requesting user can assign this manager
                request_user = self.context['request'].user
                if not request_user.can_manage_user(manager):
                    raise serializers.ValidationError("You cannot assign this user as a manager.")
                return manager.id
            except User.DoesNotExist:
                raise serializers.ValidationError("Manager not found.")
        return None
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        manager_id = validated_data.pop('manager_id', None)
        
        user = User.objects.create_user(**validated_data)
        
        if manager_id:
            user.manager = User.objects.get(id=manager_id)
        
        user.created_by = self.context['request'].user
        user.save()
        
        # Log the activity
        UserActivity.objects.create(
            performed_by=self.context['request'].user,
            target_user=user,
            action='created',
            description=f"Created user {user.username} with role {user.role}",
            new_values={'role': user.role, 'username': user.username},
            ip_address=self.context['request'].META.get('REMOTE_ADDR')
        )
        
        return user

class UserManagementSerializer(serializers.ModelSerializer):
    """Serializer for user management operations"""
    full_name = serializers.CharField(read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    manager = UserBasicSerializer(read_only=True)
    created_by = UserBasicSerializer(read_only=True)
    can_be_edited = serializers.SerializerMethodField()
    can_be_deactivated = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'full_name', 'role', 'role_display',
            'is_active', 'manager', 'created_by', 'department', 'phone',
            'date_joined', 'last_login', 'can_be_edited', 'can_be_deactivated'
        )
    
    def get_can_be_edited(self, obj):
        request_user = self.context['request'].user
        return request_user.can_manage_user(obj)
    
    def get_can_be_deactivated(self, obj):
        request_user = self.context['request'].user
        return request_user.can_manage_user(obj) and request_user.can_deactivate_users

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    
    def validate(self, data):
        username = data.get('username')
        password = data.get('password')
        
        if username and password:
            user = authenticate(username=username, password=password)
            if user:
                if user.is_active:
                    data['user'] = user
                    return data
                else:
                    raise serializers.ValidationError('User account is disabled.')
            else:
                raise serializers.ValidationError('Invalid username or password.')
        else:
            raise serializers.ValidationError('Must include username and password.')

class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    
    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Current password is incorrect.')
        return value
    
    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'password', 'password_confirm', 'role')
    
    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError("Passwords don't match.")
        return data
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = User.objects.create_user(**validated_data)
        return user

class UserActivitySerializer(serializers.ModelSerializer):
    performed_by = UserBasicSerializer(read_only=True)
    target_user = UserBasicSerializer(read_only=True)
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    
    class Meta:
        model = UserActivity
        fields = ('id', 'performed_by', 'target_user', 'action', 'action_display', 
                 'description', 'timestamp', 'old_values', 'new_values')

class DepartmentSerializer(serializers.ModelSerializer):
    head = UserBasicSerializer(read_only=True)
    head_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    
    class Meta:
        model = Department
        fields = ('id', 'name', 'description', 'head', 'head_id', 'created_at')
    
    def validate_head_id(self, value):
        if value is not None:
            try:
                head_user = User.objects.get(id=value)
                # Check if the user can be a department head (should be manager or higher)
                if head_user.role_level < 4:  # Manager level is 4
                    raise serializers.ValidationError("Only managers or higher can be department heads.")
                return value
            except User.DoesNotExist:
                raise serializers.ValidationError("User not found.")
        return None
    
    def create(self, validated_data):
        head_id = validated_data.pop('head_id', None)
        department = Department.objects.create(**validated_data)
        
        if head_id:
            department.head = User.objects.get(id=head_id)
            department.save()
        
        return department
    
    def update(self, instance, validated_data):
        head_id = validated_data.pop('head_id', None)
        
        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Update head if provided
        if head_id is not None:
            instance.head = User.objects.get(id=head_id) if head_id else None
        
        instance.save()
        return instance


class SectionSerializer(serializers.ModelSerializer):
    """Serializer for system sections"""
    name_display = serializers.CharField(source='get_name_display', read_only=True)
    
    class Meta:
        model = Section
        fields = ('id', 'name', 'name_display', 'display_name', 'description', 'is_active', 'created_at')


class SectionPermissionSerializer(serializers.ModelSerializer):
    """Serializer for section permissions"""
    user = UserBasicSerializer(read_only=True)
    section = SectionSerializer(read_only=True)
    granted_by = UserBasicSerializer(read_only=True)
    permission_level_display = serializers.CharField(source='get_permission_level_display', read_only=True)
    permission_level_numeric = serializers.IntegerField(read_only=True)
    
    # Write-only fields for creation/updates
    user_id = serializers.IntegerField(write_only=True)
    section_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = SectionPermission
        fields = (
            'id', 'user', 'section', 'permission_level', 'permission_level_display', 
            'permission_level_numeric', 'granted_by', 'granted_at', 'updated_at', 'notes',
            'user_id', 'section_id'
        )
        read_only_fields = ('granted_by', 'granted_at', 'updated_at')
    
    def validate_user_id(self, value):
        try:
            user = User.objects.get(id=value)
            # Only super admins can manage section permissions
            request_user = self.context['request'].user
            if request_user.role != 'super_admin':
                raise serializers.ValidationError("Only super admins can manage section permissions.")
            return value
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found.")
    
    def validate_section_id(self, value):
        try:
            section = Section.objects.get(id=value, is_active=True)
            return value
        except Section.DoesNotExist:
            raise serializers.ValidationError("Section not found or inactive.")
    
    def create(self, validated_data):
        user_id = validated_data.pop('user_id')
        section_id = validated_data.pop('section_id')
        
        validated_data['user'] = User.objects.get(id=user_id)
        validated_data['section'] = Section.objects.get(id=section_id)
        
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        # Remove user_id and section_id from validated_data if present
        validated_data.pop('user_id', None)
        validated_data.pop('section_id', None)
        
        return super().update(instance, validated_data)


class UserSectionPermissionsSerializer(serializers.ModelSerializer):
    """Serializer showing a user with their section permissions"""
    section_permissions = serializers.SerializerMethodField()
    accessible_sections = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ('id', 'username', 'full_name', 'role', 'role_display', 'section_permissions', 'accessible_sections')
    
    def get_section_permissions(self, obj):
        permissions = obj.section_permissions.select_related('section').all()
        return SectionPermissionSerializer(permissions, many=True, context=self.context).data
    
    def get_accessible_sections(self, obj):
        sections = obj.get_accessible_sections()
        return SectionSerializer(sections, many=True).data
