"""Generates canonical contract fixtures matching backend schemas."""

import json
import sys
from pathlib import Path
from typing import Any

# Ensure apps/api is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.fund import (
    FundDetailResponse,
    FundNavHistoryResponse,
    FundSearchItem,
    FundSearchResponse,
    NavPoint,
    NavStatusResponse,
    TrackFundResponse,
)
from app.schemas.portfolio import TargetItem
from app.schemas.transaction import (
    FundSummary,
    HoldingResponse,
    HoldingsListResponse,
    HoldingsTotals,
    PortfolioDetailResponse,
    TransactionListResponse,
    TransactionResponse,
)

FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "web"
    / "src"
    / "test"
    / "fixtures"
    / "contract"
)


def generate_fixtures() -> dict[str, Any]:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    portfolio_id = "11111111-1111-1111-1111-111111111111"
    fund_id = "33333333-3333-3333-3333-333333333333"

    # 1. Targets
    targets_data = [
        {"asset_class": "equity", "target_pct": "60.00"},
        {"asset_class": "debt", "target_pct": "30.00"},
        {"asset_class": "gold", "target_pct": "10.00"},
    ]

    # 2. Portfolio Detail
    portfolio_detail_data = {
        "id": portfolio_id,
        "name": "Retirement",
        "description": "Long-term retirement portfolio",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "targets": targets_data,
        "total_cost_basis": "6400.00",
        "open_positions": 1,
        "total_transactions": 3,
    }

    # 3. Holdings
    holdings_data = {
        "items": [
            {
                "scheme_code": 122639,
                "fund": {
                    "name": "Parag Parikh Flexi Cap Fund",
                    "amc": "PPFAS Mutual Fund",
                    "asset_class": "equity",
                    "sub_category": "flexi-cap",
                    "plan_type": "direct",
                    "option_type": "growth",
                    "latest_nav": "33.84000000",
                    "latest_nav_date": "2026-11-06",
                },
                "units": "120.0000",
                "avg_cost": "53.3333",
                "cost_basis": "6400.00",
                "total_bought": "8000.00",
                "total_sold": "2100.00",
                "first_txn_date": "2025-01-10",
                "last_txn_date": "2025-03-10",
                "txn_count": 3,
                "is_closed": False,
            }
        ],
        "totals": {
            "cost_basis": "6400.00",
            "open_positions": 1,
        },
    }

    # 4. Transactions List
    transactions_data = {
        "items": [
            {
                "id": "22222222-2222-2222-2222-222222222221",
                "portfolio_id": portfolio_id,
                "fund_id": fund_id,
                "scheme_code": 122639,
                "fund_name": "Parag Parikh Flexi Cap Fund",
                "txn_type": "buy",
                "txn_date": "2025-01-10",
                "units": "100.0000",
                "nav": "50.00000000",
                "amount": "5000.00",
                "notes": "Initial purchase",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "portfolio_id": portfolio_id,
                "fund_id": fund_id,
                "scheme_code": 122639,
                "fund_name": "Parag Parikh Flexi Cap Fund",
                "txn_type": "buy",
                "txn_date": "2025-02-10",
                "units": "50.0000",
                "nav": "60.00000000",
                "amount": "3000.00",
                "notes": None,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": "22222222-2222-2222-2222-222222222223",
                "portfolio_id": portfolio_id,
                "fund_id": fund_id,
                "scheme_code": 122639,
                "fund_name": "Parag Parikh Flexi Cap Fund",
                "txn_type": "sell",
                "txn_date": "2025-03-10",
                "units": "30.0000",
                "nav": "70.00000000",
                "amount": "2100.00",
                "notes": None,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
        ],
        "has_more": False,
    }

    # 5. Error Responses
    error_insufficient_units = {
        "code": "INSUFFICIENT_UNITS",
        "message": "Insufficient units for sell transaction",
        "details": {
            "available_units": "120.0000",
            "date": "2025-03-11",
        },
    }

    error_ledger_inconsistent = {
        "code": "LEDGER_INCONSISTENT",
        "message": "Operation would cause negative unit balance in transaction history",
        "details": {
            "fund": fund_id,
            "fund_id": fund_id,
            "date": "2025-04-10",
        },
    }

    # 6. Funds responses
    funds_search_data = {
        "items": [
            {
                "id": fund_id,
                "scheme_code": 122639,
                "name": "Parag Parikh Flexi Cap Fund",
                "amc": "PPFAS Mutual Fund",
                "category_raw": "Open Ended Schemes(Equity Scheme - Flexi Cap Fund)",
                "asset_class": "equity",
                "sub_category": "flexi-cap",
                "plan_type": "direct",
                "option_type": "growth",
                "latest_nav": "33.84000000",
                "latest_nav_date": "2026-11-06",
                "is_active": True,
                "is_tracked": True,
            }
        ],
        "has_more": False,
    }

    fund_detail_data = {
        "id": fund_id,
        "scheme_code": 122639,
        "isin_growth": "INF879O01027",
        "isin_reinvest": None,
        "name": "Parag Parikh Flexi Cap Fund",
        "amc": "PPFAS Mutual Fund",
        "scheme_type_raw": "Open Ended",
        "category_raw": "Open Ended Schemes(Equity Scheme - Flexi Cap Fund)",
        "asset_class": "equity",
        "sub_category": "flexi-cap",
        "classification_source": "category",
        "plan_type": "direct",
        "option_type": "growth",
        "latest_nav": "33.84000000",
        "latest_nav_date": "2026-11-06",
        "is_active": True,
        "is_tracked": True,
    }

    nav_history_data = {
        "scheme_code": 122639,
        "name": "Parag Parikh Flexi Cap Fund",
        "history_available": True,
        "points": [
            {"date": "2026-11-04", "nav": "33.72000000"},
            {"date": "2026-11-05", "nav": "33.80000000"},
            {"date": "2026-11-06", "nav": "33.84000000"},
        ],
    }

    nav_status_data = {
        "last_run_time": "2026-11-08T10:00:00Z",
        "last_run_status": "success",
        "last_success_time": "2026-11-08T10:00:00Z",
        "schemes_parsed": 14584,
        "funds_created": 0,
        "funds_updated": 0,
        "nav_rows_written": 0,
        "is_stale": False,
    }

    track_fund_data = {
        "scheme_code": 122639,
        "status": "already_tracked",
    }

    fixtures = {
        "targets.json": targets_data,
        "portfolio-detail.json": portfolio_detail_data,
        "holdings.json": holdings_data,
        "transactions.json": transactions_data,
        "error-insufficient-units.json": error_insufficient_units,
        "error-ledger-inconsistent.json": error_ledger_inconsistent,
        "funds-search.json": funds_search_data,
        "fund-detail.json": fund_detail_data,
        "nav-history.json": nav_history_data,
        "nav-status.json": nav_status_data,
        "track-fund.json": track_fund_data,
    }

    for filename, content in fixtures.items():
        filepath = FIXTURE_DIR / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2)
            f.write("\n")

    print(f"Generated {len(fixtures)} contract fixtures in {FIXTURE_DIR}")
    return fixtures


if __name__ == "__main__":
    generate_fixtures()
