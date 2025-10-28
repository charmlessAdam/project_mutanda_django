from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, Q
from django.utils import timezone

from .models import Worker, EquipmentAssignment, WorkerActivity
from .serializers import (
    WorkerListSerializer,
    WorkerDetailSerializer,
    WorkerCreateUpdateSerializer,
    EquipmentAssignmentListSerializer,
    EquipmentAssignmentCreateSerializer,
    EquipmentReturnSerializer,
    WorkerActivitySerializer,
    AssignedEquipmentSummarySerializer
)


class WorkerViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Worker management

    List: GET /api/workers/
    Retrieve: GET /api/workers/{id}/
    Create: POST /api/workers/
    Update: PUT /api/workers/{id}/
    Partial Update: PATCH /api/workers/{id}/
    Delete: DELETE /api/workers/{id}/
    """
    permission_classes = [IsAuthenticated]
    queryset = Worker.objects.all()

    def get_serializer_class(self):
        if self.action == 'list':
            return WorkerListSerializer
        elif self.action == 'retrieve':
            return WorkerDetailSerializer
        return WorkerCreateUpdateSerializer

    def get_queryset(self):
        """Filter workers based on query parameters"""
        queryset = Worker.objects.all()

        # Filter by status
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by department
        department = self.request.query_params.get('department', None)
        if department:
            queryset = queryset.filter(department=department)

        # Search by name or employee_id
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(employee_id__icontains=search)
            )

        return queryset.order_by('-created_at')

    def perform_create(self, serializer):
        """Set created_by when creating worker"""
        worker = serializer.save(
            created_by=self.request.user,
            last_updated_by=self.request.user
        )

        # Log activity
        WorkerActivity.objects.create(
            worker=worker,
            action='created',
            description=f'Worker {worker.full_name} created',
            performed_by=self.request.user,
            new_values={'employee_id': worker.employee_id, 'name': worker.full_name}
        )

    def perform_update(self, serializer):
        """Set last_updated_by when updating worker"""
        old_worker = self.get_object()
        old_values = {
            'status': old_worker.status,
            'department': old_worker.department,
            'position': old_worker.position
        }

        worker = serializer.save(last_updated_by=self.request.user)

        # Log activity
        WorkerActivity.objects.create(
            worker=worker,
            action='updated',
            description=f'Worker {worker.full_name} updated',
            performed_by=self.request.user,
            old_values=old_values,
            new_values={
                'status': worker.status,
                'department': worker.department,
                'position': worker.position
            }
        )

    @action(detail=True, methods=['get'])
    def assignments(self, request, pk=None):
        """Get all equipment assignments for a worker"""
        worker = self.get_object()
        assignments = worker.equipment_assignments.all()
        serializer = EquipmentAssignmentListSerializer(assignments, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def active_assignments(self, request, pk=None):
        """Get active equipment assignments for a worker"""
        worker = self.get_object()
        assignments = worker.active_assignments
        serializer = EquipmentAssignmentListSerializer(assignments, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def activities(self, request, pk=None):
        """Get activity log for a worker"""
        worker = self.get_object()
        activities = worker.activities.all()
        serializer = WorkerActivitySerializer(activities, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get worker statistics"""
        total_workers = Worker.objects.count()
        active_workers = Worker.objects.filter(status='active').count()
        on_leave = Worker.objects.filter(status='on_leave').count()
        inactive_workers = Worker.objects.filter(status='inactive').count()

        # Get department breakdown
        departments = Worker.objects.values('department').annotate(
            count=Count('id')
        ).order_by('-count')

        # Get workers with most assignments
        workers_with_assignments = Worker.objects.annotate(
            assignments_count=Count('equipment_assignments', filter=Q(equipment_assignments__is_active=True))
        ).filter(assignments_count__gt=0).order_by('-assignments_count')[:5]

        return Response({
            'total_workers': total_workers,
            'active_workers': active_workers,
            'on_leave': on_leave,
            'inactive_workers': inactive_workers,
            'by_department': departments,
            'top_assigned_workers': WorkerListSerializer(workers_with_assignments, many=True).data
        })


class EquipmentAssignmentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Equipment Assignment management

    List: GET /api/equipment-assignments/
    Retrieve: GET /api/equipment-assignments/{id}/
    Create: POST /api/equipment-assignments/
    Update: PUT /api/equipment-assignments/{id}/
    Delete: DELETE /api/equipment-assignments/{id}/
    """
    permission_classes = [IsAuthenticated]
    queryset = EquipmentAssignment.objects.all()

    def get_serializer_class(self):
        if self.action == 'create':
            return EquipmentAssignmentCreateSerializer
        return EquipmentAssignmentListSerializer

    def get_queryset(self):
        """Filter assignments based on query parameters"""
        queryset = EquipmentAssignment.objects.select_related(
            'worker', 'inventory_item', 'assigned_by', 'returned_by'
        )

        # Filter by worker
        worker_id = self.request.query_params.get('worker', None)
        if worker_id:
            queryset = queryset.filter(worker_id=worker_id)

        # Filter by active status
        is_active = self.request.query_params.get('is_active', None)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        # Filter by item type
        item_type = self.request.query_params.get('item_type', None)
        if item_type:
            queryset = queryset.filter(item_type=item_type)

        return queryset.order_by('-assigned_date')

    def perform_create(self, serializer):
        """Create assignment and log activity"""
        assignment = serializer.save()

        # Log activity
        WorkerActivity.objects.create(
            worker=assignment.worker,
            action='equipment_assigned',
            description=f'{assignment.item_name} assigned to {assignment.worker.full_name}',
            assignment=assignment,
            performed_by=self.request.user,
            new_values={
                'item': assignment.item_name,
                'quantity': str(assignment.quantity),
                'condition': assignment.condition_at_assignment
            }
        )

    @action(detail=True, methods=['post'])
    def return_equipment(self, request, pk=None):
        """Mark equipment as returned"""
        assignment = self.get_object()

        if not assignment.is_active:
            return Response(
                {'error': 'This assignment is already marked as returned'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = EquipmentReturnSerializer(data=request.data)
        if serializer.is_valid():
            assignment.return_equipment(
                returned_by_user=request.user,
                condition_at_return=serializer.validated_data['condition_at_return'],
                return_notes=serializer.validated_data.get('return_notes', '')
            )

            # Update damage notes if provided
            if serializer.validated_data.get('damage_notes'):
                assignment.damage_notes = serializer.validated_data['damage_notes']
                assignment.save()

            # Log activity
            WorkerActivity.objects.create(
                worker=assignment.worker,
                action='equipment_returned',
                description=f'{assignment.item_name} returned by {assignment.worker.full_name}',
                assignment=assignment,
                performed_by=request.user,
                new_values={
                    'condition': assignment.condition_at_return,
                    'return_notes': assignment.return_notes
                }
            )

            return Response(
                EquipmentAssignmentListSerializer(assignment).data,
                status=status.HTTP_200_OK
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get summary of all assigned equipment"""
        # Get all active assignments grouped by item
        summary = EquipmentAssignment.objects.filter(
            is_active=True
        ).values(
            'item_name',
            'item_type',
            'inventory_item_id',
            'inventory_item__category__name'
        ).annotate(
            total_quantity_assigned=Sum('quantity'),
            active_assignments_count=Count('id')
        ).order_by('item_name')

        # Format the response
        summary_data = []
        for item in summary:
            summary_data.append({
                'item_name': item['item_name'],
                'item_type': item['item_type'],
                'total_quantity_assigned': item['total_quantity_assigned'],
                'active_assignments_count': item['active_assignments_count'],
                'inventory_item_id': item['inventory_item_id'],
                'category': item['inventory_item__category__name'] or 'Uncategorized'
            })

        serializer = AssignedEquipmentSummarySerializer(summary_data, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get equipment assignment statistics"""
        total_assignments = EquipmentAssignment.objects.count()
        active_assignments = EquipmentAssignment.objects.filter(is_active=True).count()
        returned_assignments = EquipmentAssignment.objects.filter(is_active=False).count()

        # Get assignments by type
        by_type = EquipmentAssignment.objects.filter(is_active=True).values('item_type').annotate(
            count=Count('id'),
            total_quantity=Sum('quantity')
        ).order_by('-count')

        return Response({
            'total_assignments': total_assignments,
            'active_assignments': active_assignments,
            'returned_assignments': returned_assignments,
            'by_type': by_type
        })
