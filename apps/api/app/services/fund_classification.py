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


def normalize_category(category_raw: str | None) -> str:
    """Normalize category header: lowercase, collapsed whitespace, trimmed."""
    if not category_raw:
        return ""
    return re.sub(r"\s+", " ", category_raw.strip().lower())


# Explicit table-driven mapping of normalized AMFI category headers to (asset_class, sub_category).
# When None, the category is an ambiguous Index Fund or ETF that delegates to NAME rules.
_NORMALIZED_CATEGORY_TABLE: dict[str, tuple[str, str | None] | None] = {
    # --- Equity Schemes ---
    "open ended schemes(equity scheme - large cap fund)": ("equity", "large-cap"),
    "open ended schemes(equity schemes - large cap fund)": ("equity", "large-cap"),
    "open ended schemes(equity scheme - mid cap fund)": ("equity", "mid-cap"),
    "open ended schemes(equity schemes - mid cap fund)": ("equity", "mid-cap"),
    "open ended schemes(equity scheme - small cap fund)": ("equity", "small-cap"),
    "open ended schemes(equity schemes - small cap fund)": ("equity", "small-cap"),
    "open ended schemes(equity scheme - flexi cap fund)": ("equity", "flexi-cap"),
    "open ended schemes(equity schemes - flexi cap fund)": ("equity", "flexi-cap"),
    "open ended schemes(equity scheme - multi cap fund)": ("equity", "multi-cap"),
    "open ended schemes(equity schemes - multi cap fund)": ("equity", "multi-cap"),
    "open ended schemes(equity scheme - large & mid cap fund)": ("equity", "large-and-mid-cap"),
    "open ended schemes(equity schemes - large & mid cap fund)": ("equity", "large-and-mid-cap"),
    "open ended schemes(equity scheme - focused fund)": ("equity", "focused"),
    "open ended schemes(equity schemes - focused fund)": ("equity", "focused"),
    "open ended schemes(equity scheme - value fund)": ("equity", "value"),
    "open ended schemes(equity schemes - value fund)": ("equity", "value"),
    "open ended schemes(equity scheme - contra fund)": ("equity", "contra"),
    "open ended schemes(equity schemes - contra fund)": ("equity", "contra"),
    "open ended schemes(equity scheme - dividend yield fund)": ("equity", "dividend-yield"),
    "open ended schemes(equity schemes - dividend yield fund)": ("equity", "dividend-yield"),
    "open ended schemes(equity scheme - elss)": ("equity", "elss"),
    "open ended schemes(equity schemes - elss- tax saver fund)": ("equity", "elss"),
    "close ended schemes(elss)": ("equity", "elss"),
    "close ended schemes(growth)": ("equity", "growth"),
    "open ended schemes(growth)": ("equity", "growth"),
    "open ended schemes(equity scheme - sectoral/ thematic)": ("equity", "sectoral-thematic"),
    "open ended schemes(equity schemes - sectoral fund)": ("equity", "sectoral"),
    "open ended schemes(equity schemes - thematic fund)": ("equity", "thematic"),
    # New specific index/etf headings that directly state class
    "open ended schemes(index funds - equity funds)": ("equity", "index"),
    "open ended schemes(exchange traded funds (etfs) - equity etf)": ("equity", "index"),
    "open ended schemes(exchange traded funds (etfs) - etfs investing overseas)": (
        "equity",
        "international",
    ),
    # --- Debt Schemes ---
    "open ended schemes(debt scheme - overnight fund)": ("debt", "overnight"),
    "open ended schemes(debt scheme - liquid fund)": ("debt", "liquid"),
    "open ended schemes(debt scheme - ultra short duration fund)": (
        "debt",
        "ultra-short-duration",
    ),
    "open ended schemes(debt scheme - low duration fund)": ("debt", "low-duration"),
    "open ended schemes(debt scheme - money market fund)": ("debt", "money-market"),
    "open ended schemes(debt scheme - short duration fund)": ("debt", "short-duration"),
    "open ended schemes(debt scheme - medium duration fund)": ("debt", "medium-duration"),
    "open ended schemes(debt scheme - medium to long duration fund)": (
        "debt",
        "medium-to-long-duration",
    ),
    "open ended schemes(debt scheme - long duration fund)": ("debt", "long-duration"),
    "open ended schemes(debt scheme - dynamic bond)": ("debt", "dynamic-bond"),
    "open ended schemes(debt scheme - corporate bond fund)": ("debt", "corporate-bond"),
    "open ended schemes(debt scheme - credit risk fund)": ("debt", "credit-risk"),
    "open ended schemes(debt scheme - banking and psu fund)": ("debt", "banking-and-psu"),
    "open ended schemes(debt scheme - gilt fund)": ("debt", "gilt"),
    "open ended schemes(gilt)": ("debt", "gilt"),
    "open ended schemes(income)": ("debt", "income"),
    "close ended schemes(income)": ("debt", "income"),
    "close ended schemes(income/debt oriented schemes - fixed term plan)": (
        "debt",
        "fixed-term-plan",
    ),
    "close ended schemes(income/debt oriented schemes - other debt scheme)": (
        "debt",
        "other-debt",
    ),
    "interval fund schemes(income)": ("debt", "interval-income"),
    "open ended schemes(income/debt oriented schemes - 10-year constant maturity gilt fund)": (
        "debt",
        "10-year-gilt",
    ),
    "open ended schemes(income/debt oriented schemes - banking and psu debt fund)": (
        "debt",
        "banking-and-psu",
    ),
    "open ended schemes(income/debt oriented schemes - corporate bond fund)": (
        "debt",
        "corporate-bond",
    ),
    "open ended schemes(income/debt oriented schemes - credit risk fund)": (
        "debt",
        "credit-risk",
    ),
    "open ended schemes(income/debt oriented schemes - dynamic term fund)": (
        "debt",
        "dynamic-term",
    ),
    "open ended schemes(income/debt oriented schemes - floating interest rates fund)": (
        "debt",
        "floater",
    ),
    "open ended schemes(income/debt oriented schemes - gilt fund)": ("debt", "gilt"),
    "open ended schemes(income/debt oriented schemes - liquid fund)": ("debt", "liquid"),
    "open ended schemes(income/debt oriented schemes - long term fund)": ("debt", "long-term"),
    "open ended schemes(income/debt oriented schemes - medium term fund)": (
        "debt",
        "medium-term",
    ),
    "open ended schemes(income/debt oriented schemes - medium to long term fund)": (
        "debt",
        "medium-to-long-term",
    ),
    "open ended schemes(income/debt oriented schemes - money market fund)": (
        "debt",
        "money-market",
    ),
    "open ended schemes(income/debt oriented schemes - overnight fund)": ("debt", "overnight"),
    "open ended schemes(income/debt oriented schemes - sectoral fund)": ("debt", "sectoral"),
    "open ended schemes(income/debt oriented schemes - short term fund)": (
        "debt",
        "short-term",
    ),
    "open ended schemes(income/debt oriented schemes - ultra short term fund)": (
        "debt",
        "ultra-short-term",
    ),
    "open ended schemes(income/debt oriented schemes - ultra short to short term fund)": (
        "debt",
        "ultra-short-to-short-term",
    ),
    "open ended schemes(index funds - debt funds)": ("debt", "index-debt"),
    "open ended schemes(exchange traded funds (etfs) - debt etf)": ("debt", "index-debt"),
    # --- Hybrid Schemes ---
    "open ended schemes(hybrid scheme - conservative hybrid fund)": (
        "hybrid",
        "conservative-hybrid",
    ),
    "open ended schemes(hybrid schemes - conservative hybrid fund)": (
        "hybrid",
        "conservative-hybrid",
    ),
    "open ended schemes(hybrid scheme - balanced hybrid fund)": ("hybrid", "balanced-hybrid"),
    "open ended schemes(hybrid schemes - balanced hybrid fund)": ("hybrid", "balanced-hybrid"),
    "open ended schemes(hybrid scheme - aggressive hybrid fund)": (
        "hybrid",
        "aggressive-hybrid",
    ),
    "open ended schemes(hybrid schemes - aggressive hybrid fund)": (
        "hybrid",
        "aggressive-hybrid",
    ),
    "open ended schemes(hybrid scheme - dynamic asset allocation or balanced advantage)": (
        "hybrid",
        "balanced-advantage",
    ),
    "open ended schemes(hybrid schemes - balanced advantage fund/ dynamic asset allocation)": (
        "hybrid",
        "balanced-advantage",
    ),
    "open ended schemes(hybrid scheme - multi asset allocation)": (
        "hybrid",
        "multi-asset-allocation",
    ),
    "open ended schemes(hybrid schemes - multi asset allocation fund)": (
        "hybrid",
        "multi-asset-allocation",
    ),
    "open ended schemes(hybrid scheme - arbitrage fund)": ("hybrid", "arbitrage"),
    "open ended schemes(hybrid schemes - arbitrage fund)": ("hybrid", "arbitrage"),
    "open ended schemes(hybrid scheme - equity savings)": ("hybrid", "equity-savings"),
    "open ended schemes(hybrid schemes - equity savings fund)": ("hybrid", "equity-savings"),
    "open ended schemes(index funds - hybrid fund)": ("hybrid", "index-hybrid"),
    "open ended schemes(exchange traded funds (etfs) - hybrid etf)": (
        "hybrid",
        "index-hybrid",
    ),
    # --- Gold & Commodities ---
    "open ended schemes(exchange traded funds (etfs) - gold etf)": ("gold", "gold-etf"),
    "open ended schemes(other scheme - gold etf)": ("gold", "gold-etf"),
    "open ended schemes(exchange traded funds (etfs) - silver etf)": ("other", "silver-etf"),
    # --- Other Categories ---
    "open ended schemes(solution oriented scheme - children’s fund)": (
        "other",
        "solution-oriented",
    ),
    "open ended schemes(solution oriented scheme - retirement fund)": (
        "other",
        "solution-oriented",
    ),
    "open ended schemes(solution oriented schemes ** - retirement fund)": (
        "other",
        "solution-oriented",
    ),
    "open ended schemes(children’s fund - childrens' fund)": (
        "other",
        "solution-oriented",
    ),
    "open ended schemes(fund of funds scheme (domestic) - fund of funds scheme (domestic))": (
        "other",
        "fof",
    ),
    "open ended schemes(other scheme - fof domestic)": ("other", "fof"),
    "open ended schemes(other scheme - fof overseas)": ("other", "fof"),
    "open ended schemes(overseas fund of funds - fund of funds investing overseas)": (
        "other",
        "fof",
    ),
    "open ended schemes(life cycle funds - life cycle fund with maturity of 5 years)": (
        "other",
        "life-cycle",
    ),
    "open ended schemes(life cycle funds - life cycle fund with maturity of 10 years)": (
        "other",
        "life-cycle",
    ),
    "open ended schemes(life cycle funds - life cycle fund with maturity of 15 years)": (
        "other",
        "life-cycle",
    ),
    "open ended schemes(life cycle funds - life cycle fund with maturity of 30 years)": (
        "other",
        "life-cycle",
    ),
    # --- Ambiguous categories that delegate strictly to NAME rules (mapped to None) ---
    "open ended schemes(other scheme - index funds)": None,
    "open ended schemes(other scheme - other etfs)": None,
    "open ended schemes(exchange traded funds (etfs) - other etf)": None,
}

