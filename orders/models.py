from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from decimal import Decimal
from datetime import datetime

User = get_user_model()

def generate_po_number(buying_company):
    """
    Generate a unique PO number based on:
    - PO prefix
    - Two letters representing the buyer
    - Year of creation
    - Progressive 4-digit number

    Example: POMF20240001 for Mutanda Farms in 2024
    """
    # Extract buyer code from company name
    if not buying_company:
        buyer_code = "XX"
    else:
        # Handle special cases
        company_upper = buying_company.upper().strip()

        if company_upper == "MUTANDA FARMS":
            buyer_code = "MF"
        elif company_upper == "MUTANDA MILLING":
            buyer_code = "MM"
        elif company_upper == "KING EGGS":
            buyer_code = "KE"
        elif company_upper == "NTEGU SAFARIS":
            buyer_code = "NS"
        elif " " in company_upper:
            # Multi-word: take first letter of each word
            words = company_upper.split()
            buyer_code = (words[0][0] + words[1][0]) if len(words) >= 2 else words[0][:2]
        else:
            # Single word: take first two letters
            buyer_code = company_upper[:2]

    # Get current year
    current_year = datetime.now().year

    # Build prefix: PO + buyer_code + year
    prefix = f"PO{buyer_code}{current_year}"

    # Find the highest existing number for this prefix
    from django.db.models import Max
    existing_pos = QuoteOption.objects.filter(
        po_number__startswith=prefix
    ).aggregate(Max('po_number'))

    if existing_pos['po_number__max']:
        # Extract the last 4 digits and increment
        last_po = existing_pos['po_number__max']
        try:
            last_number = int(last_po[-4:])
            next_number = last_number + 1
        except (ValueError, IndexError):
            next_number = 1
    else:
        next_number = 1

    # Format as 4-digit number with leading zeros
    po_number = f"{prefix}{next_number:04d}"

    return po_number

class Order(models.Model):
    ORDER_TYPES = [
        ('medicine', 'Medicine'),
        ('equipment', 'Equipment'),
        ('supplies', 'Supplies'),
    ]
    
    URGENCY_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending Manager Approval'),
        ('approved_by_manager', 'Approved by Manager - Pending Procurement'),
        ('procurement_quote_submitted', 'Quote Submitted - Pending Manager Approval'),
        ('quote_approved_by_manager', 'Quote Approved - Pending Finance Payment'),
        ('payment_completed', 'Payment Completed'),
        ('rejected', 'Rejected'),
        ('revision_requested_by_manager', 'Revision Requested by Manager'),
        ('revision_requested_by_procurement', 'Revision Requested by Procurement'),
        ('revision_requested_by_finance', 'Revision Requested by Finance'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Order identification
    order_number = models.CharField(max_length=20, unique=True, db_index=True)

    # Order details
    order_type = models.CharField(max_length=20, choices=ORDER_TYPES)
    item_name = models.CharField(max_length=200, blank=True, default='', help_text="Name of the item being ordered")
    title = models.CharField(max_length=200)
    description = models.TextField()
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit = models.CharField(max_length=50, default='pieces')
    urgency = models.CharField(max_length=10, choices=URGENCY_LEVELS, default='medium')
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    supplier = models.CharField(max_length=200, blank=True, null=True)

    # Procurement quote details
    quote_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Quote amount from procurement")
    quote_supplier = models.CharField(max_length=200, blank=True, null=True, help_text="Supplier quoted by procurement")
    quote_notes = models.TextField(blank=True, null=True, help_text="Procurement quote notes")
    quote_submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='submitted_quotes')
    quote_submitted_at = models.DateTimeField(blank=True, null=True)

    # Payment details
    payment_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Actual payment amount")
    payment_method = models.CharField(max_length=50, blank=True, null=True, help_text="Payment method used")
    payment_reference = models.CharField(max_length=100, blank=True, null=True, help_text="Payment reference/transaction ID")
    payment_notes = models.TextField(blank=True, null=True, help_text="Payment notes")
    payment_completed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='completed_payments')
    payment_completed_at = models.DateTimeField(blank=True, null=True)
    
    # Request information
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='requested_orders')
    request_date = models.DateTimeField(auto_now_add=True)
    
    # Status tracking
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    rejection_reason = models.TextField(blank=True, null=True)
    revision_reason = models.TextField(blank=True, null=True, help_text="Reason for requesting revision")
    revision_requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='requested_revisions', help_text="User who requested the revision")
    revision_requested_at = models.DateTimeField(null=True, blank=True)
    completion_date = models.DateTimeField(blank=True, null=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['requested_by', '-created_at']),
            models.Index(fields=['order_type', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.order_number} - {self.title}"
    
    @property
    def is_pending_approval(self):
        return self.status in ['pending', 'approved_by_manager', 'procurement_quote_submitted', 'quote_approved_by_manager']

    @property
    def needs_revision(self):
        return self.status in ['revision_requested_by_manager', 'revision_requested_by_procurement', 'revision_requested_by_finance']

    @property
    def next_approver_role(self):
        if self.status == 'pending':
            return 'manager'
        elif self.status == 'approved_by_manager':
            return 'procurement'
        elif self.status == 'procurement_quote_submitted':
            return 'manager'
        elif self.status == 'quote_approved_by_manager':
            return 'finance_manager'
        return None

class OrderItem(models.Model):
    """
    Individual items within an order - supports multiple items per order
    """
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    item_name = models.CharField(max_length=200, help_text='Name of the item')
    is_custom_item = models.BooleanField(default=False, help_text='Whether this is a custom item not in predefined list')
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit = models.CharField(max_length=50, default='pieces')
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))], null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(fields=['order', 'id']),
        ]

    def __str__(self):
        return f"{self.item_name} ({self.quantity} {self.unit})"

