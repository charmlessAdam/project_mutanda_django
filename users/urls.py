from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LoginApi, 
    RegisterApi, 
    CurrentUserApi, 
    ChangePasswordApi,
    logout_api,
    UserManagementViewSet,
    UserActivityViewSet,
    SectionViewSet,
    SectionPermissionViewSet
)

router = DefaultRouter()
router.register(r'manage-users', UserManagementViewSet, basename='manage-users')
router.register(r'sections', SectionViewSet, basename='sections')
router.register(r'section-permissions', SectionPermissionViewSet, basename='section-permissions')

urlpatterns = [
    # Authentication endpoints
    path('auth/login/', LoginApi.as_view(), name='login'),
    path('auth/register/', RegisterApi.as_view(), name='register'),
    path('auth/logout/', logout_api, name='logout'),
    
    # Current user endpoints
    path('users/me/', CurrentUserApi.as_view(), name='current_user'),
    path('users/change-password/', ChangePasswordApi.as_view(), name='change_password'),
    
    # User management endpoints
    path('users/activities/', UserActivityViewSet.as_view(), name='user_activities'),
    
    # Include router URLs
    path('', include(router.urls)),
]
