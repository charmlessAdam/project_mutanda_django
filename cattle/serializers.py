from rest_framework import serializers
from .models import Animal, CattleSection, WeightRecord, HealthRecord, FeedRecord


class CattleSectionSerializer(serializers.ModelSerializer):
    animal_count = serializers.SerializerMethodField()
    active_animals = serializers.SerializerMethodField()
    
    class Meta:
        model = CattleSection
        fields = ['id', 'name', 'section_number', 'description', 'capacity', 
                 'animal_count', 'active_animals', 'created_at', 'updated_at']
    
    def get_animal_count(self, obj):
        return obj.animals.count()
    
    def get_active_animals(self, obj):
        return obj.animals.filter(is_active=True).count()


class AnimalSerializer(serializers.ModelSerializer):
    section = CattleSectionSerializer(read_only=True)
    section_id = serializers.IntegerField(write_only=True, required=False)
    age_days = serializers.ReadOnlyField()
    days_in_system = serializers.ReadOnlyField()
    
    class Meta:
        model = Animal
        fields = ['id', 'eid', 'vid', 'section', 'section_id', 'breed', 'gender', 
                 'birth_date', 'entry_date', 'entry_weight', 'current_weight', 
                 'is_active', 'exit_date', 'exit_reason', 'health_status', 
                 'notes', 'age_days', 'days_in_system', 'created_at', 'updated_at']


class WeightRecordSerializer(serializers.ModelSerializer):
    animal = AnimalSerializer(read_only=True)
    animal_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = WeightRecord
        fields = ['id', 'animal', 'animal_id', 'weight', 'measurement_date', 
                 'gain_loss', 'fcr', 'adg', 'notes', 'created_at']


class HealthRecordSerializer(serializers.ModelSerializer):
    animal = AnimalSerializer(read_only=True)
    animal_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = HealthRecord
        fields = ['id', 'animal', 'animal_id', 'record_date', 'record_type', 
                 'diagnosis', 'treatment', 'medicine_used', 'dosage', 
                 'follow_up_date', 'follow_up_required', 'treatment_cost', 
                 'veterinarian', 'notes', 'created_at']


class FeedRecordSerializer(serializers.ModelSerializer):
    section = CattleSectionSerializer(read_only=True)
    section_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = FeedRecord
        fields = ['id', 'section', 'section_id', 'feed_date', 'total_feed_kg', 
                 'total_bags', 'feed_type', 'cost_per_kg', 'total_cost', 
                 'notes', 'created_at']