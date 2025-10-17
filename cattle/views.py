from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction, models
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from datetime import datetime
import pandas as pd
import io
from .models import Animal, CattleSection, WeightRecord, HealthRecord
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


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def cleanup_animals(request):
    """
    Clean up animals - superuser only
    """
    if not request.user.is_superuser:
        return Response({'error': 'Only superusers can delete animals'}, 
                      status=status.HTTP_403_FORBIDDEN)
    
    action = request.data.get('action')
    
    if action == 'delete_all':
        count = Animal.objects.count()
        Animal.objects.all().delete()
        return Response({'message': f'Deleted all {count} animals'}, 
                      status=status.HTTP_200_OK)
    
    elif action == 'delete_default_sections':
        default_sections = CattleSection.objects.filter(
            models.Q(name__icontains='default') |
            models.Q(name__icontains='section') |
            models.Q(section_number=1)
        )
        count = Animal.objects.filter(section__in=default_sections).count()
        Animal.objects.filter(section__in=default_sections).delete()
        return Response({'message': f'Deleted {count} animals from default sections'}, 
                      status=status.HTTP_200_OK)
    
    elif action == 'delete_section':
        section_id = request.data.get('section_id')
        if not section_id:
            return Response({'error': 'section_id required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        try:
            section = CattleSection.objects.get(id=section_id)
            count = Animal.objects.filter(section=section).count()
            Animal.objects.filter(section=section).delete()
            return Response({'message': f'Deleted {count} animals from {section.name}'}, 
                          status=status.HTTP_200_OK)
        except CattleSection.DoesNotExist:
            return Response({'error': 'Section not found'}, 
                          status=status.HTTP_404_NOT_FOUND)
    
    else:
        return Response({'error': 'Invalid action. Use: delete_all, delete_default_sections, or delete_section'}, 
                      status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def animals_list(request):
    """
    Get list of all animals with filtering and pagination options
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

    # Health status filter
    health_status = request.GET.get('health_status')
    if health_status:
        animals = animals.filter(health_status=health_status)

    # Get total count before pagination
    total_count = animals.count()

    # Pagination
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 50))  # Default 50 animals per page

    # Calculate pagination
    start_index = (page - 1) * page_size
    end_index = start_index + page_size

    # Apply pagination
    paginated_animals = animals[start_index:end_index]

    # Serialize data
    serializer = AnimalSerializer(paginated_animals, many=True)

    # Return paginated response
    return Response({
        'count': total_count,
        'page': page,
        'page_size': page_size,
        'total_pages': (total_count + page_size - 1) // page_size,  # Ceiling division
        'results': serializer.data
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_weight_measurements(request):
    """
    Import weight measurements from validated frontend data
    Accepts JSON data with parsed and validated weight records
    """
    try:
        # Get data from request
        section_id = request.data.get('section_id')
        records = request.data.get('records', [])

        if not records:
            return Response({'error': 'No weight records provided'},
                          status=status.HTTP_400_BAD_REQUEST)

        imported_count = 0
        updated_animals = []
        errors = []
        skipped_count = 0

        with transaction.atomic():
            for record in records:
                try:
                    eid = record.get('eid', '').strip()
                    weight = record.get('weight')
                    date_str = record.get('date')
                    notes = record.get('notes', '')

                    # Validate required fields
                    if not eid:
                        errors.append(f'Missing EID in record')
                        skipped_count += 1
                        continue

                    if not weight or weight <= 0:
                        errors.append(f'{eid}: Invalid weight value')
                        skipped_count += 1
                        continue

                    # Find animal
                    try:
                        animal = Animal.objects.get(eid__iexact=eid, is_active=True)
                    except Animal.DoesNotExist:
                        errors.append(f'{eid}: Animal not found')
                        skipped_count += 1
                        continue
                    except Animal.MultipleObjectsReturned:
                        errors.append(f'{eid}: Multiple animals found with same EID')
                        skipped_count += 1
                        continue

                    # Parse date
                    if date_str:
                        try:
                            # Try different date formats
                            for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                                try:
                                    measurement_date = datetime.strptime(str(date_str), fmt).date()
                                    break
                                except ValueError:
                                    continue
                            else:
                                # If no format worked, use today
                                measurement_date = datetime.now().date()
                        except Exception:
                            measurement_date = datetime.now().date()
                    else:
                        measurement_date = datetime.now().date()

                    # Get previous weight record for calculating gain/loss and ADG
                    previous_record = WeightRecord.objects.filter(
                        animal=animal,
                        measurement_date__lt=measurement_date
                    ).order_by('-measurement_date').first()

                    gain_loss = None
                    adg = None

                    if previous_record:
                        # Calculate weight gain/loss
                        gain_loss = float(weight) - float(previous_record.weight)

                        # Calculate ADG (Average Daily Gain)
                        days_diff = (measurement_date - previous_record.measurement_date).days
                        if days_diff > 0:
                            adg = gain_loss / days_diff

                    # Check if record already exists for this animal on this date
                    existing_record = WeightRecord.objects.filter(
                        animal=animal,
                        measurement_date=measurement_date
                    ).first()

                    if existing_record:
                        # Update existing record
                        existing_record.weight = weight
                        existing_record.gain_loss = gain_loss
                        existing_record.adg = adg
                        existing_record.notes = notes
                        existing_record.recorded_by = request.user
                        existing_record.save()  # This will also update animal.current_weight via model's save()
                    else:
                        # Create new weight record
                        WeightRecord.objects.create(
                            animal=animal,
                            weight=weight,
                            measurement_date=measurement_date,
                            gain_loss=gain_loss,
                            adg=adg,
                            notes=notes,
                            recorded_by=request.user
                        )  # Model's save() method will update animal.current_weight

                    imported_count += 1
                    updated_animals.append(eid)

                except Exception as e:
                    errors.append(f'{eid if eid else "Unknown"}: {str(e)}')
                    skipped_count += 1
                    continue

        response_data = {
            'success': True,
            'imported_count': imported_count,
            'skipped_count': skipped_count,
            'total_records': len(records),
            'updated_animals': updated_animals[:20],  # Limit to first 20 for response
            'message': f'Successfully imported {imported_count} weight measurement(s)'
        }

        if errors:
            response_data['errors'] = errors[:10]  # Limit to first 10 errors
            response_data['total_errors'] = len(errors)

        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'error': f'Failed to import weight measurements: {str(e)}',
            'success': False
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def animal_weight_records(request, animal_id):
    """
    Get all weight records for a specific animal
    Returns weight history ordered by measurement date
    """
    try:
        # Get the animal
        animal = Animal.objects.get(id=animal_id, is_active=True)

        # Get all weight records for this animal, ordered by date
        weight_records = WeightRecord.objects.filter(
            animal=animal
        ).order_by('measurement_date')

        # Serialize the data
        records_data = []
        for record in weight_records:
            records_data.append({
                'id': record.id,
                'weight': float(record.weight),
                'measurement_date': record.measurement_date.strftime('%Y-%m-%d'),
                'gain_loss': float(record.gain_loss) if record.gain_loss is not None else 0,
                'adg': float(record.adg) if record.adg is not None else 0,
                'fcr': float(record.fcr) if record.fcr is not None else 0,
                'notes': record.notes or '',
                'recorded_by': record.recorded_by.username if record.recorded_by else None,
            })

        return Response(records_data, status=status.HTTP_200_OK)

    except Animal.DoesNotExist:
        return Response({
            'error': 'Animal not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': f'Failed to fetch weight records: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_section_weights(request, section_id):
    """
    Export all animals and their complete weight history for a specific section to Excel
    Returns an Excel file with all weight measurements
    """
    try:
        # Get the section
        try:
            section = CattleSection.objects.get(id=section_id)
        except CattleSection.DoesNotExist:
            return Response({
                'error': 'Section not found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Get all active animals in this section
        animals = Animal.objects.filter(section=section, is_active=True).order_by('eid')

        if not animals.exists():
            return Response({
                'error': 'No animals found in this section'
            }, status=status.HTTP_404_NOT_FOUND)

        # Prepare data for Excel export
        export_data = []

        for animal in animals:
            # Get all weight records for this animal, ordered by date
            weight_records = WeightRecord.objects.filter(
                animal=animal
            ).order_by('measurement_date')

            if weight_records.exists():
                # Remove duplicates by keeping only the latest record for each date
                # This handles cases where multiple records exist for the same date
                seen_dates = {}
                for record in weight_records:
                    date_key = record.measurement_date
                    if date_key not in seen_dates or record.id > seen_dates[date_key].id:
                        seen_dates[date_key] = record

                # Convert to list sorted by date
                records_list = sorted(seen_dates.values(), key=lambda x: x.measurement_date)

                for idx, record in enumerate(records_list):
                    # Recalculate gain/loss and ADG based on previous record
                    if idx > 0:
                        previous_record = records_list[idx - 1]
                        gain_loss = float(record.weight) - float(previous_record.weight)
                        days_diff = (record.measurement_date - previous_record.measurement_date).days
                        adg = gain_loss / days_diff if days_diff > 0 else 0
                    else:
                        gain_loss = 0
                        adg = 0

                    export_data.append({
                        'EID': animal.eid,
                        'Section': section.name,
                        'Breed': animal.breed or '',
                        'Gender': animal.gender,
                        'Entry Date': animal.entry_date.strftime('%Y-%m-%d'),
                        'Entry Weight (kg)': float(animal.entry_weight) if animal.entry_weight else '',
                        'Measurement Date': record.measurement_date.strftime('%Y-%m-%d'),
                        'Weight (kg)': float(record.weight),
                        'Gain/Loss (kg)': round(gain_loss, 2),
                        'ADG (kg/day)': round(adg, 2),
                        'Days in System': (record.measurement_date - animal.entry_date).days,
                        'Notes': record.notes or '',
                    })
            else:
                # Animal has no weight records, show entry weight only
                export_data.append({
                    'EID': animal.eid,
                    'Section': section.name,
                    'Breed': animal.breed or '',
                    'Gender': animal.gender,
                    'Entry Date': animal.entry_date.strftime('%Y-%m-%d'),
                    'Entry Weight (kg)': float(animal.entry_weight) if animal.entry_weight else '',
                    'Measurement Date': '',
                    'Weight (kg)': float(animal.current_weight) if animal.current_weight else '',
                    'Gain/Loss (kg)': '',
                    'ADG (kg/day)': '',
                    'Days in System': animal.days_in_system,
                    'Notes': 'No weight records',
                })

        # Create DataFrame
        df = pd.DataFrame(export_data)

        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Weight Records', index=False)

            # Get workbook and worksheet objects
            workbook = writer.book
            worksheet = writer.sheets['Weight Records']

            # Add formatting
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#57552f',
                'font_color': 'white',
                'border': 1
            })

            # Format header row
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)

            # Set column widths
            worksheet.set_column('A:A', 20)  # EID
            worksheet.set_column('B:B', 15)  # Section
            worksheet.set_column('C:C', 12)  # Breed
            worksheet.set_column('D:D', 10)  # Gender
            worksheet.set_column('E:E', 12)  # Entry Date
            worksheet.set_column('F:F', 16)  # Entry Weight
            worksheet.set_column('G:G', 16)  # Measurement Date
            worksheet.set_column('H:H', 12)  # Weight
            worksheet.set_column('I:I', 14)  # Gain/Loss
            worksheet.set_column('J:J', 14)  # ADG
            worksheet.set_column('K:K', 14)  # Days in System
            worksheet.set_column('L:L', 30)  # Notes

        output.seek(0)

        # Create response with Excel file
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

        # Generate filename with section name and current date
        filename = f'{section.name}_Weight_Records_{datetime.now().strftime("%Y%m%d")}.xlsx'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response

    except Exception as e:
        return Response({
            'error': f'Failed to export weight records: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def animal_health_records(request, animal_id):
    """
    Get all health records for a specific animal
    Returns health history ordered by record date
    """
    try:
        # Get the animal
        animal = Animal.objects.get(id=animal_id, is_active=True)

        # Get all health records for this animal, ordered by date
        health_records = HealthRecord.objects.filter(
            animal=animal
        ).order_by('-record_date')

        # Serialize the data
        records_data = []
        for record in health_records:
            records_data.append({
                'id': record.id,
                'record_date': record.record_date.strftime('%Y-%m-%d'),
                'record_type': record.record_type,
                'diagnosis': record.diagnosis or '',
                'treatment': record.treatment or '',
                'medicine_used': record.medicine_used or '',
                'dosage': record.dosage or '',
                'follow_up_date': record.follow_up_date.strftime('%Y-%m-%d') if record.follow_up_date else None,
                'follow_up_required': record.follow_up_required,
                'treatment_cost': float(record.treatment_cost) if record.treatment_cost else None,
                'veterinarian': record.veterinarian or '',
                'notes': record.notes or '',
                'recorded_by': record.recorded_by.username if record.recorded_by else None,
            })

        return Response(records_data, status=status.HTTP_200_OK)

    except Animal.DoesNotExist:
        return Response({
            'error': 'Animal not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': f'Failed to fetch health records: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def weight_trend(request):
    """
    Get aggregated weight trend data for the last 7 days
    Returns daily totals and averages for all active animals
    """
    try:
        from datetime import timedelta

        # Get date range (last 7 days)
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=6)

        # Get all weight records in the date range
        weight_records = WeightRecord.objects.filter(
            measurement_date__gte=start_date,
            measurement_date__lte=end_date,
            animal__is_active=True
        ).values('measurement_date').annotate(
            total_weight=models.Sum('weight'),
            average_weight=models.Avg('weight'),
            animal_count=models.Count('animal', distinct=True)
        ).order_by('measurement_date')

        # Convert to list and fill in missing dates
        trend_data = []
        current_date = start_date
        records_dict = {r['measurement_date']: r for r in weight_records}

        # Get current state for fallback
        current_animals = Animal.objects.filter(is_active=True, current_weight__isnull=False)
        current_total = current_animals.aggregate(total=models.Sum('current_weight'))['total'] or 0
        current_avg = current_animals.aggregate(avg=models.Avg('current_weight'))['avg'] or 0
        current_count = current_animals.count()

        while current_date <= end_date:
            if current_date in records_dict:
                record = records_dict[current_date]
                trend_data.append({
                    'date': current_date.strftime('%Y-%m-%d'),
                    'totalWeight': float(record['total_weight'] or 0),
                    'averageWeight': float(record['average_weight'] or 0),
                    'animalCount': record['animal_count']
                })
            else:
                # Use current values for dates without records
                trend_data.append({
                    'date': current_date.strftime('%Y-%m-%d'),
                    'totalWeight': float(current_total),
                    'averageWeight': float(current_avg),
                    'animalCount': current_count
                })
            current_date += timedelta(days=1)

        return Response({
            'success': True,
            'trend': trend_data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'error': f'Failed to fetch weight trend: {str(e)}',
            'success': False
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_health_record(request):
    """
    Add a new health record for an animal
    """
    try:
        animal_id = request.data.get('animal_id')
        record_date = request.data.get('record_date')
        record_type = request.data.get('record_type')
        diagnosis = request.data.get('diagnosis', '')
        treatment = request.data.get('treatment', '')
        medicine_used = request.data.get('medicine_used', '')
        dosage = request.data.get('dosage', '')
        follow_up_date = request.data.get('follow_up_date')
        follow_up_required = request.data.get('follow_up_required', False)
        treatment_cost = request.data.get('treatment_cost')
        veterinarian = request.data.get('veterinarian', '')
        notes = request.data.get('notes', '')

        # Validate required fields
        if not animal_id:
            return Response({'error': 'Animal ID is required'},
                          status=status.HTTP_400_BAD_REQUEST)

        if not record_type:
            return Response({'error': 'Record type is required'},
                          status=status.HTTP_400_BAD_REQUEST)

        # Find animal
        try:
            animal = Animal.objects.get(id=animal_id, is_active=True)
        except Animal.DoesNotExist:
            return Response({'error': 'Animal not found'},
                          status=status.HTTP_404_NOT_FOUND)

        # Parse record date
        if record_date:
            try:
                for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                    try:
                        parsed_record_date = datetime.strptime(str(record_date), fmt).date()
                        break
                    except ValueError:
                        continue
                else:
                    parsed_record_date = datetime.now().date()
            except Exception:
                parsed_record_date = datetime.now().date()
        else:
            parsed_record_date = datetime.now().date()

        # Parse follow-up date if provided
        parsed_follow_up_date = None
        if follow_up_date:
            try:
                for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                    try:
                        parsed_follow_up_date = datetime.strptime(str(follow_up_date), fmt).date()
                        break
                    except ValueError:
                        continue
            except Exception:
                parsed_follow_up_date = None

        # Create health record
        health_record = HealthRecord.objects.create(
            animal=animal,
            record_date=parsed_record_date,
            record_type=record_type,
            diagnosis=diagnosis,
            treatment=treatment,
            medicine_used=medicine_used,
            dosage=dosage,
            follow_up_date=parsed_follow_up_date,
            follow_up_required=follow_up_required,
            treatment_cost=treatment_cost if treatment_cost else None,
            veterinarian=veterinarian,
            notes=notes,
            recorded_by=request.user
        )

        # Update animal health status if it's an illness or injury
        if record_type in ['illness', 'injury']:
            animal.health_status = 'sick'
            animal.save()
        elif record_type == 'treatment':
            animal.health_status = 'under_treatment'
            animal.save()

        return Response({
            'success': True,
            'message': 'Health record added successfully',
            'record_id': health_record.id
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({
            'error': f'Failed to add health record: {str(e)}',
            'success': False
        }, status=status.HTTP_400_BAD_REQUEST)