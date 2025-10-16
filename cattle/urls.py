from django.urls import path
from . import views

urlpatterns = [
    path('import/', views.import_animals, name='import_animals'),
    path('sections/', views.sections_list, name='sections_list'),
    path('animals/', views.animals_list, name='animals_list'),
    path('cleanup/', views.cleanup_animals, name='cleanup_animals'),
    path('weights/import/', views.import_weight_measurements, name='import_weight_measurements'),
    path('animals/<int:animal_id>/weights/', views.animal_weight_records, name='animal_weight_records'),
    path('sections/<int:section_id>/weights/export/', views.export_section_weights, name='export_section_weights'),
    path('animals/<int:animal_id>/health/', views.animal_health_records, name='animal_health_records'),
    path('health/add/', views.add_health_record, name='add_health_record'),
]