class QuoteOption(models.Model):
    """
    Multiple quote options submitted by procurement
    """
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='quote_options')
    supplier_name = models.CharField(max_length=200)
    supplier_address = models.TextField(blank=True, null=True, help_text="Supplier address")
    buying_company = models.CharField(max_length=100, blank=True, null=True, help_text="Which company is buying")
    quoted_amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    vat_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), help_text="VAT percentage (e.g., 18.00 for 18%)")
    vat_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Calculated VAT amount")
    total_with_vat = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Total amount including VAT")
    po_number = models.CharField(max_length=50, blank=True, null=True, unique=True, help_text="Purchase Order number (e.g., POMF202400001)")
    delivery_time = models.CharField(max_length=100, blank=True, null=True, help_text="Estimated delivery time")
    notes = models.TextField(blank=True, null=True)
    is_recommended = models.BooleanField(default=False, help_text="Procurement's recommended option")
    is_selected = models.BooleanField(default=False, help_text="Selected by manager")

    # Tracking
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='submitted_quote_options')
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['quoted_amount']  # Order by price, lowest first
        indexes = [
            models.Index(fields=['order', 'is_recommended']),
            models.Index(fields=['order', 'is_selected']),
        ]

    def __str__(self):
        recommended = " (RECOMMENDED)" if self.is_recommended else ""
        selected = " [SELECTED]" if self.is_selected else ""
        return f"{self.supplier_name} - ${self.quoted_amount}{recommended}{selected}"

class QuoteOptionItem(models.Model):
    """
    Individual item pricing within a quote option (for multi-item orders)
    """
    quote_option = models.ForeignKey(QuoteOption, on_delete=models.CASCADE, related_name='item_quotes')
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name='quote_items')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    total_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    availability = models.CharField(max_length=100, blank=True, null=True, help_text="Item availability status")
    notes = models.TextField(blank=True, null=True, help_text="Item-specific notes")
    is_not_available = models.BooleanField(default=False, help_text="Mark if this item is not available from this supplier")

    class Meta:
        ordering = ['order_item__id']
        unique_together = ['quote_option', 'order_item']
        indexes = [
            models.Index(fields=['quote_option', 'order_item']),
        ]

    def __str__(self):
        return f"{self.order_item.item_name} - ${self.unit_price}/unit (Total: ${self.total_price})"

class OrderApproval(models.Model):
    APPROVAL_STAGES = [
        ('manager_initial', 'Manager Initial Approval'),
        ('procurement', 'Procurement Quote'),
        ('manager_quote', 'Manager Quote Approval'),
        ('finance', 'Finance Payment'),
    ]
    
    APPROVAL_ACTIONS = [
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('revision_requested', 'Revision Requested'),
    ]
    
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='approvals')
    stage = models.CharField(max_length=20, choices=APPROVAL_STAGES)
    approver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='order_approvals')
    action = models.CharField(max_length=20, choices=APPROVAL_ACTIONS)
    notes = models.TextField(blank=True, null=True)
    
    # For revision requests
    requires_revision = models.BooleanField(default=False)
    revision_completed = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = [['order', 'stage']]  # One approval per stage per order
        indexes = [
            models.Index(fields=['order', 'stage']),
            models.Index(fields=['approver', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.order.order_number} - {self.stage} {self.action} by {self.approver.get_full_name()}"

class OrderActivity(models.Model):
    """
    Detailed activity log for all order actions - visible to superadmin
    """
    ACTIVITY_TYPES = [
        ('created', 'Order Created'),
        ('updated', 'Order Updated'),
        ('submitted', 'Submitted for Approval'),
        ('manager_approved', 'Manager Approved'),
        ('manager_rejected', 'Manager Rejected'),
        ('quote_submitted', 'Quote Submitted by Procurement'),
        ('quote_approved', 'Quote Approved by Manager'),
        ('quote_rejected', 'Quote Rejected by Manager'),
        ('payment_completed', 'Payment Completed by Finance'),
        ('finance_rejected', 'Finance Rejected'),
        ('revision_requested', 'Revision Requested'),
        ('revision_submitted', 'Revision Submitted'),
        ('completed', 'Order Completed'),
        ('cancelled', 'Order Cancelled'),
        ('comment_added', 'Comment Added'),
        ('status_changed', 'Status Changed'),
    ]
    
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='order_activities')
    description = models.TextField()
    
    # Additional metadata
    previous_status = models.CharField(max_length=20, blank=True, null=True)
    new_status = models.CharField(max_length=20, blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)  # Store additional data
    
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order', '-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['activity_type', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.order.order_number} - {self.activity_type} by {self.user.get_full_name()}"

class OrderComment(models.Model):
    """
    Comments and notes on orders for communication between departments
    """
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    comment = models.TextField()
    is_internal = models.BooleanField(default=False)  # Internal comments not visible to requester
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Comment on {self.order.order_number} by {self.user.get_full_name()}"

class OrderNotification(models.Model):
    """
    System notifications for order workflow events
    """
    NOTIFICATION_TYPES = [
        ('approval_needed', 'Approval Needed'),
        ('approved', 'Order Approved'),
        ('rejected', 'Order Rejected'),
        ('revision_requested', 'Revision Requested'),
        ('completed', 'Order Completed'),
        ('overdue', 'Order Overdue'),
    ]
    
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='notifications')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='order_notifications')
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', '-created_at']),
        ]
    
    def __str__(self):
        return f"Notification for {self.recipient.get_full_name()} - {self.title}"