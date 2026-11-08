"""Pure service for fund classification, plan/option derivation, and name normalization."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FundClassification:
    """Classification details for a fund."""

    asset_class: str  # equity, debt, gold, hybrid, other
    sub_category: str | None
    classification_source: str  # category, name_rule, unknown
    plan_type: str  # direct, regular, unknown
    option_type: str  # growth, idcw, unknown


# Explicit table-driven mapping of AMFI category headers to (asset_class, sub_category)
# When value is None, the category is an Index Fund or ETF that delegates to NAME rules.
_CATEGORY_TABLE: dict[str, tuple[str, str | None] | None] = {
    # Equity schemes
    "Open Ended Schemes(Equity Scheme - Large Cap Fund)": ("equity", "large-cap"),
    "Open Ended Schemes(Equity Schemes - Large Cap Fund)": ("equity", "large-cap"),
    "Open Ended Schemes(Equity Scheme - Mid Cap Fund)": ("equity", "mid-cap"),
    "Open Ended Schemes(Equity Schemes - Mid Cap Fund)": ("equity", "mid-cap"),
    "Open Ended Schemes(Equity Scheme - Small Cap Fund)": ("equity", "small-cap"),
    "Open Ended Schemes(Equity Schemes - Small Cap Fund)": ("equity", "small-cap"),
    "Open Ended Schemes(Equity Scheme - Flexi Cap Fund)": ("equity", "flexi-cap"),
    "Open Ended Schemes(Equity Schemes - Flexi Cap Fund)": ("equity", "flexi-cap"),
    "Open Ended Schemes(Equity Scheme - Multi Cap Fund)": ("equity", "multi-cap"),
    "Open Ended Schemes(Equity Schemes - Multi Cap Fund)": ("equity", "multi-cap"),
    "Open Ended Schemes(Equity Scheme - Large & Mid Cap Fund)": ("equity", "large-and-mid-cap"),
    "Open Ended Schemes(Equity Schemes - Large & Mid Cap Fund)": ("equity", "large-and-mid-cap"),
    "Open Ended Schemes(Equity Scheme - Focused Fund)": ("equity", "focused"),
    "Open Ended Schemes(Equity Schemes - Focused Fund)": ("equity", "focused"),
    "Open Ended Schemes(Equity Scheme - Value Fund)": ("equity", "value"),
    "Open Ended Schemes(Equity Schemes - Value Fund)": ("equity", "value"),
    "Open Ended Schemes(Equity Scheme - Contra Fund)": ("equity", "contra"),
    "Open Ended Schemes(Equity Schemes - Contra Fund)": ("equity", "contra"),
    "Open Ended Schemes(Equity Scheme - Dividend Yield Fund)": ("equity", "dividend-yield"),
    "Open Ended Schemes(Equity Schemes - Dividend Yield Fund)": ("equity", "dividend-yield"),
    "Open Ended Schemes(Equity Scheme - ELSS)": ("equity", "elss"),
    "Open Ended Schemes(Equity Schemes - ELSS- Tax Saver Fund)": ("equity", "elss"),
    "Close Ended Schemes(ELSS)": ("equity", "elss"),
    "Close Ended Schemes(Growth)": ("equity", "growth"),
    "Open Ended Schemes(Growth)": ("equity", "growth"),
    "Open Ended Schemes(Equity Scheme - Sectoral/ Thematic)": ("equity", "sectoral-thematic"),
    "Open Ended Schemes(Equity Schemes - Sectoral Fund)": ("equity", "sectoral"),
    "Open Ended Schemes(Equity Schemes - Thematic Fund)": ("equity", "thematic"),
    # Debt schemes
    "Open Ended Schemes(Debt Scheme - Overnight Fund)": ("debt", "overnight"),
    "Open Ended Schemes(Debt Scheme - Liquid Fund)": ("debt", "liquid"),
    "Open Ended Schemes(Debt Scheme - Ultra Short Duration Fund)": ("debt", "ultra-short-duration"),
    "Open Ended Schemes(Debt Scheme - Low Duration Fund)": ("debt", "low-duration"),
    "Open Ended Schemes(Debt Scheme - Money Market Fund)": ("debt", "money-market"),
    "Open Ended Schemes(Debt Scheme - Short Duration Fund)": ("debt", "short-duration"),
    "Open Ended Schemes(Debt Scheme - Medium Duration Fund)": ("debt", "medium-duration"),
    "Open Ended Schemes(Debt Scheme - Medium to Long Duration Fund)": (
        "debt",
        "medium-to-long-duration",
    ),
    "Open Ended Schemes(Debt Scheme - Long Duration Fund)": ("debt", "long-duration"),
    "Open Ended Schemes(Debt Scheme - Dynamic Bond)": ("debt", "dynamic-bond"),
    "Open Ended Schemes(Debt Scheme - Corporate Bond Fund)": ("debt", "corporate-bond"),
    "Open Ended Schemes(Debt Scheme - Credit Risk Fund)": ("debt", "credit-risk"),
    "Open Ended Schemes(Debt Scheme - Banking and PSU Fund)": ("debt", "banking-and-psu"),
    "Open Ended Schemes(Debt Scheme - Gilt Fund)": ("debt", "gilt"),
    "Open Ended Schemes(Gilt)": ("debt", "gilt"),
    "Open Ended Schemes(Income)": ("debt", "income"),
    "Close Ended Schemes(Income)": ("debt", "income"),
    "Close Ended Schemes(Income/Debt Oriented Schemes - Fixed Term Plan)": (
        "debt",
        "fixed-term-plan",
    ),
    "Close Ended Schemes(Income/Debt Oriented Schemes - Other Debt Scheme)": (
        "debt",
        "other-debt",
    ),
    "Interval Fund Schemes(Income)": ("debt", "interval-income"),
    "Open Ended Schemes(Income/Debt Oriented Schemes - 10-year Constant Maturity Gilt Fund)": (
        "debt",
        "10-year-gilt",
    ),
    "Open Ended Schemes(Income/Debt Oriented Schemes - Banking and PSU Debt Fund)": (
        "debt",
        "banking-and-psu",
    ),
    "Open Ended Schemes(Income/Debt Oriented Schemes - Corporate Bond Fund)": (
        "debt",
        "corporate-bond",
    ),
    "Open Ended Schemes(Income/Debt Oriented Schemes - Credit Risk Fund)": (
        "debt",
        "credit-risk",
    ),
    "Open Ended Schemes(Income/Debt Oriented Schemes - Dynamic Term Fund)": (
        "debt",
        "dynamic-term",
    ),
    "Open Ended Schemes(Income/Debt Oriented Schemes - Floating Interest Rates Fund)": (
        "debt",
        "floater",
    ),
    "Open Ended Schemes(Income/Debt Oriented Schemes - Gilt Fund)": ("debt", "gilt"),
    "Open Ended Schemes(Income/Debt Oriented Schemes - Liquid Fund)": ("debt", "liquid"),
    "Open Ended Schemes(Income/Debt Oriented Schemes - Long Term Fund)": ("debt", "long-term"),
    "Open Ended Schemes(Income/Debt Oriented Schemes - Medium Term Fund)": ("debt", "medium-term"),
    "Open Ended Schemes(Income/Debt Oriented Schemes - Medium to Long Term Fund)": (
        "debt",
        "medium-to-long-term",
    ),
    "Open Ended Schemes(Income/Debt Oriented Schemes - Money Market Fund)": (
        "debt",
        "money-market",
    ),
    "Open Ended Schemes(Income/Debt Oriented Schemes - Overnight Fund)": ("debt", "overnight"),
    "Open Ended Schemes(Income/Debt Oriented Schemes - Sectoral Fund)": ("debt", "sectoral"),
    "Open Ended Schemes(Income/Debt Oriented Schemes - Short Term Fund)": ("debt", "short-term"),
    "Open Ended Schemes(Income/Debt Oriented Schemes - Ultra Short Term Fund)": (
        "debt",
        "ultra-short-term",
    ),
    "Open Ended Schemes(Income/Debt Oriented Schemes - Ultra Short to Short Term Fund)": (
        "debt",
        "ultra-short-to-short-term",
    ),
    # Hybrid schemes
    "Open Ended Schemes(Hybrid Scheme - Conservative Hybrid Fund)": (
        "hybrid",
        "conservative-hybrid",
    ),
    "Open Ended Schemes(Hybrid Schemes - Conservative Hybrid Fund)": (
        "hybrid",
        "conservative-hybrid",
    ),
    "Open Ended Schemes(Hybrid Scheme - Balanced Hybrid Fund)": ("hybrid", "balanced-hybrid"),
    "Open Ended Schemes(Hybrid Schemes - Balanced Hybrid Fund)": ("hybrid", "balanced-hybrid"),
    "Open Ended Schemes(Hybrid Scheme - Aggressive Hybrid Fund)": ("hybrid", "aggressive-hybrid"),
    "Open Ended Schemes(Hybrid Schemes - Aggressive Hybrid Fund)": (
        "hybrid",
        "aggressive-hybrid",
    ),
    "Open Ended Schemes(Hybrid Scheme - Dynamic Asset Allocation or Balanced Advantage)": (
        "hybrid",
        "balanced-advantage",
    ),
    "Open Ended Schemes(Hybrid Schemes - Balanced Advantage Fund/ Dynamic Asset Allocation)": (
        "hybrid",
        "balanced-advantage",
    ),
    "Open Ended Schemes(Hybrid Scheme - Multi Asset Allocation)": (
        "hybrid",
        "multi-asset-allocation",
    ),
    "Open Ended Schemes(Hybrid Schemes - Multi Asset Allocation Fund)": (
        "hybrid",
        "multi-asset-allocation",
    ),
    "Open Ended Schemes(Hybrid Scheme - Arbitrage Fund)": ("hybrid", "arbitrage"),
    "Open Ended Schemes(Hybrid Schemes - Arbitrage Fund)": ("hybrid", "arbitrage"),
    "Open Ended Schemes(Hybrid Scheme - Equity Savings)": ("hybrid", "equity-savings"),
    "Open Ended Schemes(Hybrid Schemes - Equity Savings Fund)": ("hybrid", "equity-savings"),
    # Gold categories
    "Open Ended Schemes(Exchange Traded Funds (ETFs) - Gold ETF)": ("gold", "gold-etf"),
    "Open Ended Schemes(Other Scheme - Gold ETF)": ("gold", "gold-etf"),
    # Solution Oriented, FoF, and Life Cycle (mapped to other)
    "Open Ended Schemes(Solution Oriented Scheme - Children’s Fund)": (
        "other",
        "solution-oriented",
    ),
    "Open Ended Schemes(Solution Oriented Scheme - Retirement Fund)": (
        "other",
        "solution-oriented",
    ),
    "Open Ended Schemes(Solution Oriented Schemes ** - Retirement Fund)": (
        "other",
        "solution-oriented",
    ),
    "Open Ended Schemes(Children’s Fund - Childrens' Fund)": ("other", "solution-oriented"),
    "Open Ended Schemes(Fund of Funds Scheme (Domestic) - Fund of Funds Scheme (Domestic))": (
        "other",
        "fof",
    ),
    "Open Ended Schemes(Other Scheme - FoF Domestic)": ("other", "fof"),
    "Open Ended Schemes(Other Scheme - FoF Overseas)": ("other", "fof"),
    "Open Ended Schemes(Overseas Fund of Funds - Fund of Funds investing overseas)": (
        "other",
        "fof",
    ),
    "Open Ended Schemes(Exchange Traded Funds (ETFs) - Silver ETF)": ("other", "silver-etf"),
    "Open Ended Schemes(Life Cycle Funds - Life Cycle Fund with Maturity of 5 Years)": (
        "other",
        "life-cycle",
    ),
    "Open Ended Schemes(Life Cycle Funds - Life Cycle Fund with Maturity of 10 Years)": (
        "other",
        "life-cycle",
    ),
    "Open Ended Schemes(Life Cycle Funds - Life Cycle Fund with Maturity of 15 Years)": (
        "other",
        "life-cycle",
    ),
    "Open Ended Schemes(Life Cycle Funds - Life Cycle Fund with Maturity of 30 Years)": (
        "other",
        "life-cycle",
    ),
    # Index Funds and ETFs that delegate to NAME rules (None)
    "Open Ended Schemes(Other Scheme - Index Funds)": None,
    "Open Ended Schemes(Index Funds - Equity Funds)": None,
    "Open Ended Schemes(Index Funds - Debt Funds)": None,
    "Open Ended Schemes(Index Funds - Hybrid Fund)": None,
    "Open Ended Schemes(Other Scheme - Other  ETFs)": None,
    "Open Ended Schemes(Exchange Traded Funds (ETFs) - Equity ETF)": None,
    "Open Ended Schemes(Exchange Traded Funds (ETFs) - Debt ETF)": None,
    "Open Ended Schemes(Exchange Traded Funds (ETFs) - Hybrid ETF)": None,
    "Open Ended Schemes(Exchange Traded Funds (ETFs) - Other ETF)": None,
    "Open Ended Schemes(Exchange Traded Funds (ETFs) - ETFs investing overseas)": None,
}

_GOLD_NAME_RE = re.compile(r"\bgold\b", re.IGNORECASE)

_EQUITY_INDEX_RE = re.compile(
    r"\b("
    r"nifty\s*50|nifty50|sensex|nifty\s*next\s*50|nifty\s*midcap|nifty\s*smallcap|"
    r"nifty\s*100|nifty\s*200|nifty\s*500|bse\s*100|bse\s*200|bse\s*500|"
    r"nifty\s*bank|bank\s*nifty|nifty\s*it|nifty\s*auto|nifty\s*metal|nifty\s*pharma|"
    r"nifty\s*infra|nifty\s*fmcg|nifty\s*energy"
    r")\b",
    re.IGNORECASE,
)

_DEBT_NAME_RE = re.compile(
    r"\b(g\s*-?\s*sec|gilt|sdl|liquid|bharat\s*bond|cpse|target\s*maturity|treasury|t\s*-?\s*bill)\b",
    re.IGNORECASE,
)

_DIRECT_RE = re.compile(r"\b(direct|dir)\b", re.IGNORECASE)
_REGULAR_RE = re.compile(r"\b(regular|reg)\b", re.IGNORECASE)

_GROWTH_RE = re.compile(r"\b(growth|gr)\b", re.IGNORECASE)
_IDCW_RE = re.compile(
    r"\b(idcw|dividend|div|div\.|payout|reinvestment|reinvest|bonus)\b",
    re.IGNORECASE,
)


def normalize_name(name: str) -> str:
    """Normalize fund name: lowercase, punctuation to spaces, collapsed whitespace."""
    cleaned = name.lower()
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return " ".join(cleaned.split())


def derive_plan_type(name: str, plan_raw: str | None = None) -> str:
    """Derive plan type: direct, regular, or unknown."""
    combined = f"{name} {plan_raw or ''}"
    if _DIRECT_RE.search(combined):
        return "direct"
    if _REGULAR_RE.search(combined):
        return "regular"
    return "unknown"


def derive_option_type(name: str, option_raw: str | None = None) -> str:
    """Derive option type: growth, idcw, or unknown."""
    combined = f"{name} {option_raw or ''}"
    if _GROWTH_RE.search(combined):
        return "growth"
    if _IDCW_RE.search(combined):
        return "idcw"
    return "unknown"


def _classify_by_name(name: str) -> tuple[str, str | None, str]:
    """Classify by name rules: gold, known broad equity index, or known debt."""
    if _GOLD_NAME_RE.search(name):
        return "gold", "gold", "name_rule"
    if _EQUITY_INDEX_RE.search(name):
        return "equity", "index", "name_rule"
    if _DEBT_NAME_RE.search(name):
        return "debt", "index-debt", "name_rule"
    return "other", None, "unknown"


def classify_fund(
    name: str,
    category_raw: str,
    plan_raw: str | None = None,
    option_raw: str | None = None,
) -> FundClassification:
    """Classify fund into asset class, subcategory, source, plan, and option."""
    plan_type = derive_plan_type(name, plan_raw)
    option_type = derive_option_type(name, option_raw)

    clean_category = category_raw.strip()

    if clean_category in _CATEGORY_TABLE:
        mapping = _CATEGORY_TABLE[clean_category]
        if mapping is not None:
            # Explicit category mapping
            asset_class, sub_category = mapping
            return FundClassification(
                asset_class=asset_class,
                sub_category=sub_category,
                classification_source="category",
                plan_type=plan_type,
                option_type=option_type,
            )
        # Category indicates Index Fund / ETF; delegate to name rules
        asset_class, sub_category, source = _classify_by_name(name)
        return FundClassification(
            asset_class=asset_class,
            sub_category=sub_category,
            classification_source=source,
            plan_type=plan_type,
            option_type=option_type,
        )

    # Category not in table or unknown: try name rules, fallback to other/unknown
    asset_class, sub_category, source = _classify_by_name(name)
    return FundClassification(
        asset_class=asset_class,
        sub_category=sub_category,
        classification_source=source,
        plan_type=plan_type,
        option_type=option_type,
    )
