import os
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .url_utils import extract_google_sheet_id


class GoogleSheetError(Exception):
    pass


class InvalidGoogleSheetUrl(GoogleSheetError):
    pass


class GoogleSheetAccessError(GoogleSheetError):
    pass


def _build_export_url(sheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"


def fetch_google_sheet(sheet_url: str) -> str:
    """
    Download a publicly shared Google Sheet as a temporary .xlsx file.

    Returns:
        Local temp file path.
    """
    try:
        sheet_id = extract_google_sheet_id(sheet_url)
    except ValueError as exc:
        raise InvalidGoogleSheetUrl("Invalid Google Sheet URL") from exc

    export_url = _build_export_url(sheet_id)
    request = Request(export_url, headers={"User-Agent": "FinanceDashboard/1.0"})

    try:
        with urlopen(request, timeout=20) as response:
            payload = response.read()
    except HTTPError as exc:
        if exc.code in {401, 403, 404}:
            raise GoogleSheetAccessError("Sheet not publicly accessible") from exc
        raise GoogleSheetError("Failed to fetch data") from exc
    except URLError as exc:
        raise GoogleSheetError("Failed to fetch data") from exc
    except Exception as exc:
        raise GoogleSheetError("Failed to fetch data") from exc

    # XLSX is a ZIP container, so valid files start with PK.
    if not payload or not payload.startswith(b"PK"):
        raise GoogleSheetAccessError("Sheet not publicly accessible")

    temp_file = tempfile.NamedTemporaryFile(prefix="gsheet_", suffix=".xlsx", delete=False)
    try:
        temp_file.write(payload)
        temp_path = temp_file.name
    finally:
        temp_file.close()

    if not os.path.exists(temp_path):
        raise GoogleSheetError("Failed to fetch data")

    return temp_path
