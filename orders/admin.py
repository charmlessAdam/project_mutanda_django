from django.contrib import admin
from django.utils.html import format_html
from .models import Order, OrderItem, OrderApproval, OrderActivity, OrderComment, OrderNotification, QuoteOption, QuoteOptionItem

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'order_number', 'title', 'order_type', 'urgency', 
        'status_display', 'requested_by', 'estimated_cost', 'request_date'
    ]
    list_filter = ['order_type', 'status', 'urgency', 'request_date']
    search_fields = ['order_number', 'title', 'description', 'requested_by__username']
    readonly_fields = ['order_number', 'request_date', 'created_at', 'updated_at']
    ordering = ['-request_date']
    
    fieldsets = (
        ('Order Information', {
            'fields': ('order_number', 'order_type', 'title', 'description')
        }),
        ('Requirements', {
            'fields': ('quantity', 'unit', 'urgency', 'estimated_cost', 'supplier')
        }),
        ('Request Details', {
            'fields': ('requested_by', 'request_date', 'status', 'rejection_reason')
        }),
        ('Completion', {
            'fields': ('completion_date',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def status_display(self, obj):
        colors = {
            'pending': '#f59e0b',
            'approved_by_admin': '#3b82f6',
            'approved_by_finance': '#10b981',
            'rejected': '#ef4444',
            'completed': '#6b7280',
            'cancelled': '#6b7280'
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )
    status_display.short_description = 'Status'

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ['item_name', 'is_custom_item', 'quantity', 'unit', 'estimated_cost']
    readonly_fields = []

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'order', 'item_name', 'is_custom_item', 'quantity', 'unit', 'estimated_cost']
    list_filter = ['is_custom_item', 'unit']
    search_fields = ['item_name', 'order__order_number']
    ordering = ['order', 'id']

@admin.register(OrderApproval)
class OrderApprovalAdmin(admin.ModelAdmin):
    list_display = ['order', 'stage', 'action', 'approver', 'created_at']
    list_filter = ['stage', 'action', 'created_at']
    search_fields = ['order__order_number', 'approver__username', 'notes']
    readonly_fields = ['created_at']
    ordering = ['-created_at']

@admin.register(OrderActivity)
class OrderActivityAdmin(admin.ModelAdmin):
    list_display = ['order', 'activity_type', 'user', 'description_short', 'created_at']
    list_filter = ['activity_type', 'created_at']
    search_fields = ['order__order_number', 'user__username', 'description']
    readonly_fields = ['created_at', 'ip_address', 'user_agent']
    ordering = ['-created_at']
    
    def description_short(self, obj):
        return obj.description[:50] + '...' if len(obj.description) > 50 else obj.description
    description_short.short_description = 'Description'

@admin.register(OrderComment)
class OrderCommentAdmin(admin.ModelAdmin):
    list_display = ['order', 'user', 'comment_short', 'is_internal', 'created_at']
    list_filter = ['is_internal', 'created_at']
    search_fields = ['order__order_number', 'user__username', 'comment']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    
    def comment_short(self, obj):
        return obj.comment[:50] + '...' if len(obj.comment) > 50 else obj.comment
    comment_short.short_description = 'Comment'

@admin.register(OrderNotification)
class OrderNotificationAdmin(admin.ModelAdmin):
    list_display = ['order', 'recipient', 'notification_type', 'title', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['order__order_number', 'recipient__username', 'title', 'message']
    readonly_fields = ['created_at', 'read_at']
    ordering = ['-created_at']

class QuoteOptionItemInline(admin.TabularInline):
    model = QuoteOptionItem
    extra = 0
    fields = ['order_item', 'unit_price', 'total_price', 'availability', 'notes']
    readonly_fields = []

@admin.register(QuoteOption)
class QuoteOptionAdmin(admin.ModelAdmin):
    list_display = ['order', 'supplier_name', 'quoted_amount', 'is_recommended', 'is_selected', 'submitted_at']
    list_filter = ['is_recommended', 'is_selected', 'submitted_at']
    search_fields = ['order__order_number', 'supplier_name', 'notes']
    readonly_fields = ['submitted_at']
    ordering = ['-submitted_at']
    inlines = [QuoteOptionItemInline]

@admin.register(QuoteOptionItem)
class QuoteOptionItemAdmin(admin.ModelAdmin):
    list_display = ['quote_option', 'order_item', 'unit_price', 'total_price', 'availability']
    list_filter = ['availability']
    search_fields = ['quote_option__supplier_name', 'order_item__item_name']
    ordering = ['quote_option', 'order_item']