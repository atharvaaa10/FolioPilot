"""Pure normalization and validation for Excel import rows."""

import datetime as dt
import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from app.core.constants import LEDGER_DATE_FLOOR
from app.services.import_file import RawRow
from app.services.transaction_math import (
    AMOUNT_SCALE,
    NAV_SCALE,
    UNITS_SCALE,
    resolve_transaction_amounts,
)

KOLKATA_TZ = ZoneInfo("Asia/Kolkata")
ISIN_PATTERN = re.compile(r"^IN[A-Z0-9]{10}$")

TYPE_ALIASES = {
    "buy": "buy",
    "purchase": "buy",
    "sell": "sell",
    "redemption": "sell",
    "redeem": "sell",
    "dividend_reinvest": "dividend_reinvest",
    "dividend reinvest": "dividend_reinvest",
    "dividend reinvestment": "dividend_reinvest",
    "idcw reinvest": "dividend_reinvest",
    "idcw_reinvest": "dividend_reinvest",
}


@dataclass(frozen=True)
class NormalizedRow:
    """Normalized row candidate with parsed values and collected messages."""

    row_number: int
    txn_date: dt.date | None
    txn_type: str | None
    scheme_code: int | None
    isin: str | None
    units: Decimal | None
    nav: Decimal | None
    amount: Decimal | None
    notes: str | None
    fund_name_in_file: str | None
    raw: dict[str, str]
    messages: list[dict[str, Any]]


def parse_row_date(
    val: Any,
    clock: Callable[[], dt.datetime] | None = None,
) -> tuple[dt.date | None, list[dict[str, Any]]]:
    """Parse transaction date from Excel cell or text string."""
    messages: list[dict[str, Any]] = []
    if val is None or (isinstance(val, str) and not val.strip()):
        messages.append(
            {
                "level": "error",
                "code": "INVALID_DATE",
                "field": "txn_date",
                "message": "Transaction date is required",
            }
        )
        return None, messages

    parsed_date: dt.date | None = None

    if isinstance(val, (dt.datetime, dt.date)):
        parsed_date = val.date() if isinstance(val, dt.datetime) else val
    elif isinstance(val, str):
        text = val.strip()
        # Try YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY
        formats = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"]
        for fmt in formats:
            try:
                parsed_date = dt.datetime.strptime(text, fmt).date()
                break
            except ValueError:
                continue

    if parsed_date is None:
        messages.append(
            {
                "level": "error",
                "code": "INVALID_DATE",
                "field": "txn_date",
                "message": (
                    f"Invalid date format: '{val}'. Expected YYYY-MM-DD, DD-MM-YYYY, or DD/MM/YYYY"
                ),
            }
        )
        return None, messages

    # Range checks
    now_kolkata = (clock() if clock else dt.datetime.now(dt.UTC)).astimezone(KOLKATA_TZ)
    today_kolkata = now_kolkata.date()

    if parsed_date > today_kolkata:
        messages.append(
            {
                "level": "error",
                "code": "FUTURE_DATE",
                "field": "txn_date",
                "message": f"Transaction date {parsed_date.isoformat()} cannot be in the future",
            }
        )
    elif parsed_date < LEDGER_DATE_FLOOR:
        messages.append(
            {
                "level": "error",
                "code": "DATE_BEFORE_FLOOR",
                "field": "txn_date",
                "message": (
                    f"Transaction date {parsed_date.isoformat()} is earlier than floor "
                    f"{LEDGER_DATE_FLOOR.isoformat()}"
                ),
            }
        )

    return parsed_date, messages


def parse_row_type(val: Any) -> tuple[str | None, list[dict[str, Any]]]:
    """Parse and normalize transaction type with alias support."""
    messages: list[dict[str, Any]] = []
    if val is None or (isinstance(val, str) and not val.strip()):
        messages.append(
            {
                "level": "error",
                "code": "INVALID_TYPE",
                "field": "txn_type",
                "message": "Transaction type is required",
            }
        )
        return None, messages

    clean_str = str(val).strip().lower()
    mapped = TYPE_ALIASES.get(clean_str)
    if mapped is None:
        messages.append(
            {
                "level": "error",
                "code": "INVALID_TYPE",
                "field": "txn_type",
                "message": (
                    f"Invalid transaction type: '{val}'. Expected buy, sell, or dividend_reinvest"
                ),
            }
        )
        return None, messages

    return mapped, messages


