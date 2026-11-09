"""Unit tests for fund classification, plan/option derivation, and name normalization."""

from pathlib import Path

import pytest

from app.core.classification_constants import CANONICAL_CLASSIFICATIONS
from app.services.fund_classification import (
    classify_fund,
    derive_option_type,
    derive_plan_type,
    normalize_category,
    normalize_name,
)

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "NAVAll_sample.txt"


def _load_all_categories() -> list[str]:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        cats = sorted(
            list(
                set(
                    line.strip()
                    for line in f
                    if line.strip().startswith(
                        (
                            "Open Ended Schemes",
                            "Close Ended Schemes",
                            "Interval Fund Schemes",
                        )
                    )
                )
            )
        )
    return cats


ALL_CATEGORIES = _load_all_categories()


@pytest.mark.parametrize("category", ALL_CATEGORIES)
def test_classification_covers_all_categories(category: str) -> None:
    """Every category header from Step 1 must map to a valid canonical classification."""
    classification = classify_fund(
        name="Sample Standard Fund",
        category_raw=category,
        plan_raw="Direct",
        option_raw="Growth",
    )
    assert (classification.asset_class, classification.sub_category) in CANONICAL_CLASSIFICATIONS
    assert classification.classification_source in ("category", "name_rule", "unknown")
    assert classification.plan_type == "direct"
    assert classification.option_type == "growth"


def test_category_normalization() -> None:
    """Verify category normalization collapses multiple spaces and lowercases."""
    c1 = "Open Ended Schemes(Other Scheme - Other  ETFs)"  # double space
    assert normalize_category(c1) == "open ended schemes(other scheme - other etfs)"

    # Should match correctly despite whitespace anomalies
    res = classify_fund("Groww Gold ETF", c1)
    assert res.asset_class == "gold"
    assert res.sub_category == "gold-etf"


def test_direct_index_and_etf_category_headings() -> None:
    """Category headings that explicitly specify equity, debt, gold must map directly."""
    # Equity Funds
    c_eq_idx = classify_fund(
        name="Any Random Name",
        category_raw="Open Ended Schemes(Index Funds - Equity Funds)",
    )
    assert c_eq_idx.asset_class == "equity"
    assert c_eq_idx.sub_category == "index"
    assert c_eq_idx.classification_source == "category"

    c_eq_etf = classify_fund(
        name="Any Random Name",
        category_raw="Open Ended Schemes(Exchange Traded Funds (ETFs) - Equity ETF)",
    )
    assert c_eq_etf.asset_class == "equity"
    assert c_eq_etf.sub_category == "index"
    assert c_eq_etf.classification_source == "category"

    # Debt Funds
    c_debt_idx = classify_fund(
        name="Any Random Name",
        category_raw="Open Ended Schemes(Index Funds - Debt Funds)",
    )
    assert c_debt_idx.asset_class == "debt"
    assert c_debt_idx.sub_category == "index-debt"
    assert c_debt_idx.classification_source == "category"

    c_debt_etf = classify_fund(
        name="Any Random Name",
        category_raw="Open Ended Schemes(Exchange Traded Funds (ETFs) - Debt ETF)",
    )
    assert c_debt_etf.asset_class == "debt"
    assert c_debt_etf.sub_category == "index-debt"
    assert c_debt_etf.classification_source == "category"


def test_negative_guards_name_rules_never_override_definite_category() -> None:
    """Name rules must NEVER override a category that already gives a definite answer."""
    # Bank of India contains "Bank", but category is Liquid Fund -> MUST be debt / liquid
    c_liquid = classify_fund(
        name="Bank of India Liquid Fund",
        category_raw="Open Ended Schemes(Debt Scheme - Liquid Fund)",
    )
    assert c_liquid.asset_class == "debt"
    assert c_liquid.sub_category == "liquid"
    assert c_liquid.classification_source == "category"

    # Bank of India Short Term Income Fund contains "Bank", but category is Short Term -> debt
    c_income = classify_fund(
        name="Bank of India Short Term Income Fund",
        category_raw="Open Ended Schemes(Income/Debt Oriented Schemes - Short Term Fund)",
    )
    assert c_income.asset_class == "debt"
    assert c_income.sub_category == "short-term"
    assert c_income.classification_source == "category"


