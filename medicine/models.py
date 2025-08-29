from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class MedicineClass(models.Model):
    """Medicine classification categories"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']


class Medicine(models.Model):
    """Medicine inventory items"""
    medicine_class = models.ForeignKey(MedicineClass, on_delete=models.CASCADE, related_name='medicines')
    product = models.CharField(max_length=200)
    stock_remaining = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit = models.CharField(max_length=50)
    minimum_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Detailed product information
    brand = models.CharField(max_length=200, blank=True, help_text="Brand or manufacturer")
    generic_name = models.CharField(max_length=200, blank=True, help_text="Generic/scientific name")
    strength = models.CharField(max_length=100, blank=True, help_text="Concentration/strength (e.g., 100mg/ml)")
    dosage_form = models.CharField(max_length=100, blank=True, help_text="Injectable, tablet, powder, etc.")
    route_of_administration = models.CharField(max_length=100, blank=True, help_text="IV, IM, oral, topical, etc.")
    
    # Storage and expiry
    expiry_date = models.DateField(blank=True, null=True)
    batch_number = models.CharField(max_length=100, blank=True)
    lot_number = models.CharField(max_length=100, blank=True)
    storage_temperature = models.CharField(max_length=50, blank=True, help_text="Storage temperature requirements")
    storage_conditions = models.TextField(blank=True, help_text="Special storage requirements")
    
    # Supplier and cost information
    supplier = models.CharField(max_length=200, blank=True)
    supplier_contact = models.CharField(max_length=200, blank=True)
    purchase_date = models.DateField(blank=True, null=True)
    cost_per_unit = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    
    # Regulatory and safety
    license_number = models.CharField(max_length=100, blank=True, help_text="Drug license/registration number")
    controlled_substance = models.BooleanField(default=False)
    prescription_required = models.BooleanField(default=True)
    withdrawal_period = models.CharField(max_length=100, blank=True, help_text="Withdrawal period for food animals")
    
    # Usage information
    indication = models.TextField(blank=True, help_text="What this medicine is used for")
    dosage_instructions = models.TextField(blank=True)
    contraindications = models.TextField(blank=True)
    side_effects = models.TextField(blank=True)
    
    # Inventory management
    location_in_storage = models.CharField(max_length=200, blank=True, help_text="Physical location in storage")
    barcode = models.CharField(max_length=100, blank=True, unique=True, null=True)
    qr_code = models.CharField(max_length=200, blank=True)
    
    # Status and alerts
    is_active = models.BooleanField(default=True)
    requires_prescription = models.BooleanField(default=True)
    is_emergency_medicine = models.BooleanField(default=False)
    is_controlled_drug = models.BooleanField(default=False)
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_medicines')
    last_updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='updated_medicines')
    
    def __str__(self):
        return f"{self.product} - {self.stock_remaining} {self.unit}"
    
    @property
    def stock_status(self):
        """Get stock status based on remaining stock vs minimum"""
        if self.stock_remaining <= 0:
            return 'out'
        elif self.stock_remaining <= self.minimum_stock:
            return 'low'
        return 'adequate'
    
    class Meta:
        ordering = ['medicine_class__name', 'product']


class StoragePermission(models.Model):
    """Storage access permissions for users"""
    PERMISSION_TYPES = [
        ('read', 'Read Only'),
        ('add_stock', 'Add Stock'),
        ('remove_stock', 'Remove Stock'),
        ('full_access', 'Full Access'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='storage_permissions')
    permission_type = models.CharField(max_length=20, choices=PERMISSION_TYPES)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='granted_storage_permissions'
    )
    granted_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['user', 'permission_type']
    
    def __str__(self):
        return f"{self.user.username} - {self.get_permission_type_display()}"


class StockTransaction(models.Model):
    """Track all stock movements"""
    TRANSACTION_TYPES = [
        ('add', 'Stock Added'),
        ('remove', 'Stock Removed'),
        ('adjustment', 'Stock Adjustment'),
        ('expired', 'Expired Stock Removed'),
    ]
    
    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    previous_stock = models.DecimalField(max_digits=10, decimal_places=2)
    new_stock = models.DecimalField(max_digits=10, decimal_places=2)
    
    # User and tracking
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='stock_transactions')
    reason = models.CharField(max_length=500, blank=True)
    notes = models.TextField(blank=True)
    
    # Batch info for specific transactions
    batch_number = models.CharField(max_length=100, blank=True)
    expiry_date = models.DateField(blank=True, null=True)
    
    timestamp = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.medicine.product} - {self.transaction_type} - {self.quantity} {self.medicine.unit}"
    
    class Meta:
        ordering = ['-timestamp']