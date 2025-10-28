from rest_framework import serializers
from .models import Worker, EquipmentAssignment, WorkerActivity
from inventory.models import InventoryItem


class EquipmentAssignmentListSerializer(serializers.ModelSerializer):
    """Serializer for equipment assignments (nested in worker)"""
    item_name = serializers.CharField(read_only=True)
    inventory_item_id = serializers.IntegerField(source='inventory_item.id', read_only=True)
    inventory_item_name = serializers.CharField(source='inventory_item.name', read_only=True)
    assigned_by_name = serializers.CharField(source='assigned_by.get_full_name', read_only=True)
    returned_by_name = serializers.CharField(source='returned_by.get_full_name', read_only=True, allow_null=True)

    class Meta:
        model = EquipmentAssignment
        fields = [
            'id', 'inventory_item_id', 'inventory_item_name', 'item_name', 'item_type',
            'quantity', 'assigned_date', 'expected_return_date', 'returned_date',
            'is_active', 'condition_at_assignment', 'condition_at_return',
            'assignment_notes', 'return_notes', 'damage_notes',
            'assigned_by_name', 'returned_by_name', 'created_at', 'updated_at'
        ]


class WorkerListSerializer(serializers.ModelSerializer):
    """Serializer for worker list view"""
    full_name = serializers.CharField(read_only=True)
    total_assigned_items = serializers.IntegerField(read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True, allow_null=True)

    class Meta:
        model = Worker
        fields = [
            'id', 'employee_id', 'first_name', 'last_name', 'full_name',
            'email', 'phone', 'department', 'position', 'hire_date',
            'status', 'total_assigned_items', 'created_at', 'created_by_name'
        ]


class WorkerDetailSerializer(serializers.ModelSerializer):
    """Serializer for detailed worker view with assignments"""
    full_name = serializers.CharField(read_only=True)
    total_assigned_items = serializers.IntegerField(read_only=True)
    equipment_assignments = EquipmentAssignmentListSerializer(many=True, read_only=True)
    active_assignments = EquipmentAssignmentListSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True, allow_null=True)
    last_updated_by_name = serializers.CharField(source='last_updated_by.get_full_name', read_only=True, allow_null=True)
    supervisor_name = serializers.CharField(source='supervisor.full_name', read_only=True, allow_null=True)

    class Meta:
        model = Worker
        fields = [
            'id', 'employee_id', 'first_name', 'last_name', 'full_name',
            'email', 'phone', 'department', 'position', 'hire_date',
            'termination_date', 'status', 'supervisor', 'supervisor_name',
            'notes', 'emergency_contact', 'emergency_phone',
            'total_assigned_items', 'equipment_assignments', 'active_assignments',
            'created_at', 'updated_at', 'created_by_name', 'last_updated_by_name'
        ]


class WorkerCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating workers"""

    class Meta:
        model = Worker
        fields = [
            'employee_id', 'first_name', 'last_name', 'email', 'phone',
            'department', 'position', 'hire_date', 'termination_date',
            'status', 'supervisor', 'notes', 'emergency_contact', 'emergency_phone'
        ]

    def validate_employee_id(self, value):
        """Ensure employee_id is unique"""
        instance = self.instance
        if Worker.objects.exclude(pk=instance.pk if instance else None).filter(employee_id=value).exists():
            raise serializers.ValidationError("A worker with this employee ID already exists.")
        return value

    def validate(self, data):
        """Validate worker data"""
        if data.get('termination_date') and data.get('hire_date'):
            if data['termination_date'] < data['hire_date']:
                raise serializers.ValidationError({
                    'termination_date': 'Termination date cannot be before hire date.'
                })
        return data


class EquipmentAssignmentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating equipment assignments"""

    class Meta:
        model = EquipmentAssignment
        fields = [
            'worker', 'inventory_item', 'item_type', 'quantity',
            'expected_return_date', 'condition_at_assignment', 'assignment_notes'
        ]

    def validate(self, data):
        """Validate assignment data"""
        inventory_item = data.get('inventory_item')
        quantity = data.get('quantity', 1)

        # Check if inventory item has enough quantity
        if inventory_item and inventory_item.quantity < quantity:
            raise serializers.ValidationError({
                'quantity': f'Insufficient inventory. Available: {inventory_item.quantity} {inventory_item.unit}'
            })

        return data

    def create(self, validated_data):
        """Create assignment and cache item name"""
        inventory_item = validated_data['inventory_item']
        validated_data['item_name'] = inventory_item.name

        # Set assigned_by from request user
        request = self.context.get('request')
        if request and request.user:
            validated_data['assigned_by'] = request.user

        return super().create(validated_data)


class EquipmentReturnSerializer(serializers.Serializer):
    """Serializer for returning equipment"""
    condition_at_return = serializers.ChoiceField(
        choices=EquipmentAssignment.CONDITION_CHOICES,
        required=True
    )
    return_notes = serializers.CharField(required=False, allow_blank=True)
    damage_notes = serializers.CharField(required=False, allow_blank=True)


class WorkerActivitySerializer(serializers.ModelSerializer):
    """Serializer for worker activities/audit trail"""
    worker_name = serializers.CharField(source='worker.full_name', read_only=True)
    performed_by_name = serializers.CharField(source='performed_by.get_full_name', read_only=True)

    class Meta:
        model = WorkerActivity
        fields = [
            'id', 'worker', 'worker_name', 'action', 'description',
            'assignment', 'performed_by', 'performed_by_name',
            'timestamp', 'old_values', 'new_values'
        ]
        read_only_fields = ['timestamp']


class AssignedEquipmentSummarySerializer(serializers.Serializer):
    """Serializer for assigned equipment summary statistics"""
    item_name = serializers.CharField()
    item_type = serializers.CharField()
    total_quantity_assigned = serializers.DecimalField(max_digits=10, decimal_places=2)
    active_assignments_count = serializers.IntegerField()
    inventory_item_id = serializers.IntegerField()
    category = serializers.CharField()
