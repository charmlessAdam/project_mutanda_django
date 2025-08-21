from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Create test users with different roles'

    def handle(self, *args, **options):
        test_users = [
            {
                'username': 'test',
                'password': 'test',
                'email': 'test@example.com',
                'first_name': 'Test',
                'last_name': 'Manager',
                'role': 'manager',
                'phone': '+1 (555) 123-4567',
                'location': 'New York, NY',
                'bio': 'Manager at Project Mutanda, focusing on agricultural operations and livestock management.'
            },
            {
                'username': 'warehouse',
                'password': 'warehouse',
                'email': 'warehouse@example.com',
                'first_name': 'Warehouse',
                'last_name': 'Worker',
                'role': 'warehouse_worker',
                'phone': '+1 (555) 234-5678',
                'location': 'Chicago, IL',
                'bio': 'Warehouse worker responsible for inventory and stock management.'
            },
            {
                'username': 'operator',
                'password': 'operator',
                'email': 'operator@example.com',
                'first_name': 'System',
                'last_name': 'Operator',
                'role': 'operator',
                'phone': '+1 (555) 345-6789',
                'location': 'Los Angeles, CA',
                'bio': 'System operator managing daily operations and analytics.'
            }
        ]

        for user_data in test_users:
            username = user_data['username']
            if User.objects.filter(username=username).exists():
                self.stdout.write(
                    self.style.WARNING(f'User "{username}" already exists, skipping...')
                )
                continue
            
            password = user_data.pop('password')
            user = User.objects.create_user(**user_data)
            user.set_password(password)
            user.save()
            
            self.stdout.write(
                self.style.SUCCESS(f'Successfully created user "{username}" with role "{user.role}"')
            )

        self.stdout.write(
            self.style.SUCCESS('\nTest users created successfully!')
        )
        self.stdout.write('Login credentials:')
        self.stdout.write('- Manager: test / test')
        self.stdout.write('- Warehouse Worker: warehouse / warehouse')
        self.stdout.write('- System Operator: operator / operator')