from django.core.management.base import BaseCommand
from users.models import Section


class Command(BaseCommand):
    help = 'Create initial system sections'

    def handle(self, *args, **options):
        sections_data = [
            {
                'name': 'medicine_management',
                'display_name': 'Medicine Management',
                'description': 'Access to medicine inventory, prescriptions, and medical supplies management'
            },
            {
                'name': 'cattle_management',
                'display_name': 'Cattle Management',
                'description': 'Access to animal tracking, health records, weight monitoring, and livestock management'
            },
            {
                'name': 'user_management',
                'display_name': 'User Management',
                'description': 'Access to user administration, role management, and system permissions'
            },
            {
                'name': 'warehouse_storage',
                'display_name': 'Warehouse Storage',
                'description': 'Access to equipment storage, warehouse operations, and supply management'
            },
            {
                'name': 'reports',
                'display_name': 'Reports',
                'description': 'Access to generate and view system reports, analytics, and data exports'
            },
            {
                'name': 'settings',
                'display_name': 'Settings',
                'description': 'Access to system configuration, preferences, and administrative settings'
            }
        ]

        created_count = 0
        updated_count = 0

        for section_data in sections_data:
            section, created = Section.objects.get_or_create(
                name=section_data['name'],
                defaults={
                    'display_name': section_data['display_name'],
                    'description': section_data['description'],
                    'is_active': True
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created section: {section.display_name}')
                )
            else:
                # Update existing section if needed
                if (section.display_name != section_data['display_name'] or 
                    section.description != section_data['description']):
                    section.display_name = section_data['display_name']
                    section.description = section_data['description']
                    section.save()
                    updated_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'Updated section: {section.display_name}')
                    )
                else:
                    self.stdout.write(f'Section already exists: {section.display_name}')

        self.stdout.write(
            self.style.SUCCESS(
                f'\nCompleted: {created_count} sections created, {updated_count} sections updated'
            )
        )