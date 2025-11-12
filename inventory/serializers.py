from rest_framework import serializers
from .models import (
    InventoryCategory, StorageLocation, InventoryItem, StockTransaction,
    InventoryAlert, FeedPrescription, PrescriptionIngredient, FeedConsumption
)


class InventoryCategorySerializer(serializers.ModelSerializer):
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = InventoryCategory
        fields = [
            'id', 'name', 'description', 'icon', 'color',
            'requires_expiration', 'requires_batch_tracking',
            'is_active', 'created_at', 'item_count'
        ]
        read_only_fields = ['created_at']

    def get_item_count(self, obj):
        """Get count of active items in this category"""
        return obj.inventory_items.filter(is_active=True).count()


class StorageLocationSerializer(serializers.ModelSerializer):
    utilization = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = StorageLocation
        fields = [
            'id', 'name', 'location_type', 'description',
            'capacity', 'capacity_unit', 'temperature_controlled',
            'current_temperature', 'humidity', 'building', 'floor',
            'section', 'coordinates', 'requires_authorization',
            'is_active', 'notes', 'created_at', 'updated_at',
            'utilization', 'item_count'
        ]
        read_only_fields = ['created_at', 'updated_at', 'utilization', 'item_count']

    def get_utilization(self, obj):
        """Get current utilization percentage"""
        return obj.current_utilization

    def get_item_count(self, obj):
        """Get count of items in this location"""
        return obj.inventory_items.filter(is_active=True).count()


class InventoryItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    location_name = serializers.CharField(source='storage_location.name', read_only=True)
    stock_status = serializers.CharField(read_only=True)
    total_value = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = InventoryItem
        fields = [
            'id', 'name', 'category', 'category_name', 'storage_location', 'location_name',
            'quantity', 'unit', 'reorder_level', 'optimal_quantity',
            'brand', 'model_number', 'description', 'specifications',
            'supplier', 'supplier_contact', 'purchase_date',
            'cost_per_unit', 'currency', 'total_value',
            'expiration_date', 'batch_number', 'lot_number',
            'barcode', 'sku', 'condition',
            'last_maintenance_date', 'next_maintenance_date', 'maintenance_notes',
            'is_active', 'is_consumable', 'notes', 'stock_status',
            'created_at', 'updated_at', 'created_by', 'created_by_username', 'last_updated_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'stock_status', 'total_value']


class StockTransactionSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_unit = serializers.CharField(source='item.unit', read_only=True)
    performed_by_username = serializers.CharField(source='performed_by.username', read_only=True)
    from_location_name = serializers.CharField(source='from_location.name', read_only=True)
    to_location_name = serializers.CharField(source='to_location.name', read_only=True)

    class Meta:
        model = StockTransaction
        fields = [
            'id', 'item', 'item_name', 'item_unit', 'transaction_type',
            'quantity', 'previous_quantity', 'new_quantity',
            'transaction_date', 'reference_number',
            'from_location', 'from_location_name', 'to_location', 'to_location_name',
            'cost', 'cost_per_unit', 'purpose', 'notes',
            'batch_number', 'expiration_date',
            'performed_by', 'performed_by_username'
        ]
        read_only_fields = ['transaction_date']


class InventoryAlertSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    resolved_by_username = serializers.CharField(source='resolved_by.username', read_only=True)

    class Meta:
        model = InventoryAlert
        fields = [
            'id', 'alert_type', 'severity', 'item', 'item_name',
            'location', 'location_name', 'message', 'recommended_action',
            'is_read', 'is_resolved', 'created_at', 'resolved_at',
            'resolved_by', 'resolved_by_username', 'resolution_notes'
        ]
        read_only_fields = ['created_at']


class PrescriptionIngredientSerializer(serializers.ModelSerializer):
    ingredient_id = serializers.IntegerField(source='inventory_item.id', read_only=True)
    ingredient_name = serializers.CharField(source='inventory_item.name', read_only=True)
    ingredient_category = serializers.CharField(source='inventory_item.category.name', read_only=True)
    inventory_item_id = serializers.IntegerField(write_only=True, source='inventory_item.id')

    class Meta:
        model = PrescriptionIngredient
        fields = [
            'id', 'inventory_item_id', 'ingredient_id', 'ingredient_name', 'ingredient_category',
            'percentage', 'kg_per_ton', 'order'
        ]


class FeedPrescriptionSerializer(serializers.ModelSerializer):
    ingredients = PrescriptionIngredientSerializer(many=True, read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)

    class Meta:
        model = FeedPrescription
        fields = [
            'id', 'name', 'description', 'target_animal_type', 'target_weight',
            'total_protein', 'total_energy', 'total_fiber', 'cost_per_ton',
            'status', 'is_active', 'created_at', 'updated_at',
            'created_by', 'created_by_username', 'created_by_name', 'ingredients'
        ]
        read_only_fields = ['created_at', 'updated_at']


class FeedPrescriptionCreateUpdateSerializer(serializers.ModelSerializer):
    ingredients_data = serializers.ListField(write_only=True, required=False)

    class Meta:
        model = FeedPrescription
        fields = [
            'id', 'name', 'description', 'target_animal_type', 'target_weight',
            'total_protein', 'total_energy', 'total_fiber', 'cost_per_ton',
            'status', 'is_active', 'ingredients_data'
        ]

    def create(self, validated_data):
        ingredients_data = validated_data.pop('ingredients_data', [])
        prescription = FeedPrescription.objects.create(**validated_data)

        # Create ingredients
        for idx, ingredient_data in enumerate(ingredients_data):
            PrescriptionIngredient.objects.create(
                prescription=prescription,
                inventory_item_id=ingredient_data.get('inventory_item_id'),
                percentage=ingredient_data.get('percentage'),
                kg_per_ton=ingredient_data.get('kg_per_ton'),
                order=idx
            )

        return prescription

    def update(self, instance, validated_data):
        ingredients_data = validated_data.pop('ingredients_data', None)

        # Update prescription fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update ingredients if provided
        if ingredients_data is not None:
            # Delete old ingredients
            instance.ingredients.all().delete()

            # Create new ingredients
            for idx, ingredient_data in enumerate(ingredients_data):
                PrescriptionIngredient.objects.create(
                    prescription=instance,
                    inventory_item_id=ingredient_data.get('inventory_item_id'),
                    percentage=ingredient_data.get('percentage'),
                    kg_per_ton=ingredient_data.get('kg_per_ton'),
                    order=idx
                )

        return instance


class FeedConsumptionSerializer(serializers.ModelSerializer):
    prescription_name = serializers.CharField(source='prescription.name', read_only=True)
    recorded_by_username = serializers.CharField(source='recorded_by.username', read_only=True)
    ingredient_usage = serializers.JSONField(read_only=True)

    class Meta:
        model = FeedConsumption
        fields = [
            'id', 'prescription', 'prescription_name', 'quantity', 'unit',
            'target_section', 'animal_count', 'consumption_date',
            'ingredient_usage', 'notes', 'recorded_by', 'recorded_by_username',
            'created_at'
        ]
        read_only_fields = ['created_at', 'ingredient_usage', 'recorded_by', 'recorded_by_username']
