"""
Dashboard Views — clean, thin controllers.
All business logic lives in services/.
"""
import logging
import os
import shutil
import uuid
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import FileUploadHistory
from .services.google_sheet_service import (
    GoogleSheetAccessError,
    GoogleSheetError,
    InvalidGoogleSheetUrl,
    open_google_sheet,
)
from .services.aggregator import build_dashboard_context, clear_dashboard_cache
from .services.metal_price_service import (
    refresh_prices,
    set_manual_price,
)
from .services.workbook_validation import InvalidWorkbookError, validate_xlsx
from .services.net_worth_history import read_history, save_net_worth, seed_demo_history, uses_s3_history


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


def _is_google_temp_file(file_path: str) -> bool:
    name = os.path.basename(file_path)
    return name.startswith("gsheet_") or name == "latest_gsheet.xlsx"


def _local_history_enabled(request, file_path):
    return (
        settings.DEBUG
        and not os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
        and request.get_host().split(":")[0] in {"localhost", "127.0.0.1"}
        and not _is_google_temp_file(file_path)
    )


def _delete_managed_file(file_path: str) -> None:
    media_root = Path(settings.MEDIA_ROOT).resolve()
    candidate = Path(file_path).resolve()
    if not candidate.is_relative_to(media_root):
        logger.warning("Refused to delete a file outside MEDIA_ROOT")
        return
    try:
        candidate.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Failed to remove replaced workbook: %s", type(exc).__name__)


def _replace_loaded_file(file_path: str) -> None:
    old = FileUploadHistory.objects.first()
    try:
        with transaction.atomic():
            FileUploadHistory.objects.all().delete()
            FileUploadHistory.objects.create(file_path=file_path)
    except Exception:
        _delete_managed_file(file_path)
        raise

    if old and old.file_path != file_path:
        _delete_managed_file(old.file_path)

def dashboard_view(request):
    context = {
        "portfolio": None,
        "file_info": None,
        "alerts": [],
        "errors": [],
        "warnings": [],
        "snapshots": [],
        "economic_allocation": None,
    }

    last_upload = FileUploadHistory.objects.first()
    if not last_upload or not os.path.exists(last_upload.file_path):
        messages.info(request, "Upload an Excel file to view your dashboard.")
        return render(request, "dashboard/dashboard.html", context)

    try:
        payload = build_dashboard_context(last_upload.file_path)
        context.update(payload)
        context["errors"] = list(payload.get("errors", []))
        source = "Google Sheet" if _is_google_temp_file(last_upload.file_path) else "Local File"
        context["file_info"] = {
            "filename": os.path.basename(last_upload.file_path),
            "source": source,
            "uploaded_at": last_upload.uploaded_at,
        }
        context["local_net_worth_history"] = _local_history_enabled(request, last_upload.file_path)
        context["net_worth_s3_history"] = uses_s3_history()
        context["net_worth_history_enabled"] = uses_s3_history() or context["local_net_worth_history"]
        if context["net_worth_history_enabled"]:
            context["net_worth_demo"] = not uses_s3_history() and request.GET.get("history") == "demo"
            context["snapshots"] = []
            try:
                context["snapshots"] = read_history(demo=context["net_worth_demo"])
            except (OSError, ValueError, TypeError, KeyError, BotoCoreError, ClientError):
                logger.exception("Net worth history could not be read")
                context["errors"].append("Net worth history could not be read. Check storage access and record format; no history was changed.")
    except OSError as exc:
        logger.warning("Dashboard workbook access failed: %s", type(exc).__name__)
        context["errors"].append("The loaded workbook is no longer available. Please load it again.")
    except Exception:
        logger.exception("Dashboard rendering failed")
        context["errors"].append("Dashboard processing failed. Please verify the workbook and try again.")

    return render(request, "dashboard/dashboard.html", context)


