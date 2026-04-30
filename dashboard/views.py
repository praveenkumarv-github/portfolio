"""
Dashboard Views — clean, thin controllers.
All business logic lives in services/.
"""
import os

from django.conf import settings
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.shortcuts import redirect, render

from .models import FileUploadHistory
from .services.aggregator import build_dashboard_context, clear_dashboard_cache
from .services.metal_price_service import (
    refresh_prices,
    set_manual_price,
)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

def dashboard_view(request):
    context = {
        "portfolio": None,
        "file_info": None,
        "alerts": [],
        "errors": [],
        "warnings": [],
        "snapshots": [],
    }

    last_upload = FileUploadHistory.objects.first()
    if not last_upload or not os.path.exists(last_upload.file_path):
        messages.info(request, "Upload an Excel file to view your dashboard.")
        return render(request, "dashboard/dashboard.html", context)

    try:
        payload = build_dashboard_context(last_upload.file_path)
        context.update(payload)
        context["file_info"] = {
            "filename": os.path.basename(last_upload.file_path),
            "uploaded_at": last_upload.uploaded_at,
        }
    except OSError as exc:
        context["errors"].append(f"File access error: {exc}")
    except Exception as exc:
        context["errors"].append(str(exc))

    return render(request, "dashboard/dashboard.html", context)


def upload_file(request):
    if request.method != "POST" or not request.FILES.get("excel_file"):
        return redirect("dashboard")

    excel_file = request.FILES["excel_file"]
    if not excel_file.name.lower().endswith(".xlsx"):
        messages.error(request, "Please upload a valid .xlsx file.")
        return redirect("dashboard")

    try:
        fs = FileSystemStorage(location=settings.MEDIA_ROOT)
        old = FileUploadHistory.objects.first()
        if old and os.path.exists(old.file_path):
            try:
                os.remove(old.file_path)
            except OSError:
                pass

        filename  = fs.save(excel_file.name, excel_file)
        file_path = os.path.join(settings.MEDIA_ROOT, filename)
        FileUploadHistory.objects.all().delete()
        FileUploadHistory.objects.create(file_path=file_path)
        clear_dashboard_cache()
        messages.success(request, f'"{excel_file.name}" loaded successfully.')
    except Exception as exc:
        messages.error(request, f"Upload error: {exc}")

    return redirect("dashboard")


def update_metal_prices(request):
    """POST: manual override.  GET ?refresh=1: force live re-fetch."""
    if request.method == "POST":
        updated = []
        for metal in ("gold", "silver"):
            raw = request.POST.get(f"{metal}_price", "").strip()
            if raw:
                try:
                    price = float(raw)
                    if set_manual_price(metal, price):
                        updated.append(f"{metal.capitalize()} ₹{price:,.0f}/g")
                except ValueError:
                    messages.error(request, f"Invalid price for {metal}: {raw}")
        if updated:
            clear_dashboard_cache()
            messages.success(request, "Prices saved → " + ", ".join(updated))
        return redirect("dashboard")

    if request.GET.get("refresh") == "1":
        prices = refresh_prices()
        clear_dashboard_cache()
        g, gs = prices.get("gold",   (0, "N/A"))
        s, ss = prices.get("silver", (0, "N/A"))
        messages.success(
            request,
            f"Prices refreshed — Gold ₹{g:,.0f}/g ({gs}) · Silver ₹{s:,.0f}/g ({ss})",
        )

    return redirect("dashboard")

