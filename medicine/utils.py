import pandas as pd
import io
from django.core.files.uploadedfile import InMemoryUploadedFile
from .models import Medicine, MedicineClass
from django.db import transaction
import re


def clean_numeric_value(value):
    """Clean and convert numeric values, handling spaces and commas"""
    if pd.isna(value) or value == '':
        return 0
    
    # Convert to string and clean
    value_str = str(value).strip()
    
    # Remove spaces and commas from numbers
    value_str = re.sub(r'[,\s]', '', value_str)
    
    try:
        return float(value_str)
    except (ValueError, TypeError):
        return 0


def process_excel_upload(file, user):
    """Process uploaded Excel/CSV file and import medicines"""
    results = {
        'success': True,
        'created_count': 0,
        'updated_count': 0,
        'skipped_count': 0,
        'errors': []
    }
    
    try:
        # Determine file type and read accordingly
        if file.name.endswith('.csv'):
            df = pd.read_csv(file, encoding='utf-8')
        elif file.name.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file)
        else:
            results['success'] = False
            results['errors'].append('Unsupported file format. Please upload CSV or Excel file.')
            return results
        
        # Clean column names (remove BOM and extra spaces)
        df.columns = df.columns.str.strip().str.replace('\ufeff', '')
        
        # Expected columns mapping
        expected_columns = {
            'CLASS': ['CLASS', 'Category', 'Medicine Class', 'Type'],
            'PRODUCT': ['PRODUCT', 'Product Name', 'Medicine', 'Name'],
            'STOCK REMAINING': ['STOCK REMAINING', 'Stock', 'Current Stock', 'Quantity'],
        }
        
        # Try to find the right columns
        column_mapping = {}
        for expected, alternatives in expected_columns.items():
            found_column = None
            for alt in alternatives:
                if alt in df.columns:
                    found_column = alt
                    break
            if found_column:
                column_mapping[expected] = found_column
            else:
                results['success'] = False
                results['errors'].append(f'Required column "{expected}" not found. Available columns: {list(df.columns)}')
                return results
        
        # Process each row
        with transaction.atomic():
            for index, row in df.iterrows():
                try:
                    # Extract data
                    class_name = str(row[column_mapping['CLASS']]).strip()
                    product_name = str(row[column_mapping['PRODUCT']]).strip()
                    
                    # Skip empty rows
                    if pd.isna(class_name) or pd.isna(product_name) or class_name == '' or product_name == '' or product_name.lower() == 'nan':
                        results['skipped_count'] += 1
                        continue
                    
                    # Clean stock remaining
                    stock_remaining = clean_numeric_value(row[column_mapping['STOCK REMAINING']])
                    
                    # Try to determine unit from the next column or use default
                    unit = 'ml'  # default
                    try:
                        # Look for unit in the column after stock remaining
                        unit_column_index = df.columns.get_loc(column_mapping['STOCK REMAINING']) + 1
                        if unit_column_index < len(df.columns):
                            potential_unit = row.iloc[unit_column_index]
                            if pd.notna(potential_unit) and str(potential_unit).strip():
                                unit = str(potential_unit).strip()
                    except:
                        pass
                    
                    # Create or get medicine class
                    medicine_class, created = MedicineClass.objects.get_or_create(
                        name=class_name,
                        defaults={'description': f'Auto-created from upload: {class_name}'}
                    )
                    
                    # Try to update existing medicine or create new one
                    medicine, created = Medicine.objects.get_or_create(
                        product=product_name,
                        medicine_class=medicine_class,
                        defaults={
                            'stock_remaining': stock_remaining,
                            'unit': unit,
                            'minimum_stock': max(stock_remaining * 0.2, 10),  # Set minimum stock to 20% of current or 10
                            'created_by': user
                        }
                    )
                    
                    if created:
                        results['created_count'] += 1
                    else:
                        # Update existing medicine
                        medicine.stock_remaining = stock_remaining
                        medicine.unit = unit
                        medicine.save()
                        results['updated_count'] += 1
                
                except Exception as e:
                    results['errors'].append(f'Row {index + 1}: {str(e)}')
                    results['skipped_count'] += 1
                    continue
    
    except Exception as e:
        results['success'] = False
        results['errors'].append(f'File processing error: {str(e)}')
    
    return results


def generate_sample_template():
    """Generate a sample CSV template for download"""
    sample_data = [
        ['Antibiotics', 'Sample Antibiotic', 1000, 'ml', 500],
        ['Vaccines', 'Sample Vaccine', 2000, 'ml', 200],
        ['Supplements', 'Sample Supplement', 500, 'tabs', 100],
    ]
    
    df = pd.DataFrame(sample_data, columns=[
        'CLASS', 'PRODUCT', 'STOCK REMAINING', 'UNIT', 'MINIMUM STOCK'
    ])
    
    # Convert to CSV string
    output = io.StringIO()
    df.to_csv(output, index=False)
    csv_string = output.getvalue()
    output.close()
    
    return csv_string