@require_POST
def update_net_worth(request):
    last_upload = FileUploadHistory.objects.first()
    if not last_upload or not (uses_s3_history() or _local_history_enabled(request, last_upload.file_path)):
        messages.error(request, "Net worth history requires configured S3 storage or a local Excel upload on localhost.")
        return redirect("dashboard")
    action = request.POST.get("action", "update")
    if action not in {"update", "demo"}:
        messages.error(request, "Invalid net worth action.")
        return redirect("dashboard")
    if action == "demo" and uses_s3_history():
        messages.error(request, "Demo history is available only locally.")
        return redirect("dashboard")
    try:
        payload = build_dashboard_context(last_upload.file_path)
        portfolio = payload.get("portfolio")
        if portfolio is None or payload.get("errors"):
            messages.error(request, "Load a valid portfolio before saving net worth.")
            return redirect("dashboard")
        if action == "demo":
            seed_demo_history(portfolio.net_worth)
            return redirect(reverse("dashboard") + "?history=demo")
        save_net_worth(portfolio.net_worth)
        messages.success(request, "Net worth saved for today. Any earlier value for today was replaced.")
    except Exception:
        logger.exception("Net worth history update failed")
        messages.error(request, "Net worth could not be saved. Check the portfolio and history storage access.")
    return redirect("dashboard")


def upload_file(request):
    if request.method != "POST" or not request.FILES.get("excel_file"):
        return redirect("dashboard")

    excel_file = request.FILES["excel_file"]
    if not excel_file.name.lower().endswith(".xlsx"):
        messages.error(request, "Please upload a valid .xlsx file.")
        return redirect("dashboard")

    try:
        validate_xlsx(excel_file)
        excel_file.seek(0)
        fs = FileSystemStorage(location=settings.MEDIA_ROOT)
        filename  = fs.save(excel_file.name, excel_file)
        file_path = os.path.join(settings.MEDIA_ROOT, filename)
        _replace_loaded_file(file_path)
        clear_dashboard_cache()
        messages.success(request, f'"{excel_file.name}" loaded successfully from Local File.')
    except InvalidWorkbookError:
        messages.error(request, "Please upload a valid .xlsx file no larger than 10 MB.")
    except Exception:
        logger.exception("Workbook upload failed")
        messages.error(request, "Upload failed. Please try again.")

    return redirect("dashboard")


def load_google_sheet(request):
    if request.method != "POST":
        return redirect("dashboard")

    sheet_url = request.POST.get("sheet_url", "").strip()
    if not sheet_url:
        messages.error(request, "Invalid Google Sheet URL")
        return redirect("dashboard")

    try:
        with open_google_sheet(sheet_url) as temp_path:
            stable_dir = os.path.join(settings.MEDIA_ROOT, "gsheets")
            os.makedirs(stable_dir, exist_ok=True)
            stable_path = os.path.join(stable_dir, f"gsheet_{uuid.uuid4().hex}.xlsx")
            shutil.copy2(temp_path, stable_path)

        _replace_loaded_file(stable_path)
        clear_dashboard_cache()
        messages.success(request, "Google Sheet loaded successfully.")
    except InvalidGoogleSheetUrl:
        messages.error(request, "Invalid Google Sheet URL")
    except GoogleSheetAccessError:
        messages.error(request, "Sheet not publicly accessible")
    except GoogleSheetError:
        messages.error(request, "Failed to fetch data")
    except Exception:
        logger.exception("Google Sheet load failed")
        messages.error(request, "Failed to fetch data")

    return redirect("dashboard")


def update_metal_prices(request):
    """Apply a manual override or force live re-fetch via CSRF-protected POST."""
    if request.method != "POST":
        return redirect("dashboard")

    if request.POST.get("action") == "refresh":
        prices = refresh_prices()
        clear_dashboard_cache()
        g, gs = prices.get("gold",   (0, "N/A"))
        s, ss = prices.get("silver", (0, "N/A"))
        messages.success(
            request,
            f"Prices refreshed — Gold ₹{g:,.0f}/g ({gs}) · Silver ₹{s:,.0f}/g ({ss})",
        )
        return redirect("dashboard")

    updated = []
    for metal in ("gold", "silver"):
        raw = request.POST.get(f"{metal}_price", "").strip()
        if raw:
            try:
                price = float(raw)
                if set_manual_price(metal, price):
                    updated.append(f"{metal.capitalize()} ₹{price:,.0f}/g")
                else:
                    messages.error(request, f"Price for {metal} is outside the allowed range.")
            except ValueError:
                messages.error(request, f"Invalid price for {metal}: {raw}")
    if updated:
        clear_dashboard_cache()
        messages.success(request, "Prices saved → " + ", ".join(updated))

    return redirect("dashboard")

