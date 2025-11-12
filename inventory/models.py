from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class InventoryCategory(models.Model):
    """Categories for inventory items (Feed, Equipment, Supplies, etc.)"""
    name = models.CharField(max_length=100, unique=True, help_text="Category name (e.g., Feed, Equipment)")
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Icon name for UI")
    color = models.CharField(max_length=20, blank=True, help_text="Color code for UI (e.g., #57552f)")

    # Category settings
    requires_expiration = models.BooleanField(default=False, help_text="Does this category require expiration tracking?")
    requires_batch_tracking = models.BooleanField(default=False, help_text="Does this category require batch/lot tracking?")

    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_inventory_categories')

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Inventory Category'
        verbose_name_plural = 'Inventory Categories'
        ordering = ['name']


class StorageLocation(models.Model):
    """Physical storage locations (Silos, Warehouses, Sheds, etc.)"""
    LOCATION_TYPES = [
        ('silo', 'Silo'),
        ('warehouse', 'Warehouse'),
        ('shed', 'Shed'),
        ('cabinet', 'Cabinet'),
        ('refrigerator', 'Refrigerator'),
        ('tank', 'Tank'),
        ('yard', 'Yard'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=200, help_text="Location name (e.g., Silo 1, Main Warehouse)")
    location_type = models.CharField(max_length=20, choices=LOCATION_TYPES)
    description = models.TextField(blank=True)

    # Capacity tracking
    capacity = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Total capacity")
    capacity_unit = models.CharField(max_length=50, blank=True, help_text="Unit (kg, liters, cubic meters)")

    # Environmental monitoring
    temperature_controlled = models.BooleanField(default=False)
    current_temperature = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, help_text="Current temperature (°C)")
    humidity = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, help_text="Current humidity (%)")

    # Location details
    building = models.CharField(max_length=200, blank=True, help_text="Building name or number")
    floor = models.CharField(max_length=50, blank=True)
    section = models.CharField(max_length=100, blank=True)
    coordinates = models.JSONField(blank=True, null=True, help_text="GPS or map coordinates")

    # Access control
    requires_authorization = models.BooleanField(default=False)

    # Status
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_storage_locations')

    def __str__(self):
        return f"{self.name} ({self.get_location_type_display()})"

    @property
    def current_utilization(self):
        """Calculate current utilization percentage"""
        if not self.capacity:
            return None

        total_stock = sum(
            item.quantity for item in self.inventory_items.filter(is_active=True)
            if item.unit == self.capacity_unit
        )

        if self.capacity > 0:
            return round((total_stock / float(self.capacity)) * 100, 2)
        return 0

    class Meta:
        ordering = ['location_type', 'name']


class InventoryItem(models.Model):
    """General inventory items (Feed, Equipment, Supplies, etc.)"""
    name = models.CharField(max_length=200, help_text="Item name")
    category = models.ForeignKey(InventoryCategory, on_delete=models.CASCADE, related_name='inventory_items')
    storage_location = models.ForeignKey(StorageLocation, on_delete=models.SET_NULL, null=True, related_name='inventory_items')

    # Quantity and units
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Current quantity")
    unit = models.CharField(max_length=50, help_text="Unit of measurement (kg, liters, pieces, bags)")
    reorder_level = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Alert when quantity drops below this")
    optimal_quantity = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Optimal stock level")

    # Product details
    brand = models.CharField(max_length=200, blank=True)
    model_number = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    specifications = models.TextField(blank=True, help_text="Technical specifications")

    # Purchase information
    supplier = models.CharField(max_length=200, blank=True)
    supplier_contact = models.CharField(max_length=200, blank=True)
    purchase_date = models.DateField(blank=True, null=True)
    cost_per_unit = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    currency = models.CharField(max_length=10, default='USD')

    # Expiration and batch (for items like feed, chemicals)
    expiration_date = models.DateField(blank=True, null=True, help_text="Expiration or best-before date")
    batch_number = models.CharField(max_length=100, blank=True)
    lot_number = models.CharField(max_length=100, blank=True)

    # Identification
    barcode = models.CharField(max_length=100, blank=True, null=True)
    sku = models.CharField(max_length=100, blank=True, help_text="Stock Keeping Unit")

    # Condition (for equipment)
    condition = models.CharField(max_length=50, blank=True, choices=[
        ('new', 'New'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
        ('needs_repair', 'Needs Repair'),
        ('broken', 'Broken'),
    ])

    # Maintenance (for equipment)
    last_maintenance_date = models.DateField(blank=True, null=True)
    next_maintenance_date = models.DateField(blank=True, null=True)
    maintenance_notes = models.TextField(blank=True)

    # Status and tracking
    is_active = models.BooleanField(default=True)
    is_consumable = models.BooleanField(default=True, help_text="Is this item consumed/used up?")
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_inventory_items')
    last_updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='updated_inventory_items')

    def __str__(self):
        return f"{self.name} - {self.quantity} {self.unit}"

    @property
    def stock_status(self):
        """Get stock status based on remaining stock vs reorder level"""
        if self.quantity <= 0:
            return 'out'
        elif self.quantity <= self.reorder_level:
            return 'low'
        elif self.optimal_quantity and self.quantity >= self.optimal_quantity:
            return 'optimal'
        return 'adequate'

    @property
    def total_value(self):
        """Calculate total value of current stock"""
        if self.cost_per_unit:
            return float(self.quantity) * float(self.cost_per_unit)
        return None

    class Meta:
        ordering = ['category__name', 'name']
        indexes = [
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['storage_location', 'is_active']),
            models.Index(fields=['expiration_date']),
        ]


