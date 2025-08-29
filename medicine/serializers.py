from rest_framework import serializers
from .models import MedicineClass, Medicine, StoragePermission, StockTransaction
from users.models import User


class MedicineClassSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicineClass
        fields = '__all__'


class MedicineSerializer(serializers.ModelSerializer):
    medicine_class_name = serializers.CharField(source='medicine_class.name', read_only=True)
    stock_status = serializers.ReadOnlyField()
    
    class Meta:
        model = Medicine
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'created_by']


class StoragePermissionSerializer(serializers.ModelSerializer):
    user_details = serializers.SerializerMethodField()
    granted_by_details = serializers.SerializerMethodField()
    
    class Meta:
        model = StoragePermission
        fields = '__all__'
    
    def get_user_details(self, obj):
        return {
            'id': obj.user.id,
            'username': obj.user.username,
            'full_name': obj.user.full_name,
            'role': obj.user.role
        }
    
    def get_granted_by_details(self, obj):
        if obj.granted_by:
            return {
                'id': obj.granted_by.id,
                'username': obj.granted_by.username,
                'full_name': obj.granted_by.full_name
            }
        return None


class StockTransactionSerializer(serializers.ModelSerializer):
    medicine_details = serializers.SerializerMethodField()
    performed_by_details = serializers.SerializerMethodField()
    
    class Meta:
        model = StockTransaction
        fields = '__all__'
        read_only_fields = ['performed_by', 'timestamp']
    
    def get_medicine_details(self, obj):
        return {
            'id': obj.medicine.id,
            'product': obj.medicine.product,
            'unit': obj.medicine.unit
        }
    
    def get_performed_by_details(self, obj):
        return {
            'id': obj.performed_by.id,
            'username': obj.performed_by.username,
            'full_name': obj.performed_by.full_name
        }


class StockAdjustmentSerializer(serializers.Serializer):
    """Serializer for stock adjustments (add/remove stock)"""
    medicine_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = serializers.ChoiceField(choices=StockTransaction.TRANSACTION_TYPES)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    batch_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    
    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be positive")
        return value
    
    def validate(self, data):
        try:
            medicine = Medicine.objects.get(id=data['medicine_id'])
            if data['transaction_type'] == 'remove' and medicine.stock_remaining < data['quantity']:
                raise serializers.ValidationError(
                    f"Cannot remove {data['quantity']} {medicine.unit}. Only {medicine.stock_remaining} {medicine.unit} available."
                )
        except Medicine.DoesNotExist:
            raise serializers.ValidationError("Medicine not found")
        
        return data