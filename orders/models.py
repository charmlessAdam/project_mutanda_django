from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from decimal import Decimal

User = get_user_model()

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
        ('pending', 'Pending Admin Approval'),
        ('approved_by_admin', 'Approved by Admin - Pending Finance'),
        ('approved_by_finance', 'Fully Approved'),
        ('rejected', 'Rejected'),
        ('revision_requested_by_admin', 'Revision Requested by Admin'),
        ('revision_requested_by_finance', 'Revision Requested by Finance'),
        ('revision_in_progress', 'Being Revised by Requester'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Order identification
    order_number = models.CharField(max_length=20, unique=True, db_index=True)
    
    # Order details
    order_type = models.CharField(max_length=20, choices=ORDER_TYPES)
    title = models.CharField(max_length=200)
    description = models.TextField()
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit = models.CharField(max_length=50, default='pieces')
    urgency = models.CharField(max_length=10, choices=URGENCY_LEVELS, default='medium')
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    supplier = models.CharField(max_length=200, blank=True, null=True)
    
    # Request information
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='requested_orders')
    request_date = models.DateTimeField(auto_now_add=True)
    
    # Status tracking
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending')
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
        return self.status in ['pending', 'approved_by_admin']
    
    @property
    def needs_revision(self):
        return self.status in ['revision_requested_by_admin', 'revision_requested_by_finance', 'revision_in_progress']
    
    @property
    def next_approver_role(self):
        if self.status == 'pending':
            return 'admin'
        elif self.status == 'approved_by_admin':
            return 'finance_manager'
        return None

class OrderApproval(models.Model):
    APPROVAL_STAGES = [
        ('admin', 'Admin Approval'),
        ('finance', 'Finance Approval'),
    ]
    
    APPROVAL_ACTIONS = [
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('revision_requested', 'Revision Requested'),
    ]
    
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='approvals')
    stage = models.CharField(max_length=10, choices=APPROVAL_STAGES)
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
        ('admin_approved', 'Admin Approved'),
        ('admin_rejected', 'Admin Rejected'),
        ('finance_approved', 'Finance Approved'),
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