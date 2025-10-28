from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import WorkerViewSet, EquipmentAssignmentViewSet

router = DefaultRouter()
router.register(r'workers', WorkerViewSet, basename='worker')
router.register(r'equipment-assignments', EquipmentAssignmentViewSet, basename='equipment-assignment')

urlpatterns = [
    path('', include(router.urls)),
]
