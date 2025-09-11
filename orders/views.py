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

from .models import Order, OrderApproval, OrderActivity, OrderComment, OrderNotification
from .serializers import (
    OrderListSerializer, OrderDetailSerializer, OrderCreateSerializer,
    OrderApprovalActionSerializer, OrderCommentCreateSerializer,
    OrderNotificationSerializer, SuperAdminOrderDetailSerializer
)

User = get_user_model()

class OrderPermission(permissions.BasePermission):
    """
    Custom permission for order management
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Allow all authenticated users to view their own orders and create new ones
        if view.action in ['list', 'create', 'retrieve']:
            return True
            
        # Admin and super_admin can approve, reject, view all
        if view.action in ['approve', 'reject', 'admin_dashboard']:
            return request.user.role in ['admin', 'super_admin']
            
        # Finance managers can approve finance stage
        if view.action in ['finance_approve', 'finance_reject']:
            return request.user.role in ['finance_manager', 'super_admin']
            
        # Veterinary users can submit revisions
        if view.action in ['submit_revision']:
            return request.user.role in ['head_veterinary', 'veterinary', 'super_admin']
            
        # Super admin can access everything including delete
        if view.action in ['superadmin_dashboard', 'activity_log', 'bulk_actions', 'destroy']:
            return request.user.role == 'super_admin'
            
        return False
    
    def has_object_permission(self, request, view, obj):
        # Users can view their own orders
        if view.action == 'retrieve' and obj.requested_by == request.user:
            return True
            
        # Admins and super_admins can access all orders
        if request.user.role in ['admin', 'super_admin']:
            return True
            
        # Finance managers can view orders in finance approval stage
        if request.user.role == 'finance_manager' and obj.status == 'approved_by_admin':
            return True
            
        # Submit revision permissions - original requester or veterinary users for medicine orders
        if view.action == 'submit_revision':
            can_revise = (
                obj.requested_by == request.user or 
                (request.user.role in ['head_veterinary', 'veterinary'] and obj.order_type == 'medicine')
            )
            return can_revise
            
        # Complete order permissions - only super_admin can finalize orders
        if view.action == 'complete':
            return request.user.role == 'super_admin'
            
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
    
    # Get count of orders this year
    count = Order.objects.filter(
        order_number__startswith=f"{prefix}-{year}-"
    ).count() + 1
    
    return f"{prefix}-{year}-{count:04d}"

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
            
            # Create notifications for admins
            admins = User.objects.filter(role__in=['admin', 'super_admin'])
            for admin in admins:
                create_notification(
                    order=order,
                    recipient=admin,
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
        """Mark order as completed"""
        order = self.get_object()
        
        if order.status != 'approved_by_finance':
            return Response(
                {'error': 'Order must be fully approved before completion'}, 
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