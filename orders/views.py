from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.db.models import Q, Count, Sum
from rest_framework.filters import OrderingFilter, SearchFilter
import uuid
from datetime import datetime
from decimal import Decimal

from .models import Order, OrderItem, OrderApproval, OrderActivity, OrderComment, OrderNotification, QuoteOption, QuoteOptionItem
from .serializers import (
    OrderListSerializer, OrderDetailSerializer, OrderCreateSerializer,
    OrderApprovalActionSerializer, OrderCommentCreateSerializer,
    OrderNotificationSerializer, SuperAdminOrderDetailSerializer,
    SubmitQuotesSerializer, QuoteOptionSerializer
)

User = get_user_model()

class OrderPermission(permissions.BasePermission):
    """
    Custom permission for order management
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Super admin can do everything
        if request.user.role == 'super_admin':
            return True

        # Allow all authenticated users to view their own orders and create new ones
        if view.action in ['list', 'create', 'retrieve', 'dashboard_stats']:
            return True

        # Manager can approve initial orders and quotes
        if view.action in ['manager_approve', 'approve_quote', 'manager_dashboard']:
            return request.user.role == 'manager'

        # Procurement can submit quotes
        if view.action in ['submit_quote', 'procurement_dashboard']:
            return request.user.role == 'procurement'

        # Finance managers can complete payments
        if view.action in ['complete_payment', 'finance_dashboard']:
            return request.user.role == 'finance_manager'

        # Veterinary users can submit revisions
        if view.action in ['submit_revision']:
            return request.user.role in ['head_veterinary', 'veterinary']

        # Keep old approve/finance_approve for backward compatibility
        if view.action in ['approve', 'reject', 'admin_dashboard']:
            return request.user.role in ['admin', 'manager']

        if view.action in ['finance_approve', 'finance_reject']:
            return request.user.role == 'finance_manager'

        return False
    
    def has_object_permission(self, request, view, obj):
        # Super admin can do everything
        if request.user.role == 'super_admin':
            return True

        # Users can view their own orders
        if view.action == 'retrieve' and obj.requested_by == request.user:
            return True

        # Admins and managers can access all orders
        if request.user.role in ['admin', 'manager']:
            return True

        # Procurement can view orders that need quotes
        if request.user.role == 'procurement' and obj.status == 'approved_by_manager':
            return True

        # Finance managers can view orders ready for payment
        if request.user.role == 'finance_manager' and obj.status == 'quote_approved_by_manager':
            return True

        # Submit revision permissions - original requester or veterinary users for medicine orders
        if view.action == 'submit_revision':
            can_revise = (
                obj.requested_by == request.user or
                (request.user.role in ['head_veterinary', 'veterinary'] and obj.order_type == 'medicine')
            )
            return can_revise

        return False

def log_order_activity(order, user, activity_type, description, request=None, **metadata):
    """Helper function to log order activities with full audit trail"""
    
    def convert_decimals(obj):
        """Recursively convert Decimal objects to floats for JSON serialization"""
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, dict):
            return {key: convert_decimals(value) for key, value in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [convert_decimals(item) for item in obj]
        else:
            return obj
    
    # Convert Decimal objects to float for JSON serialization
    serializable_metadata = {}
    for key, value in metadata.items():
        serializable_metadata[key] = convert_decimals(value)
    
    activity_data = {
        'order': order,
        'user': user,
        'activity_type': activity_type,
        'description': description,
        'metadata': serializable_metadata
    }
    
    if request:
        # Get client IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0]
        else:
            ip_address = request.META.get('REMOTE_ADDR')
        
        activity_data.update({
            'ip_address': ip_address,
            'user_agent': request.META.get('HTTP_USER_AGENT', '')[:500]  # Limit length
        })
    
    return OrderActivity.objects.create(**activity_data)

def create_notification(order, recipient, notification_type, title, message):
    """Helper function to create notifications"""
    return OrderNotification.objects.create(
        order=order,
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        message=message
    )

def generate_order_number(order_type):
    """Generate unique order number"""
    prefix = order_type.upper()[:3]
    year = datetime.now().year

    # Get highest number for this prefix and year to avoid duplicates
    existing_orders = Order.objects.filter(
        order_number__startswith=f"{prefix}-{year}-"
    ).order_by('-order_number').values_list('order_number', flat=True)

    if existing_orders:
        # Extract number from last order (format: PREFIX-YEAR-NNNN)
        last_number = int(existing_orders[0].split('-')[-1])
        count = last_number + 1
    else:
        count = 1

    # Try to create unique number, increment if collision occurs
    max_attempts = 100
    for attempt in range(max_attempts):
        order_number = f"{prefix}-{year}-{count:04d}"
        if not Order.objects.filter(order_number=order_number).exists():
            return order_number
        count += 1

    # Fallback: use timestamp if we can't find unique number
    import time
    timestamp = int(time.time() * 1000) % 10000
    return f"{prefix}-{year}-{timestamp:04d}"

class OrderViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing orders with full workflow support
    """
    permission_classes = [OrderPermission]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['order_number', 'title', 'description']
    ordering_fields = ['created_at', 'request_date', 'estimated_cost']
    ordering = ['-created_at']
    
    def get_queryset(self):
        user = self.request.user
        
        # Base queryset based on user role
        if user.role == 'super_admin':
            # Super admin can see all orders
            queryset = Order.objects.all().select_related('requested_by')
        elif user.role in ['admin', 'manager']:
            # Admins can see all orders in their domain
            queryset = Order.objects.all().select_related('requested_by')
        elif user.role == 'finance_manager':
            # Finance managers see orders that need finance approval or are approved
            queryset = Order.objects.filter(
                Q(status__in=['approved_by_admin', 'approved_by_finance', 'completed']) |
                Q(requested_by=user)
            ).select_related('requested_by')
        else:
            # Regular users see only their own orders
            queryset = Order.objects.filter(requested_by=user).select_related('requested_by')
        
        # Apply additional filters from query params
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
            
        order_type = self.request.query_params.get('order_type')
        if order_type:
            queryset = queryset.filter(order_type=order_type)
            
        urgency = self.request.query_params.get('urgency')
        if urgency:
            queryset = queryset.filter(urgency=urgency)
            
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'create':
            return OrderCreateSerializer
        elif self.action == 'retrieve':
            # Use superadmin serializer for detailed view if user is superadmin
            if self.request.user.role == 'super_admin':
                return SuperAdminOrderDetailSerializer
            return OrderDetailSerializer
        return OrderListSerializer
    
    def perform_create(self, serializer):
        """Create order with activity logging"""
        with transaction.atomic():
            # Generate order number
            order_number = generate_order_number(serializer.validated_data['order_type'])
            
            # Create order
            order = serializer.save(
                requested_by=self.request.user,
                order_number=order_number
            )
            
            # Log creation activity
            log_order_activity(
                order=order,
                user=self.request.user,
                activity_type='created',
                description=f"Order {order.order_number} created for {order.title}",
                request=self.request,
                order_data=serializer.validated_data
            )
            
            # Create notifications for managers (NEW WORKFLOW)
            managers = User.objects.filter(role__in=['manager', 'super_admin'])
            for manager in managers:
                create_notification(
                    order=order,
                    recipient=manager,
                    notification_type='approval_needed',
                    title=f'New Order Requires Approval: {order.order_number}',
                    message=f'{order.requested_by.get_full_name()} has requested approval for {order.title} (Estimated cost: ${order.estimated_cost})'
                )
    
    def create(self, request, *args, **kwargs):
        """Override create to return proper serialized response"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        # Return the created order with proper serialization including user details
        instance = serializer.instance
        response_serializer = OrderDetailSerializer(instance, context={'request': request})
        headers = self.get_success_headers(response_serializer.data)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Admin approval action"""
        order = self.get_object()
        serializer = OrderApprovalActionSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        if order.status != 'pending':
            return Response(
                {'error': 'Order is not in pending status'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        action_type = serializer.validated_data['action']
        notes = serializer.validated_data.get('notes', '')
        
        with transaction.atomic():
            if action_type == 'approved':
                # Create or update approval record
                approval, created = OrderApproval.objects.update_or_create(
                    order=order,
                    stage='admin',
                    defaults={
                        'approver': request.user,
                        'action': 'approved',
                        'notes': notes,
                        'requires_revision': False,
                        'revision_completed': False
                    }
                )
                
                # Update order status
                old_status = order.status
                order.status = 'approved_by_admin'
                order.save()
                
                # Log activity
                log_order_activity(
                    order=order,
                    user=request.user,
                    activity_type='admin_approved',
                    description=f"Order approved by admin {request.user.get_full_name()}",
                    request=request,
                    previous_status=old_status,
                    new_status=order.status,
                    notes=notes
                )
                
                # Notify finance managers
                finance_managers = User.objects.filter(role='finance_manager')
                for manager in finance_managers:
                    create_notification(
                        order=order,
                        recipient=manager,
                        notification_type='approval_needed',
                        title=f'Finance Approval Needed: {order.order_number}',
                        message=f'Admin-approved order for {order.title} needs finance approval (Cost: ${order.estimated_cost})'
                    )
                
                # Notify requester
                create_notification(
                    order=order,
                    recipient=order.requested_by,
                    notification_type='approved',
                    title=f'Order Admin Approved: {order.order_number}',
                    message=f'Your order for {order.title} has been approved by admin and is now pending finance approval'
                )
                
            elif action_type == 'rejected':
                # Create or update rejection record
                approval, created = OrderApproval.objects.update_or_create(
                    order=order,
                    stage='admin',
                    defaults={
                        'approver': request.user,
                        'action': 'rejected',
                        'notes': notes,
                        'requires_revision': False,
                        'revision_completed': False
                    }
                )
                
                # Update order
                old_status = order.status
                order.status = 'rejected'
                order.rejection_reason = notes
                order.save()
                
                # Log activity
                log_order_activity(
                    order=order,
                    user=request.user,
                    activity_type='admin_rejected',
                    description=f"Order rejected by admin {request.user.get_full_name()}: {notes}",
                    request=request,
                    previous_status=old_status,
                    new_status=order.status,
                    rejection_reason=notes
                )
                
                # Notify requester
                create_notification(
                    order=order,
                    recipient=order.requested_by,
                    notification_type='rejected',
                    title=f'Order Rejected: {order.order_number}',
                    message=f'Your order for {order.title} has been rejected by admin. Reason: {notes}'
                )
            
            elif action_type == 'revision_requested':
                # Update order with revision information
                old_status = order.status
                order.status = 'revision_requested_by_admin'
                order.revision_reason = notes
                order.revision_requested_by = request.user
                order.revision_requested_at = timezone.now()
                order.save()
                
                # Create or update revision request approval record
                approval, created = OrderApproval.objects.update_or_create(
                    order=order,
                    stage='admin',
                    defaults={
                        'approver': request.user,
                        'action': 'revision_requested',
                        'notes': notes,
                        'requires_revision': True,
                        'revision_completed': False
                    }
                )
                
                # Log activity
                log_order_activity(
                    order=order,
                    user=request.user,
                    activity_type='revision_requested',
                    description=f"Revision requested by admin {request.user.get_full_name()}: {notes}",
                    request=request,
                    previous_status=old_status,
                    new_status=order.status,
                    revision_notes=notes
                )
                
                # Notify requester
                create_notification(
                    order=order,
                    recipient=order.requested_by,
                    notification_type='revision_requested',
                    title=f'Order Revision Required: {order.order_number}',
                    message=f'Admin has requested revisions to your order for {order.title}. Notes: {notes}'
                )
        
        return Response({'message': f'Order {action_type} successfully'})

    @action(detail=True, methods=['post'])
    def manager_approve(self, request, pk=None):
        """Manager initial approval action - NEW WORKFLOW"""
        order = self.get_object()
        serializer = OrderApprovalActionSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        if order.status != 'pending':
            return Response(
                {'error': 'Order is not in pending status'},
                status=status.HTTP_400_BAD_REQUEST
            )

        action_type = serializer.validated_data['action']
        notes = serializer.validated_data.get('notes', '')

        with transaction.atomic():
            if action_type == 'approved':
                # Create approval record
                approval, created = OrderApproval.objects.update_or_create(
                    order=order,
                    stage='manager_initial',
                    defaults={
                        'approver': request.user,
                        'action': 'approved',
                        'notes': notes,
                        'requires_revision': False,
                        'revision_completed': False
                    }
                )

                # Update order status
                old_status = order.status
                order.status = 'approved_by_manager'
                order.save()

                # Log activity
                log_order_activity(
                    order=order,
                    user=request.user,
                    activity_type='manager_approved',
                    description=f"Order approved by manager {request.user.get_full_name()}",
                    request=request,
                    previous_status=old_status,
                    new_status=order.status,
                    notes=notes
                )

                # Notify procurement team
                procurement_users = User.objects.filter(role='procurement')
                for proc_user in procurement_users:
                    create_notification(
                        order=order,
                        recipient=proc_user,
                        notification_type='approval_needed',
                        title=f'Quote Needed: {order.order_number}',
                        message=f'Manager-approved order for {order.title} needs procurement quote (Estimated: ${order.estimated_cost})'
                    )

                # Notify requester
                create_notification(
                    order=order,
                    recipient=order.requested_by,
                    notification_type='approved',
                    title=f'Order Approved by Manager: {order.order_number}',
                    message=f'Your order for {order.title} has been approved by manager and sent to procurement'
                )

            elif action_type == 'rejected':
                # Create rejection record
                approval, created = OrderApproval.objects.update_or_create(
                    order=order,
                    stage='manager_initial',
                    defaults={
                        'approver': request.user,
                        'action': 'rejected',
                        'notes': notes,
                        'requires_revision': False,
                        'revision_completed': False
                    }
                )

                # Update order
                old_status = order.status
                order.status = 'rejected'
                order.rejection_reason = notes
                order.save()

                # Log activity
                log_order_activity(
                    order=order,
                    user=request.user,
                    activity_type='manager_rejected',
                    description=f"Order rejected by manager {request.user.get_full_name()}: {notes}",
                    request=request,
                    previous_status=old_status,
                    new_status=order.status,
                    rejection_reason=notes
                )

                # Notify requester
                create_notification(
                    order=order,
                    recipient=order.requested_by,
                    notification_type='rejected',
                    title=f'Order Rejected: {order.order_number}',
                    message=f'Your order for {order.title} has been rejected by manager. Reason: {notes}'
                )

            elif action_type == 'revision_requested':
                # Update order with revision information
                old_status = order.status
                order.status = 'revision_requested_by_manager'
                order.revision_reason = notes
                order.revision_requested_by = request.user
                order.revision_requested_at = timezone.now()
                order.save()

                # Create revision request approval record
                approval, created = OrderApproval.objects.update_or_create(
                    order=order,
                    stage='manager_initial',
                    defaults={
                        'approver': request.user,
                        'action': 'revision_requested',
                        'notes': notes,
                        'requires_revision': True,
                        'revision_completed': False
                    }
                )

                # Log activity
                log_order_activity(
                    order=order,
                    user=request.user,
                    activity_type='revision_requested',
                    description=f"Revision requested by manager {request.user.get_full_name()}: {notes}",
                    request=request,
                    previous_status=old_status,
                    new_status=order.status,
                    revision_notes=notes
                )

                # Notify requester
                create_notification(
                    order=order,
                    recipient=order.requested_by,
                    notification_type='revision_requested',
                    title=f'Order Revision Required: {order.order_number}',
                    message=f'Manager has requested revisions to your order for {order.title}. Notes: {notes}'
                )

        return Response({'message': f'Order {action_type} by manager successfully'})

    @action(detail=True, methods=['post'])
    def submit_quote(self, request, pk=None):
        """Procurement submits multiple quote options - NEW WORKFLOW"""
        order = self.get_object()

        # Allow quote submission/update when manager approved OR quotes already submitted (but not yet approved)
        if order.status not in ['approved_by_manager', 'procurement_quote_submitted']:
            return Response(
                {'error': 'Order must be manager-approved before quote submission'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate quote data
        serializer = SubmitQuotesSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # Delete any existing quote options for this order
            order.quote_options.all().delete()

            # Create new quote options
            quotes_data = serializer.validated_data['quotes']
            created_quotes = []
            recommended_quote = None

            for quote_data in quotes_data:
                # Extract item_quotes data before creating QuoteOption
                item_quotes_data = quote_data.pop('item_quotes', [])

                quote = QuoteOption.objects.create(
                    order=order,
                    submitted_by=request.user,
                    **quote_data
                )
                created_quotes.append(quote)

                # Create item-level quotes if provided
                if item_quotes_data:
                    for item_quote in item_quotes_data:
                        is_not_available = item_quote.get('is_not_available', False)
                        QuoteOptionItem.objects.create(
                            quote_option=quote,
                            order_item_id=item_quote['order_item_id'],
                            unit_price=item_quote.get('unit_price', Decimal('0.01')) if not is_not_available else Decimal('0.01'),
                            total_price=item_quote.get('total_price', Decimal('0.01')) if not is_not_available else Decimal('0.01'),
                            availability=item_quote.get('availability', ''),
                            notes=item_quote.get('notes', ''),
                            is_not_available=is_not_available
                        )

                if quote.is_recommended:
                    recommended_quote = quote

            # Update order status
            old_status = order.status
            order.quote_submitted_by = request.user
            order.quote_submitted_at = timezone.now()
            order.status = 'procurement_quote_submitted'
            order.save()

            # Create procurement approval record
            OrderApproval.objects.update_or_create(
                order=order,
                stage='procurement',
                defaults={
                    'approver': request.user,
                    'action': 'approved',
                    'notes': f'{len(created_quotes)} quote options submitted',
                    'requires_revision': False,
                    'revision_completed': False
                }
            )

            # Log activity
            quote_summary = ', '.join([f"${q.quoted_amount} from {q.supplier_name}" for q in created_quotes[:3]])
            if len(created_quotes) > 3:
                quote_summary += f" and {len(created_quotes) - 3} more"

            log_order_activity(
                order=order,
                user=request.user,
                activity_type='quote_submitted',
                description=f"Quotes submitted by {request.user.get_full_name()} - {quote_summary}. Recommended: ${recommended_quote.quoted_amount} from {recommended_quote.supplier_name}",
                request=request,
                previous_status=old_status,
                new_status=order.status,
                quote_count=len(created_quotes),
                recommended_supplier=recommended_quote.supplier_name if recommended_quote else None,
                recommended_amount=float(recommended_quote.quoted_amount) if recommended_quote else None
            )

            # Notify managers
            managers = User.objects.filter(role='manager')
            for manager in managers:
                create_notification(
                    order=order,
                    recipient=manager,
                    notification_type='approval_needed',
                    title=f'Quote Approval Needed: {order.order_number}',
                    message=f'{len(created_quotes)} quotes submitted for {order.title}. Recommended: ${recommended_quote.quoted_amount} from {recommended_quote.supplier_name}'
                )

        # Return created quotes
        return Response({
            'message': 'Quotes submitted successfully',
            'quotes': QuoteOptionSerializer(created_quotes, many=True).data
        })

    @action(detail=True, methods=['post'])
    def approve_quote(self, request, pk=None):
        """Manager selects and approves a quote option - NEW WORKFLOW"""
        order = self.get_object()

        if order.status != 'procurement_quote_submitted':
            return Response(
                {'error': 'Order must have submitted quotes for approval'},
                status=status.HTTP_400_BAD_REQUEST
            )

        action_type = request.data.get('action')
        selected_quote_id = request.data.get('selected_quote_id')
        notes = request.data.get('notes', '')

        if not action_type:
            return Response(
                {'error': 'Action is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            if action_type == 'approved':
                # Validate selected quote
                if not selected_quote_id:
                    return Response(
                        {'error': 'selected_quote_id is required when approving'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                try:
                    selected_quote = QuoteOption.objects.get(id=selected_quote_id, order=order)
                except QuoteOption.DoesNotExist:
                    return Response(
                        {'error': 'Selected quote not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )

                # Mark selected quote
                order.quote_options.update(is_selected=False)  # Clear all selections
                selected_quote.is_selected = True
                selected_quote.save()

                # Update order with selected quote details
                order.quote_amount = selected_quote.quoted_amount
                order.quote_supplier = selected_quote.supplier_name
                order.quote_notes = selected_quote.notes or ''
                order.estimated_cost = selected_quote.quoted_amount  # Update estimated_cost to the actual quote price

                # Create quote approval record
                approval, created = OrderApproval.objects.update_or_create(
                    order=order,
                    stage='manager_quote',
                    defaults={
                        'approver': request.user,
                        'action': 'approved',
                        'notes': notes,
                        'requires_revision': False,
                        'revision_completed': False
                    }
                )

                # Update order status
                old_status = order.status
                order.status = 'quote_approved_by_manager'
                order.save()

                # Log activity
                log_order_activity(
                    order=order,
                    user=request.user,
                    activity_type='quote_approved',
                    description=f"Quote approved by manager {request.user.get_full_name()} - Selected ${selected_quote.quoted_amount} from {selected_quote.supplier_name}",
                    request=request,
                    previous_status=old_status,
                    new_status=order.status,
                    selected_quote_id=selected_quote.id,
                    selected_supplier=selected_quote.supplier_name,
                    selected_amount=float(selected_quote.quoted_amount),
                    notes=notes
                )

                # Notify finance team
                finance_users = User.objects.filter(role='finance_manager')
                for fin_user in finance_users:
                    create_notification(
                        order=order,
                        recipient=fin_user,
                        notification_type='approval_needed',
                        title=f'Payment Needed: {order.order_number}',
                        message=f'Quote approved for {order.title} - ${selected_quote.quoted_amount} to {selected_quote.supplier_name}'
                    )

                # Notify requester
                create_notification(
                    order=order,
                    recipient=order.requested_by,
                    notification_type='approved',
                    title=f'Quote Approved: {order.order_number}',
                    message=f'Quote for {order.title} approved - ${selected_quote.quoted_amount} from {selected_quote.supplier_name}. Sent to finance for payment.'
                )

                # Notify procurement
                if order.quote_submitted_by:
                    create_notification(
                        order=order,
                        recipient=order.quote_submitted_by,
                        notification_type='approved',
                        title=f'Quote Approved: {order.order_number}',
                        message=f'Your quote from {selected_quote.supplier_name} (${selected_quote.quoted_amount}) was selected and approved.'
                    )

            elif action_type == 'rejected':
                # Reject all quotes and send back to procurement
                old_status = order.status
                order.status = 'approved_by_manager'  # Back to procurement
                order.save()

                # Log activity
                log_order_activity(
                    order=order,
                    user=request.user,
                    activity_type='quote_rejected',
                    description=f"All quotes rejected by manager {request.user.get_full_name()}: {notes}",
                    request=request,
                    previous_status=old_status,
                    new_status=order.status,
                    rejection_reason=notes
                )

                # Notify procurement
                if order.quote_submitted_by:
                    create_notification(
                        order=order,
                        recipient=order.quote_submitted_by,
                        notification_type='revision_requested',
                        title=f'Quotes Rejected: {order.order_number}',
                        message=f'All quotes for {order.title} were rejected. Please submit new quotes. Reason: {notes}'
                    )

        return Response({'message': f'Quote {action_type} successfully'})

    @action(detail=True, methods=['post'])
    def approve_mixed_quote(self, request, pk=None):
        """Manager selects individual items from different quotes - MIXED QUOTE APPROVAL"""
        order = self.get_object()

        if order.status != 'procurement_quote_submitted':
            return Response(
                {'error': 'Order must have submitted quotes for approval'},
                status=status.HTTP_400_BAD_REQUEST
            )

        selected_item_quote_ids = request.data.get('selected_item_quotes', [])

        if not selected_item_quote_ids or len(selected_item_quote_ids) == 0:
            return Response(
                {'error': 'selected_item_quotes is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            # Validate all selected item quotes exist and belong to this order
            selected_items = QuoteOptionItem.objects.filter(
                id__in=selected_item_quote_ids,
                quote_option__order=order
            ).select_related('quote_option', 'order_item')

            if selected_items.count() != len(selected_item_quote_ids):
                return Response(
                    {'error': 'One or more selected item quotes not found'},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Group selected items by quote option
            quote_selections = {}
            total_amount = Decimal('0.00')

            for item_quote in selected_items:
                quote_id = item_quote.quote_option.id
                if quote_id not in quote_selections:
                    quote_selections[quote_id] = {
                        'quote': item_quote.quote_option,
                        'items': []
                    }
                quote_selections[quote_id]['items'].append(item_quote)
                total_amount += item_quote.total_price

            # Mark which quote options are selected (partial or full)
            order.quote_options.update(is_selected=False)
            for quote_id in quote_selections.keys():
                quote_selections[quote_id]['quote'].is_selected = True
                quote_selections[quote_id]['quote'].save()

            # Update order with aggregated quote details
            suppliers = [qs['quote'].supplier_name for qs in quote_selections.values()]
            order.quote_amount = total_amount
            order.quote_supplier = ', '.join(suppliers) if len(suppliers) > 1 else suppliers[0]
            order.quote_notes = f"Mixed quote: {len(selected_item_quote_ids)} items from {len(suppliers)} supplier(s)"
            order.estimated_cost = total_amount  # Update estimated_cost to match total mixed quote amount

            # Create quote approval record
            approval_notes = f"Approved mixed quote from {len(suppliers)} supplier(s): {', '.join(suppliers)}"
            OrderApproval.objects.update_or_create(
                order=order,
                stage='manager_quote',
                defaults={
                    'approver': request.user,
                    'action': 'approved',
                    'notes': approval_notes,
                    'requires_revision': False,
                    'revision_completed': False
                }
            )

            # Update order status
            old_status = order.status
            order.status = 'quote_approved_by_manager'
            order.save()

            # Log activity
            log_order_activity(
                order=order,
                user=request.user,
                activity_type='quote_approved',
                description=f"Mixed quote approved by manager {request.user.get_full_name()} - ${total_amount} from {len(suppliers)} suppliers: {', '.join(suppliers)}",
                request=request,
                previous_status=old_status,
                new_status=order.status,
                selected_quote_ids=list(quote_selections.keys()),
                selected_suppliers=suppliers,
                selected_amount=float(total_amount),
                notes=approval_notes
            )

            # Notify finance team
            finance_users = User.objects.filter(role='finance_manager')
            for fin_user in finance_users:
                create_notification(
                    order=order,
                    recipient=fin_user,
                    notification_type='approval_needed',
                    title=f'Payment Needed: {order.order_number}',
                    message=f'Mixed quote approved for {order.title} - ${total_amount} from {len(suppliers)} suppliers'
                )

            # Notify requester
            create_notification(
                order=order,
                recipient=order.requested_by,
                notification_type='approved',
                title=f'Quote Approved: {order.order_number}',
                message=f'Mixed quote for {order.title} approved - ${total_amount} from {len(suppliers)} suppliers. Sent to finance for payment.'
            )

        return Response({'message': 'Mixed quote approved successfully', 'total_amount': str(total_amount)})

    @action(detail=True, methods=['post'])
    def complete_payment(self, request, pk=None):
        """Finance completes payment - NEW WORKFLOW"""
        order = self.get_object()

        if order.status != 'quote_approved_by_manager':
            return Response(
                {'error': 'Order must have approved quote before payment'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get payment data
        payment_amount = request.data.get('payment_amount')
        payment_method = request.data.get('payment_method')
        payment_reference = request.data.get('payment_reference')
        payment_notes = request.data.get('payment_notes', '')

        if not payment_amount:
            return Response(
                {'error': 'Payment amount is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            # Update order with payment details
            old_status = order.status
            order.payment_amount = payment_amount
            order.payment_method = payment_method
            order.payment_reference = payment_reference
            order.payment_notes = payment_notes
            order.payment_completed_by = request.user
            order.payment_completed_at = timezone.now()
            order.status = 'payment_completed'
            order.save()

            # Create finance approval record
            OrderApproval.objects.update_or_create(
                order=order,
                stage='finance',
                defaults={
                    'approver': request.user,
                    'action': 'approved',
                    'notes': payment_notes,
                    'requires_revision': False,
                    'revision_completed': False
                }
            )

            # Log activity
            log_order_activity(
                order=order,
                user=request.user,
                activity_type='payment_completed',
                description=f"Payment completed by {request.user.get_full_name()} - ${payment_amount}",
                request=request,
                previous_status=old_status,
                new_status=order.status,
                payment_amount=float(payment_amount),
                payment_method=payment_method,
                payment_reference=payment_reference
            )

            # Notify requester
            create_notification(
                order=order,
                recipient=order.requested_by,
                notification_type='completed',
                title=f'Payment Completed: {order.order_number}',
                message=f'Payment of ${payment_amount} completed for {order.title}. Reference: {payment_reference}'
            )

            # Notify procurement
            if order.quote_submitted_by:
                create_notification(
                    order=order,
                    recipient=order.quote_submitted_by,
                    notification_type='completed',
                    title=f'Order Payment Completed: {order.order_number}',
                    message=f'Payment completed for {order.title} - ${payment_amount} to {order.quote_supplier}'
                )

        return Response({'message': 'Payment completed successfully'})

    @action(detail=True, methods=['post'])
    def finance_approve(self, request, pk=None):
        """Finance manager approval action"""
        order = self.get_object()
        serializer = OrderApprovalActionSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        if order.status != 'approved_by_admin':
            return Response(
                {'error': 'Order must be admin-approved first'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        action_type = serializer.validated_data['action']
        notes = serializer.validated_data.get('notes', '')
        
        with transaction.atomic():
            if action_type == 'approved':
                # Create or update finance approval
                approval, created = OrderApproval.objects.update_or_create(
                    order=order,
                    stage='finance',
                    defaults={
                        'approver': request.user,
                        'action': 'approved',
                        'notes': notes,
                        'requires_revision': False,
                        'revision_completed': False
                    }
                )
                
                # Update order status
                old_status = order.status
                order.status = 'approved_by_finance'
                order.save()
                
                # Log activity
                log_order_activity(
                    order=order,
                    user=request.user,
                    activity_type='finance_approved',
                    description=f"Order fully approved by finance {request.user.get_full_name()}",
                    request=request,
                    previous_status=old_status,
                    new_status=order.status,
                    notes=notes
                )
                
                # Notify requester and relevant staff
                create_notification(
                    order=order,
                    recipient=order.requested_by,
                    notification_type='approved',
                    title=f'Order Fully Approved: {order.order_number}',
                    message=f'Your order for {order.title} has been fully approved and can now be processed'
                )
                
            elif action_type == 'rejected':
                # Create or update finance rejection
                approval, created = OrderApproval.objects.update_or_create(
                    order=order,
                    stage='finance',
                    defaults={
                        'approver': request.user,
                        'action': 'rejected',
                        'notes': notes,
                        'requires_revision': False,
                        'revision_completed': False
                    }
                )
                
                # Update order
                old_status = order.status
                order.status = 'rejected'
                order.rejection_reason = f"Finance rejection: {notes}"
                order.save()
                
                # Log activity
                log_order_activity(
                    order=order,
                    user=request.user,
                    activity_type='finance_rejected',
                    description=f"Order rejected by finance {request.user.get_full_name()}: {notes}",
                    request=request,
                    previous_status=old_status,
                    new_status=order.status,
                    rejection_reason=notes
                )
                
                # Notify requester
                create_notification(
                    order=order,
                    recipient=order.requested_by,
                    notification_type='rejected',
                    title=f'Order Rejected by Finance: {order.order_number}',
                    message=f'Your order for {order.title} has been rejected by finance. Reason: {notes}'
                )
                
            elif action_type == 'revision_requested':
                # Update order with revision information
                old_status = order.status
                order.status = 'revision_requested_by_finance'
                order.revision_reason = notes
                order.revision_requested_by = request.user
                order.revision_requested_at = timezone.now()
                order.save()
                
                # Create or update revision request approval record
                approval, created = OrderApproval.objects.update_or_create(
                    order=order,
                    stage='finance',
                    defaults={
                        'approver': request.user,
                        'action': 'revision_requested',
                        'notes': notes,
                        'requires_revision': True,
                        'revision_completed': False
                    }
                )
                
                # Log activity
                log_order_activity(
                    order=order,
                    user=request.user,
                    activity_type='revision_requested',
                    description=f"Revision requested by finance {request.user.get_full_name()}: {notes}",
                    request=request,
                    previous_status=old_status,
                    new_status=order.status,
                    revision_notes=notes
                )
                
                # Notify requester
                create_notification(
                    order=order,
                    recipient=order.requested_by,
                    notification_type='revision_requested',
                    title=f'Order Revision Required: {order.order_number}',
                    message=f'Finance has requested revisions to your order for {order.title}. Notes: {notes}'
                )
        
        return Response({'message': f'Order {action_type} by finance successfully'})
    
    @action(detail=True, methods=['post'])
    def add_comment(self, request, pk=None):
        """Add comment to order"""
        order = self.get_object()
        serializer = OrderCommentCreateSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        comment = serializer.save(order=order, user=request.user)
        
        # Log activity
        log_order_activity(
            order=order,
            user=request.user,
            activity_type='comment_added',
            description=f"Comment added by {request.user.get_full_name()}",
            request=request,
            comment=comment.comment,
            is_internal=comment.is_internal
        )
        
        return Response({'message': 'Comment added successfully'})
    
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Mark order as completed - finalize and move to history"""
        order = self.get_object()

        # Debug: Log user role
        print(f"DEBUG: User {request.user.username} with role '{request.user.role}' attempting to complete order {order.id}")

        # NEW WORKFLOW: Check for payment_completed status
        # OLD WORKFLOW: Check for approved_by_finance status (for backward compatibility)
        if order.status not in ['payment_completed', 'approved_by_finance']:
            return Response(
                {'error': 'Order must have payment completed before finalization'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            old_status = order.status
            order.status = 'completed'
            order.completion_date = timezone.now()
            order.save()
            
            # Log completion
            log_order_activity(
                order=order,
                user=request.user,
                activity_type='completed',
                description=f"Order completed by {request.user.get_full_name()}",
                request=request,
                previous_status=old_status,
                new_status=order.status
            )
            
            # Notify requester
            create_notification(
                order=order,
                recipient=order.requested_by,
                notification_type='completed',
                title=f'Order Completed: {order.order_number}',
                message=f'Your order for {order.title} has been completed successfully'
            )
        
        return Response({'message': 'Order marked as completed'})

    @action(detail=True, methods=['post'])
    def split_and_approve(self, request, pk=None):
        """Split order into multiple orders based on item groups and approve - NEW FEATURE"""
        try:
            order = self.get_object()

            # Debug logging
            print(f"DEBUG: split_and_approve called for order {order.id} by user {request.user.username}")
            print(f"DEBUG: Request data: {request.data}")

            # Only managers and super_admins can split orders
            if request.user.role not in ['manager', 'super_admin']:
                return Response(
                    {'error': 'Only managers can split orders'},
                    status=status.HTTP_403_FORBIDDEN
                )

            if order.status != 'pending':
                return Response(
                    {'error': 'Can only split orders that are pending manager approval'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            item_groups = request.data.get('item_groups', [])
            notes = request.data.get('notes', 'Order split by manager')

            print(f"DEBUG: item_groups: {item_groups}")
        except Exception as e:
            print(f"ERROR in split_and_approve initial validation: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {'error': f'Initial validation failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        if not item_groups or len(item_groups) < 1:
            return Response(
                {'error': 'Must provide at least one item group'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get all order items
        order_items = list(order.items.all())
        if not order_items:
            return Response(
                {'error': 'Order has no items to split'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate that all item IDs are valid and belong to this order
        all_item_ids = {item.id for item in order_items}
        provided_item_ids = set()
        for group in item_groups:
            provided_item_ids.update(group)

        if provided_item_ids != all_item_ids:
            return Response(
                {'error': 'Item groups must include all items exactly once'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                created_orders = []

                # If only one group, just approve the existing order
                if len(item_groups) == 1:
                    old_status = order.status
                    order.status = 'approved_by_manager'
                    order.save()

                    # Log activity
                    log_order_activity(
                        order=order,
                        user=request.user,
                        activity_type='manager_approved',
                        description=f"Order approved by manager {request.user.get_full_name()}",
                        request=request,
                        previous_status=old_status,
                        new_status=order.status
                    )

                    return Response({
                        'message': 'Order approved successfully',
                        'created_orders': [order.id]
                    })

                # Create a new order for each group
                for group_index, item_ids in enumerate(item_groups, 1):
                    # Get items for this group
                    group_items = [item for item in order_items if item.id in item_ids]

                    # Calculate total cost for this group
                    group_cost = sum(float(item.estimated_cost or 0) for item in group_items)

                    # Create title based on items
                    if len(group_items) == 1:
                        new_title = group_items[0].item_name
                    else:
                        new_title = f"Split Order {group_index}/{len(item_groups)} - {len(group_items)} items"

                    # Create new order with unique order number
                    new_order = Order.objects.create(
                        order_number=generate_order_number(order.order_type),
                        order_type=order.order_type,
                        title=new_title,
                        description=f"{order.description}\n\n[Split from order {order.order_number} - Group {group_index}]",
                        quantity=sum(item.quantity for item in group_items),
                        unit='items',
                        urgency=order.urgency,
                        estimated_cost=group_cost or Decimal('0.01'),
                        supplier=order.supplier,
                        requested_by=order.requested_by,
                        status='approved_by_manager'  # Automatically approve the split orders
                    )

                    # Copy items to new order
                    for item in group_items:
                        OrderItem.objects.create(
                            order=new_order,
                            item_name=item.item_name,
                            is_custom_item=item.is_custom_item,
                            quantity=item.quantity,
                            unit=item.unit,
                            estimated_cost=item.estimated_cost
                        )

                    # Log activity for new order
                    try:
                        log_order_activity(
                            order=new_order,
                            user=request.user,
                            activity_type='created',
                            description=f"Order created by splitting {order.order_number} and approved by manager {request.user.get_full_name()}",
                            request=request,
                            previous_status='pending',
                            new_status='approved_by_manager'
                        )
                    except Exception as e:
                        # Log failed, but continue - order was created successfully
                        print(f"Warning: Failed to log activity for new order {new_order.id}: {str(e)}")

                    created_orders.append(new_order.id)

                # Mark original order as completed/cancelled
                old_status = order.status
                order.status = 'completed'
                order.completion_date = timezone.now()
                order.save()

                # Log that original was split
                log_order_activity(
                    order=order,
                    user=request.user,
                    activity_type='status_changed',
                    description=f"Order split into {len(item_groups)} separate orders by manager {request.user.get_full_name()}. New order IDs: {created_orders}. {notes}",
                    request=request,
                    previous_status=old_status,
                    new_status='completed'
                )

            return Response({
                'message': f'Order successfully split into {len(created_orders)} orders and approved',
                'created_orders': created_orders
            })
        except Exception as e:
            print(f"ERROR in split_and_approve transaction: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {'error': f'Failed to split order: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['put'])
    def submit_revision(self, request, pk=None):
        """Submit revised order by original requester"""
        order = self.get_object()
        
        # Check if user can submit revisions for this order
        # Allow: original requester OR veterinary users for medicine orders
        can_revise = (
            order.requested_by == request.user or 
            (request.user.role in ['head_veterinary', 'veterinary'] and order.order_type == 'medicine')
        )
        
        if not can_revise:
            return Response(
                {'error': 'You do not have permission to revise this order'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if order needs revision
        if not order.needs_revision:
            return Response(
                {'error': 'Order is not in revision state'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get the data for updating the order
        serializer = self.get_serializer(order, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            # Update the order details
            old_status = order.status
            serializer.save()
            
            # Reset order to pending for re-approval
            order.status = 'pending'
            order.revision_reason = None
            order.revision_requested_by = None
            order.revision_requested_at = None
            order.save()
            
            # Log activity
            log_order_activity(
                order=order,
                user=request.user,
                activity_type='revision_submitted',
                description=f"Revised order resubmitted by {request.user.get_full_name()}",
                request=request,
                previous_status=old_status,
                new_status=order.status,
                order_data=serializer.validated_data
            )
            
            # Notify admins that revision has been submitted
            admins = User.objects.filter(role__in=['admin', 'super_admin'])
            for admin in admins:
                create_notification(
                    order=order,
                    recipient=admin,
                    notification_type='approval_needed',
                    title=f'Revised Order Submitted: {order.order_number}',
                    message=f'Revised order for {order.title} has been resubmitted and requires approval'
                )
        
        return Response({'message': 'Revised order submitted successfully'})
    
    @action(detail=False, methods=['get'])
    def dashboard_stats(self, request):
        """Get dashboard statistics"""
        user = request.user
        
        if user.role == 'super_admin':
            # Super admin sees all statistics
            queryset = Order.objects.all()
        else:
            queryset = self.get_queryset()
        
        stats = queryset.aggregate(
            total_orders=Count('id'),
            pending_orders=Count('id', filter=Q(status='pending')),
            admin_approved=Count('id', filter=Q(status='approved_by_admin')),
            fully_approved=Count('id', filter=Q(status='approved_by_finance')),
            rejected_orders=Count('id', filter=Q(status='rejected')),
            completed_orders=Count('id', filter=Q(status='completed'))
        )
        
        return Response(stats)
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def superadmin_dashboard(self, request):
        """
        Comprehensive dashboard for superadmin with full order oversight
        """
        if request.user.role != 'super_admin':
            return Response(
                {'error': 'Access denied. Super admin only.'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Recent activities across all orders
        recent_activities = OrderActivity.objects.select_related(
            'order', 'user'
        ).order_by('-created_at')[:50]
        
        # Orders requiring attention
        pending_approvals = Order.objects.filter(
            status__in=['pending', 'approved_by_admin']
        ).count()
        
        # System-wide statistics
        stats = {
            'total_orders': Order.objects.count(),
            'pending_admin': Order.objects.filter(status='pending').count(),
            'pending_finance': Order.objects.filter(status='approved_by_admin').count(),
            'approved': Order.objects.filter(status='approved_by_finance').count(),
            'completed': Order.objects.filter(status='completed').count(),
            'rejected': Order.objects.filter(status='rejected').count(),
            'total_value': Order.objects.filter(
                status__in=['approved_by_finance', 'completed']
            ).aggregate(total=Sum('estimated_cost'))['total'] or 0,
        }
        
        # Recent activities serialized
        from .serializers import SuperAdminOrderActivitySerializer
        activities_data = SuperAdminOrderActivitySerializer(recent_activities, many=True).data
        
        return Response({
            'stats': stats,
            'recent_activities': activities_data,
            'pending_approvals': pending_approvals
        })
    
    def destroy(self, request, *args, **kwargs):
        """Delete order - only allowed for superadmin"""
        if request.user.role != 'super_admin':
            return Response(
                {'error': 'Only superadmin can delete orders'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        order = self.get_object()
        order_number = order.order_number
        order_title = order.title
        
        # Log the deletion activity before deleting
        log_order_activity(
            order=order,
            user=request.user,
            activity_type='deleted',
            description=f"Order deleted by superadmin {request.user.get_full_name()}",
            request=request,
            reason="Superadmin deletion"
        )
        
        # Delete the order (this will cascade delete related objects)
        order.delete()
        
        return Response({
            'message': f'Order {order_number} ({order_title}) has been successfully deleted'
        })

# Additional viewsets for notifications
class OrderNotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderNotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return OrderNotification.objects.filter(
            recipient=self.request.user
        ).select_related('order', 'order__requested_by')
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save()
        return Response({'message': 'Notification marked as read'})