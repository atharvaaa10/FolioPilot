"""Unit tests for pure row parsing, normalization, and validation."""

import datetime as dt
from decimal import Decimal

from app.services.import_file import RawRow
from app.services.import_rows import (
    normalize_row,
    parse_decimal_value,
    parse_isin,
    parse_notes,
    parse_row_date,
    parse_row_type,
    parse_scheme_code,
)


def _make_raw_row(
    cells: dict[str, object], formula_without_value: set[str] | None = None
) -> RawRow:
    return RawRow(
        row_number=2,
        cells=cells,
        formula_cells_without_value=formula_without_value or set(),
    )


def test_date_parsing_formats() -> None:
    def clock_fn() -> dt.datetime:
        return dt.datetime(2025, 6, 1, 12, 0, 0, tzinfo=dt.UTC)

    # Real Excel date
    d1, m1 = parse_row_date(dt.date(2025, 1, 15), clock=clock_fn)
    assert d1 == dt.date(2025, 1, 15) and not m1

    # YYYY-MM-DD
    d2, m2 = parse_row_date("2025-01-15", clock=clock_fn)
    assert d2 == dt.date(2025, 1, 15) and not m2

    # DD-MM-YYYY
    d3, m3 = parse_row_date("15-01-2025", clock=clock_fn)
    assert d3 == dt.date(2025, 1, 15) and not m3

    # DD/MM/YYYY
    d4, m4 = parse_row_date("15/01/2025", clock=clock_fn)
    assert d4 == dt.date(2025, 1, 15) and not m4


def test_date_rejections() -> None:
    def clock_fn() -> dt.datetime:
        return dt.datetime(2025, 6, 1, 12, 0, 0, tzinfo=dt.UTC)

    # Bare number rejected
    _, m1 = parse_row_date(45678, clock=clock_fn)
    assert any(m["code"] == "INVALID_DATE" for m in m1)

    # Invalid text
    _, m2 = parse_row_date("31-02-2025", clock=clock_fn)
    assert any(m["code"] == "INVALID_DATE" for m in m2)

    # Future date (beyond injected clock)
    _, m3 = parse_row_date("2025-07-01", clock=clock_fn)
    assert any(m["code"] == "FUTURE_DATE" for m in m3)

    # Date before floor 1990-01-01
    _, m4 = parse_row_date("1989-12-31", clock=clock_fn)
    assert any(m["code"] == "DATE_BEFORE_FLOOR" for m in m4)


def test_type_aliases() -> None:
    for alias in ["buy", "BUY", " Purchase ", "purchase"]:
        t, msgs = parse_row_type(alias)
        assert t == "buy" and not msgs

    for alias in ["sell", "SELL", "redemption", "Redeem", " REDEEM "]:
        t, msgs = parse_row_type(alias)
        assert t == "sell" and not msgs

    for alias in [
        "dividend_reinvest",
        "dividend reinvest",
        "dividend reinvestment",
        "idcw reinvest",
        "idcw_reinvest",
        "IDCW REINVEST",
    ]:
        t, msgs = parse_row_type(alias)
        assert t == "dividend_reinvest" and not msgs

    _, err_msgs = parse_row_type("swap")
    assert any(m["code"] == "INVALID_TYPE" for m in err_msgs)


def test_number_parsing_and_float_noise() -> None:
    # Float representation noise
    val, msgs = parse_decimal_value(1234.5600000000002, "amount", 2)
    assert val == Decimal("1234.56") and not msgs

    # Integer
    val2, msgs2 = parse_decimal_value(5000, "amount", 2)
    assert val2 == Decimal("5000") and not msgs2

    # Formatted strings with currency symbols and commas
    val3, msgs3 = parse_decimal_value(" ₹ 1,23,456.78 ", "amount", 2)
    assert val3 == Decimal("123456.78") and not msgs3

    val4, msgs4 = parse_decimal_value("INR 5,000.00", "amount", 2)
    assert val4 == Decimal("5000.00") and not msgs4

    val5, msgs5 = parse_decimal_value("Rs. 5,000.00", "amount", 2)
    assert val5 == Decimal("5000.00") and not msgs5


