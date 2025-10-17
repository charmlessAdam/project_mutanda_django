from django.core.management.base import BaseCommand
from inventory.models import InventoryItem, InventoryCategory, StorageLocation
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Import sample inventory data'

    def handle(self, *args, **kwargs):
        # Get or create a super admin user for created_by field
        try:
            user = User.objects.filter(is_superuser=True).first()
            if not user:
                self.stdout.write(self.style.WARNING('No superuser found. Creating items without user reference.'))
                user = None
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Error getting user: {e}'))
            user = None

        # Create categories
        categories_data = [
            {'name': 'Equipment', 'description': 'Farm equipment and machinery'},
            {'name': 'Supplies', 'description': 'General farm supplies'},
            {'name': 'Tools', 'description': 'Hand tools and equipment'},
            {'name': 'Fertilizers', 'description': 'Fertilizers and soil amendments'},
            {'name': 'Cleaning Supplies', 'description': 'Cleaning and sanitation supplies'},
            {'name': 'Bedding Materials', 'description': 'Animal bedding materials'},
            {'name': 'Fuel', 'description': 'Fuel and lubricants'},
            {'name': 'Spare Parts', 'description': 'Spare parts and replacements'},
            {'name': 'Safety Equipment', 'description': 'Safety gear and equipment'},
        ]

        for cat_data in categories_data:
            category, created = InventoryCategory.objects.get_or_create(
                name=cat_data['name'],
                defaults={'description': cat_data['description'], 'created_by': user}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created category: {category.name}'))

        # Create storage locations
        locations_data = [
            {'name': 'Silo 1', 'location_type': 'silo'},
            {'name': 'Silo 2', 'location_type': 'silo'},
            {'name': 'Warehouse A', 'location_type': 'warehouse'},
            {'name': 'Warehouse B', 'location_type': 'warehouse'},
            {'name': 'Shed 1', 'location_type': 'shed'},
            {'name': 'Shed 2', 'location_type': 'shed'},
            {'name': 'Storage Cabinet', 'location_type': 'cabinet'},
            {'name': 'Tool Room', 'location_type': 'other'},
            {'name': 'Fuel Tank', 'location_type': 'tank'},
            {'name': 'Yard Storage', 'location_type': 'yard'},
        ]

        for loc_data in locations_data:
            location, created = StorageLocation.objects.get_or_create(
                name=loc_data['name'],
                defaults={'location_type': loc_data['location_type'], 'created_by': user}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created location: {location.name}'))

        # Create inventory items
        items_data = [
            {
                'name': 'Water Trough',
                'category': 'Equipment',
                'storage_location': 'Shed 1',
                'quantity': 5,
                'unit': 'pieces',
                'reorder_level': 2,
                'supplier': 'Farm Equipment Ltd',
                'cost_per_unit': 150,
                'condition': 'good',
            },
            {
                'name': 'Mineral Supplements',
                'category': 'Supplies',
                'storage_location': 'Storage Cabinet',
                'quantity': 50,
                'unit': 'kg',
                'reorder_level': 100,
                'optimal_quantity': 200,
                'supplier': 'Nutrition Plus',
                'cost_per_unit': 8,
                'condition': 'new',
            },
            {
                'name': 'Work Gloves',
                'category': 'Safety Equipment',
                'storage_location': 'Tool Room',
                'quantity': 25,
                'unit': 'pairs',
                'reorder_level': 10,
                'optimal_quantity': 50,
                'brand': 'SafetyPro',
                'cost_per_unit': 5,
                'condition': 'new',
            },
            {
                'name': 'Tractor Oil',
                'category': 'Fuel',
                'storage_location': 'Fuel Tank',
                'quantity': 100,
                'unit': 'liters',
                'reorder_level': 50,
                'optimal_quantity': 300,
                'brand': 'Shell',
                'supplier': 'Fuel Depot',
                'cost_per_unit': 3.5,
                'condition': 'good',
            },
            {
                'name': 'Shovel',
                'category': 'Tools',
                'storage_location': 'Tool Room',
                'quantity': 8,
                'unit': 'pieces',
                'reorder_level': 3,
                'cost_per_unit': 25,
                'condition': 'fair',
            },
            {
                'name': 'Straw Bedding',
                'category': 'Bedding Materials',
                'storage_location': 'Warehouse B',
                'quantity': 30,
                'unit': 'bales',
                'reorder_level': 50,
                'optimal_quantity': 100,
                'supplier': 'Local Farms',
                'cost_per_unit': 8,
                'condition': 'good',
            },
            {
                'name': 'Wheelbarrow',
                'category': 'Equipment',
                'storage_location': 'Shed 2',
                'quantity': 3,
                'unit': 'pieces',
                'reorder_level': 1,
                'cost_per_unit': 85,
                'condition': 'good',
            },
            {
                'name': 'Disinfectant Spray',
                'category': 'Cleaning Supplies',
                'storage_location': 'Storage Cabinet',
                'quantity': 15,
                'unit': 'bottles',
                'reorder_level': 20,
                'optimal_quantity': 50,
                'brand': 'CleanPro',
                'cost_per_unit': 12,
                'condition': 'new',
            },
        ]

        for item_data in items_data:
            category = InventoryCategory.objects.get(name=item_data['category'])
            location = StorageLocation.objects.get(name=item_data['storage_location'])

            item, created = InventoryItem.objects.get_or_create(
                name=item_data['name'],
                category=category,
                defaults={
                    'storage_location': location,
                    'quantity': item_data['quantity'],
                    'unit': item_data['unit'],
                    'reorder_level': item_data['reorder_level'],
                    'optimal_quantity': item_data.get('optimal_quantity'),
                    'brand': item_data.get('brand', ''),
                    'supplier': item_data.get('supplier', ''),
                    'cost_per_unit': item_data.get('cost_per_unit'),
                    'condition': item_data.get('condition', 'new'),
                    'created_by': user,
                    'last_updated_by': user,
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created item: {item.name}'))
            else:
                self.stdout.write(self.style.WARNING(f'Item already exists: {item.name}'))

        self.stdout.write(self.style.SUCCESS('\nSample inventory data imported successfully!'))
        self.stdout.write(self.style.SUCCESS(f'Total items: {InventoryItem.objects.count()}'))