# --- Strict Name Heuristic Patterns for Ambiguous Headings ---

# (1) Debt keywords: Bond, G-Sec, Gilt, SDL, State Development, Target Maturity,
#     CRISIL-IBX, Debt Index, Treasury, Money Market, Liquid, Overnight, AAA
_NAME_DEBT_RE = re.compile(
    r"\b("
    r"bond|g\s*-?\s*sec|gilt|sdl|state\s+development|target\s+maturity|"
    r"crisil\s*-?\s*ibx|debt\s+index|treasury|money\s+market|liquid|overnight|aaa"
    r")\b",
    re.IGNORECASE,
)

# (2) Gold and Silver keywords
_NAME_GOLD_RE = re.compile(r"\bgold\b", re.IGNORECASE)
_NAME_SILVER_RE = re.compile(r"\bsilver\b", re.IGNORECASE)

# (3) International index keywords: Nasdaq, S&P 500, Hang Seng, NYSE FANG, etc.
_NAME_INTERNATIONAL_RE = re.compile(
    r"\b(nasdaq|s&p\s*500|sp500|hang\s*seng|nyse\s*fang\+?|dow\s*jones)\b",
    re.IGNORECASE,
)

# (4) Known Equity index words: Nifty, Sensex, BSE, Nifty Next 50, Midcap, Smallcap,
#     LargeMidcap, Total Market, Alpha, Quality, Value, Momentum, Low Volatility,
#     sector words such as Bank, IT, Healthcare, Pharma, Manufacturing, Insurance, PSU
_NAME_EQUITY_RE = re.compile(
    r"\b("
    r"nifty|sensex|bse|midcap|smallcap|largemidcap|large\s*midcap|total\s*market|"
    r"alpha|quality|value|momentum|low\s*volatility|bank|it|healthcare|pharma|"
    r"manufacturing|insurance|psu"
    r")\b",
    re.IGNORECASE,
)