class StockTransaction(models.Model):
    """Track all inventory stock movements"""
    TRANSACTION_TYPES = [
        ('purchase', 'Purchase/Stock In'),
        ('usage', 'Usage/Stock Out'),
        ('transfer', 'Transfer Between Locations'),
        ('adjustment', 'Stock Adjustment'),
        ('waste', 'Waste/Spoilage'),
        ('return', 'Return to Supplier'),
        ('loss', 'Loss/Theft'),
    ]

    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)

    # Quantity changes
    quantity = models.DecimalField(max_digits=10, decimal_places=2, help_text="Quantity added or removed (use positive for in, negative for out)")
    previous_quantity = models.DecimalField(max_digits=10, decimal_places=2)
    new_quantity = models.DecimalField(max_digits=10, decimal_places=2)

    # Transaction details
    transaction_date = models.DateTimeField(auto_now_add=True)
    reference_number = models.CharField(max_length=100, blank=True, help_text="Invoice, receipt, or reference number")

    # Location tracking
    from_location = models.ForeignKey(StorageLocation, on_delete=models.SET_NULL, null=True, blank=True, related_name='outgoing_transactions')
    to_location = models.ForeignKey(StorageLocation, on_delete=models.SET_NULL, null=True, blank=True, related_name='incoming_transactions')

    # Cost tracking
    cost = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    cost_per_unit = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    # Purpose and notes
    purpose = models.TextField(blank=True, help_text="Why this transaction occurred")
    notes = models.TextField(blank=True)

    # Batch info for specific transactions
    batch_number = models.CharField(max_length=100, blank=True)
    expiration_date = models.DateField(blank=True, null=True)

    # User tracking
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='inventory_transactions')

    def __str__(self):
        return f"{self.item.name} - {self.transaction_type} - {self.quantity} {self.item.unit}"

    class Meta:
        ordering = ['-transaction_date']
        indexes = [
            models.Index(fields=['-transaction_date']),
            models.Index(fields=['item', '-transaction_date']),
        ]


class InventoryAlert(models.Model):
    """Automated alerts for inventory issues"""
    ALERT_TYPES = [
        ('low_stock', 'Low Stock'),
        ('out_of_stock', 'Out of Stock'),
        ('expiring_soon', 'Expiring Soon'),
        ('expired', 'Expired'),
        ('needs_maintenance', 'Needs Maintenance'),
        ('overstock', 'Overstock'),
        ('temperature', 'Temperature Alert'),
        ('other', 'Other'),
    ]

    SEVERITY_LEVELS = [
        ('critical', 'Critical'),
        ('warning', 'Warning'),
        ('info', 'Info'),
    ]

    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    severity = models.CharField(max_length=10, choices=SEVERITY_LEVELS)

    # Related objects
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, null=True, blank=True, related_name='alerts')
    location = models.ForeignKey(StorageLocation, on_delete=models.CASCADE, null=True, blank=True, related_name='alerts')

    # Alert details
    message = models.TextField()
    recommended_action = models.TextField(blank=True)

    # Status
    is_read = models.BooleanField(default=False)
    is_resolved = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_inventory_alerts')
    resolution_notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.get_alert_type_display()} - {self.severity}"

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_resolved', '-created_at']),
            models.Index(fields=['severity', '-created_at']),
        ]


