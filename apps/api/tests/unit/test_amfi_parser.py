"""Unit tests for AMFI NAVAll.txt parser."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from app.services.amfi_parser import parse_navall


def test_parse_navall_fixture() -> None:
    fixture_path = Path(__file__).parent.parent / "fixtures" / "NAVAll_sample.txt"
    with open(fixture_path, encoding="utf-8") as f:
        content = f.read()

    result = parse_navall(content)

    assert result.total_data_lines > 0
    assert len(result.schemes) > 0
    assert result.duplicate_schemes_count >= 1
    assert result.malformed_lines >= 0

    # Check Parag Parikh Flexi Cap Fund if in sample or Bank of India
    boi_fund = next(
        (s for s in result.schemes if s.scheme_code == 141950),
        None,
    )
    assert boi_fund is not None
    assert boi_fund.name == "BANK OF INDIA MID CAP TAX FUND SERIES 1"
    assert boi_fund.isin_growth == "INF761K01DS3"
    assert boi_fund.isin_reinvest is None
    assert boi_fund.amc == "Bank of India Mutual Fund"
    assert boi_fund.category_raw == "Close Ended Schemes(ELSS)"
    assert boi_fund.scheme_type_raw == "Close Ended Schemes"
    assert boi_fund.nav == Decimal("31.01")
    assert boi_fund.nav_date == date(2026, 11, 6)


def test_parse_navall_bom_and_crlf() -> None:
    header = (
        "Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;"
        "Scheme Name;Plan;Option;Net Asset Value;Date\r\n"
    )
    raw = (
        f"\ufeff{header}"
        "\r\n"
        "Open Ended Schemes(Equity Scheme - Large Cap Fund)\r\n"
        "Test AMC\r\n"
        "100001;INF001;INF002;Test Large Cap Fund;Direct;Growth;123.4567;06-Nov-2026\r\n"
    )
    result = parse_navall(raw)
    assert len(result.schemes) == 1
    s = result.schemes[0]
    assert s.scheme_code == 100001
    assert s.name == "Test Large Cap Fund"
    assert s.nav == Decimal("123.4567")
    assert s.nav_date == date(2026, 11, 6)
    assert s.amc == "Test AMC"
    assert s.category_raw == "Open Ended Schemes(Equity Scheme - Large Cap Fund)"
    assert s.scheme_type_raw == "Open Ended Schemes"


def test_parse_navall_missing_isin_and_unavailable_nav() -> None:
    raw = (
        "Open Ended Schemes(Debt Scheme - Liquid Fund)\n"
        "Liquid AMC\n"
        "100002;-;-;Test Liquid Fund;Regular;Growth;N.A.;06-Nov-2026\n"
        "100003; ; ;Test Liquid Fund 2;Regular;Growth;NA;-\n"
    )
    result = parse_navall(raw)
    assert len(result.schemes) == 2

    s1 = next(s for s in result.schemes if s.scheme_code == 100002)
    assert s1.isin_growth is None
    assert s1.isin_reinvest is None
    assert s1.nav is None
    assert s1.nav_date == date(2026, 11, 6)

    s2 = next(s for s in result.schemes if s.scheme_code == 100003)
    assert s2.isin_growth is None
    assert s2.nav is None
    assert s2.nav_date is None


def test_parse_navall_duplicate_scheme_code_last_wins() -> None:
    raw = (
        "Open Ended Schemes(Equity Scheme - Mid Cap Fund)\n"
        "Mid Cap AMC\n"
        "100004;INF004A;-;Old Name;Direct;Growth;10.0;01-Nov-2026\n"
        "100004;INF004B;-;New Name Updated;Direct;Growth;12.5;06-Nov-2026\n"
    )
    result = parse_navall(raw)
    assert len(result.schemes) == 1
    assert result.duplicate_schemes_count == 1
    s = result.schemes[0]
    assert s.scheme_code == 100004
    assert s.name == "New Name Updated"
    assert s.isin_growth == "INF004B"
    assert s.nav == Decimal("12.5")
    assert s.nav_date == date(2026, 11, 6)


def test_parse_navall_malformed_lines_counted_never_raised() -> None:
    raw = (
        "Open Ended Schemes(Equity Scheme - Small Cap Fund)\n"
        "Small Cap AMC\n"
        "100005;Only;Three;Columns\n"
        "NotAnInt;INF005;-;Bad Code Scheme;Direct;Growth;15.0;06-Nov-2026\n"
        "100006;INF006;-;;Direct;Growth;15.0;06-Nov-2026\n"  # empty name
        "100007;INF007;-;Valid Scheme;Direct;Growth;25.0;06-Nov-2026\n"
    )
    result = parse_navall(raw)
    assert len(result.schemes) == 1
    assert result.schemes[0].scheme_code == 100007
    assert result.malformed_lines == 3
