from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction

User = get_user_model()

class Command(BaseCommand):
    help = 'Create test users for order workflow testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete existing test users first',
        )

    def handle(self, *args, **options):
        test_users = [
            {
                'username': 'superadmin',
                'email': 'superadmin@example.com',
                'password': 'admin123',
                'role': 'super_admin',
                'first_name': 'Super',
                'last_name': 'Admin',
                'department': 'Administration'
            },
            {
                'username': 'admin',
                'email': 'admin@example.com', 
                'password': 'admin123',
                'role': 'admin',
                'first_name': 'John',
                'last_name': 'Admin',
                'department': 'Administration'
            },
            {
                'username': 'financemanager',
                'email': 'finance@example.com',
                'password': 'admin123', 
                'role': 'finance_manager',
                'first_name': 'Sarah',
                'last_name': 'Finance',
                'department': 'Finance'
            },
            {
                'username': 'veterinary',
                'email': 'vet@example.com',
                'password': 'admin123',
                'role': 'head_veterinary', 
                'first_name': 'Dr. Mike',
                'last_name': 'Veterinary',
                'department': 'Veterinary'
            },
            {
                'username': 'regularuser',
                'email': 'user@example.com',
                'password': 'admin123',
                'role': 'operator',
                'first_name': 'Jane',
                'last_name': 'Operator',
                'department': 'Operations'
            }
        ]

        if options['reset']:
            self.stdout.write('Deleting existing test users...')
            User.objects.filter(username__in=[user['username'] for user in test_users]).delete()

        with transaction.atomic():
            created_count = 0
            for user_data in test_users:
                user, created = User.objects.get_or_create(
                    username=user_data['username'],
                    defaults={
                        'email': user_data['email'],
                        'role': user_data['role'],
                        'first_name': user_data['first_name'],
                        'last_name': user_data['last_name'],
                        'department': user_data['department']
                    }
                )
                
                if created:
                    user.set_password(user_data['password'])
                    user.save()
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ Created {user_data["role"]} user: {user_data["username"]}')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'- User already exists: {user_data["username"]}')
                    )

        self.stdout.write(
            self.style.SUCCESS(f'\nCreated {created_count} new test users.')
        )
        
        self.stdout.write('\n' + '='*60)
        self.stdout.write('TEST USER CREDENTIALS:')
        self.stdout.write('='*60)
        for user_data in test_users:
            self.stdout.write(f'Role: {user_data["role"]}')
            self.stdout.write(f'Username: {user_data["username"]}')
            self.stdout.write(f'Password: {user_data["password"]}')
            self.stdout.write(f'Name: {user_data["first_name"]} {user_data["last_name"]}')
            self.stdout.write('-' * 30)
        
        self.stdout.write('\nTESTING WORKFLOW:')
        self.stdout.write('1. Login as "veterinary" → Create medicine orders')
        self.stdout.write('2. Login as "admin" → Approve orders in SuperAdmin dashboard')
        self.stdout.write('3. Login as "financemanager" → Give final approval')
        self.stdout.write('4. Login as "superadmin" → View all activities in Order Oversight')
        self.stdout.write('='*60)
