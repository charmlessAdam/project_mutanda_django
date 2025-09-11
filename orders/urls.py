from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet, OrderNotificationViewSet

router = DefaultRouter()
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'notifications', OrderNotificationViewSet, basename='notification')

urlpatterns = [
    path('', include(router.urls)),
]