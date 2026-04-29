"""
Dashboard Views
Handle all view logic for the finance dashboard
"""
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.conf import settings
import os
from .services.excel_parser import parse_excel_file, ExcelParserError
from .models import FileUploadHistory


def dashboard_view(request):
    """
    Main dashboard view
    Displays financial data from the last uploaded Excel file
    """
    context = {
        'data': None,
        'file_info': None,
        'errors': [],
        'warnings': [],
    }
    
    # Get the last uploaded file from history
    last_upload = FileUploadHistory.objects.first()
    
    if last_upload and os.path.exists(last_upload.file_path):
        try:
            # Parse the Excel file
            result = parse_excel_file(last_upload.file_path)
            
            if result['success']:
                context['data'] = result['data']
                context['errors'] = result['errors']
                context['warnings'] = result['warnings']
                context['file_info'] = {
                    'filename': os.path.basename(last_upload.file_path),
                    'uploaded_at': last_upload.uploaded_at,
                }
            else:
                messages.error(request, 'Failed to parse Excel file')
                context['errors'] = result.get('errors', ['Unknown error'])
                
        except ExcelParserError as e:
            messages.error(request, f'Error: {str(e)}')
            context['errors'].append(str(e))
        except Exception as e:
            messages.error(request, f'Unexpected error: {str(e)}')
            context['errors'].append(str(e))
    else:
        messages.info(request, 'No Excel file uploaded yet. Please upload a file to get started.')
    
    return render(request, 'dashboard/dashboard.html', context)


def upload_file(request):
    """
    Handle file upload
    Accepts Excel file upload and stores the file path
    """
    if request.method == 'POST' and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']
        
        # Validate file extension
        if not excel_file.name.endswith('.xlsx'):
            messages.error(request, 'Please upload a valid .xlsx file')
            return redirect('dashboard')
        
        try:
            # Save the uploaded file
            fs = FileSystemStorage(location=settings.MEDIA_ROOT)
            
            # Delete old file if exists
            if FileUploadHistory.objects.exists():
                last_upload = FileUploadHistory.objects.first()
                if os.path.exists(last_upload.file_path):
                    try:
                        os.remove(last_upload.file_path)
                    except:
                        pass
            
            filename = fs.save(excel_file.name, excel_file)
            file_path = os.path.join(settings.MEDIA_ROOT, filename)
            
            # Save to history (clear old entries)
            FileUploadHistory.objects.all().delete()
            FileUploadHistory.objects.create(file_path=file_path)
            
            messages.success(request, f'File "{excel_file.name}" uploaded successfully!')
            
        except Exception as e:
            messages.error(request, f'Error uploading file: {str(e)}')
    
    return redirect('dashboard')
