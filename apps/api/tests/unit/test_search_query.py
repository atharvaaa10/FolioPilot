"""Unit tests for search query normalization, wildcard escaping, and query detection."""

from app.services.search_query import (
    escape_like_wildcards,
    is_isin_query,
    is_scheme_code_query,
    parse_search_query,
)


def test_escape_like_wildcards() -> None:
    # SQL wildcards % and _ and backslash must be escaped
    assert escape_like_wildcards("100% Equity") == "100\\% Equity"
    assert escape_like_wildcards("Fund_Name") == "Fund\\_Name"
    assert escape_like_wildcards("a\\b%c_d") == "a\\\\b\\%c\\_d"


def test_is_scheme_code_query() -> None:
    assert is_scheme_code_query("122639") is True
    assert is_scheme_code_query(" 122639 ") is True
    assert is_scheme_code_query("122639a") is False
    assert is_scheme_code_query("INF879O01027") is False
    assert is_scheme_code_query("") is False


def test_is_isin_query() -> None:
    assert is_isin_query("INF879O01027") is True
    assert is_isin_query("inf879o01027") is True
    assert is_isin_query("INF879O0102") is False  # 11 chars
    assert is_isin_query("12F879O01027") is False  # doesn't start with 2 letters
    assert is_isin_query("INF879O010279") is False  # 13 chars


def test_parse_search_query() -> None:
    # Scheme code detection
    q1 = parse_search_query("122639")
    assert q1.is_scheme_code is True
    assert q1.scheme_code == 122639
    assert q1.is_isin is False

    # ISIN detection
    q2 = parse_search_query("inf879o01027")
    assert q2.is_isin is True
    assert q2.isin == "INF879O01027"
    assert q2.is_scheme_code is False

    # Multi-token text search
    q3 = parse_search_query("  Parag Parikh   Flexi-Cap  ")
    assert q3.is_scheme_code is False
    assert q3.is_isin is False
    assert q3.tokens == ["parag", "parikh", "flexi", "cap"]

    # Empty query
    q4 = parse_search_query("   ")
    assert q4.raw_query == ""
    assert q4.tokens == []