def test_number_rejections() -> None:
    # 5 decimals on units (max 4)
    _, m1 = parse_decimal_value(10.12345, "units", 4)
    assert any(m["code"] == "TOO_MANY_DECIMALS" for m in m1)

    # 3 decimals on amount (max 2)
    _, m2 = parse_decimal_value("100.125", "amount", 2)
    assert any(m["code"] == "TOO_MANY_DECIMALS" for m in m2)

    # Zero
    _, m3 = parse_decimal_value(0, "units", 4)
    assert any(m["code"] == "NOT_POSITIVE" for m in m3)

    # Negative
    _, m4 = parse_decimal_value(-50, "amount", 2)
    assert any(m["code"] == "NOT_POSITIVE" for m in m4)

    # NaN / Inf
    _, m5 = parse_decimal_value(float("nan"), "amount", 2)
    assert any(m["code"] == "INVALID_NUMBER" for m in m5)

    _, m6 = parse_decimal_value("not_a_number", "units", 4)
    assert any(m["code"] == "INVALID_NUMBER" for m in m6)


def test_scheme_code_parsing() -> None:
    assert parse_scheme_code(122639)[0] == 122639
    assert parse_scheme_code(" 122639 ")[0] == 122639
    assert parse_scheme_code("122639.0")[0] == 122639
    assert parse_scheme_code(122639.0)[0] == 122639

    _, m = parse_scheme_code("INVALID_CODE")
    assert any(m_item["code"] == "INVALID_SCHEME_CODE" for m_item in m)


def test_isin_parsing() -> None:
    assert parse_isin("INF879O01018")[0] == "INF879O01018"
    assert parse_isin(" inf879o01018 ")[0] == "INF879O01018"

    # Too short
    _, m1 = parse_isin("INF879O0101")
    assert any(m["code"] == "INVALID_ISIN" for m in m1)

    # Non-Indian prefix
    _, m2 = parse_isin("US879O010182")
    assert any(m["code"] == "INVALID_ISIN" for m in m2)


def test_notes_rules() -> None:
    assert parse_notes("Valid notes")[0] == "Valid notes"
    # Control chars removed
    assert parse_notes("Bad\x00Control\x1fChars")[0] == "BadControlChars"

    # 201 chars rejected without truncation
    long_notes = "N" * 201
    _, m = parse_notes(long_notes)
    assert any(item["code"] == "NOTES_TOO_LONG" for item in m)


def test_formula_without_value() -> None:
    raw = _make_raw_row(
        {"txn_date": "2025-01-10", "txn_type": "buy"}, formula_without_value={"amount"}
    )
    norm = normalize_row(raw)
    assert any(
        m["code"] == "FORMULA_WITHOUT_VALUE" and m["field"] == "amount" for m in norm.messages
    )


def test_amount_resolution_in_row() -> None:
    # 2 provided, 3rd derived: units 100, nav 50 -> amount derived 5000.00
    raw1 = _make_raw_row(
        {
            "txn_date": "2025-01-10",
            "txn_type": "buy",
            "scheme_code": 122639,
            "units": 100,
            "nav": 50,
        }
    )
    norm1 = normalize_row(raw1)
    assert norm1.amount == Decimal("5000.00")
    assert not any(m["level"] == "error" for m in norm1.messages)

    # Units 30, amount 2100 -> nav derived 70.00000000
    raw2 = _make_raw_row(
        {
            "txn_date": "2025-01-10",
            "txn_type": "sell",
            "scheme_code": 122639,
            "units": 30,
            "amount": 2100,
        }
    )
    norm2 = normalize_row(raw2)
    assert norm2.nav == Decimal("70.00000000")
    assert not any(m["level"] == "error" for m in norm2.messages)

    # Discrepancy beyond tolerance
    raw3 = _make_raw_row(
        {
            "txn_date": "2025-01-10",
            "txn_type": "buy",
            "scheme_code": 122639,
            "units": 100,
            "nav": 50,
            "amount": 9999,
        }
    )
    norm3 = normalize_row(raw3)
    assert any(m["code"] == "AMOUNT_MISMATCH" for m in norm3.messages)