# Plan & Option regexes
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


def _classify_ambiguous_by_name(name: str) -> tuple[str, str | None, str]:
    """Classify ambiguous index/ETF schemes using strict 4-level precedence.

    (1) Debt keywords -> debt / index-debt
    (2) Gold -> gold / gold-etf; Silver -> other / silver
    (3) International -> equity / international
    (4) Known equity index words -> equity / index
    Everything else stays other with source unknown.
    """
    clean_name = name.lower()

    # Precedence 1: Debt keywords
    if _NAME_DEBT_RE.search(clean_name):
        return "debt", "index-debt", "name_rule"

    # Precedence 2: Gold & Silver
    if _NAME_GOLD_RE.search(clean_name):
        return "gold", "gold-etf", "name_rule"
    if _NAME_SILVER_RE.search(clean_name):
        return "other", "silver", "name_rule"

    # Check for mixed domestic & global mandates (e.g. Edelweiss MSCI India Domestic & World)
    # which deliberately remain other/unknown
    if "domestic & world" in clean_name or "domestic and world" in clean_name:
        return "other", "unknown", "unknown"

    # Precedence 3: International
    if _NAME_INTERNATIONAL_RE.search(clean_name):
        return "equity", "international", "name_rule"

    # Precedence 4: Known equity index words
    if _NAME_EQUITY_RE.search(clean_name):
        return "equity", "index", "name_rule"

    return "other", "unknown", "unknown"


