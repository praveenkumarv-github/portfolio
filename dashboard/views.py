"""
Dashboard Views
Handle all view logic for the finance dashboard
"""
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from datetime import datetime
import os
from .services.excel_parser import parse_excel_file, ExcelParserError
from .services.metal_price_service import set_manual_price, refresh_prices, get_all_metal_prices
from .services.alerts import run_alerts
from .models import FileUploadHistory, NetWorthSnapshot


def _capture_snapshot(data: dict) -> None:
    """
    Upsert a NetWorthSnapshot for the current month.
    Safe to call on every page load — only one row per YYYY-MM.
    """
    try:
        month = datetime.now().strftime("%Y-%m")
        metrics = data.get("global_metrics", {})
        NetWorthSnapshot.objects.update_or_create(
            month=month,
            defaults={
                "total_net_worth": metrics.get("total_net_worth", 0),
                "mutual_funds":    data.get("mutual_funds_summary", {}).get("total_current_value", 0),
                "retirement":      data.get("retirement_total", 0),
                "liquid":          data.get("liquid_total", 0),
                "emergency_fund":  data.get("emergency_fund_total", 0),
                "metals":          data.get("metals_total", 0),
            },
        )
    except Exception:
        pass   # snapshots are non-critical


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
                # Run alerts engine
                context['alerts'] = run_alerts(result['data'])
                # Capture monthly snapshot
                _capture_snapshot(result['data'])
                # History for sparkline
                context['snapshots'] = list(
                    NetWorthSnapshot.objects.values(
                        'month', 'total_net_worth', 'mutual_funds',
                        'retirement', 'liquid', 'emergency_fund', 'metals'
                    ).order_by('month')
                )
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


def update_metal_prices(request):
    """
    Handle manual metal price override or force-refresh.
    POST: gold_price, silver_price → store as manual
    GET with ?refresh=1 → force live fetch
    """
    if request.method == 'POST':
        updated = []
        for metal in ['gold', 'silver']:
            raw = request.POST.get(f'{metal}_price', '').strip()
            if raw:
                try:
                    price = float(raw)
                    if set_manual_price(metal, price):
                        updated.append(f'{metal.capitalize()}: ₹{price:.0f}/g')
                except ValueError:
                    messages.error(request, f'Invalid price for {metal}: {raw}')

        if updated:
            messages.success(request, f'Prices updated → {", ".join(updated)}')
        return redirect('dashboard')

    if request.GET.get('refresh') == '1':
        prices = refresh_prices()
        gold_p, gold_src = prices.get('gold', (0, 'N/A'))
        silver_p, silver_src = prices.get('silver', (0, 'N/A'))
        messages.success(
            request,
            f'Prices refreshed — Gold: ₹{gold_p:.0f}/g ({gold_src}) | '
            f'Silver: ₹{silver_p:.0f}/g ({silver_src})'
        )
        return redirect('dashboard')

    return redirect('dashboard')
