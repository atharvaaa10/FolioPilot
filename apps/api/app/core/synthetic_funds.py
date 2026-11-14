"""Shared synthetic fund definitions for fixture generation and integration tests.

Used by:
- apps/api/scripts/generate_import_fixtures.py
- apps/api/tests/integration/test_imports_api.py
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SyntheticFund:
    scheme_code: int
    name: str
    isin_growth: str | None
    isin_reinvest: str | None
    asset_class: str
    sub_category: str
    is_active: bool = True
    nav: str = "50.00"


# Canonical funds used in Phase 4 tests and fixtures
SYNTHETIC_PPFC = SyntheticFund(
    scheme_code=122639,
    name="Parag Parikh Flexi Cap Fund - Direct Plan - Growth",
    isin_growth="INF879O01018",
    isin_reinvest="INF879O01026",
    asset_class="equity",
    sub_category="flexi-cap",
    is_active=True,
    nav="50.00",
)

SYNTHETIC_ISIN_FUND_A = SyntheticFund(
    scheme_code=999001,
    name="FolioPilot Synthetic Growth Fund A",
    isin_growth="INF999001018",
    isin_reinvest="INF999001026",
    asset_class="equity",
    sub_category="flexi-cap",
    is_active=True,
    nav="100.00",
)

SYNTHETIC_ISIN_FUND_B = SyntheticFund(
    scheme_code=999002,
    name="FolioPilot Synthetic Bluechip Fund B",
    isin_growth="INF999002016",
    isin_reinvest="INF999002024",
    asset_class="equity",
    sub_category="large-cap",
    is_active=True,
    nav="200.00",
)

SYNTHETIC_INACTIVE_FUND = SyntheticFund(
    scheme_code=999003,
    name="FolioPilot Synthetic Inactive Fund C",
    isin_growth="INF999003014",
    isin_reinvest="INF999003022",
    asset_class="debt",
    sub_category="liquid",
    is_active=False,
    nav="10.00",
)

SYNTHETIC_AMBIGUOUS_FUND_1 = SyntheticFund(
    scheme_code=999004,
    name="FolioPilot Synthetic Shared ISIN Fund 1",
    isin_growth="INF999999999",
    isin_reinvest=None,
    asset_class="equity",
    sub_category="index",
    is_active=True,
    nav="30.00",
)

SYNTHETIC_AMBIGUOUS_FUND_2 = SyntheticFund(
    scheme_code=999005,
    name="FolioPilot Synthetic Shared ISIN Fund 2",
    isin_growth="INF999999999",
    isin_reinvest=None,
    asset_class="equity",
    sub_category="index",
    is_active=True,
    nav="40.00",
)

SYNTHETIC_VALUATION_FUND = SyntheticFund(
    scheme_code=999101,
    name="FolioPilot Synthetic Valuation Fund",
    isin_growth="INF999101018",
    isin_reinvest="INF999101026",
    asset_class="equity",
    sub_category="flexi-cap",
    is_active=True,
    nav="115.5000",
)

ALL_SYNTHETIC_FUNDS: list[SyntheticFund] = [
    SYNTHETIC_PPFC,
    SYNTHETIC_ISIN_FUND_A,
    SYNTHETIC_ISIN_FUND_B,
    SYNTHETIC_INACTIVE_FUND,
    SYNTHETIC_AMBIGUOUS_FUND_1,
    SYNTHETIC_AMBIGUOUS_FUND_2,
    SYNTHETIC_VALUATION_FUND,
]
