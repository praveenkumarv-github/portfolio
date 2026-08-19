import io
import zipfile

import pytest

from dashboard.services import workbook_validation
from dashboard.services.workbook_validation import InvalidWorkbookError, validate_xlsx


def _archive(extra_content: bytes = b"") -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("xl/workbook.xml", "<workbook />")
        if extra_content:
            archive.writestr("xl/sharedStrings.xml", extra_content)
    return payload.getvalue()


def test_valid_workbook_container_is_accepted():
    validate_xlsx(_archive())


def test_missing_workbook_metadata_is_rejected():
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("unrelated.txt", "data")
    with pytest.raises(InvalidWorkbookError):
        validate_xlsx(payload.getvalue())


def test_expanded_archive_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(workbook_validation, "MAX_XLSX_EXPANDED_BYTES", 32)
    with pytest.raises(InvalidWorkbookError, match="expands beyond"):
        validate_xlsx(_archive(b"A" * 128))