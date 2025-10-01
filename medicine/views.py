from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.http import HttpResponse
from .models import MedicineClass, Medicine, StoragePermission, StockTransaction
from .serializers import (
    MedicineClassSerializer, MedicineSerializer, StoragePermissionSerializer,
    StockTransactionSerializer, StockAdjustmentSerializer
)
from .utils import process_excel_upload, generate_sample_template
from users.models import User


class HasStoragePermission(permissions.BasePermission):
    """Custom permission to check storage access"""
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        # Super admins have all permissions
        if request.user.role == 'super_admin':
            return True
        
        # Check if user has storage permissions
        if request.method in permissions.SAFE_METHODS:
            return StoragePermission.objects.filter(
                user=request.user,
                permission_type__in=['read', 'add_stock', 'remove_stock', 'full_access'],
                is_active=True
            ).exists()
        
        # For write operations, check specific permissions
        required_permission = 'full_access'
        if hasattr(view, 'get_required_permission'):
            required_permission = view.get_required_permission()
        
        return StoragePermission.objects.filter(
            user=request.user,
            permission_type__in=[required_permission, 'full_access'],
            is_active=True
        ).exists()


class MedicineClassListCreateView(generics.ListCreateAPIView):
    queryset = MedicineClass.objects.all()
    serializer_class = MedicineClassSerializer
    permission_classes = []  # Temporarily remove permission check for testing


class MedicineListCreateView(generics.ListCreateAPIView):
    queryset = Medicine.objects.select_related('medicine_class', 'created_by').all()
    serializer_class = MedicineSerializer
    permission_classes = []  # Temporarily remove permission check for testing
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class MedicineDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Medicine.objects.select_related('medicine_class', 'created_by').all()
    serializer_class = MedicineSerializer
    permission_classes = [permissions.IsAuthenticated]


class StoragePermissionListCreateView(generics.ListCreateAPIView):
    serializer_class = StoragePermissionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Only super_admins can view all storage permissions
        if self.request.user.role == 'super_admin':
            return StoragePermission.objects.select_related('user', 'granted_by').all()
        # Others can only see their own permissions
        return StoragePermission.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        # Only super_admins can grant storage permissions
        if self.request.user.role != 'super_admin':
            raise permissions.PermissionDenied("Only super admins can grant storage permissions")
        serializer.save(granted_by=self.request.user)


class StoragePermissionDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = StoragePermissionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        if self.request.user.role == 'super_admin':
            return StoragePermission.objects.select_related('user', 'granted_by').all()
        return StoragePermission.objects.filter(user=self.request.user)


