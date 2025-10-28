from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class Worker(models.Model):
    """Farm workers and staff members"""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('on_leave', 'On Leave'),
        ('terminated', 'Terminated'),
    ]

    DEPARTMENT_CHOICES = [
        ('veterinary', 'Veterinary'),
        ('cattle_management', 'Cattle Management'),
        ('feed_management', 'Feed Management'),
        ('warehouse', 'Warehouse'),
        ('operations', 'Operations'),
        ('maintenance', 'Maintenance'),
        ('security', 'Security'),
        ('administration', 'Administration'),
        ('finance', 'Finance'),
        ('procurement', 'Procurement'),
        ('other', 'Other'),
    ]

    POSITION_CHOICES = [
        ('farm_worker', 'Farm Worker'),
        ('livestock_handler', 'Livestock Handler'),
        ('equipment_operator', 'Equipment Operator'),
        ('veterinary_assistant', 'Veterinary Assistant'),
        ('warehouse_clerk', 'Warehouse Clerk'),
        ('supervisor', 'Supervisor'),
        ('technician', 'Technician'),
        ('driver', 'Driver'),
        ('security_guard', 'Security Guard'),
        ('maintenance_worker', 'Maintenance Worker'),
        ('administrator', 'Administrator'),
        ('other', 'Other'),
    ]

    # Identification
    employee_id = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique employee identification number"
    )

    # Personal Information
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)

    # Employment Information
    department = models.CharField(max_length=50, choices=DEPARTMENT_CHOICES)
    position = models.CharField(max_length=50, choices=POSITION_CHOICES)
    hire_date = models.DateField(help_text="Date when worker was hired")
    termination_date = models.DateField(blank=True, null=True)

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    # System User Link (optional - if worker has a system account)
    user_account = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='worker_profile',
        help_text="Linked system user account if worker has login access"
    )

    # Management
    supervisor = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supervised_workers',
        help_text="Direct supervisor"
    )

    # Additional Information
    notes = models.TextField(blank=True, help_text="Additional notes about the worker")
    emergency_contact = models.CharField(max_length=200, blank=True)
    emergency_phone = models.CharField(max_length=20, blank=True)

    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_workers'
    )
    last_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='updated_workers'
    )

    def __str__(self):
        return f"{self.employee_id} - {self.full_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def active_assignments(self):
        """Get all currently active equipment assignments"""
        return self.equipment_assignments.filter(is_active=True)

    @property
    def total_assigned_items(self):
        """Count total number of active assigned items"""
        return self.active_assignments.count()

    def clean(self):
        """Validate worker data"""
        if self.termination_date and self.hire_date:
            if self.termination_date < self.hire_date:
                raise ValidationError("Termination date cannot be before hire date")

    class Meta:
        ordering = ['employee_id']
        indexes = [
            models.Index(fields=['employee_id']),
            models.Index(fields=['department', 'status']),
            models.Index(fields=['status']),
        ]


class EquipmentAssignment(models.Model):
    """Track equipment and items assigned to workers"""
    CONDITION_CHOICES = [
        ('new', 'New'),
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
        ('damaged', 'Damaged'),
    ]

    ITEM_TYPE_CHOICES = [
        ('safety_equipment', 'Safety Equipment'),
        ('tools', 'Tools'),
        ('protective_gear', 'Protective Gear'),
        ('communication_device', 'Communication Device'),
        ('vehicle', 'Vehicle'),
        ('uniform', 'Uniform'),
        ('other', 'Other'),
    ]

    # Assignment Details
    worker = models.ForeignKey(
        Worker,
        on_delete=models.CASCADE,
        related_name='equipment_assignments'
    )
    inventory_item = models.ForeignKey(
        'inventory.InventoryItem',
        on_delete=models.CASCADE,
        related_name='worker_assignments',
        help_text="Item from inventory that is assigned"
    )

    # Item Details at Assignment Time
    item_name = models.CharField(
        max_length=200,
        help_text="Item name at time of assignment (cached for history)"
    )
    item_type = models.CharField(
        max_length=50,
        choices=ITEM_TYPE_CHOICES,
        default='other',
        blank=True
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1,
        help_text="Quantity assigned"
    )

    # Assignment Tracking
    assigned_date = models.DateField(auto_now_add=True)
    expected_return_date = models.DateField(blank=True, null=True)
    returned_date = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(
        default=True,
        help_text="True if item is still assigned, False if returned"
    )

    # Condition Tracking
    condition_at_assignment = models.CharField(
        max_length=20,
        choices=CONDITION_CHOICES,
        default='good'
    )
    condition_at_return = models.CharField(
        max_length=20,
        choices=CONDITION_CHOICES,
        blank=True,
        null=True
    )

    # Notes
    assignment_notes = models.TextField(
        blank=True,
        help_text="Notes when assigning the item"
    )
    return_notes = models.TextField(
        blank=True,
        help_text="Notes when returning the item"
    )
    damage_notes = models.TextField(
        blank=True,
        help_text="Description of any damage"
    )

    # User Tracking
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='assigned_equipment'
    )
    returned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_equipment_returns'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        status = "Active" if self.is_active else "Returned"
        return f"{self.worker.full_name} - {self.item_name} ({status})"

    def clean(self):
        """Validate assignment data"""
        if self.returned_date and self.assigned_date:
            if self.returned_date < self.assigned_date:
                raise ValidationError("Return date cannot be before assignment date")

        if not self.is_active and not self.returned_date:
            raise ValidationError("Inactive assignments must have a return date")

        if self.returned_date and self.is_active:
            raise ValidationError("Cannot have return date if assignment is still active")

    def return_equipment(self, returned_by_user, condition_at_return, return_notes=''):
        """Mark equipment as returned"""
        from django.utils import timezone

        if not self.is_active:
            raise ValidationError("This assignment is already marked as returned")

        self.is_active = False
        self.returned_date = timezone.now().date()
        self.returned_by = returned_by_user
        self.condition_at_return = condition_at_return
        self.return_notes = return_notes
        self.save()

    class Meta:
        ordering = ['-assigned_date']
        indexes = [
            models.Index(fields=['worker', 'is_active']),
            models.Index(fields=['inventory_item', 'is_active']),
            models.Index(fields=['is_active', '-assigned_date']),
        ]


class WorkerActivity(models.Model):
    """Track worker management activities for audit trail"""
    ACTION_CHOICES = [
        ('created', 'Worker Created'),
        ('updated', 'Worker Updated'),
        ('status_changed', 'Status Changed'),
        ('equipment_assigned', 'Equipment Assigned'),
        ('equipment_returned', 'Equipment Returned'),
        ('terminated', 'Worker Terminated'),
        ('reinstated', 'Worker Reinstated'),
    ]

    worker = models.ForeignKey(
        Worker,
        on_delete=models.CASCADE,
        related_name='activities'
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    description = models.TextField(blank=True)

    # Optional link to assignment if action is equipment-related
    assignment = models.ForeignKey(
        EquipmentAssignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activities'
    )

    # Tracking
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='worker_activities'
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    old_values = models.JSONField(blank=True, null=True)
    new_values = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f"{self.worker.full_name} - {self.get_action_display()} at {self.timestamp}"

    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = 'Worker Activities'
