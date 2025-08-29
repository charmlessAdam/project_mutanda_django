from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class CattleSection(models.Model):
    """Different sections/pens where cattle are housed"""
    name = models.CharField(max_length=100, help_text="Section name (e.g., FED3, FED4, FED5)")
    section_number = models.IntegerField(unique=True, help_text="Section number")
    description = models.TextField(blank=True, help_text="Description of the section")
    capacity = models.IntegerField(help_text="Maximum number of cattle this section can hold")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_sections')
    
    def __str__(self):
        return f"Section {self.section_number} - {self.name}"
    
    class Meta:
        ordering = ['section_number']


class Animal(models.Model):
    """Individual animals in the cattle management system"""
    eid = models.CharField(max_length=50, unique=True, help_text="Electronic ID (e.g., 964 001034143697)")
    vid = models.CharField(max_length=50, blank=True, help_text="Visual ID if different from EID")
    section = models.ForeignKey(CattleSection, on_delete=models.CASCADE, related_name='animals')
    
    # Basic information
    breed = models.CharField(max_length=100, blank=True)
    gender = models.CharField(max_length=10, choices=[
        ('male', 'Male'),
        ('female', 'Female'),
        ('castrated', 'Castrated')
    ], blank=True)
    birth_date = models.DateField(blank=True, null=True)
    entry_date = models.DateField(help_text="Date animal entered the system")
    entry_weight = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True, help_text="Weight at entry (kg)")
    
    # Current status
    current_weight = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True, help_text="Current weight (kg)")
    is_active = models.BooleanField(default=True, help_text="Is animal currently in the system")
    exit_date = models.DateField(blank=True, null=True, help_text="Date animal left the system")
    exit_reason = models.CharField(max_length=100, blank=True, choices=[
        ('sold', 'Sold'),
        ('deceased', 'Deceased'),
        ('transferred', 'Transferred'),
        ('other', 'Other')
    ])
    
    # Health and notes
    health_status = models.CharField(max_length=50, choices=[
        ('healthy', 'Healthy'),
        ('sick', 'Sick'),
        ('under_treatment', 'Under Treatment'),
        ('quarantine', 'Quarantine')
    ], default='healthy')
    notes = models.TextField(blank=True)
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_animals')
    last_updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='updated_animals')
    
    def __str__(self):
        return f"{self.eid} - Section {self.section.section_number}"
    
    @property
    def age_days(self):
        """Calculate age in days"""
        if self.birth_date:
            from datetime import date
            return (date.today() - self.birth_date).days
        return None
    
    @property
    def days_in_system(self):
        """Calculate days in the system"""
        from datetime import date
        end_date = self.exit_date if self.exit_date else date.today()
        return (end_date - self.entry_date).days
    
    class Meta:
        ordering = ['section__section_number', 'eid']


class WeightRecord(models.Model):
    """Weight measurements for animals over time"""
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name='weight_records')
    weight = models.DecimalField(max_digits=6, decimal_places=2, help_text="Weight in kg")
    measurement_date = models.DateField(help_text="Date of weight measurement")
    
    # Calculated fields (can be computed from data)
    gain_loss = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True, help_text="Weight gain/loss from previous measurement")
    fcr = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True, help_text="Feed Conversion Ratio")
    adg = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True, help_text="Average Daily Gain")
    
    # Tracking
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='weight_records')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def save(self, *args, **kwargs):
        # Update animal's current weight
        if self.animal:
            self.animal.current_weight = self.weight
            self.animal.save()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.animal.eid} - {self.weight}kg on {self.measurement_date}"
    
    class Meta:
        ordering = ['-measurement_date', 'animal__eid']
        unique_together = ['animal', 'measurement_date']


class FeedRecord(models.Model):
    """Feed consumption records for sections"""
    section = models.ForeignKey(CattleSection, on_delete=models.CASCADE, related_name='feed_records')
    feed_date = models.DateField(help_text="Date of feed record")
    
    # Feed amounts
    total_feed_kg = models.DecimalField(max_digits=8, decimal_places=2, help_text="Total feed in kg")
    total_bags = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True, help_text="Number of feed bags")
    feed_type = models.CharField(max_length=100, blank=True, help_text="Type of feed used")
    
    # Cost tracking
    cost_per_kg = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, help_text="Cost per kg of feed")
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Total feed cost")
    
    # Tracking
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='feed_records')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Section {self.section.section_number} - {self.total_feed_kg}kg on {self.feed_date}"
    
    class Meta:
        ordering = ['-feed_date', 'section__section_number']


class HealthRecord(models.Model):
    """Health records and treatments for animals"""
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name='health_records')
    record_date = models.DateField(help_text="Date of health record")
    record_type = models.CharField(max_length=50, choices=[
        ('checkup', 'Regular Checkup'),
        ('vaccination', 'Vaccination'),
        ('treatment', 'Treatment'),
        ('illness', 'Illness'),
        ('injury', 'Injury'),
        ('other', 'Other')
    ])
    
    # Health details
    diagnosis = models.CharField(max_length=200, blank=True)
    treatment = models.TextField(blank=True, help_text="Treatment provided")
    medicine_used = models.CharField(max_length=200, blank=True, help_text="Medicine/drugs administered")
    dosage = models.CharField(max_length=100, blank=True, help_text="Dosage information")
    
    # Follow-up
    follow_up_date = models.DateField(blank=True, null=True, help_text="Next follow-up date")
    follow_up_required = models.BooleanField(default=False)
    
    # Cost
    treatment_cost = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, help_text="Cost of treatment")
    
    # Tracking
    veterinarian = models.CharField(max_length=200, blank=True, help_text="Veterinarian name")
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='health_records')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.animal.eid} - {self.record_type} on {self.record_date}"
    
    class Meta:
        ordering = ['-record_date', 'animal__eid']


class AnimalMovement(models.Model):
    """Track movements of animals between sections"""
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name='movements')
    from_section = models.ForeignKey(CattleSection, on_delete=models.SET_NULL, null=True, related_name='animals_moved_from')
    to_section = models.ForeignKey(CattleSection, on_delete=models.CASCADE, related_name='animals_moved_to')
    movement_date = models.DateTimeField()
    reason = models.CharField(max_length=200, blank=True, help_text="Reason for movement")
    
    # Tracking
    moved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='animal_movements')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def save(self, *args, **kwargs):
        # Update animal's current section
        if self.animal:
            self.animal.section = self.to_section
            self.animal.save()
        super().save(*args, **kwargs)
    
    def __str__(self):
        from_section_name = f"Section {self.from_section.section_number}" if self.from_section else "Entry"
        return f"{self.animal.eid} moved from {from_section_name} to Section {self.to_section.section_number}"
    
    class Meta:
        ordering = ['-movement_date']


class CattlePermission(models.Model):
    """Permissions for cattle management access"""
    PERMISSION_TYPES = [
        ('read', 'Read Only'),
        ('add_records', 'Add Records'),
        ('edit_records', 'Edit Records'),
        ('full_access', 'Full Access'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cattle_permissions')
    permission_type = models.CharField(max_length=20, choices=PERMISSION_TYPES)
    section = models.ForeignKey(CattleSection, on_delete=models.CASCADE, blank=True, null=True, help_text="Specific section access, leave blank for all sections")
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='granted_cattle_permissions'
    )
    granted_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['user', 'permission_type', 'section']
    
    def __str__(self):
        section_str = f" for Section {self.section.section_number}" if self.section else " for all sections"
        return f"{self.user.username} - {self.get_permission_type_display()}{section_str}"