from django.urls import path
from . import views

urlpatterns = [
    path('import/', views.import_animals, name='import_animals'),
    path('sections/', views.sections_list, name='sections_list'),
    path('animals/', views.animals_list, name='animals_list'),
]