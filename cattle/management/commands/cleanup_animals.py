from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from cattle.models import Animal, CattleSection


class Command(BaseCommand):
    help = 'Clean up cattle database - delete all animals or animals from specific sections'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Delete ALL animals (use with caution)',
        )
        parser.add_argument(
            '--section-id',
            type=int,
            help='Delete animals from specific section ID',
        )
        parser.add_argument(
            '--section-name',
            type=str,
            help='Delete animals from section with this name',
        )
        parser.add_argument(
            '--default-sections',
            action='store_true',
            help='Delete animals from default sections (Section 1, Default Section, etc.)',
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm deletion (required for safety)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        if not options['confirm'] and not options['dry_run']:
            raise CommandError(
                'You must use --confirm to actually delete, or --dry-run to preview. '
                'This prevents accidental deletions.'
            )

        animals_to_delete = Animal.objects.none()
        description = ""

        if options['all']:
            animals_to_delete = Animal.objects.all()
            description = "ALL animals"
        
        elif options['section_id']:
            try:
                section = CattleSection.objects.get(id=options['section_id'])
                animals_to_delete = Animal.objects.filter(section=section)
                description = f"animals from section '{section.name}' (ID: {section.id})"
            except CattleSection.DoesNotExist:
                raise CommandError(f'Section with ID {options["section_id"]} does not exist')
        
        elif options['section_name']:
            sections = CattleSection.objects.filter(name__icontains=options['section_name'])
            if not sections.exists():
                raise CommandError(f'No sections found containing "{options["section_name"]}"')
            animals_to_delete = Animal.objects.filter(section__in=sections)
            section_names = ', '.join([s.name for s in sections])
            description = f"animals from sections: {section_names}"
        
        elif options['default_sections']:
            # Find default/generic sections
            default_sections = CattleSection.objects.filter(
                models.Q(name__icontains='default') |
                models.Q(name__icontains='section 1') |
                models.Q(section_number=1)
            )
            if not default_sections.exists():
                self.stdout.write(
                    self.style.WARNING('No default sections found.')
                )
                return
            
            animals_to_delete = Animal.objects.filter(section__in=default_sections)
            section_names = ', '.join([s.name for s in default_sections])
            description = f"animals from default sections: {section_names}"
        
        else:
            raise CommandError(
                'You must specify what to delete: --all, --section-id, --section-name, or --default-sections'
            )

        count = animals_to_delete.count()
        
        if count == 0:
            self.stdout.write(
                self.style.WARNING(f'No animals found to delete for: {description}')
            )
            return

        # Show what will be deleted
        self.stdout.write(f'\nFound {count} animals to delete ({description}):')
        
        # Group by section for better overview
        sections_summary = {}
        for animal in animals_to_delete.select_related('section'):
            section_name = animal.section.name
            if section_name not in sections_summary:
                sections_summary[section_name] = []
            sections_summary[section_name].append(animal.eid)
        
        for section_name, eids in sections_summary.items():
            self.stdout.write(f'  Section "{section_name}": {len(eids)} animals')
            if len(eids) <= 10:  # Show EIDs if not too many
                self.stdout.write(f'    EIDs: {", ".join(eids)}')
            else:
                self.stdout.write(f'    EIDs: {", ".join(eids[:5])} ... and {len(eids)-5} more')

        if options['dry_run']:
            self.stdout.write(
                self.style.SUCCESS(f'\n[DRY RUN] Would delete {count} animals. Use --confirm to actually delete.')
            )
            return

        # Confirm deletion
        self.stdout.write(
            self.style.WARNING(f'\nAre you sure you want to delete {count} animals?')
        )
        confirm = input('Type "DELETE" to confirm: ')
        
        if confirm != 'DELETE':
            self.stdout.write('Deletion cancelled.')
            return

        # Perform deletion
        with transaction.atomic():
            deleted_count = animals_to_delete.count()
            animals_to_delete.delete()
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully deleted {deleted_count} animals.')
        )
        
        # Show remaining animals count
        remaining_count = Animal.objects.count()
        self.stdout.write(f'Remaining animals in database: {remaining_count}')


# Add the missing import for Q
from django.db import models