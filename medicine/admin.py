from django.contrib import admin
from .models import MedicineClass, Medicine, StoragePermission, StockTransaction


@admin.register(MedicineClass)
class MedicineClassAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'created_at']
    search_fields = ['name']


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = ['product', 'medicine_class', 'stock_remaining', 'unit', 'stock_status', 'minimum_stock', 'updated_at']
    list_filter = ['medicine_class', 'unit', 'created_at']
    search_fields = ['product', 'batch_number', 'supplier']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(StoragePermission)
class StoragePermissionAdmin(admin.ModelAdmin):
    list_display = ['user', 'permission_type', 'is_active', 'granted_by', 'granted_at']
    list_filter = ['permission_type', 'is_active', 'granted_at']
    search_fields = ['user__username', 'user__first_name', 'user__last_name']


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ['medicine', 'transaction_type', 'quantity', 'performed_by', 'timestamp']
    list_filter = ['transaction_type', 'timestamp']
    search_fields = ['medicine__product', 'performed_by__username', 'reason']
    readonly_fields = ['timestamp']