def parse_decimal_value(
    val: Any,
    field_name: str,
    max_decimals: int,
) -> tuple[Decimal | None, list[dict[str, Any]]]:
    """Parse and validate numeric cell value according to strict financial decimal rules."""
    messages: list[dict[str, Any]] = []
    if val is None or (isinstance(val, str) and not val.strip()):
        return None, messages

    dec_val: Decimal | None = None

    if isinstance(val, (int, float)):
        try:
            # Excel floats formatted with 15g to eliminate float representation noise
            formatted = format(val, ".15g")
            dec_val = Decimal(formatted)
        except (InvalidOperation, ValueError):
            messages.append(
                {
                    "level": "error",
                    "code": "INVALID_NUMBER",
                    "field": field_name,
                    "message": f"Invalid numeric value for {field_name}: '{val}'",
                }
            )
            return None, messages
    elif isinstance(val, str):
        cleaned = val.strip()
        # Remove currency symbols (INR, ₹, Rs., Rs) and thousands commas
        cleaned = re.sub(r"^(?:₹|inr|rs\.?)\s*", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = cleaned.replace(",", "")
        try:
            dec_val = Decimal(cleaned)
        except InvalidOperation:
            messages.append(
                {
                    "level": "error",
                    "code": "INVALID_NUMBER",
                    "field": field_name,
                    "message": f"Invalid numeric format for {field_name}: '{val}'",
                }
            )
            return None, messages
    else:
        messages.append(
            {
                "level": "error",
                "code": "INVALID_NUMBER",
                "field": field_name,
                "message": f"Unsupported data type for {field_name}",
            }
        )
        return None, messages

    if not dec_val.is_finite():
        messages.append(
            {
                "level": "error",
                "code": "INVALID_NUMBER",
                "field": field_name,
                "message": f"{field_name} must be a finite number",
            }
        )
        return None, messages

    if dec_val <= Decimal("0"):
        messages.append(
            {
                "level": "error",
                "code": "NOT_POSITIVE",
                "field": field_name,
                "message": f"{field_name} must be greater than zero",
            }
        )
        return None, messages

    exp = dec_val.as_tuple().exponent
    if isinstance(exp, int) and exp < -max_decimals:
        messages.append(
            {
                "level": "error",
                "code": "TOO_MANY_DECIMALS",
                "field": field_name,
                "message": f"{field_name} cannot exceed {max_decimals} decimal places",
            }
        )
        return None, messages

    return dec_val, messages


def parse_scheme_code(val: Any) -> tuple[int | None, list[dict[str, Any]]]:
    """Parse AMFI scheme code (supports int, string, or float-string like '122639.0')."""
    messages: list[dict[str, Any]] = []
    if val is None or (isinstance(val, str) and not val.strip()):
        return None, messages

    if isinstance(val, int):
        if val > 0:
            return val, messages

    if isinstance(val, float):
        if val.is_integer() and val > 0:
            return int(val), messages

    text = str(val).strip()
    if text.endswith(".0"):
        text = text[:-2]

    if text.isdigit() and int(text) > 0:
        return int(text), messages

    messages.append(
        {
            "level": "error",
            "code": "INVALID_SCHEME_CODE",
            "field": "scheme_code",
            "message": f"Invalid scheme code: '{val}'. Expected positive integer",
        }
    )
    return None, messages


def parse_isin(val: Any) -> tuple[str | None, list[dict[str, Any]]]:
    """Parse and validate Indian mutual fund ISIN."""
    messages: list[dict[str, Any]] = []
    if val is None or (isinstance(val, str) and not val.strip()):
        return None, messages

    text = str(val).strip().upper()
    if ISIN_PATTERN.match(text):
        return text, messages

    messages.append(
        {
            "level": "error",
            "code": "INVALID_ISIN",
            "field": "isin",
            "message": f"Invalid ISIN format: '{val}'. Expected 12-char pattern ^IN[A-Z0-9]{{10}}$",
        }
    )
    return None, messages


def parse_notes(val: Any) -> tuple[str | None, list[dict[str, Any]]]:
    """Parse plain text notes up to 200 characters without truncation."""
    messages: list[dict[str, Any]] = []
    if val is None or (isinstance(val, str) and not val.strip()):
        return None, messages

    text = str(val).strip()
    # Strip control characters (ASCII 0-31 and 127 except tab/newlines)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    if len(text) > 200:
        messages.append(
            {
                "level": "error",
                "code": "NOTES_TOO_LONG",
                "field": "notes",
                "message": f"Notes length {len(text)} exceeds limit of 200 characters",
            }
        )
        return None, messages

    return text if text else None, messages


def normalize_row(
    raw_row: RawRow,
    clock: Callable[[], dt.datetime] | None = None,
) -> NormalizedRow:
    """Purely normalize a single raw Excel row into typed candidate values and messages."""
    cells = raw_row.cells
    row_messages: list[dict[str, Any]] = []

    # Check for formula cells without cached values
    for col_name in sorted(raw_row.formula_cells_without_value):
        row_messages.append(
            {
                "level": "error",
                "code": "FORMULA_WITHOUT_VALUE",
                "field": col_name,
                "message": f"Cell in column '{col_name}' contains a formula without a cached value",
            }
        )

    # 1. Date
    txn_date, date_msgs = parse_row_date(cells.get("txn_date"), clock=clock)
    row_messages.extend(date_msgs)

    # 2. Type
    txn_type, type_msgs = parse_row_type(cells.get("txn_type"))
    row_messages.extend(type_msgs)

    # 3. Fund Identifiers
    scheme_code, sc_msgs = parse_scheme_code(cells.get("scheme_code"))
    row_messages.extend(sc_msgs)

    isin, isin_msgs = parse_isin(cells.get("isin"))
    row_messages.extend(isin_msgs)

    if scheme_code is None and isin is None:
        if not sc_msgs and not isin_msgs:
            row_messages.append(
                {
                    "level": "error",
                    "code": "FUND_REQUIRED",
                    "field": "scheme_code",
                    "message": "At least one of scheme_code or isin must be provided",
                }
            )

    # 4. Financial numbers
    units, units_msgs = parse_decimal_value(cells.get("units"), "units", UNITS_SCALE)
    row_messages.extend(units_msgs)

    nav, nav_msgs = parse_decimal_value(cells.get("nav"), "nav", NAV_SCALE)
    row_messages.extend(nav_msgs)

    amount, amount_msgs = parse_decimal_value(cells.get("amount"), "amount", AMOUNT_SCALE)
    row_messages.extend(amount_msgs)

    # 5. Resolve amounts if numeric parsing succeeded
    has_numeric_errors = any(
        m["field"] in ("units", "nav", "amount") for m in row_messages if m["level"] == "error"
    )

    if not has_numeric_errors:
        provided_count = sum(v is not None for v in (units, nav, amount))
        if provided_count < 2:
            row_messages.append(
                {
                    "level": "error",
                    "code": "MISSING_VALUES",
                    "field": "amount",
                    "message": "Must provide at least two of units, nav, and amount",
                }
            )
        else:
            try:
                res_units, res_nav, res_amount = resolve_transaction_amounts(units, nav, amount)
                units = res_units
                nav = res_nav
                amount = res_amount
            except Exception as e:
                row_messages.append(
                    {
                        "level": "error",
                        "code": "AMOUNT_MISMATCH",
                        "field": "amount",
                        "message": str(e),
                    }
                )

    # 6. Notes & optional fund_name
    notes, notes_msgs = parse_notes(cells.get("notes"))
    row_messages.extend(notes_msgs)

    fund_name_val = cells.get("fund_name")
    fund_name_in_file = str(fund_name_val).strip() if fund_name_val is not None else None
    if fund_name_in_file == "":
        fund_name_in_file = None

    # Original cell values formatted as strings for display/audit
    raw_dict: dict[str, str] = {}
    for k, v in cells.items():
        if v is not None:
            raw_dict[k] = str(v)

    return NormalizedRow(
        row_number=raw_row.row_number,
        txn_date=txn_date,
        txn_type=txn_type,
        scheme_code=scheme_code,
        isin=isin,
        units=units,
        nav=nav,
        amount=amount,
        notes=notes,
        fund_name_in_file=fund_name_in_file,
        raw=raw_dict,
        messages=row_messages,
    )
