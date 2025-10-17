from django.contrib import admin
from .models import InventoryCategory, StorageLocation, InventoryItem, StockTransaction, InventoryAlert


@admin.register(InventoryCategory)
class InventoryCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'requires_expiration', 'requires_batch_tracking', 'is_active', 'created_at')
    list_filter = ('is_active', 'requires_expiration', 'requires_batch_tracking')
    search_fields = ('name', 'description')
    ordering = ('name',)


@admin.register(StorageLocation)
class StorageLocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'location_type', 'capacity', 'capacity_unit', 'temperature_controlled', 'is_active')
    list_filter = ('location_type', 'temperature_controlled', 'requires_authorization', 'is_active')
    search_fields = ('name', 'description', 'building')
    ordering = ('location_type', 'name')


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'quantity', 'unit', 'storage_location', 'stock_status', 'expiration_date', 'is_active')
    list_filter = ('category', 'storage_location', 'is_active', 'is_consumable', 'condition')
    search_fields = ('name', 'brand', 'description', 'sku', 'barcode')
    ordering = ('category__name', 'name')
    date_hierarchy = 'created_at'
    readonly_fields = ('stock_status', 'total_value', 'created_at', 'updated_at')


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ('item', 'transaction_type', 'quantity', 'transaction_date', 'performed_by')
    list_filter = ('transaction_type', 'transaction_date')
    search_fields = ('item__name', 'reference_number', 'purpose')
    ordering = ('-transaction_date',)
    date_hierarchy = 'transaction_date'
    readonly_fields = ('transaction_date',)


@admin.register(InventoryAlert)
class InventoryAlertAdmin(admin.ModelAdmin):
    list_display = ('alert_type', 'severity', 'item', 'location', 'is_read', 'is_resolved', 'created_at')
    list_filter = ('alert_type', 'severity', 'is_read', 'is_resolved')
    search_fields = ('message', 'item__name', 'location__name')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)
