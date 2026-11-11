"""Unit tests for pure Excel file safety, packaging, and openpyxl inspection."""

import io
import zipfile
from typing import Any

import openpyxl
import pytest

from app.core.constants import (
    IMPORT_MAX_FILE_BYTES,
    IMPORT_MAX_ROWS,
    IMPORT_MAX_UNCOMPRESSED_BYTES,
    IMPORT_MAX_ZIP_ENTRIES,
)
from app.core.errors import (
    ImportEmptyError,
    ImportFileInvalidError,
    ImportFileTooLargeError,
    ImportTemplateMismatchError,
    ImportTooManyRowsError,
)
from app.services.import_file import (
    OLE_HEADER,
    inspect_and_read_workbook,
    sanitize_filename,
)
from app.services.import_template import TEMPLATE_HEADERS


def _create_minimal_xlsx(headers: list[str], rows: list[list[Any]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Transactions"
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_sanitize_filename() -> None:
    assert sanitize_filename("my_portfolio.xlsx") == "my_portfolio.xlsx"
    assert sanitize_filename("C:\\Users\\admin\\secret.xlsx") == "secret.xlsx"
    assert sanitize_filename("/var/tmp/upload.xlsx") == "upload.xlsx"
    assert sanitize_filename("bad\x00file\x1fname.xlsx") == "badfilename.xlsx"
    assert sanitize_filename(None) == "import.xlsx"
    assert len(sanitize_filename("a" * 300 + ".xlsx")) == 255


def test_valid_file_passes() -> None:
    data = _create_minimal_xlsx(
        TEMPLATE_HEADERS, [["2025-01-10", 122639, None, "buy", 10, 50, 500]]
    )
    parsed = inspect_and_read_workbook(data, "valid.xlsx")
    assert parsed.filename == "valid.xlsx"
    assert len(parsed.raw_rows) == 1
    assert parsed.raw_rows[0].cells["scheme_code"] == 122639


def test_oversized_input_rejected() -> None:
    oversized = b"P" * (IMPORT_MAX_FILE_BYTES + 1)
    with pytest.raises(ImportFileTooLargeError) as exc_info:
        inspect_and_read_workbook(oversized, "huge.xlsx")
    assert exc_info.value.code == "IMPORT_FILE_TOO_LARGE"


def test_non_xlsx_extension_rejected() -> None:
    data = _create_minimal_xlsx(TEMPLATE_HEADERS, [])
    with pytest.raises(ImportFileInvalidError) as exc:
        inspect_and_read_workbook(data, "transactions.csv")
    assert exc.value.code == "IMPORT_FILE_INVALID"


def test_not_a_zip_rejected() -> None:
    plain_text = b"This is just a plain text file renamed to xlsx"
    with pytest.raises(ImportFileInvalidError) as exc:
        inspect_and_read_workbook(plain_text, "test.xlsx")
    assert exc.value.code == "IMPORT_FILE_INVALID"


def test_ole_header_rejected() -> None:
    fake_ole = OLE_HEADER + b"\x00" * 1024
    with pytest.raises(ImportFileInvalidError) as exc:
        inspect_and_read_workbook(fake_ole, "encrypted.xlsx")
    assert exc.value.code == "IMPORT_FILE_INVALID"


def test_missing_required_zip_entries_rejected() -> None:
    # A valid zip archive that does not contain [Content_Types].xml
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("some_file.txt", "hello")
    with pytest.raises(ImportFileInvalidError) as exc:
        inspect_and_read_workbook(buf.getvalue(), "bad_zip.xlsx")
    assert exc.value.code == "IMPORT_FILE_INVALID"


def test_zip_entry_count_guard() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("xl/workbook.xml", "<workbook/>")
        for i in range(IMPORT_MAX_ZIP_ENTRIES + 5):
            zf.writestr(f"file_{i}.xml", "content")
    with pytest.raises(ImportFileInvalidError) as exc:
        inspect_and_read_workbook(buf.getvalue(), "bomb.xlsx")
    assert "too many zip entries" in exc.value.message


def test_zip_uncompressed_size_guard() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("xl/workbook.xml", "<workbook/>")
        # 21 MB of zeroes compresses into negligible bytes
        zf.writestr("xl/large.xml", b"\x00" * (IMPORT_MAX_UNCOMPRESSED_BYTES + 1024))
    with pytest.raises(ImportFileInvalidError) as exc:
        inspect_and_read_workbook(buf.getvalue(), "size_bomb.xlsx")
    assert "uncompressed size exceeds limit" in exc.value.message


def test_macro_vba_project_rejected() -> None:
    valid_data = _create_minimal_xlsx(TEMPLATE_HEADERS, [])
    # Inject vbaProject.bin into the zip
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(valid_data), "r") as zf_in:
        with zipfile.ZipFile(buf, "w") as zf_out:
            for item in zf_in.infolist():
                zf_out.writestr(item, zf_in.read(item.filename))
            zf_out.writestr("xl/vbaProject.bin", b"fake macro binary")
    with pytest.raises(ImportFileInvalidError) as exc:
        inspect_and_read_workbook(buf.getvalue(), "macro.xlsx")
    assert "Macro-enabled" in exc.value.message


def test_macro_content_type_rejected() -> None:
    valid_data = _create_minimal_xlsx(TEMPLATE_HEADERS, [])
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(valid_data), "r") as zf_in:
        with zipfile.ZipFile(buf, "w") as zf_out:
            for item in zf_in.infolist():
                if item.filename == "[Content_Types].xml":
                    macro_ct = (
                        b'<?xml version="1.0"?><Types><Override PartName="/xl/workbook.xml" '
                        b'ContentType="application/vnd.ms-excel.sheet.macroEnabled.main+xml"/>'
                        b"</Types>"
                    )
                    zf_out.writestr(item, macro_ct)
                else:
                    zf_out.writestr(item, zf_in.read(item.filename))
    with pytest.raises(ImportFileInvalidError) as exc:
        inspect_and_read_workbook(buf.getvalue(), "macro_type.xlsx")
    assert "Macro-enabled" in exc.value.message


def test_missing_required_headers_rejected() -> None:
    # Missing txn_type
    bad_headers = [h for h in TEMPLATE_HEADERS if h != "txn_type"]
    data = _create_minimal_xlsx(bad_headers, [["2025-01-10", 122639, None, 10, 50, 500]])
    with pytest.raises(ImportTemplateMismatchError) as exc:
        inspect_and_read_workbook(data, "missing_col.xlsx")
    assert "txn_type" in exc.value.details["missing_headers"]


def test_empty_file_rejected() -> None:
    data = _create_minimal_xlsx(TEMPLATE_HEADERS, [])
    with pytest.raises(ImportEmptyError) as exc:
        inspect_and_read_workbook(data, "empty.xlsx")
    assert exc.value.code == "IMPORT_EMPTY"


def test_too_many_rows_rejected() -> None:
    rows = [["2025-01-10", 122639, None, "buy", 10, 50, 500] for _ in range(IMPORT_MAX_ROWS + 1)]
    data = _create_minimal_xlsx(TEMPLATE_HEADERS, rows)
    with pytest.raises(ImportTooManyRowsError) as exc:
        inspect_and_read_workbook(data, "rows.xlsx")
    assert exc.value.code == "IMPORT_TOO_MANY_ROWS"
