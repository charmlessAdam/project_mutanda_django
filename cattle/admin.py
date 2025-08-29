from django.contrib import admin
from .models import CattleSection, Animal, WeightRecord, FeedRecord, HealthRecord, AnimalMovement, CattlePermission


@admin.register(CattleSection)
class CattleSectionAdmin(admin.ModelAdmin):
    list_display = ['name', 'section_number', 'capacity', 'animal_count', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'section_number']
    ordering = ['section_number']
    
    def animal_count(self, obj):
        return obj.animals.filter(is_active=True).count()
    animal_count.short_description = 'Active Animals'


@admin.register(Animal)
class AnimalAdmin(admin.ModelAdmin):
    list_display = ['eid', 'section', 'current_weight', 'health_status', 'is_active', 'entry_date']
    list_filter = ['section', 'health_status', 'is_active', 'gender', 'entry_date']
    search_fields = ['eid', 'vid']
    ordering = ['section__section_number', 'eid']
    readonly_fields = ['age_days', 'days_in_system']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('eid', 'vid', 'section', 'breed', 'gender')
        }),
        ('Dates & Weights', {
            'fields': ('birth_date', 'entry_date', 'entry_weight', 'current_weight')
        }),
        ('Status', {
            'fields': ('is_active', 'exit_date', 'exit_reason', 'health_status')
        }),
        ('Calculated Fields', {
            'fields': ('age_days', 'days_in_system'),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('notes',)
        })
    )


@admin.register(WeightRecord)
class WeightRecordAdmin(admin.ModelAdmin):
    list_display = ['animal', 'weight', 'measurement_date', 'gain_loss', 'adg', 'recorded_by']
    list_filter = ['measurement_date', 'animal__section']
    search_fields = ['animal__eid']
    ordering = ['-measurement_date']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('animal', 'animal__section', 'recorded_by')


@admin.register(FeedRecord)
class FeedRecordAdmin(admin.ModelAdmin):
    list_display = ['section', 'feed_date', 'total_feed_kg', 'total_bags', 'total_cost', 'recorded_by']
    list_filter = ['feed_date', 'section', 'feed_type']
    search_fields = ['section__name']
    ordering = ['-feed_date']


@admin.register(HealthRecord)
class HealthRecordAdmin(admin.ModelAdmin):
    list_display = ['animal', 'record_date', 'record_type', 'diagnosis', 'follow_up_required', 'recorded_by']
    list_filter = ['record_date', 'record_type', 'follow_up_required', 'animal__section']
    search_fields = ['animal__eid', 'diagnosis', 'treatment']
    ordering = ['-record_date']


@admin.register(AnimalMovement)
class AnimalMovementAdmin(admin.ModelAdmin):
    list_display = ['animal', 'from_section', 'to_section', 'movement_date', 'reason', 'moved_by']
    list_filter = ['movement_date', 'from_section', 'to_section']
    search_fields = ['animal__eid', 'reason']
    ordering = ['-movement_date']


@admin.register(CattlePermission)
class CattlePermissionAdmin(admin.ModelAdmin):
    list_display = ['user', 'permission_type', 'section', 'is_active', 'granted_by', 'granted_at']
    list_filter = ['permission_type', 'is_active', 'section', 'granted_at']
    search_fields = ['user__username', 'user__full_name']
    ordering = ['-granted_at']