def classify_fund(
    name: str,
    category_raw: str,
    plan_raw: str | None = None,
    option_raw: str | None = None,
) -> FundClassification:
    """Classify fund into asset class, subcategory, source, plan, and option.

    Guarantees:
    - Never uses name rules if category gives a definite answer.
    - Normalizes category whitespace and casing.
    - Uses strict precedence for ambiguous headings.
    - Resulting (asset_class, sub_category) is in CANONICAL_CLASSIFICATIONS.
    """
    plan_type = derive_plan_type(name, plan_raw)
    option_type = derive_option_type(name, option_raw)

    norm_category = normalize_category(category_raw)

    if norm_category in _NORMALIZED_CATEGORY_TABLE:
        mapping = _NORMALIZED_CATEGORY_TABLE[norm_category]
        if mapping is not None:
            # Explicit category mapping - name rules are NEVER consulted
            asset_class, sub_category = mapping
            return FundClassification(
                asset_class=asset_class,
                sub_category=sub_category,
                classification_source="category",
                plan_type=plan_type,
                option_type=option_type,
            )
        # Category indicates an ambiguous Index Fund / ETF; delegate to name rules
        asset_class, sub_category, source = _classify_ambiguous_by_name(name)
        return FundClassification(
            asset_class=asset_class,
            sub_category=sub_category,
            classification_source=source,
            plan_type=plan_type,
            option_type=option_type,
        )

    # Category not in table: fallback directly to other / unknown (name rules not used)
    return FundClassification(
        asset_class="other",
        sub_category="unknown",
        classification_source="unknown",
        plan_type=plan_type,
        option_type=option_type,
    )
