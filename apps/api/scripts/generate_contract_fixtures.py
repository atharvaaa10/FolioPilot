"""Generates canonical contract fixtures matching backend schemas."""

import json
import sys
from pathlib import Path
from typing import Any

# Ensure apps/api is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent.parent / "web" / "src" / "test" / "fixtures" / "contract"
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

    # 7. SIPs responses
    sip_id = "44444444-4444-4444-4444-444444444444"
    installment_id_1 = "55555555-5555-5555-5555-555555555551"
    installment_id_2 = "55555555-5555-5555-5555-555555555552"

    sip_detail_data = {
        "id": sip_id,
        "portfolio_id": portfolio_id,
        "fund": {
            "scheme_code": 122639,
            "name": "Parag Parikh Flexi Cap Fund",
            "amc": "PPFAS Mutual Fund",
            "plan_type": "direct",
            "option_type": "growth",
            "asset_class": "equity",
            "sub_category": "flexi-cap",
        },
        "amount": "5000.00",
        "day_of_month": 10,
        "start_date": "2026-05-10",
        "end_date": "2026-10-10",
        "step_up_percent": "0.00",
        "notes": "Monthly Flexi Cap SIP",
        "status": "active",
        "next_due_date": "2026-06-10",
        "next_installment_amount": "5000.00",
        "pauses": [],
        "stats": {
            "installments_total": 6,
            "executed": 1,
            "pending": 5,
            "skipped": 0,
            "total_invested": "5000.00",
            "units_acquired": "90.2527",
        },
        "created_at": "2026-05-01T00:00:00Z",
    }

    sips_list_data = {
        "items": [sip_detail_data],
        "total": 1,
    }

    sip_installments_data = {
        "items": [
            {
                "id": installment_id_1,
                "sip_id": sip_id,
                "due_date": "2026-05-10",
                "planned_amount": "5000.00",
                "status": "executed",
                "nav_date": "2026-05-11",
                "transaction": {
                    "id": "22222222-2222-2222-2222-222222222221",
                    "txn_date": "2026-05-11",
                    "units": "90.2527",
                    "nav": "55.40000000",
                    "amount": "5000.00",
                },
            },
            {
                "id": installment_id_2,
                "sip_id": sip_id,
                "due_date": "2026-06-10",
                "planned_amount": "5000.00",
                "status": "pending",
                "nav_date": None,
                "transaction": None,
            },
        ],
        "total": 2,
        "has_more": False,
        "limit": 50,
        "offset": 0,
    }

    sip_preview_data = {
        "items": [
            {"due_date": "2026-05-10", "planned_amount": "5000.00"},
            {"due_date": "2026-06-10", "planned_amount": "5000.00"},
            {"due_date": "2026-07-10", "planned_amount": "5000.00"},
            {"due_date": "2026-08-10", "planned_amount": "5000.00"},
            {"due_date": "2026-09-10", "planned_amount": "5000.00"},
            {"due_date": "2026-10-10", "planned_amount": "5000.00"},
        ],
        "count": 6,
    }

    error_sip_invalid_schedule = {
        "code": "SIP_INVALID_SCHEDULE",
        "message": "SIP schedule contains no valid due dates in the specified range",
        "details": {
            "start_date": "2026-05-10",
            "day_of_month": 10,
            "end_date": "2026-05-01",
        },
    }

    error_sip_already_paused = {
        "code": "SIP_ALREADY_PAUSED",
        "message": "SIP is already paused",
        "details": {
            "open_pause_id": "66666666-6666-6666-6666-666666666666",
        },
    }

    error_sip_not_paused = {
        "code": "SIP_NOT_PAUSED",
        "message": "SIP is not currently paused",
        "details": {},
    }

    error_sip_already_ended = {
        "code": "SIP_ALREADY_ENDED",
        "message": "SIP has already ended",
        "details": {
            "end_date": "2026-10-10",
        },
    }

    error_transaction_managed_by_sip = {
        "code": "TRANSACTION_MANAGED_BY_SIP",
        "message": "Transaction is managed by a SIP and cannot be edited or deleted directly",
        "details": {
            "sip_installment_id": installment_id_1,
        },
    }

    error_installment_not_skippable = {
        "code": "INSTALLMENT_NOT_SKIPPABLE",
        "message": "Installment has already been skipped",
        "details": {
            "status": "skipped",
        },
    }

    error_fund_inactive = {
        "code": "FUND_INACTIVE",
        "message": "Fund is inactive and cannot accept new investments",
        "details": {
            "fund_id": fund_id,
        },
    }

    # Phase 4 Import Contract Fixtures
    import_id = "55555555-5555-5555-5555-555555555555"
    import_summary_data = {
        "id": import_id,
        "portfolio_id": portfolio_id,
        "filename": "worked-example.xlsx",
        "file_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "status": "previewed",
        "rows_total": 3,
        "rows_ok": 3,
        "rows_warning": 0,
        "rows_duplicate": 0,
        "rows_error": 0,
        "will_import": 3,
        "plan_fingerprint": "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        "extra_columns": [],
        "funds_count": 1,
        "date_range": {
            "from": "2025-01-10",
            "to": "2025-03-10",
        },
        "totals": {
            "buy_amount": "8000.00",
            "sell_amount": "2100.00",
        },
        "blocking_errors": [],
        "previewed_at": "2026-01-01T00:00:00Z",
        "expires_at": "2026-01-02T00:00:00Z",
        "committed_count": None,
        "committed_at": None,
        "undone_count": None,
        "undone_at": None,
    }

    import_rows_data = {
        "items": [
            {
                "row_number": 2,
                "status": "ok",
                "fund": {
                    "scheme_code": 122639,
                    "name": "Parag Parikh Flexi Cap Fund",
                    "amc": "PPFAS Mutual Fund",
                    "plan_type": "direct",
                    "option_type": "growth",
                    "is_active": True,
                },
                "fund_name_in_file": "Parag Parikh Flexi Cap",
                "txn_type": "buy",
                "txn_date": "2025-01-10",
                "units": "100.0000",
                "nav": "50.00000000",
                "amount": "5000.00",
                "notes": "Initial lump sum",
                "raw": {
                    "txn_date": "2025-01-10",
                    "scheme_code": "122639",
                    "txn_type": "buy",
                    "units": "100",
                    "nav": "50",
                    "amount": "5000",
                },
                "messages": [],
            }
        ],
        "has_more": False,
    }

    import_history_data = [import_summary_data]

    error_import_file_invalid = {
        "code": "IMPORT_FILE_INVALID",
        "message": "Invalid import file format",
        "details": None,
    }

    error_import_file_too_large = {
        "code": "IMPORT_FILE_TOO_LARGE",
        "message": "Import file exceeds maximum allowed size",
        "details": {"max_bytes": 2097152},
    }

    error_import_template_mismatch = {
        "code": "IMPORT_TEMPLATE_MISMATCH",
        "message": "Missing required columns in template header",
        "details": {"missing_headers": ["txn_type"]},
    }

    error_import_has_errors = {
        "code": "IMPORT_HAS_ERRORS",
        "message": "Import contains invalid rows",
        "details": {"rows_error": 9, "will_import": 1},
    }

    error_import_stale = {
        "code": "IMPORT_STALE",
        "message": "Import preview is stale due to recent ledger changes",
        "details": None,
    }

    error_import_nothing_to_import = {
        "code": "IMPORT_NOTHING_TO_IMPORT",
        "message": "No rows to import",
        "details": None,
    }

    error_import_already_committed = {
        "code": "IMPORT_ALREADY_COMMITTED",
        "message": "Import has already been committed",
        "details": None,
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
        "sip-detail.json": sip_detail_data,
        "sips-list.json": sips_list_data,
        "sip-installments.json": sip_installments_data,
        "sip-preview.json": sip_preview_data,
        "error-sip-invalid-schedule.json": error_sip_invalid_schedule,
        "error-sip-already-paused.json": error_sip_already_paused,
        "error-sip-not-paused.json": error_sip_not_paused,
        "error-sip-already-ended.json": error_sip_already_ended,
        "error-transaction-managed-by-sip.json": error_transaction_managed_by_sip,
        "error-installment-not-skippable.json": error_installment_not_skippable,
        "error-fund-inactive.json": error_fund_inactive,
        "import-summary.json": import_summary_data,
        "import-rows.json": import_rows_data,
        "import-history.json": import_history_data,
        "error-import-file-invalid.json": error_import_file_invalid,
        "error-import-file-too-large.json": error_import_file_too_large,
        "error-import-template-mismatch.json": error_import_template_mismatch,
        "error-import-has-errors.json": error_import_has_errors,
        "error-import-stale.json": error_import_stale,
        "error-import-nothing-to-import.json": error_import_nothing_to_import,
        "error-import-already-committed.json": error_import_already_committed,
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