class FeedPrescription(models.Model):
    """Feed mixing formulas/prescriptions"""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('draft', 'Draft'),
        ('inactive', 'Inactive'),
    ]

    name = models.CharField(max_length=200, help_text="Prescription name")
    description = models.TextField(blank=True)
    target_animal_type = models.CharField(max_length=100, help_text="e.g., Dairy Cattle, Growing Cattle")
    target_weight = models.CharField(max_length=50, blank=True, help_text="Weight range e.g., 500-700kg")

    # Nutritional profile
    total_protein = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Total protein %")
    total_energy = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Total energy MCal/kg")
    total_fiber = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Total fiber %")

    # Cost
    cost_per_ton = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Cost per ton")

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    is_active = models.BooleanField(default=True)

    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_feed_prescriptions')

    def __str__(self):
        return f"{self.name} - {self.target_animal_type}"

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'is_active']),
            models.Index(fields=['target_animal_type']),
        ]


class PrescriptionIngredient(models.Model):
    """Ingredients in a feed prescription"""
    prescription = models.ForeignKey(FeedPrescription, on_delete=models.CASCADE, related_name='ingredients')
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, help_text="Feed ingredient")

    # Composition
    percentage = models.DecimalField(max_digits=5, decimal_places=2, help_text="Percentage in mix")
    kg_per_ton = models.DecimalField(max_digits=7, decimal_places=2, help_text="Kilograms per ton")

    # Order for display
    order = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.prescription.name} - {self.inventory_item.name} ({self.percentage}%)"

    class Meta:
        ordering = ['order', 'id']
        unique_together = ['prescription', 'inventory_item']


class FeedConsumption(models.Model):
    """Track feed consumption records"""
    prescription = models.ForeignKey(
        FeedPrescription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='consumption_records',
        help_text="Feed prescription used (optional)"
    )

    # Consumption details
    quantity = models.DecimalField(max_digits=10, decimal_places=2, help_text="Quantity consumed in kg or tons")
    unit = models.CharField(max_length=20, default='kg', choices=[('kg', 'Kilograms'), ('ton', 'Tons')])

    # Target information
    target_section = models.CharField(max_length=200, blank=True, help_text="Farm section or animal group")
    animal_count = models.IntegerField(null=True, blank=True, help_text="Number of animals fed")

    # Date and tracking
    consumption_date = models.DateField(help_text="Date of consumption")
    notes = models.TextField(blank=True)

    # Calculated field - ingredient usage
    ingredient_usage = models.JSONField(blank=True, null=True, help_text="Auto-calculated ingredient breakdown")

    # User tracking
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='feed_consumptions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def calculate_ingredient_usage(self):
        """Calculate ingredient usage based on prescription"""
        if not self.prescription:
            return None

        # Convert quantity to kg
        quantity_kg = float(self.quantity)
        if self.unit == 'ton':
            quantity_kg = quantity_kg * 1000

        # Calculate each ingredient
        usage = {}
        for ing in self.prescription.ingredients.all():
            kg_used = (float(ing.kg_per_ton) / 1000) * quantity_kg
            usage[ing.inventory_item.name] = {
                'quantity': round(kg_used, 2),
                'unit': 'kg',
                'percentage': float(ing.percentage),
                'item_id': ing.inventory_item.id
            }

        return usage

    def save(self, *args, **kwargs):
        # Auto-calculate ingredient usage if prescription is provided
        if self.prescription:
            self.ingredient_usage = self.calculate_ingredient_usage()
        super().save(*args, **kwargs)

    def __str__(self):
        prescription_name = self.prescription.name if self.prescription else 'Custom Feed'
        return f"{prescription_name} - {self.quantity} {self.unit} on {self.consumption_date}"

    class Meta:
        ordering = ['-consumption_date', '-created_at']
        indexes = [
            models.Index(fields=['-consumption_date']),
            models.Index(fields=['prescription', '-consumption_date']),
        ]
