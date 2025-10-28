from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from inventory.models import InventoryCategory, StorageLocation

User = get_user_model()


class Command(BaseCommand):
    help = 'Create default inventory categories and storage locations'

    def handle(self, *args, **kwargs):
        self.stdout.write('Creating default inventory categories and storage locations...')

        # Get or create admin user for created_by field
        admin_user = User.objects.filter(is_superuser=True).first()

        # Default categories
        categories_data = [
            {
                'name': 'Equipment',
                'description': 'Farm equipment and machinery',
                'icon': 'wrench',
                'color': '#3b82f6',
                'requires_expiration': False,
                'requires_batch_tracking': False
            },
            {
                'name': 'Feed',
                'description': 'Animal feed and supplements',
                'icon': 'grain',
                'color': '#f59e0b',
                'requires_expiration': True,
                'requires_batch_tracking': True
            },
            {
                'name': 'Medicine',
                'description': 'Veterinary medicines and vaccines',
                'icon': 'pills',
                'color': '#ef4444',
                'requires_expiration': True,
                'requires_batch_tracking': True
            },
            {
                'name': 'Supplies',
                'description': 'General farm supplies',
                'icon': 'box',
                'color': '#8b5cf6',
                'requires_expiration': False,
                'requires_batch_tracking': False
            },
            {
                'name': 'Tools',
                'description': 'Hand tools and small equipment',
                'icon': 'tool',
                'color': '#06b6d4',
                'requires_expiration': False,
                'requires_batch_tracking': False
            },
            {
                'name': 'Safety Equipment',
                'description': 'Personal protective equipment and safety gear',
                'icon': 'shield',
                'color': '#10b981',
                'requires_expiration': False,
                'requires_batch_tracking': False
            },
            {
                'name': 'Fertilizers',
                'description': 'Fertilizers and soil amendments',
                'icon': 'leaf',
                'color': '#84cc16',
                'requires_expiration': True,
                'requires_batch_tracking': True
            },
            {
                'name': 'Cleaning Supplies',
                'description': 'Cleaning and sanitation products',
                'icon': 'spray',
                'color': '#14b8a6',
                'requires_expiration': True,
                'requires_batch_tracking': False
            },
        ]

        created_categories = 0
        for cat_data in categories_data:
            category, created = InventoryCategory.objects.get_or_create(
                name=cat_data['name'],
                defaults={
                    **cat_data,
                    'created_by': admin_user
                }
            )
            if created:
                created_categories += 1
                self.stdout.write(self.style.SUCCESS(f'Created category: {category.name}'))
            else:
                self.stdout.write(f'Category already exists: {category.name}')

        # Default storage locations
        locations_data = [
            {
                'name': 'Main Warehouse',
                'location_type': 'warehouse',
                'description': 'Primary storage facility for general inventory',
                'capacity': 1000,
                'capacity_unit': 'cubic meters',
                'temperature_controlled': False,
                'is_active': True
            },
            {
                'name': 'Feed Silo 1',
                'location_type': 'silo',
                'description': 'Large silo for bulk feed storage',
                'capacity': 50000,
                'capacity_unit': 'kg',
                'temperature_controlled': False,
                'is_active': True
            },
            {
                'name': 'Feed Silo 2',
                'location_type': 'silo',
                'description': 'Large silo for bulk feed storage',
                'capacity': 50000,
                'capacity_unit': 'kg',
                'temperature_controlled': False,
                'is_active': True
            },
            {
                'name': 'Medicine Cabinet',
                'location_type': 'cabinet',
                'description': 'Secure storage for veterinary medicines',
                'temperature_controlled': True,
                'current_temperature': 4,
                'is_active': True,
                'requires_authorization': True
            },
            {
                'name': 'Tool Shed',
                'location_type': 'shed',
                'description': 'Storage for hand tools and small equipment',
                'temperature_controlled': False,
                'is_active': True
            },
            {
                'name': 'Equipment Shed',
                'location_type': 'shed',
                'description': 'Storage for farm equipment and machinery',
                'capacity': 200,
                'capacity_unit': 'square meters',
                'temperature_controlled': False,
                'is_active': True
            },
            {
                'name': 'Cold Storage',
                'location_type': 'refrigerator',
                'description': 'Refrigerated storage for temperature-sensitive items',
                'capacity': 50,
                'capacity_unit': 'cubic meters',
                'temperature_controlled': True,
                'current_temperature': 2,
                'humidity': 85,
                'is_active': True
            },
            {
                'name': 'Yard Storage',
                'location_type': 'yard',
                'description': 'Outdoor storage area',
                'capacity': 500,
                'capacity_unit': 'square meters',
                'temperature_controlled': False,
                'is_active': True
            },
        ]

        created_locations = 0
        for loc_data in locations_data:
            location, created = StorageLocation.objects.get_or_create(
                name=loc_data['name'],
                defaults={
                    **loc_data,
                    'created_by': admin_user
                }
            )
            if created:
                created_locations += 1
                self.stdout.write(self.style.SUCCESS(f'Created location: {location.name}'))
            else:
                self.stdout.write(f'Location already exists: {location.name}')

        self.stdout.write(self.style.SUCCESS(
            f'\n✓ Seeding complete! Created {created_categories} categories and {created_locations} locations.'
        ))
        if created_categories == 0 and created_locations == 0:
            self.stdout.write(self.style.WARNING('All items already existed in the database.'))
