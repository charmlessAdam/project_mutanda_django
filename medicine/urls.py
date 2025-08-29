from django.urls import path
from . import views

urlpatterns = [
    # Medicine classes
    path('classes/', views.MedicineClassListCreateView.as_view(), name='medicine-classes'),
    
    # Medicines
    path('medicines/', views.MedicineListCreateView.as_view(), name='medicine-list'),
    path('medicines/<int:pk>/', views.MedicineDetailView.as_view(), name='medicine-detail'),
    
    # Storage permissions
    path('storage-permissions/', views.StoragePermissionListCreateView.as_view(), name='storage-permissions'),
    path('storage-permissions/<int:pk>/', views.StoragePermissionDetailView.as_view(), name='storage-permission-detail'),
    
    # Stock transactions
    path('stock-transactions/', views.StockTransactionListView.as_view(), name='stock-transactions'),
    path('adjust-stock/', views.adjust_stock, name='adjust-stock'),
    
    # Utility endpoints
    path('users-without-permissions/', views.get_users_without_storage_permission, name='users-without-permissions'),
    path('user-permissions/', views.get_user_permissions, name='user-permissions'),
    
    # File upload endpoints
    path('upload-excel/', views.upload_excel, name='upload-excel'),
    path('download-template/', views.download_template, name='download-template'),
    path('import-sample-data/', views.import_from_csv_data, name='import-sample-data'),
]