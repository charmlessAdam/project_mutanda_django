from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Create a super admin user'

    def handle(self, *args, **options):
        # Check if super admin already exists
        if User.objects.filter(role='super_admin').exists():
            self.stdout.write(
                self.style.WARNING('A super admin user already exists.')
            )
            return
        
        # Create super admin
        super_admin = User.objects.create_user(
            username='superadmin',
            password='admin123',
            email='superadmin@example.com',
            first_name='Super',
            last_name='Admin',
            role='super_admin',
            phone='+1 (555) 000-0001',
            location='Headquarters',
            bio='Super Administrator with full system access',
            department='IT Administration'
        )
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created super admin user: {super_admin.username}')
        )
        self.stdout.write('Login credentials: superadmin / admin123')
        
        # Also create an admin user
        admin_user = User.objects.create_user(
            username='admin',
            password='admin123',
            email='admin@example.com',
            first_name='System',
            last_name='Admin',
            role='admin',
            phone='+1 (555) 000-0002',
            location='Headquarters',
            bio='System Administrator',
            department='IT Administration',
            manager=super_admin,
            created_by=super_admin
        )
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created admin user: {admin_user.username}')
        )
        self.stdout.write('Login credentials: admin / admin123')
        
        # Update existing test user to be managed by admin
        try:
            test_user = User.objects.get(username='test')
            test_user.manager = admin_user
            test_user.created_by = admin_user
            test_user.department = 'Operations'
            test_user.save()
            
            self.stdout.write(
                self.style.SUCCESS(f'Updated test user to be managed by admin')
            )
        except User.DoesNotExist:
            pass
        
        # Update other test users
        try:
            warehouse_user = User.objects.get(username='warehouse')
            warehouse_user.manager = test_user if test_user else admin_user
            warehouse_user.created_by = admin_user
            warehouse_user.department = 'Warehouse'
            warehouse_user.save()
            
            operator_user = User.objects.get(username='operator')
            operator_user.manager = test_user if test_user else admin_user  
            operator_user.created_by = admin_user
            operator_user.department = 'Operations'
            operator_user.save()
            
            self.stdout.write(
                self.style.SUCCESS('Updated existing test users with hierarchy')
            )
        except User.DoesNotExist:
            pass
        
        self.stdout.write('\n' + '='*50)
        self.stdout.write('HIERARCHICAL USER SYSTEM CREATED')
        self.stdout.write('='*50)
        self.stdout.write('Super Admin: superadmin / admin123')
        self.stdout.write('Admin:       admin / admin123')
        self.stdout.write('Manager:     test / test')
        self.stdout.write('Warehouse:   warehouse / warehouse')
        self.stdout.write('Operator:    operator / operator')
        self.stdout.write('='*50)