@pytest.mark.parametrize(
    ("scheme_code", "name", "category_raw", "expected_asset", "expected_sub"),
    [
        (
            153425,
            "Tata BSE Quality Index Fund",
            "Open Ended Schemes(Other Scheme - Index Funds)",
            "equity",
            "index",
        ),
        (
            153235,
            "ICICI Prudential CRISIL-IBX AAA Bond Financial Services Index -Dec 2026 Fund",
            "Open Ended Schemes(Other Scheme - Index Funds)",
            "debt",
            "index-debt",
        ),
        (
            153234,
            "ICICI Prudential CRISIL-IBX AAA Bond Financial Services Index -Dec 2026 Fund",
            "Open Ended Schemes(Other Scheme - Index Funds)",
            "debt",
            "index-debt",
        ),
        (
            153838,
            "Bandhan BSE India Sector Leaders Index Fund",
            "Open Ended Schemes(Other Scheme - Index Funds)",
            "equity",
            "index",
        ),
        (
            154723,
            "Mirae Asset BSE Information Technology Index Fund",
            "Open Ended Schemes(Index Funds - Equity Funds)",
            "equity",
            "index",
        ),
        (
            154503,
            "ICICI Prudential BSE Insurance ETF",
            "Open Ended Schemes(Exchange Traded Funds (ETFs) - Other ETF)",
            "equity",
            "index",
        ),
        (
            153212,
            "Bandhan Nifty Alpha Low Volatility 30 Index Fund",
            "Open Ended Schemes(Other Scheme - Index Funds)",
            "equity",
            "index",
        ),
        (
            152306,
            "DSP Nifty Healthcare ETF",
            "Open Ended Schemes(Other Scheme - Other  ETFs)",
            "equity",
            "index",
        ),
        (
            153346,
            "DSP Nifty Private Bank Index Fund",
            "Open Ended Schemes(Other Scheme - Index Funds)",
            "equity",
            "index",
        ),
        (
            149786,
            "Mirae Asset Nifty India Manufacturing ETF",
            "Open Ended Schemes(Exchange Traded Funds (ETFs) - Equity ETF)",
            "equity",
            "index",
        ),
        (
            152127,
            "Groww Nifty Total Market Index Fund",
            "Open Ended Schemes(Index Funds - Equity Funds)",
            "equity",
            "index",
        ),
        (
            154752,
            "HDFC BSE REITS and Commercial Real Estate Index Fund",
            "Open Ended Schemes(Index Funds - Equity Funds)",
            "equity",
            "index",
        ),
        (
            152482,
            "ICICI Prudential Nifty LargeMidcap 250 Index Fund",
            "Open Ended Schemes(Other Scheme - Index Funds)",
            "equity",
            "index",
        ),
        (
            114984,
            "Motilal Oswal Nasdaq 100 ETF",
            "Open Ended Schemes(Other Scheme - Other  ETFs)",
            "equity",
            "international",
        ),
        (
            154332,
            "SBI CRISIL-IBX Financial Services 3-6 Months Debt Index Fund",
            "Open Ended Schemes(Other Scheme - Index Funds)",
            "debt",
            "index-debt",
        ),
        (
            148382,
            "Motilal Oswal S&P 500 Index Fund",
            "Open Ended Schemes(Other Scheme - Index Funds)",
            "equity",
            "international",
        ),
        (
            153434,
            "SBI BSE PSU BANK INDEX FUND",
            "Open Ended Schemes(Other Scheme - Index Funds)",
            "equity",
            "index",
        ),
        (
            153683,
            "Kotak Nifty AAA Bond Financial Services Mar 2028 Index Fund",
            "Open Ended Schemes(Other Scheme - Index Funds)",
            "debt",
            "index-debt",
        ),
        (
            149221,
            "ICICI Prudential NASDAQ 100 Index Fund",
            "Open Ended Schemes(Other Scheme - Index Funds)",
            "equity",
            "international",
        ),
        (
            148558,
            "Edelweiss MSCI India Domestic & World Healthcare 45 Index Fund",
            "Open Ended Schemes(Other Scheme - Index Funds)",
            "other",
            "unknown",
        ),
    ],
)
def test_real_sample_regression(
    scheme_code: int,
    name: str,
    category_raw: str,
    expected_asset: str,
    expected_sub: str,
) -> None:
    """Test all 20 real regression cases specified in Step 0.2."""
    res = classify_fund(name=name, category_raw=category_raw)
    assert res.asset_class == expected_asset, f"Mismatch for scheme {scheme_code}: {name}"
    assert res.sub_category == expected_sub, f"Mismatch for scheme {scheme_code}: {name}"
    assert (res.asset_class, res.sub_category) in CANONICAL_CLASSIFICATIONS


