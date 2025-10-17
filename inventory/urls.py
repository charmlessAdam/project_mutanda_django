from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    InventoryCategoryViewSet,
    StorageLocationViewSet,
    InventoryItemViewSet,
    StockTransactionViewSet,
    InventoryAlertViewSet
)

router = DefaultRouter()
router.register(r'categories', InventoryCategoryViewSet, basename='inventory-category')
router.register(r'locations', StorageLocationViewSet, basename='storage-location')
router.register(r'items', InventoryItemViewSet, basename='inventory-item')
router.register(r'transactions', StockTransactionViewSet, basename='stock-transaction')
router.register(r'alerts', InventoryAlertViewSet, basename='inventory-alert')

urlpatterns = [
    path('', include(router.urls)),
]
