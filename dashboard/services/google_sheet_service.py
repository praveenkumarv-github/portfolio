"""
Google Sheet Service
====================
Fetches a Google Sheet as a temporary .xlsx file.

Two modes — selected automatically based on environment:

  Private  — GOOGLE_SERVICE_ACCOUNT_JSON env var is set.
             Uses Google Drive API.  Sheet must be shared with the
             service account email (stays private, no public link).

  Public   — fallback when env var is absent.
             Uses the public export URL.  Sheet must be shared as
             "Anyone with the link → Viewer".

Raises:
  InvalidGoogleSheetUrl   — URL not parseable or not a Google Sheet.
  GoogleSheetAccessError  — 403/404 or sheet not shared correctly.
  GoogleSheetError        — network or unexpected failure.
"""

import contextlib
import io
import json
import logging
import os
import tempfile
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .url_utils import extract_google_sheet_id
from .workbook_validation import InvalidWorkbookError, validate_xlsx

logger = logging.getLogger(__name__)


class GoogleSheetError(Exception):
    pass


class InvalidGoogleSheetUrl(GoogleSheetError):
    pass


class GoogleSheetAccessError(GoogleSheetError):
    pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_service_account_json() -> str:
    direct_value = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if direct_value:
        return direct_value

    secret_id = os.environ.get("GOOGLE_SERVICE_ACCOUNT_SECRET_ID", "").strip()
    if not secret_id:
        return ""

    try:
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "secretsmanager",
            region_name=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
            config=Config(connect_timeout=2, read_timeout=2, retries={"max_attempts": 2}),
        )
        return client.get_secret_value(SecretId=secret_id).get("SecretString", "").strip()
    except Exception as exc:
        logger.warning("[GSheet] service-account secret unavailable: %s", type(exc).__name__)
        return ""

def _save_to_temp(payload: bytes) -> str:
    """Write bytes to a prefixed temp .xlsx; return path."""
    tmp = tempfile.NamedTemporaryFile(prefix="gsheet_", suffix=".xlsx", delete=False)
    try:
        tmp.write(payload)
    finally:
        tmp.close()
    return tmp.name


def _validate_xlsx(payload: bytes) -> None:
    """Reject oversized, malformed, or unsafe workbook responses."""
    try:
        validate_xlsx(payload)
    except InvalidWorkbookError as exc:
        raise GoogleSheetAccessError("Downloaded response is not a valid XLSX file") from exc


def _fetch_private(sheet_id: str) -> bytes:
    """
    Download via Google Drive API using a Service Account.

    Credentials are read from the GOOGLE_SERVICE_ACCOUNT_JSON env var
    (the full service account JSON as a single-line string).

    The sheet must be shared with the service account's client_email.
    """
    try:
        from google.oauth2 import service_account          # type: ignore
        from googleapiclient.discovery import build         # type: ignore
        from googleapiclient.http import MediaIoBaseDownload  # type: ignore
    except ImportError as exc:
        raise GoogleSheetError(
            "Private sheet mode requires additional packages: "
            "pip install google-auth google-auth-httplib2 google-api-python-client"
        ) from exc

    raw = _load_service_account_json()
    if not raw:
        raise GoogleSheetError("GOOGLE_SERVICE_ACCOUNT_JSON env var is empty")

    try:
        creds_info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GoogleSheetError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON") from exc

    try:
        creds = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/drive.readonly"],
        )
        drive = build("drive", "v3", credentials=creds)
        export_req = drive.files().export_media(
            fileId=sheet_id,
            mimeType=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, export_req)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        payload = buf.getvalue()
        logger.info("[GSheet][private] fetched %d bytes", len(payload))
        return payload
    except Exception as exc:
        msg = str(exc).lower()
        if any(k in msg for k in ("403", "forbidden", "permission", "access denied")):
            raise GoogleSheetAccessError(
                "Sheet not accessible with service account — "
                "share it with the service account email"
            ) from exc
        if any(k in msg for k in ("404", "not found")):
            raise GoogleSheetAccessError("Sheet not found") from exc
        raise GoogleSheetError("Failed to fetch data") from exc


def _fetch_public(sheet_id: str) -> bytes:
    """Download via public export URL."""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    req = Request(url, headers={"User-Agent": "FinanceDashboard/1.0"})
    try:
        with urlopen(req, timeout=20) as resp:
            payload = resp.read()
    except HTTPError as exc:
        if exc.code in {401, 403, 404}:
            raise GoogleSheetAccessError("Sheet not publicly accessible") from exc
        raise GoogleSheetError("Failed to fetch data") from exc
    except URLError as exc:
        raise GoogleSheetError("Failed to fetch data") from exc
    except Exception as exc:
        raise GoogleSheetError("Failed to fetch data") from exc
    return payload


@contextlib.contextmanager
def open_google_sheet(sheet_url: str):
    """
    Context manager that fetches the sheet, yields the temp file path,
    then guarantees deletion on exit — ideal for Lambda /tmp hygiene.

    Usage:
        with open_google_sheet(url) as path:
            result = parse_excel_file(path)
    """
    path = fetch_google_sheet(sheet_url)
    try:
        yield path
    finally:
        with contextlib.suppress(OSError):
            os.unlink(path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_google_sheet(sheet_url: str) -> str:
    """
    Download a Google Sheet as a temporary .xlsx file.

    Mode is selected automatically:
      - GOOGLE_SERVICE_ACCOUNT_JSON set → private (Drive API)
      - not set                         → public export URL

    Returns:
        Absolute path to temp .xlsx file.  Caller is responsible for
        deleting it after use.

    Raises:
        InvalidGoogleSheetUrl, GoogleSheetAccessError, GoogleSheetError
    """
    try:
        sheet_id = extract_google_sheet_id(sheet_url)
    except ValueError as exc:
        raise InvalidGoogleSheetUrl("Invalid Google Sheet URL") from exc

    use_private = bool(_load_service_account_json())

    if use_private:
        logger.info("[GSheet] attempting private export")
        try:
            payload = _fetch_private(sheet_id)
            _validate_xlsx(payload)
        except GoogleSheetError as exc:
            logger.warning(
                "[GSheet] private export unavailable (%s); trying public export",
                type(exc).__name__,
            )
            payload = _fetch_public(sheet_id)
            _validate_xlsx(payload)
    else:
        logger.info("[GSheet] attempting public export")
        payload = _fetch_public(sheet_id)
        _validate_xlsx(payload)

    path = _save_to_temp(payload)
    if not os.path.exists(path):
        raise GoogleSheetError("Failed to fetch data")
    return path
