from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction, models
from django.contrib.auth import get_user_model
from datetime import datetime
import pandas as pd
import io
from .models import Animal, CattleSection
from .serializers import AnimalSerializer, CattleSectionSerializer

User = get_user_model()

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_animals(request):
    """
    Import animals from Excel or CSV file
    """
    if 'file' not in request.FILES:
        return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
    
    file = request.FILES['file']
    
    try:
        # Read file based on extension
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        elif file.name.endswith('.xlsx') or file.name.endswith('.xls'):
            df = pd.read_excel(file)
        else:
            return Response({'error': 'Unsupported file format. Please use CSV or Excel.'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        # Column mapping - flexible to handle different column names
        column_mapping = {
            # RFID/EID columns
            'rfid': 'eid',
            'eid': 'eid', 
            'electronic_id': 'eid',
            'animal_id': 'eid',
            'id': 'eid',
            
            # Visual ID/Tag columns
            'vid': 'vid',
            'visual_id': 'vid',
            'tag': 'vid',
            'tag_number': 'vid',
            'visual_tag': 'vid',
            'brand': 'vid',
            
            # Section columns
            'section': 'section',
            'pen': 'section',
            'section_number': 'section',
            'feedlot': 'section',
            'area': 'section',
            'group': 'section',  # Added for your Excel GROUP column
            'groups': 'section',
            
            # Other columns
            'breed': 'breed',
            'gender': 'gender',
            'sex': 'gender',
            'weight': 'entry_weight',
            'entry_weight': 'entry_weight',
            'initial_weight': 'entry_weight',
            'birth_date': 'birth_date',
            'entry_date': 'entry_date',
        }
        
        # Normalize column names (lowercase, remove spaces/special chars)
        df.columns = df.columns.str.lower().str.replace(' ', '_').str.replace('-', '_').str.replace('.', '')
        
        # Map columns to model fields
        mapped_columns = {}
        for col in df.columns:
            if col in column_mapping:
                mapped_columns[col] = column_mapping[col]
        
        if not any(field == 'eid' for field in mapped_columns.values()):
            return Response({'error': 'RFID/EID column is required but not found'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        imported_count = 0
        skipped_count = 0
        errors = []
        
        with transaction.atomic():
            for index, row in df.iterrows():
                try:
                    # Extract EID (required)
                    eid = None
                    for col, field in mapped_columns.items():
                        if field == 'eid' and pd.notna(row[col]):
                            eid = str(row[col]).strip()
                            break
                    
                    if not eid:
                        errors.append(f'Row {index + 1}: Missing RFID/EID')
                        skipped_count += 1
                        continue
                    
                    # Check if animal already exists
                    if Animal.objects.filter(eid=eid).exists():
                        errors.append(f'Row {index + 1}: Animal with EID {eid} already exists')
                        skipped_count += 1
                        continue
                    
                    # Extract other fields
                    animal_data = {'eid': eid}
                    
                    # VID
                    for col, field in mapped_columns.items():
                        if field == 'vid' and pd.notna(row[col]):
                            animal_data['vid'] = str(row[col]).strip()
                            break
                    
                    # Breed
                    for col, field in mapped_columns.items():
                        if field == 'breed' and pd.notna(row[col]):
                            animal_data['breed'] = str(row[col]).strip()
                            break
                    
                    # Gender
                    for col, field in mapped_columns.items():
                        if field == 'gender' and pd.notna(row[col]):
                            gender = str(row[col]).strip().lower()
                            if gender in ['male', 'm']:
                                animal_data['gender'] = 'male'
                            elif gender in ['female', 'f']:
                                animal_data['gender'] = 'female'
                            elif gender in ['castrated', 'c']:
                                animal_data['gender'] = 'castrated'
                            break
                    
                    # Entry weight
                    for col, field in mapped_columns.items():
                        if field == 'entry_weight' and pd.notna(row[col]):
                            try:
                                animal_data['entry_weight'] = float(row[col])
                                animal_data['current_weight'] = float(row[col])
                            except (ValueError, TypeError):
                                pass
                            break
                    
                    # Section handling
                    section = None
                    section_identifier = None
                    for col, field in mapped_columns.items():
                        if field == 'section' and pd.notna(row[col]):
                            section_identifier = str(row[col]).strip()
                            break
                    
                    if section_identifier:
                        # First, try to find section by exact name match
                        section = CattleSection.objects.filter(name__iexact=section_identifier).first()
                        
                        if not section:
                            # Try to find by partial name match
                            section = CattleSection.objects.filter(name__icontains=section_identifier).first()
                        
                        if not section:
                            # Try to find by section number if it's numeric
                            try:
                                section_number = int(section_identifier)
                                section = CattleSection.objects.filter(section_number=section_number).first()
                            except ValueError:
                                section_number = None
                        
                        # If section doesn't exist, create it
                        if not section:
                            # Generate section number
                            if section_identifier.isdigit():
                                section_number = int(section_identifier)
                            else:
                                # For group names like "JUMBO BULLS", generate sequential number
                                max_section = CattleSection.objects.order_by('-section_number').first()
                                section_number = (max_section.section_number + 1) if max_section else 1
                            
                            section = CattleSection.objects.create(
                                name=section_identifier,  # Use the exact group name like "JUMBO BULLS"
                                section_number=section_number,
                                capacity=100,  # Larger capacity for group sections
                                description=f'Auto-created from import - Group: {section_identifier}',
                                created_by=request.user
                            )
                    else:
                        # Default section if none specified
                        section = CattleSection.objects.first()
                        if not section:
                            section = CattleSection.objects.create(
                                name='Default Section',
                                section_number=1,
                                capacity=50,
                                description='Default section for imports',
                                created_by=request.user
                            )
                    
                    animal_data['section'] = section
                    
                    # Set entry date to today if not provided
                    animal_data['entry_date'] = datetime.now().date()
                    animal_data['created_by'] = request.user
                    animal_data['last_updated_by'] = request.user
                    
                    # Create animal
                    animal = Animal.objects.create(**animal_data)
                    imported_count += 1
                    
                except Exception as e:
                    errors.append(f'Row {index + 1}: {str(e)}')
                    skipped_count += 1
                    continue
        
        response_data = {
            'imported_count': imported_count,
            'skipped_count': skipped_count,
            'total_rows': len(df),
            'success': True
        }
        
        if errors:
            response_data['errors'] = errors[:10]  # Limit to first 10 errors
            response_data['total_errors'] = len(errors)
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({'error': f'Failed to process file: {str(e)}'}, 
                      status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def sections_list(request):
    """
    Get list of all cattle sections
    """
    sections = CattleSection.objects.all().order_by('section_number')
    serializer = CattleSectionSerializer(sections, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def animals_list(request):
    """
    Get list of all animals with filtering options
    """
    animals = Animal.objects.select_related('section').filter(is_active=True)
    
    # Filter by section if specified
    section_id = request.GET.get('section')
    if section_id:
        animals = animals.filter(section_id=section_id)
    
    # Search filter
    search = request.GET.get('search')
    if search:
        animals = animals.filter(
            models.Q(eid__icontains=search) |
            models.Q(vid__icontains=search) |
            models.Q(breed__icontains=search)
        )
    
    serializer = AnimalSerializer(animals, many=True)
    return Response(serializer.data)