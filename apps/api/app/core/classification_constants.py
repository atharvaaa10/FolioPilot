"""Canonical taxonomy of mutual fund asset classes and sub-categories."""

from typing import Final

# Canonical set of valid (asset_class, sub_category) tuples
CANONICAL_CLASSIFICATIONS: Final[frozenset[tuple[str, str | None]]] = frozenset(
    {
        # Equity sub-categories
        ("equity", "large-cap"),
        ("equity", "mid-cap"),
        ("equity", "small-cap"),
        ("equity", "flexi-cap"),
        ("equity", "multi-cap"),
        ("equity", "large-and-mid-cap"),
        ("equity", "focused"),
        ("equity", "value"),
        ("equity", "contra"),
        ("equity", "dividend-yield"),
        ("equity", "elss"),
        ("equity", "growth"),
        ("equity", "sectoral-thematic"),
        ("equity", "sectoral"),
        ("equity", "thematic"),
        ("equity", "index"),
        ("equity", "international"),
        # Debt sub-categories
        ("debt", "overnight"),
        ("debt", "liquid"),
        ("debt", "ultra-short-duration"),
        ("debt", "low-duration"),
        ("debt", "money-market"),
        ("debt", "short-duration"),
        ("debt", "medium-duration"),
        ("debt", "medium-to-long-duration"),
        ("debt", "long-duration"),
        ("debt", "dynamic-bond"),
        ("debt", "corporate-bond"),
        ("debt", "credit-risk"),
        ("debt", "banking-and-psu"),
        ("debt", "gilt"),
        ("debt", "10-year-gilt"),
        ("debt", "floater"),
        ("debt", "dynamic-term"),
        ("debt", "fixed-term-plan"),
        ("debt", "other-debt"),
        ("debt", "interval-income"),
        ("debt", "income"),
        ("debt", "long-term"),
        ("debt", "medium-term"),
        ("debt", "medium-to-long-term"),
        ("debt", "short-term"),
        ("debt", "ultra-short-term"),
        ("debt", "ultra-short-to-short-term"),
        ("debt", "sectoral"),
        ("debt", "index-debt"),
        # Hybrid sub-categories
        ("hybrid", "conservative-hybrid"),
        ("hybrid", "balanced-hybrid"),
        ("hybrid", "aggressive-hybrid"),
        ("hybrid", "balanced-advantage"),
        ("hybrid", "multi-asset-allocation"),
        ("hybrid", "arbitrage"),
        ("hybrid", "equity-savings"),
        ("hybrid", "index-hybrid"),
        # Gold
        ("gold", "gold-etf"),
        # Other (commodities, specialized, solution-oriented, fof, unknown)
        ("other", "silver"),
        ("other", "silver-etf"),
        ("other", "solution-oriented"),
        ("other", "fof"),
        ("other", "life-cycle"),
        ("other", "unknown"),
        ("other", None),
    }
)

VALID_ASSET_CLASSES: Final[frozenset[str]] = frozenset(
    {"equity", "debt", "hybrid", "gold", "other"}
)
