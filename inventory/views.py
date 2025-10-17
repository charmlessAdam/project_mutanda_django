from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db.models import Q, Sum, F
from decimal import Decimal

from .models import (
    InventoryCategory,
    StorageLocation,
    InventoryItem,
    StockTransaction,
    InventoryAlert
)
from .serializers import (
    InventoryCategorySerializer,
    StorageLocationSerializer,
    InventoryItemSerializer,
    StockTransactionSerializer,
    InventoryAlertSerializer
)


class InventoryCategoryViewSet(viewsets.ModelViewSet):
    """
    API endpoint for inventory categories
    """
    queryset = InventoryCategory.objects.all()
    serializer_class = InventoryCategorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class StorageLocationViewSet(viewsets.ModelViewSet):
    """
    API endpoint for storage locations
    """
    queryset = StorageLocation.objects.all()
    serializer_class = StorageLocationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['location_type', 'temperature_controlled', 'is_active']
    search_fields = ['name', 'description', 'building']
    ordering_fields = ['name', 'location_type', 'created_at']
    ordering = ['location_type', 'name']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=['get'])
    def utilization_report(self, request):
        """Get utilization report for all active locations"""
        locations = self.get_queryset().filter(is_active=True)
        data = []
        for location in locations:
            data.append({
                'id': location.id,
                'name': location.name,
                'location_type': location.location_type,
                'capacity': location.capacity,
                'capacity_unit': location.capacity_unit,
                'utilization': location.current_utilization,
                'item_count': location.inventory_items.filter(is_active=True).count()
            })
        return Response(data)


