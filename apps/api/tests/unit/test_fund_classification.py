"""Unit tests for fund classification, plan/option derivation, and name normalization."""

from pathlib import Path

import pytest

from app.services.fund_classification import (
    classify_fund,
    derive_option_type,
    derive_plan_type,
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
    """Every single category header from Step 1 must produce a valid classification."""
    classification = classify_fund(
        name="Sample Standard Fund",
        category_raw=category,
        plan_raw="Direct",
        option_raw="Growth",
    )
    assert classification.asset_class in (
        "equity",
        "debt",
        "gold",
        "hybrid",
        "other",
    )
    assert classification.classification_source in (
        "category",
        "name_rule",
        "unknown",
    )
    assert classification.plan_type == "direct"
    assert classification.option_type == "growth"


def test_name_rules_for_index_funds() -> None:
    cat = "Open Ended Schemes(Other Scheme - Index Funds)"

    # Gold name rule
    c_gold = classify_fund(
        name="HDFC Gold ETF Fund of Fund",
        category_raw=cat,
    )
    assert c_gold.asset_class == "gold"
    assert c_gold.sub_category == "gold"
    assert c_gold.classification_source == "name_rule"

    # Known equity index rules
    c_nifty50 = classify_fund(
        name="UTI Nifty 50 Index Fund",
        category_raw=cat,
    )
    assert c_nifty50.asset_class == "equity"
    assert c_nifty50.sub_category == "index"
    assert c_nifty50.classification_source == "name_rule"

    c_sensex = classify_fund(
        name="ICICI Prudential Sensex Index Fund",
        category_raw=cat,
    )
    assert c_sensex.asset_class == "equity"
    assert c_sensex.sub_category == "index"
    assert c_sensex.classification_source == "name_rule"

    c_next50 = classify_fund(
        name="Mirae Asset Nifty Next 50 ETF",
        category_raw="Open Ended Schemes(Other Scheme - Other  ETFs)",
    )
    assert c_next50.asset_class == "equity"
    assert c_next50.sub_category == "index"
    assert c_next50.classification_source == "name_rule"

    # Debt name rules
    c_gsec = classify_fund(
        name="Nippon India ETF Nifty 8-13 yr G-Sec",
        category_raw=cat,
    )
    assert c_gsec.asset_class == "debt"
    assert c_gsec.sub_category == "index-debt"
    assert c_gsec.classification_source == "name_rule"

    c_liquid = classify_fund(
        name="DSP Nifty 1D Rate Liquid ETF",
        category_raw="Open Ended Schemes(Other Scheme - Other  ETFs)",
    )
    assert c_liquid.asset_class == "debt"
    assert c_liquid.sub_category == "index-debt"
    assert c_liquid.classification_source == "name_rule"

    # Unknown fallback
    c_unknown = classify_fund(
        name="Custom Exotic Global Thematic ETF",
        category_raw=cat,
    )
    assert c_unknown.asset_class == "other"
    assert c_unknown.sub_category is None
    assert c_unknown.classification_source == "unknown"


def test_derive_plan_type() -> None:
    assert derive_plan_type("Parag Parikh Flexi Cap Fund - Direct Plan") == "direct"
    assert derive_plan_type("HDFC Top 100 - Dir - Growth") == "direct"
    assert derive_plan_type("SBI Bluechip Fund - Regular Plan") == "regular"
    assert derive_plan_type("Axis Long Term Equity Fund - Reg") == "regular"
    assert derive_plan_type("Nippon India Small Cap Fund", plan_raw="Direct Plan") == "direct"
    assert derive_plan_type("Unknown Scheme Without Keywords") == "unknown"


def test_derive_option_type() -> None:
    assert derive_option_type("Parag Parikh Flexi Cap Fund - Direct Plan - Growth") == "growth"
    assert derive_option_type("HDFC Top 100 - Dir - Gr") == "growth"
    assert derive_option_type("Axis Bluechip Fund - IDCW Reinvestment") == "idcw"
    assert derive_option_type("SBI Small Cap Fund - Dividend Payout") == "idcw"
    assert derive_option_type("DSP Midcap Fund", option_raw="IDCW") == "idcw"
    assert derive_option_type("UTI Mastershare", option_raw="Bonus") == "idcw"
    assert derive_option_type("Unknown Fund Without Option") == "unknown"


def test_normalize_name() -> None:
    raw = "  Parag Parikh Flexi-Cap Fund (Direct) -- Growth!!  "
    expected = "parag parikh flexi cap fund direct growth"
    assert normalize_name(raw) == expected
