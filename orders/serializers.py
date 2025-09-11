from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Order, OrderApproval, OrderActivity, OrderComment, OrderNotification

User = get_user_model()

class UserBasicSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'full_name', 'role']
    
    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username

class OrderCommentSerializer(serializers.ModelSerializer):
    user = UserBasicSerializer(read_only=True)
    
    class Meta:
        model = OrderComment
        fields = ['id', 'comment', 'is_internal', 'user', 'created_at', 'updated_at']

class OrderApprovalSerializer(serializers.ModelSerializer):
    approver = UserBasicSerializer(read_only=True)
    
    class Meta:
        model = OrderApproval
        fields = [
            'id', 'stage', 'approver', 'action', 'notes', 
            'requires_revision', 'revision_completed', 'created_at'
        ]

class OrderActivitySerializer(serializers.ModelSerializer):
    user = UserBasicSerializer(read_only=True)
    
    class Meta:
        model = OrderActivity
        fields = [
            'id', 'activity_type', 'user', 'description', 
            'previous_status', 'new_status', 'metadata', 'created_at'
        ]

class OrderListSerializer(serializers.ModelSerializer):
    requested_by = UserBasicSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    urgency_display = serializers.CharField(source='get_urgency_display', read_only=True)
    order_type_display = serializers.CharField(source='get_order_type_display', read_only=True)
    is_pending_approval = serializers.BooleanField(read_only=True)
    next_approver_role = serializers.CharField(read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'order_type', 'order_type_display',
            'title', 'description', 'quantity', 'unit', 'urgency', 'urgency_display', 
            'estimated_cost', 'supplier', 'requested_by', 'request_date',
            'status', 'status_display', 'is_pending_approval', 'next_approver_role',
            'created_at', 'updated_at'
        ]

class OrderDetailSerializer(serializers.ModelSerializer):
    requested_by = UserBasicSerializer(read_only=True)
    approvals = OrderApprovalSerializer(many=True, read_only=True)
    comments = OrderCommentSerializer(many=True, read_only=True)
    activities = OrderActivitySerializer(many=True, read_only=True)
    
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    urgency_display = serializers.CharField(source='get_urgency_display', read_only=True)
    order_type_display = serializers.CharField(source='get_order_type_display', read_only=True)
    is_pending_approval = serializers.BooleanField(read_only=True)
    next_approver_role = serializers.CharField(read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'order_type', 'order_type_display',
            'title', 'description', 'quantity', 'unit', 'urgency', 'urgency_display',
            'estimated_cost', 'supplier', 'requested_by', 'request_date',
            'status', 'status_display', 'rejection_reason', 'completion_date',
            'is_pending_approval', 'next_approver_role',
            'approvals', 'comments', 'activities',
            'created_at', 'updated_at'
        ]

class OrderCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = [
            'order_type', 'title', 'description', 'quantity', 'unit',
            'urgency', 'estimated_cost', 'supplier'
        ]
    
    def validate_estimated_cost(self, value):
        if value <= 0:
            raise serializers.ValidationError("Estimated cost must be greater than 0")
        return value
    
    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0")
        return value

class OrderApprovalActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['approved', 'rejected', 'revision_requested'])
    notes = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, data):
        if data['action'] in ['rejected', 'revision_requested'] and not data.get('notes'):
            raise serializers.ValidationError({
                'notes': 'Notes are required when rejecting or requesting revision'
            })
        return data

class OrderCommentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderComment
        fields = ['comment', 'is_internal']
    
    def validate_comment(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Comment cannot be empty")
        return value.strip()

class OrderNotificationSerializer(serializers.ModelSerializer):
    order = OrderListSerializer(read_only=True)
    
    class Meta:
        model = OrderNotification
        fields = [
            'id', 'order', 'notification_type', 'title', 'message', 
            'is_read', 'created_at', 'read_at'
        ]

# Superadmin-specific serializers with more detailed information
class SuperAdminOrderActivitySerializer(OrderActivitySerializer):
    """Extended activity serializer for superadmin with IP and user agent"""
    
    class Meta(OrderActivitySerializer.Meta):
        fields = OrderActivitySerializer.Meta.fields + ['ip_address', 'user_agent']

class SuperAdminOrderDetailSerializer(OrderDetailSerializer):
    """Extended order serializer for superadmin with full audit trail"""
    activities = SuperAdminOrderActivitySerializer(many=True, read_only=True)
    
    class Meta(OrderDetailSerializer.Meta):
        pass