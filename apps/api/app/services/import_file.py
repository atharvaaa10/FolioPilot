"""In-memory safe inspection and openpyxl parsing of uploaded Excel workbooks."""

import hashlib
import io
import os
import re
import zipfile
from dataclasses import dataclass
from typing import Any

import defusedxml  # noqa: F401 - ensures defusedxml is active
import openpyxl

from app.core.constants import (
    IMPORT_MAX_FILE_BYTES,
    IMPORT_MAX_ROWS,
    IMPORT_MAX_SCAN_ROWS,
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

OLE_HEADER = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
REQUIRED_ZIP_ENTRIES = {"[Content_Types].xml", "xl/workbook.xml"}
CONSECUTIVE_EMPTY_ROWS_LIMIT = 1000

REQUIRED_HEADER_COLS = ["txn_date", "txn_type"]


@dataclass(frozen=True)
class RawRow:
    """Raw unnormalized row extracted from the Excel spreadsheet."""

    row_number: int  # 1-based row number in sheet
    cells: dict[str, Any]  # normalized_header -> raw value
    formula_cells_without_value: set[str]  # set of column names where formula has no cached value


@dataclass(frozen=True)
class ParsedWorkbook:
    """Safe pre-parsed workbook contents ready for normalization."""

    filename: str
    file_sha256: str
    file_size: int
    headers: list[str]
    extra_columns: list[str]
    raw_rows: list[RawRow]


def sanitize_filename(filename: str | None) -> str:
    """Sanitize uploaded filename to a safe basename of max 255 chars without control characters."""
    if not filename:
        return "import.xlsx"
    # Normalize both Windows and Unix slashes to handle cross-platform uploads
    clean = filename.replace("\\", "/")
    base = os.path.basename(clean)
    # Strip control characters (ASCII 0-31 and 127)
    sanitized = re.sub(r"[\x00-\x1f\x7f]", "", base).strip()
    if not sanitized:
        sanitized = "import.xlsx"
    return sanitized[:255]


def normalize_header(header_val: Any) -> str:
    """Normalize header string: trim, lowercase, spaces converted to underscores."""
    if header_val is None:
        return ""
    text = str(header_val).strip().lower()
    return re.sub(r"\s+", "_", text)


def inspect_and_read_workbook(
    file_bytes: bytes,
    filename: str | None,
) -> ParsedWorkbook:
    """Validate workbook structure in-memory and extract raw rows."""
    file_size = len(file_bytes)
    if file_size > IMPORT_MAX_FILE_BYTES:
        raise ImportFileTooLargeError(
            f"File size {file_size} exceeds limit of {IMPORT_MAX_FILE_BYTES} bytes",
            details={"file_size": file_size, "max_bytes": IMPORT_MAX_FILE_BYTES},
        )

    clean_filename = sanitize_filename(filename)
    if not clean_filename.lower().endswith(".xlsx"):
        raise ImportFileInvalidError("File must have a .xlsx extension")

    # 1. Reject OLE Header (encrypted Office file or legacy compound document)
    if file_bytes.startswith(OLE_HEADER):
        raise ImportFileInvalidError("Encrypted or legacy binary Excel files are not supported")

    # 2. Validate zip structure
    file_io = io.BytesIO(file_bytes)
    if not zipfile.is_zipfile(file_io):
        raise ImportFileInvalidError("Uploaded file is not a valid Excel (.xlsx) archive")

    file_io.seek(0)
    try:
        with zipfile.ZipFile(file_io, "r") as zf:
            infolist = zf.infolist()
            if len(infolist) > IMPORT_MAX_ZIP_ENTRIES:
                raise ImportFileInvalidError(
                    f"Excel file contains too many zip entries "
                    f"({len(infolist)} > {IMPORT_MAX_ZIP_ENTRIES})"
                )

            total_uncompressed = sum(info.file_size for info in infolist)
            if total_uncompressed > IMPORT_MAX_UNCOMPRESSED_BYTES:
                raise ImportFileInvalidError(
                    f"Excel file uncompressed size exceeds limit "
                    f"({total_uncompressed} > {IMPORT_MAX_UNCOMPRESSED_BYTES})"
                )

            entry_names = set(zf.namelist())
            for req in REQUIRED_ZIP_ENTRIES:
                if req not in entry_names:
                    raise ImportFileInvalidError(f"Missing required Excel package entry: {req}")

            # Macro-enabled check
            if any(name.endswith("vbaProject.bin") for name in entry_names):
                raise ImportFileInvalidError("Macro-enabled workbooks (.xlsm) are not allowed")

            # Check [Content_Types].xml for xlsm or macro content types
            try:
                content_types = zf.read("[Content_Types].xml").decode("utf-8", errors="ignore")
                if "application/vnd.ms-excel.sheet.macroEnabled.main+xml" in content_types:
                    raise ImportFileInvalidError("Macro-enabled workbooks are not allowed")
            except Exception as e:
                if isinstance(e, ImportFileInvalidError):
                    raise
                raise ImportFileInvalidError("Could not inspect Excel package content types") from e
    except zipfile.BadZipFile as e:
        raise ImportFileInvalidError("Malformed or corrupted zip archive") from e

    # 3. Detect formulas without values with a non-data_only pass
    file_io.seek(0)
    formula_cells_by_row: dict[int, set[int]] = {}  # row_idx -> set of col_idx
    try:
        wb_formula = openpyxl.load_workbook(file_io, read_only=True, data_only=False)
        sheet_name_formula = (
            "Transactions" if "Transactions" in wb_formula.sheetnames else wb_formula.sheetnames[0]
        )
        ws_formula = wb_formula[sheet_name_formula]
        for row_idx, row in enumerate(ws_formula.iter_rows(values_only=False), start=1):
            if row_idx == 1:
                continue
            for col_idx, cell in enumerate(row, start=1):
                if cell.data_type == "f" or (
                    isinstance(cell.value, str) and cell.value.startswith("=")
                ):
                    if row_idx not in formula_cells_by_row:
                        formula_cells_by_row[row_idx] = set()
                    formula_cells_by_row[row_idx].add(col_idx)
        wb_formula.close()
    except Exception as e:
        raise ImportFileInvalidError("Could not read Excel workbook structure") from e

    # 4. Read cached values with data_only=True
    file_io.seek(0)
    try:
        wb_data = openpyxl.load_workbook(file_io, read_only=True, data_only=True)
    except Exception as e:
        raise ImportFileInvalidError("Could not parse Excel workbook data") from e

    sheet_name = "Transactions" if "Transactions" in wb_data.sheetnames else wb_data.sheetnames[0]
    ws = wb_data[sheet_name]

    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        wb_data.close()
        raise ImportEmptyError("Excel file has no headers or data") from None

    if not header_row or all(v is None for v in header_row):
        wb_data.close()
        raise ImportEmptyError("Excel file header row is empty")

    # Map column index -> normalized header
    col_map: dict[int, str] = {}
    normalized_headers: list[str] = []
    for col_idx, h_val in enumerate(header_row, start=1):
        if h_val is not None and str(h_val).strip():
            norm_h = normalize_header(h_val)
            col_map[col_idx] = norm_h
            normalized_headers.append(norm_h)

    # Validate required headers
    missing_headers = [h for h in REQUIRED_HEADER_COLS if h not in col_map.values()]
    has_fund_ident = "scheme_code" in col_map.values() or "isin" in col_map.values()
    if not has_fund_ident:
        missing_headers.append("scheme_code or isin")

    if missing_headers:
        wb_data.close()
        raise ImportTemplateMismatchError(
            f"Missing required columns in header: {', '.join(missing_headers)}",
            details={"missing_headers": missing_headers},
        )

    known_headers = {
        "txn_date",
        "scheme_code",
        "isin",
        "txn_type",
        "units",
        "nav",
        "amount",
        "notes",
        "fund_name",
    }
    extra_columns = [h for h in normalized_headers if h not in known_headers]

    raw_rows: list[RawRow] = []
    consecutive_empty = 0
    total_scanned = 0

    for sheet_row_idx, row_values in enumerate(rows_iter, start=2):
        total_scanned += 1
        if total_scanned > IMPORT_MAX_SCAN_ROWS:
            wb_data.close()
            raise ImportTooManyRowsError(
                f"File scanned row limit ({IMPORT_MAX_SCAN_ROWS}) exceeded",
                details={"scanned_rows": total_scanned},
            )

        # Check if row is completely empty
        if not row_values or all(
            v is None or (isinstance(v, str) and not v.strip()) for v in row_values
        ):
            consecutive_empty += 1
            if consecutive_empty >= CONSECUTIVE_EMPTY_ROWS_LIMIT:
                break
            continue

        consecutive_empty = 0

        # Build cells map for row
        cells: dict[str, Any] = {}
        formulas_without_value: set[str] = set()

        for col_idx, val in enumerate(row_values, start=1):
            if col_idx in col_map:
                header_name = col_map[col_idx]
                cells[header_name] = val
                # Check formula cached value
                if (
                    sheet_row_idx in formula_cells_by_row
                    and col_idx in formula_cells_by_row[sheet_row_idx]
                    and val is None
                ):
                    formulas_without_value.add(header_name)

        raw_rows.append(
            RawRow(
                row_number=sheet_row_idx,
                cells=cells,
                formula_cells_without_value=formulas_without_value,
            )
        )

        if len(raw_rows) > IMPORT_MAX_ROWS:
            wb_data.close()
            raise ImportTooManyRowsError(
                f"File contains more than {IMPORT_MAX_ROWS} data rows",
                details={"data_rows": len(raw_rows), "max_rows": IMPORT_MAX_ROWS},
            )

    wb_data.close()

    if not raw_rows:
        raise ImportEmptyError("Excel file contains no data rows")

    file_sha256 = hashlib.sha256(file_bytes).hexdigest()

    return ParsedWorkbook(
        filename=clean_filename,
        file_sha256=file_sha256,
        file_size=file_size,
        headers=normalized_headers,
        extra_columns=extra_columns,
        raw_rows=raw_rows,
    )