class InventoryItemViewSet(viewsets.ModelViewSet):
    """
    API endpoint for inventory items
    """
    queryset = InventoryItem.objects.select_related('category', 'storage_location', 'created_by').all()
    serializer_class = InventoryItemSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'storage_location', 'is_active', 'is_consumable', 'condition']
    search_fields = ['name', 'brand', 'description', 'sku', 'barcode', 'supplier']
    ordering_fields = ['name', 'quantity', 'created_at', 'updated_at', 'expiration_date']
    ordering = ['category__name', 'name']

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by stock status
        stock_status = self.request.query_params.get('stock_status', None)
        if stock_status:
            if stock_status == 'out':
                queryset = queryset.filter(quantity__lte=0)
            elif stock_status == 'low':
                queryset = queryset.filter(quantity__gt=0, quantity__lte=F('reorder_level'))
            elif stock_status == 'optimal':
                queryset = queryset.filter(quantity__gte=F('optimal_quantity'))

        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, last_updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(last_updated_by=self.request.user)

    @action(detail=True, methods=['post'])
    def stock_in(self, request, pk=None):
        """Add stock to an item"""
        item = self.get_object()
        quantity = Decimal(request.data.get('quantity', 0))

        if quantity <= 0:
            return Response(
                {'error': 'Quantity must be greater than 0'},
                status=status.HTTP_400_BAD_REQUEST
            )

        previous_quantity = item.quantity
        item.quantity += quantity
        item.save()

        # Create transaction record
        transaction = StockTransaction.objects.create(
            item=item,
            transaction_type='purchase',
            quantity=quantity,
            previous_quantity=previous_quantity,
            new_quantity=item.quantity,
            to_location=item.storage_location,
            cost=request.data.get('cost'),
            cost_per_unit=request.data.get('cost_per_unit'),
            reference_number=request.data.get('reference_number', ''),
            purpose=request.data.get('purpose', 'Stock in'),
            notes=request.data.get('notes', ''),
            batch_number=request.data.get('batch_number', ''),
            expiration_date=request.data.get('expiration_date'),
            performed_by=request.user
        )

        # Check if low stock alert should be resolved
        if previous_quantity <= item.reorder_level and item.quantity > item.reorder_level:
            InventoryAlert.objects.filter(
                item=item,
                alert_type='low_stock',
                is_resolved=False
            ).update(
                is_resolved=True,
                resolved_at=timezone.now(),
                resolved_by=request.user,
                resolution_notes='Stock replenished'
            )

        serializer = self.get_serializer(item)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def stock_out(self, request, pk=None):
        """Remove stock from an item"""
        item = self.get_object()
        quantity = Decimal(request.data.get('quantity', 0))

        if quantity <= 0:
            return Response(
                {'error': 'Quantity must be greater than 0'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if quantity > item.quantity:
            return Response(
                {'error': 'Insufficient stock'},
                status=status.HTTP_400_BAD_REQUEST
            )

        previous_quantity = item.quantity
        item.quantity -= quantity
        item.save()

        # Create transaction record
        transaction = StockTransaction.objects.create(
            item=item,
            transaction_type=request.data.get('transaction_type', 'usage'),
            quantity=-quantity,
            previous_quantity=previous_quantity,
            new_quantity=item.quantity,
            from_location=item.storage_location,
            purpose=request.data.get('purpose', 'Stock out'),
            notes=request.data.get('notes', ''),
            performed_by=request.user
        )

        # Create low stock alert if needed
        if item.quantity <= item.reorder_level:
            alert_type = 'out_of_stock' if item.quantity <= 0 else 'low_stock'
            severity = 'critical' if item.quantity <= 0 else 'warning'

            InventoryAlert.objects.create(
                alert_type=alert_type,
                severity=severity,
                item=item,
                location=item.storage_location,
                message=f'{item.name} is {"out of stock" if item.quantity <= 0 else "low in stock"} ({item.quantity} {item.unit} remaining)',
                recommended_action=f'Reorder {item.name}. Reorder level: {item.reorder_level} {item.unit}'
            )

        serializer = self.get_serializer(item)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def transfer(self, request, pk=None):
        """Transfer item between locations"""
        item = self.get_object()
        to_location_id = request.data.get('to_location')

        if not to_location_id:
            return Response(
                {'error': 'to_location is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            to_location = StorageLocation.objects.get(id=to_location_id)
        except StorageLocation.DoesNotExist:
            return Response(
                {'error': 'Storage location not found'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from_location = item.storage_location

        # Create transaction record
        StockTransaction.objects.create(
            item=item,
            transaction_type='transfer',
            quantity=0,  # No quantity change
            previous_quantity=item.quantity,
            new_quantity=item.quantity,
            from_location=from_location,
            to_location=to_location,
            purpose=request.data.get('purpose', 'Location transfer'),
            notes=request.data.get('notes', ''),
            performed_by=request.user
        )

        # Update item location
        item.storage_location = to_location
        item.save()

        serializer = self.get_serializer(item)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """Get all items with low stock"""
        items = self.get_queryset().filter(
            is_active=True,
            quantity__gt=0,
            quantity__lte=F('reorder_level')
        )
        serializer = self.get_serializer(items, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def expiring_soon(self, request):
        """Get items expiring in the next 30 days"""
        from datetime import timedelta
        thirty_days_from_now = timezone.now().date() + timedelta(days=30)

        items = self.get_queryset().filter(
            is_active=True,
            expiration_date__isnull=False,
            expiration_date__lte=thirty_days_from_now,
            expiration_date__gte=timezone.now().date()
        )
        serializer = self.get_serializer(items, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def expired(self, request):
        """Get expired items"""
        items = self.get_queryset().filter(
            is_active=True,
            expiration_date__isnull=False,
            expiration_date__lt=timezone.now().date()
        )
        serializer = self.get_serializer(items, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get inventory summary statistics"""
        items = self.get_queryset().filter(is_active=True)

        total_items = items.count()
        total_value = sum(item.total_value or 0 for item in items)
        low_stock_count = items.filter(quantity__gt=0, quantity__lte=F('reorder_level')).count()
        out_of_stock_count = items.filter(quantity__lte=0).count()

        from datetime import timedelta
        thirty_days = timezone.now().date() + timedelta(days=30)
        expiring_soon_count = items.filter(
            expiration_date__isnull=False,
            expiration_date__lte=thirty_days,
            expiration_date__gte=timezone.now().date()
        ).count()

        expired_count = items.filter(
            expiration_date__isnull=False,
            expiration_date__lt=timezone.now().date()
        ).count()

        return Response({
            'total_items': total_items,
            'total_value': total_value,
            'low_stock_count': low_stock_count,
            'out_of_stock_count': out_of_stock_count,
            'expiring_soon_count': expiring_soon_count,
            'expired_count': expired_count
        })


class StockTransactionViewSet(viewsets.ModelViewSet):
    """
    API endpoint for stock transactions
    """
    queryset = StockTransaction.objects.select_related('item', 'from_location', 'to_location', 'performed_by').all()
    serializer_class = StockTransactionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['item', 'transaction_type', 'from_location', 'to_location']
    search_fields = ['reference_number', 'purpose', 'notes']
    ordering_fields = ['transaction_date']
    ordering = ['-transaction_date']

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by date range
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)

        if start_date:
            queryset = queryset.filter(transaction_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(transaction_date__lte=end_date)

        return queryset


class InventoryAlertViewSet(viewsets.ModelViewSet):
    """
    API endpoint for inventory alerts
    """
    queryset = InventoryAlert.objects.select_related('item', 'location', 'resolved_by').all()
    serializer_class = InventoryAlertSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['alert_type', 'severity', 'is_read', 'is_resolved', 'item', 'location']
    ordering_fields = ['created_at', 'severity']
    ordering = ['-created_at']

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark alert as read"""
        alert = self.get_object()
        alert.is_read = True
        alert.save()
        serializer = self.get_serializer(alert)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Mark alert as resolved"""
        alert = self.get_object()
        alert.is_resolved = True
        alert.resolved_at = timezone.now()
        alert.resolved_by = request.user
        alert.resolution_notes = request.data.get('resolution_notes', '')
        alert.save()
        serializer = self.get_serializer(alert)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def unresolved(self, request):
        """Get all unresolved alerts"""
        alerts = self.get_queryset().filter(is_resolved=False)
        serializer = self.get_serializer(alerts, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def unread(self, request):
        """Get all unread alerts"""
        alerts = self.get_queryset().filter(is_read=False)
        serializer = self.get_serializer(alerts, many=True)
        return Response(serializer.data)
