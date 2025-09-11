from django.core.management.base import BaseCommand
from users.models import User, Department

class Command(BaseCommand):
    help = 'Assign existing users to departments'
    
    def handle(self, *args, **options):
        # Get departments
        try:
            operations = Department.objects.get(name='Operations')
            finance = Department.objects.get(name='Finance')
            veterinary = Department.objects.get(name='Veterinary')
            administration = Department.objects.get(name='Administration')
            quality_control = Department.objects.get(name='Quality Control')
        except Department.DoesNotExist:
            self.stdout.write(
                self.style.ERROR('Please create departments first using: python manage.py create_departments')
            )
            return
        
        # Update users with departments based on their roles
        updated_count = 0
        
        # Assign users based on roles
        for user in User.objects.all():
            old_dept = user.department
            
            # Skip if user already has a department
            if user.department:
                continue
                
            if user.role in ['super_admin', 'admin']:
                user.department = administration.name
            elif user.role == 'finance_manager':
                user.department = finance.name
            elif user.role == 'head_veterinary':
                user.department = veterinary.name
            elif user.role == 'manager':
                user.department = operations.name
            elif user.role == 'operator':
                user.department = operations.name
            elif user.role == 'warehouse_worker':
                user.department = operations.name
            else:  # viewer and others
                user.department = quality_control.name
            
            user.save()
            updated_count += 1
            
            self.stdout.write(
                self.style.SUCCESS(f'Assigned {user.username} ({user.get_role_display()}) to {user.department}')
            )
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully assigned {updated_count} users to departments')
        )
        
        # Show department statistics
        self.stdout.write(self.style.SUCCESS('\nDepartment Statistics:'))
        for dept in Department.objects.all():
            user_count = User.objects.filter(department=dept.name).count()
            self.stdout.write(f'  {dept.name}: {user_count} users')