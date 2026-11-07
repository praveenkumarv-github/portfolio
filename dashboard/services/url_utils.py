import re
from urllib.parse import parse_qs, urlparse


def extract_google_sheet_id(sheet_url: str) -> str:
    """Extract Google Sheet ID from common docs.google.com URL formats."""
    if not sheet_url or not isinstance(sheet_url, str):
        raise ValueError("Invalid Google Sheet URL")

    parsed = urlparse(sheet_url.strip())
    if parsed.scheme != "https" or parsed.netloc not in {"docs.google.com", "www.docs.google.com"}:
        raise ValueError("Invalid Google Sheet URL")

    # Pattern: /spreadsheets/d/{SHEET_ID}/...
    match = re.fullmatch(r"/spreadsheets/d/([a-zA-Z0-9_-]+)(?:/.*)?", parsed.path)
    if match:
        return match.group(1)

    # Pattern: ...?id={SHEET_ID}
    query_id = parse_qs(parsed.query).get("id", [""])[0]
    if parsed.path.startswith("/spreadsheets/") and re.fullmatch(r"[a-zA-Z0-9_-]+", query_id):
        return query_id

    raise ValueError("Invalid Google Sheet URL")
