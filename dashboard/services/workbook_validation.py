import io
import zipfile
from typing import BinaryIO, Union


MAX_XLSX_BYTES = 10 * 1024 * 1024
MAX_XLSX_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_XLSX_ENTRIES = 2_000
_REQUIRED_PARTS = {"[Content_Types].xml", "xl/workbook.xml"}


class InvalidWorkbookError(ValueError):
    pass


def validate_xlsx(source: Union[bytes, BinaryIO]) -> None:
    """Validate an XLSX container without extracting it to disk."""
    stream = io.BytesIO(source) if isinstance(source, bytes) else source
    original_position = stream.tell()
    try:
        stream.seek(0, 2)
        compressed_size = stream.tell()
        if compressed_size <= 0 or compressed_size > MAX_XLSX_BYTES:
            raise InvalidWorkbookError("Workbook exceeds the 10 MB limit")

        stream.seek(0)
        try:
            with zipfile.ZipFile(stream) as archive:
                entries = archive.infolist()
                if len(entries) > MAX_XLSX_ENTRIES:
                    raise InvalidWorkbookError("Workbook contains too many files")
                if any(entry.flag_bits & 0x1 for entry in entries):
                    raise InvalidWorkbookError("Encrypted workbooks are not supported")

                expanded_size = sum(entry.file_size for entry in entries)
                if expanded_size > MAX_XLSX_EXPANDED_BYTES:
                    raise InvalidWorkbookError("Workbook expands beyond the safe limit")

                names = {entry.filename for entry in entries}
                if not _REQUIRED_PARTS.issubset(names):
                    raise InvalidWorkbookError("File is not a valid XLSX workbook")
        except zipfile.BadZipFile as exc:
            raise InvalidWorkbookError("File is not a valid XLSX workbook") from exc
    finally:
        stream.seek(original_position)