def test_silver_classification() -> None:
    """Silver funds should classify as other / silver."""
    res = classify_fund(
        name="HDFC Silver ETF",
        category_raw="Open Ended Schemes(Other Scheme - Other  ETFs)",
    )
    assert res.asset_class == "other"
    assert res.sub_category == "silver"
    assert res.classification_source == "name_rule"
    assert (res.asset_class, res.sub_category) in CANONICAL_CLASSIFICATIONS


def test_derive_plan_type() -> None:
    assert derive_plan_type("HDFC Flexi Cap Fund - Direct Plan - Growth") == "direct"
    assert derive_plan_type("HDFC Flexi Cap Fund - Regular Plan") == "regular"
    assert derive_plan_type("HDFC Flexi Cap Fund", plan_raw="Direct") == "direct"
    assert derive_plan_type("HDFC Flexi Cap Fund", plan_raw="Regular") == "regular"
    assert derive_plan_type("HDFC Flexi Cap Fund") == "unknown"


def test_derive_option_type() -> None:
    assert derive_option_type("SBI Bluechip Fund - Growth") == "growth"
    assert derive_option_type("SBI Bluechip Fund - IDCW") == "idcw"
    assert derive_option_type("SBI Bluechip Fund - Dividend Payout") == "idcw"
    assert derive_option_type("SBI Bluechip Fund", option_raw="Growth") == "growth"
    assert derive_option_type("SBI Bluechip Fund", option_raw="IDCW Reinvestment") == "idcw"
    assert derive_option_type("SBI Bluechip Fund") == "unknown"


def test_normalize_name() -> None:
    assert normalize_name("HDFC Top 100 Fund - Direct (G)") == "hdfc top 100 fund direct g"
    assert (
        normalize_name("Parag Parikh Flexi Cap Fund - Direct Plan - Growth")
        == "parag parikh flexi cap fund direct plan growth"
    )


def test_canonical_classification_json_consistency() -> None:
    """Verify that docs/classification.json is fully consistent with CANONICAL_CLASSIFICATIONS."""
    import json

    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent / "docs" / "classification.json",
        Path(__file__).resolve().parent.parent.parent / "docs" / "classification.json",
        Path("/app/docs/classification.json"),
        Path("/docs/classification.json"),
    ]
    json_path = next((p for p in candidates if p.exists()), None)
    err_msg = "docs/classification.json does not exist. Run export_classification.py"
    assert json_path is not None and json_path.exists(), err_msg

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    root_json = Path(__file__).resolve().parent.parent.parent.parent / "docs" / "classification.json"
    api_json = Path(__file__).resolve().parent.parent.parent / "docs" / "classification.json"
    if root_json.exists() and api_json.exists():
        assert root_json.read_bytes() == api_json.read_bytes(), (
            "docs/classification.json and apps/api/docs/classification.json must be byte-for-byte identical"
        )

    json_tuples = {(item["asset_class"], item["sub_category"]) for item in data["classifications"]}
    assert json_tuples == CANONICAL_CLASSIFICATIONS
