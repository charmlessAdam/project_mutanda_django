from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Order, OrderApproval, OrderActivity, OrderComment, OrderNotification, QuoteOption, OrderItem, QuoteOptionItem

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

class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['id', 'item_name', 'is_custom_item', 'quantity', 'unit', 'estimated_cost', 'created_at']
        read_only_fields = ['id', 'created_at']

class QuoteOptionItemSerializer(serializers.ModelSerializer):
    order_item_name = serializers.CharField(source='order_item.item_name', read_only=True)
    order_item_quantity = serializers.IntegerField(source='order_item.quantity', read_only=True)
    order_item_unit = serializers.CharField(source='order_item.unit', read_only=True)

    class Meta:
        model = QuoteOptionItem
        fields = [
            'id', 'order_item', 'order_item_name', 'order_item_quantity', 'order_item_unit',
            'unit_price', 'total_price', 'availability', 'notes'
        ]

class QuoteOptionSerializer(serializers.ModelSerializer):
    submitted_by = UserBasicSerializer(read_only=True)
    item_quotes = QuoteOptionItemSerializer(many=True, read_only=True)

    class Meta:
        model = QuoteOption
        fields = [
            'id', 'supplier_name', 'supplier_address', 'buying_company',
            'quoted_amount', 'delivery_time', 'notes',
            'is_recommended', 'is_selected',
            'submitted_by', 'submitted_at', 'item_quotes'
        ]
        read_only_fields = ['is_selected', 'submitted_by', 'submitted_at']

class OrderListSerializer(serializers.ModelSerializer):
    requested_by = UserBasicSerializer(read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
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
            'items',  # New field for multiple items
            'created_at', 'updated_at'
        ]

class OrderDetailSerializer(serializers.ModelSerializer):
    requested_by = UserBasicSerializer(read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    approvals = OrderApprovalSerializer(many=True, read_only=True)
    comments = OrderCommentSerializer(many=True, read_only=True)
    activities = OrderActivitySerializer(many=True, read_only=True)
    quote_options = QuoteOptionSerializer(many=True, read_only=True)
    quote_submitted_by = UserBasicSerializer(read_only=True)
    payment_completed_by = UserBasicSerializer(read_only=True)

    status_display = serializers.CharField(source='get_status_display', read_only=True)
    urgency_display = serializers.CharField(source='get_urgency_display', read_only=True)
    order_type_display = serializers.CharField(source='get_order_type_display', read_only=True)
    is_pending_approval = serializers.BooleanField(read_only=True)
    next_approver_role = serializers.CharField(read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'order_type', 'order_type_display', 'item_name',
            'title', 'description', 'quantity', 'unit', 'urgency', 'urgency_display',
            'estimated_cost', 'supplier', 'requested_by', 'request_date',
            'status', 'status_display', 'rejection_reason', 'completion_date',
            'is_pending_approval', 'next_approver_role',
            # Quote details
            'quote_amount', 'quote_supplier', 'quote_notes', 'quote_submitted_by', 'quote_submitted_at',
            'quote_options',
            # Payment details
            'payment_amount', 'payment_method', 'payment_reference', 'payment_notes',
            'payment_completed_by', 'payment_completed_at',
            # Related data
            'items', 'approvals', 'comments', 'activities',
            'created_at', 'updated_at'
        ]

class OrderItemCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['item_name', 'is_custom_item', 'quantity', 'unit', 'estimated_cost']

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0")
        return value

class OrderCreateSerializer(serializers.ModelSerializer):
    items = OrderItemCreateSerializer(many=True, required=True)

    class Meta:
        model = Order
        fields = [
            'order_type', 'description', 'urgency', 'estimated_cost', 'supplier', 'items'
        ]

    def validate_estimated_cost(self, value):
        if value <= 0:
            raise serializers.ValidationError("Estimated cost must be greater than 0")
        return value

    def validate_items(self, value):
        if not value or len(value) == 0:
            raise serializers.ValidationError("At least one item is required")
        return value

    def create(self, validated_data):
        items_data = validated_data.pop('items')

        # Create title from items (for backward compatibility)
        if len(items_data) == 1:
            title = items_data[0]['item_name']
            quantity = items_data[0]['quantity']
            unit = items_data[0]['unit']
        else:
            title = f"Multi-item Order ({len(items_data)} items)"
            quantity = sum(item['quantity'] for item in items_data)
            unit = 'items'

        validated_data['title'] = title
        validated_data['quantity'] = quantity
        validated_data['unit'] = unit

        # Create order
        order = Order.objects.create(**validated_data)

        # Create order items
        for item_data in items_data:
            OrderItem.objects.create(order=order, **item_data)

        return order

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

class QuoteOptionItemCreateSerializer(serializers.Serializer):
    """Serializer for creating quote option items"""
    order_item_id = serializers.IntegerField()
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)
    availability = serializers.CharField(max_length=100, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)

class QuoteOptionCreateSerializer(serializers.ModelSerializer):
    item_quotes = QuoteOptionItemCreateSerializer(many=True, required=False)

    class Meta:
        model = QuoteOption
        fields = ['supplier_name', 'supplier_address', 'buying_company', 'quoted_amount', 'delivery_time', 'notes', 'is_recommended', 'item_quotes']

    def validate_quoted_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quoted amount must be greater than 0")
        return value

class SubmitQuotesSerializer(serializers.Serializer):
    """Serializer for submitting multiple quote options with item-level pricing"""
    quotes = QuoteOptionCreateSerializer(many=True)

    def validate_quotes(self, value):
        if not value or len(value) == 0:
            raise serializers.ValidationError("At least one quote option is required")

        # Check if only one quote is marked as recommended
        recommended_count = sum(1 for quote in value if quote.get('is_recommended', False))
        if recommended_count == 0:
            raise serializers.ValidationError("At least one quote must be marked as recommended")
        if recommended_count > 1:
            raise serializers.ValidationError("Only one quote can be marked as recommended")

        return value

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