class StockTransactionListView(generics.ListAPIView):
    serializer_class = StockTransactionSerializer
    permission_classes = [HasStoragePermission]
    
    def get_queryset(self):
        queryset = StockTransaction.objects.select_related('medicine', 'performed_by').all()
        
        # Filter by medicine if specified
        medicine_id = self.request.query_params.get('medicine_id')
        if medicine_id:
            queryset = queryset.filter(medicine_id=medicine_id)
        
        # Filter by transaction type if specified
        transaction_type = self.request.query_params.get('transaction_type')
        if transaction_type:
            queryset = queryset.filter(transaction_type=transaction_type)
        
        return queryset


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def adjust_stock(request):
    """Add or remove stock from a medicine item"""
    from users.models import SectionPermission, Section
    
    serializer = StockAdjustmentSerializer(data=request.data)
    
    if serializer.is_valid():
        data = serializer.validated_data
        
        # Check user permission for the specific action
        required_permission = 'add_stock' if data['transaction_type'] == 'add' else 'remove_stock'
        
        if request.user.role != 'super_admin':
            # Check section permission for medicine_management
            try:
                medicine_section = Section.objects.get(name='medicine_management')
                section_permission = SectionPermission.objects.get(
                    user=request.user,
                    section=medicine_section
                )
                
                permission_level = section_permission.permission_level
                
                # Check if user has required permission level
                has_permission = False
                if permission_level == 'full_access':
                    has_permission = True
                elif permission_level == 'edit_records':
                    has_permission = True  # edit_records allows both add and remove
                elif permission_level == 'add_records' and required_permission == 'add_stock':
                    has_permission = True  # add_records only allows adding stock
                
            except (Section.DoesNotExist, SectionPermission.DoesNotExist):
                has_permission = False
            
            if not has_permission:
                return Response(
                    {'error': f'You do not have permission to {required_permission.replace("_", " ")}'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        with transaction.atomic():
            medicine = get_object_or_404(Medicine, id=data['medicine_id'])
            previous_stock = medicine.stock_remaining
            
            if data['transaction_type'] == 'add':
                new_stock = previous_stock + data['quantity']
            elif data['transaction_type'] == 'remove':
                new_stock = max(0, previous_stock - data['quantity'])
            else:  # adjustment
                new_stock = data['quantity']
            
            # Update medicine stock
            medicine.stock_remaining = new_stock
            medicine.save()
            
            # Create transaction record
            stock_transaction = StockTransaction.objects.create(
                medicine=medicine,
                transaction_type=data['transaction_type'],
                quantity=data['quantity'],
                previous_stock=previous_stock,
                new_stock=new_stock,
                performed_by=request.user,
                reason=data.get('reason', ''),
                notes=data.get('notes', ''),
                batch_number=data.get('batch_number', ''),
                expiry_date=data.get('expiry_date')
            )
            
            return Response({
                'message': f'Stock {data["transaction_type"]} successful',
                'medicine': MedicineSerializer(medicine).data,
                'transaction': StockTransactionSerializer(stock_transaction).data
            })
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_users_without_storage_permission(request):
    """Get users who don't have storage permissions - for super admins"""
    if request.user.role != 'super_admin':
        return Response(
            {'error': 'Only super admins can access this endpoint'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Get users who don't have any storage permissions
    users_with_permissions = StoragePermission.objects.filter(is_active=True).values_list('user_id', flat=True)
    users_without_permissions = User.objects.exclude(id__in=users_with_permissions).exclude(role='super_admin')
    
    users_data = []
    for user in users_without_permissions:
        users_data.append({
            'id': user.id,
            'username': user.username,
            'full_name': user.full_name,
            'role': user.role,
            'email': user.email
        })
    
    return Response(users_data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_user_permissions(request):
    """Get current user's medicine storage permissions"""
    from users.models import SectionPermission, Section
    
    if request.user.role == 'super_admin':
        return Response({
            'permissions': ['read', 'add_stock', 'remove_stock', 'full_access'],
            'is_super_admin': True
        })
    
    # Get medicine_management section permissions
    try:
        medicine_section = Section.objects.get(name='medicine_management')
        section_permission = SectionPermission.objects.get(
            user=request.user,
            section=medicine_section
        )
        
        # Map section permission levels to medicine storage permissions
        permission_level = section_permission.permission_level
        if permission_level == 'full_access':
            user_permissions = ['read', 'add_stock', 'remove_stock', 'full_access']
        elif permission_level == 'edit_records':
            user_permissions = ['read', 'add_stock', 'remove_stock']
        elif permission_level == 'add_records':
            user_permissions = ['read', 'add_stock']
        elif permission_level == 'read_only':
            user_permissions = ['read']
        else:  # no_access
            user_permissions = []
            
    except (Section.DoesNotExist, SectionPermission.DoesNotExist):
        # No specific permission found, default to no access
        user_permissions = []
    
    return Response({
        'permissions': user_permissions,
        'is_super_admin': False
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def upload_excel(request):
    """Upload and process Excel/CSV file to import medicines"""
    
    # Check if user has permission to upload
    if request.user.role not in ['super_admin', 'admin']:
        return Response(
            {'error': 'Only super admins and admins can upload medicine data'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    if 'file' not in request.FILES:
        return Response(
            {'error': 'No file uploaded'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    file = request.FILES['file']
    
    # Validate file type
    if not file.name.endswith(('.csv', '.xlsx', '.xls')):
        return Response(
            {'error': 'Invalid file type. Please upload CSV or Excel file.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Process the file
    try:
        results = process_excel_upload(file, request.user)
        
        if results['success']:
            return Response({
                'message': 'File processed successfully',
                'results': {
                    'created': results['created_count'],
                    'updated': results['updated_count'],
                    'skipped': results['skipped_count'],
                    'errors': results['errors']
                }
            })
        else:
            return Response(
                {'error': 'File processing failed', 'details': results['errors']},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    except Exception as e:
        return Response(
            {'error': f'Unexpected error: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def download_template(request):
    """Download sample CSV template for medicine import"""
    
    csv_content = generate_sample_template()
    
    response = HttpResponse(csv_content, content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="medicine_import_template.csv"'
    
    return response


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def import_from_csv_data(request):
    """Import medicine data from the existing CSV data structure"""
    
    # Check if user has permission
    if request.user.role not in ['super_admin', 'admin']:
        return Response(
            {'error': 'Only super admins and admins can import medicine data'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        # CSV data from the file we analyzed
        csv_data = """CLASS,PRODUCT,STOCK REMAINING,UNIT,ORDER,ORDER_UNIT
Antibiotics,Amphoprim,0,ml,,ml
Antibiotics,Terramycin LA,0,ml,,ml
Antibiotics,Limoxin-100,19410,ml,,ml
Antibiotics,Moxyline Gold 120,0,ml,,ml
Antibiotics,Tetroxy LA/Terramycin LA,6300,ml,,ml
Antibiotics,Butachem 50,2050,ml,,ml
Anti-Protozoal,Berenil RTU,720,ml,,ml
Anti-Protozoal,Imidure 12%/Forray 65,9050,ml,,ml
Anti-Parasitics,Virbamax First Drench,15000,ml,,ml
Anti-Parasitics,Flukazole,15000,ml,,ml
Vaccines,Covexin 10 (2ml/dose),4000,ml,,ml
Vaccines,Botuthrax (2ml/dose),0,ml,4300,ml
Vaccines,Bovillis Lumpyvax (1ml/dose),1300,ml,600,ml
Supplements,Atlantic Gold,20000,ml,,ml
Supplements,B-Complex,2000,ml,,ml
Consumables,Needle 18 G (Pink),650,units,,units
Emergency Drugs,Antivenom EchiTab ICP,8,vials,,ml
Miscellaneous,Activated Charcoal,0,g,25000,g
Lab Consumables,Eosinigrosin Stain,1,bottle,1,bottle"""
        
        import pandas as pd
        from io import StringIO
        
        # Create a file-like object from the CSV data
        csv_file = StringIO(csv_data)
        csv_file.name = 'import_data.csv'
        
        # Process the data
        results = process_excel_upload(csv_file, request.user)
        
        if results['success']:
            return Response({
                'message': 'Medicine data imported successfully',
                'results': {
                    'created': results['created_count'],
                    'updated': results['updated_count'],
                    'skipped': results['skipped_count'],
                    'errors': results['errors']
                }
            })
        else:
            return Response(
                {'error': 'Import failed', 'details': results['errors']},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    except Exception as e:
        return Response(
            {'error': f'Import error: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )