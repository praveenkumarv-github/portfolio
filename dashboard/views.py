"""
Dashboard Views — clean, thin controllers.
All business logic lives in services/.
"""
import os
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.shortcuts import redirect, render

from .models import FileUploadHistory, NetWorthSnapshot
from .services.alerts import run_alerts
from .services.calculation_engine import build_portfolio
from .services.excel_parser import ExcelParserError, parse_excel_file
from .services.metal_price_service import (
    get_all_metal_prices,
    refresh_prices,
    set_manual_price,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _upsert_snapshot(data: dict) -> None:
    """Upsert monthly net-worth snapshot. Non-critical — never raises."""
    try:
        metrics = data.get("global_metrics", {})
        NetWorthSnapshot.objects.update_or_create(
            month=datetime.now().strftime("%Y-%m"),
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
        pass


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
        result = parse_excel_file(last_upload.file_path)
        if result["success"]:
            data = result["data"]
            context.update({
                "portfolio": build_portfolio(data),
                "file_info": {
                    "filename":    os.path.basename(last_upload.file_path),
                    "uploaded_at": last_upload.uploaded_at,
                },
                "alerts":   run_alerts(data),
                "errors":   result["errors"],
                "warnings": result["warnings"],
                "snapshots": list(
                    NetWorthSnapshot.objects.values(
                        "month", "total_net_worth", "mutual_funds",
                        "retirement", "liquid", "emergency_fund", "metals",
                    ).order_by("month")
                ),
            })
            _upsert_snapshot(data)
        else:
            context["errors"] = result.get("errors", ["Unknown parse error"])

    except ExcelParserError as exc:
        context["errors"].append(str(exc))
    except Exception as exc:
        context["errors"].append(f"Unexpected error: {exc}")

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
            messages.success(request, "Prices saved → " + ", ".join(updated))
        return redirect("dashboard")

    if request.GET.get("refresh") == "1":
        prices = refresh_prices()
        g, gs = prices.get("gold",   (0, "N/A"))
        s, ss = prices.get("silver", (0, "N/A"))
        messages.success(
            request,
            f"Prices refreshed — Gold ₹{g:,.0f}/g ({gs}) · Silver ₹{s:,.0f}/g ({ss})",
        )

    return redirect("dashboard")

