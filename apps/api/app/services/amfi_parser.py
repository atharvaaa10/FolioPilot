"""Pure parser for AMFI NAVAll.txt data."""

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class ParsedScheme:
    """Parsed representation of a single fund row from AMFI."""

    scheme_code: int
    isin_growth: str | None
    isin_reinvest: str | None
    name: str
    plan_raw: str | None
    option_raw: str | None
    nav: Decimal | None
    nav_date: date | None
    amc: str
    category_raw: str
    scheme_type_raw: str | None


@dataclass
class AmfiParseResult:
    """Result of parsing the entire AMFI NAVAll.txt file."""

    schemes: list[ParsedScheme]
    total_data_lines: int
    malformed_lines: int
    duplicate_schemes_count: int


_CATEGORY_RE = re.compile(
    r"^(Open Ended Schemes|Close Ended Schemes|Interval Fund Schemes)(?:\((.*)\))?$",
    re.IGNORECASE,
)


def _clean_field(val: str | None) -> str | None:
    if val is None:
        return None
    val = val.strip()
    if not val or val == "-":
        return None
    return val


def _parse_date(date_str: str) -> date | None:
    val = _clean_field(date_str)
    if not val:
        return None
    try:
        return datetime.strptime(val, "%d-%b-%Y").date()
    except (ValueError, TypeError):
        return None


def _parse_decimal(nav_str: str) -> Decimal | None:
    val = _clean_field(nav_str)
    if not val or val.upper() in ("N.A.", "NA", "NIL", "NAN"):
        return None
    try:
        return Decimal(val)
    except (InvalidOperation, ValueError, TypeError):
        return None


def parse_navall(text: str) -> AmfiParseResult:
    """Parse AMFI NAVAll.txt into structured schemes and problem statistics.

    Handles UTF-8 BOM, CRLF line endings, category headers, AMC lines,
    duplicate scheme codes (last wins), and malformed rows.
    """
    if text.startswith("\ufeff"):
        text = text[1:]

    lines = text.splitlines()

    current_scheme_type: str | None = None
    current_category: str = "Unknown"
    current_amc: str = "Unknown"

    schemes_dict: dict[int, ParsedScheme] = {}
    total_data_lines = 0
    malformed_lines = 0
    duplicate_schemes_count = 0

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        # Check if line is a category header or AMC line (no semicolons)
        if ";" not in line_str:
            match = _CATEGORY_RE.match(line_str)
            if match:
                current_scheme_type = match.group(1).strip()
                current_category = line_str
            else:
                # AMC line
                current_amc = line_str
            continue

        # Header line check: skip table header
        if line_str.lower().startswith("scheme code;isin"):
            continue

        parts = line_str.split(";")
        if len(parts) != 8:
            malformed_lines += 1
            continue

        total_data_lines += 1

        # Scheme code must be integer
        raw_code = parts[0].strip()
        try:
            scheme_code = int(raw_code)
        except (ValueError, TypeError):
            malformed_lines += 1
            continue

        isin_growth = _clean_field(parts[1])
        isin_reinvest = _clean_field(parts[2])
        name = parts[3].strip()
        if not name:
            malformed_lines += 1
            continue

        plan_raw = _clean_field(parts[4])
        option_raw = _clean_field(parts[5])
        nav = _parse_decimal(parts[6])
        nav_date = _parse_date(parts[7])

        if scheme_code in schemes_dict:
            duplicate_schemes_count += 1

        schemes_dict[scheme_code] = ParsedScheme(
            scheme_code=scheme_code,
            isin_growth=isin_growth,
            isin_reinvest=isin_reinvest,
            name=name,
            plan_raw=plan_raw,
            option_raw=option_raw,
            nav=nav,
            nav_date=nav_date,
            amc=current_amc,
            category_raw=current_category,
            scheme_type_raw=current_scheme_type,
        )

    return AmfiParseResult(
        schemes=list(schemes_dict.values()),
        total_data_lines=total_data_lines,
        malformed_lines=malformed_lines,
        duplicate_schemes_count=duplicate_schemes_count,
    )
