from django.core.management.base import BaseCommand
from users.models import User, Department

class Command(BaseCommand):
    help = 'Create initial departments'
    
    def handle(self, *args, **options):
        # Create sample departments
        departments_data = [
            {
                'name': 'Operations',
                'description': 'Farm operations and daily management',
            },
            {
                'name': 'Finance',
                'description': 'Financial management and accounting',
            },
            {
                'name': 'Veterinary',
                'description': 'Animal health and veterinary services',
            },
            {
                'name': 'Administration',
                'description': 'Administrative and human resources',
            },
            {
                'name': 'Quality Control',
                'description': 'Quality assurance and safety',
            },
        ]
        
        created_count = 0
        for dept_data in departments_data:
            dept, created = Department.objects.get_or_create(
                name=dept_data['name'],
                defaults={'description': dept_data['description']}
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created department: {dept.name}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Department already exists: {dept.name}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {created_count} departments')
        )
        
        # Show total department count
        total_departments = Department.objects.count()
        self.stdout.write(
            self.style.SUCCESS(f'Total departments in database: {total_departments}')
        )