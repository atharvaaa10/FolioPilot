"""Generate Phase 4 Excel import fixtures and expected summary results."""

import datetime as dt
import json
import sys
from pathlib import Path

import openpyxl

# Add apps/api to sys.path so we can import app modules directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.synthetic_funds import (
    SYNTHETIC_ISIN_FUND_A,
    SYNTHETIC_ISIN_FUND_B,
    SYNTHETIC_PPFC,
)
from app.services.import_file import inspect_and_read_workbook
from app.services.import_planner import plan_import
from app.services.import_rows import normalize_row
from app.services.import_template import TEMPLATE_HEADERS

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "imports"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)


def create_workbook(headers: list[str], rows: list[list[object]]) -> openpyxl.Workbook:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Transactions"
    ws.append(headers)
    for r in rows:
        ws.append(r)
    return wb


def generate_worked_example() -> Path:
    wb = create_workbook(
        TEMPLATE_HEADERS,
        [
            # row 2: real date cell
            [
                dt.date(2025, 1, 10),
                122639,
                None,
                "buy",
                100,
                50,
                5000,
                "Initial lump sum",
                "Parag Parikh Flexi Cap",
            ],
            # row 3: amount blank (derived 3000.00)
            [
                dt.date(2025, 2, 10),
                122639,
                None,
                "buy",
                50,
                60,
                None,
                "Second buy",
                "Parag Parikh Flexi Cap",
            ],
            # row 4: text date, nav blank (derived 70)
            [
                "2025-03-10",
                122639,
                None,
                "sell",
                30,
                None,
                2100,
                "Partial redemption",
                "Parag Parikh Flexi Cap",
            ],
        ],
    )
    path = FIXTURES_DIR / "worked-example.xlsx"
    wb.save(path)
    return path


def generate_with_errors() -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Transactions"
    ws.append(TEMPLATE_HEADERS)

    # row 2: valid row
    ws.append([dt.date(2025, 1, 10), 122639, None, "buy", 100, 50, 5000, "Valid row", None])
    # row 3: unknown scheme code
    ws.append([dt.date(2025, 1, 11), 888888, None, "buy", 10, 50, 500, "Unknown fund", None])
    # row 4: bad date "31-02-2025"
    ws.append(["31-02-2025", 122639, None, "buy", 10, 50, 500, "Bad date", None])
    # row 5: type "swap"
    ws.append([dt.date(2025, 1, 12), 122639, None, "swap", 10, 50, 500, "Invalid type", None])
    # row 6: units with 5 decimals
    ws.append(
        [dt.date(2025, 1, 13), 122639, None, "buy", 10.12345, 50, 506.17, "5 decimals units", None]
    )
    # row 7: negative amount
    ws.append([dt.date(2025, 1, 14), 122639, None, "buy", 10, 50, -500, "Negative amount", None])
    # row 8: oversell (balance is only 100 units from row 2, trying to sell 500 units)
    ws.append([dt.date(2025, 1, 15), 122639, None, "sell", 500, 50, 25000, "Oversell error", None])
    # row 9: no fund identifier
    ws.append([dt.date(2025, 1, 16), None, None, "buy", 10, 50, 500, "Missing fund", None])
    # row 10: 201-character notes
    ws.append([dt.date(2025, 1, 17), 122639, None, "buy", 10, 50, 500, "A" * 201, None])
    # row 11: formula cell without a cached value
    ws.cell(row=11, column=1, value=dt.date(2025, 1, 18))
    ws.cell(row=11, column=2, value=122639)
    ws.cell(row=11, column=3, value=None)
    ws.cell(row=11, column=4, value="buy")
    ws.cell(row=11, column=5, value=10)
    ws.cell(row=11, column=6, value=50)
    # Put formula in column 7 without cached value
    cell_formula = ws.cell(row=11, column=7, value="=E11*F11")
    cell_formula.data_type = "f"
    ws.cell(row=11, column=8, value="Formula row")
    ws.cell(row=11, column=9, value=None)

    path = FIXTURES_DIR / "with-errors.xlsx"
    wb.save(path)
    return path


def generate_duplicates_in_file() -> Path:
    wb = create_workbook(
        TEMPLATE_HEADERS,
        [
            # row 2
            [dt.date(2025, 1, 10), 122639, None, "buy", 100, 50, 5000, "Duplicate 1", None],
            # row 3: identical to row 2
            [dt.date(2025, 1, 10), 122639, None, "buy", 100, 50, 5000, "Duplicate 2", None],
            # row 4: different
            [dt.date(2025, 2, 10), 122639, None, "buy", 50, 60, 3000, "Different buy", None],
        ],
    )
    path = FIXTURES_DIR / "duplicates-in-file.xlsx"
    wb.save(path)
    return path


def generate_formats() -> Path:
    wb = create_workbook(
        TEMPLATE_HEADERS,
        [
            # row 2: DD/MM/YYYY text date, scheme_code float "122639.0", alias Purchase, commas
            [
                "15/01/2025",
                "122639.0",
                None,
                "Purchase",
                "10,000.5000",
                "50.25",
                "₹ 502,525.13",
                "Formatted text",
                None,
            ],
            # row 3: DD-MM-YYYY text date, alias REDEMPTION, INR symbol
            [
                "20-02-2025",
                122639,
                None,
                "REDEMPTION",
                "1,000",
                "55",
                "INR 55,000.00",
                "Redemption",
                None,
            ],
        ],
    )
    path = FIXTURES_DIR / "formats.xlsx"
    wb.save(path)
    return path


def generate_isin() -> Path:
    wb = create_workbook(
        TEMPLATE_HEADERS,
        [
            # row 2: fund A by ISIN only
            [
                dt.date(2025, 1, 10),
                None,
                SYNTHETIC_ISIN_FUND_A.isin_growth,
                "buy",
                10,
                100,
                1000,
                "ISIN Fund A",
                None,
            ],
            # row 3: fund B by ISIN only
            [
                dt.date(2025, 1, 12),
                None,
                SYNTHETIC_ISIN_FUND_B.isin_growth,
                "buy",
                20,
                200,
                4000,
                "ISIN Fund B",
                None,
            ],
        ],
    )
    path = FIXTURES_DIR / "isin.xlsx"
    wb.save(path)
    return path


def generate_headers_only() -> Path:
    wb = create_workbook(TEMPLATE_HEADERS, [])
    path = FIXTURES_DIR / "headers-only.xlsx"
    wb.save(path)
    return path


def generate_missing_header() -> Path:
    # Header missing 'txn_type'
    headers = [h for h in TEMPLATE_HEADERS if h != "txn_type"]
    wb = create_workbook(
        headers,
        [
            [dt.date(2025, 1, 10), 122639, None, 100, 50, 5000, "Notes", "PPFC"],
        ],
    )
    path = FIXTURES_DIR / "missing-header.xlsx"
    wb.save(path)
    return path


def generate_extra_columns() -> Path:
    headers = list(TEMPLATE_HEADERS) + ["broker_name", "folio_number", "external_id"]
    wb = create_workbook(
        headers,
        [
            [
                dt.date(2025, 1, 10),
                122639,
                None,
                "buy",
                100,
                50,
                5000,
                "Notes",
                "PPFC",
                "Zerodha",
                "12345/67",
                "EXT-999",
            ],
        ],
    )
    path = FIXTURES_DIR / "extra-columns.xlsx"
    wb.save(path)
    return path


def compute_expected_for_fixtures() -> dict[str, object]:
    """Compute expected preview outputs for the committed valid/parseable fixtures."""

    # Synthetic fund master objects for mock planning
    class MockFund:
        def __init__(self, f: object) -> None:
            self.id = f.scheme_code
            self.scheme_code = f.scheme_code
            self.name = f.name
            self.isin_growth = f.isin_growth
            self.isin_reinvest = f.isin_reinvest
            self.is_active = getattr(f, "is_active", True)

    mock_ppfc = MockFund(SYNTHETIC_PPFC)
    mock_fund_a = MockFund(SYNTHETIC_ISIN_FUND_A)
    mock_fund_b = MockFund(SYNTHETIC_ISIN_FUND_B)

    fund_by_code = {122639: mock_ppfc, 999001: mock_fund_a, 999002: mock_fund_b}
    fund_by_isin = {
        mock_ppfc.isin_growth: [mock_ppfc],
        mock_fund_a.isin_growth: [mock_fund_a],
        mock_fund_b.isin_growth: [mock_fund_b],
    }

    expected_results: dict[str, object] = {}

    fixture_files = [
        "worked-example.xlsx",
        "with-errors.xlsx",
        "duplicates-in-file.xlsx",
        "formats.xlsx",
        "isin.xlsx",
        "extra-columns.xlsx",
    ]

    for fname in fixture_files:
        fpath = FIXTURES_DIR / fname
        parsed = inspect_and_read_workbook(fpath.read_bytes(), fname)
        normalized = [normalize_row(r) for r in parsed.raw_rows]
        plan = plan_import(
            normalized_rows=normalized,
            fund_lookup_by_code=fund_by_code,
            fund_lookup_by_isin=fund_by_isin,
            existing_ledger_by_fund={},
            existing_duplicate_counts={},
            active_sips=[],
        )

        rows_summary = [
            {
                "row_number": r.row_number,
                "status": r.status,
                "txn_type": r.txn_type,
                "units": f"{r.units:.4f}" if r.units is not None else None,
                "nav": f"{r.nav:.8f}" if r.nav is not None else None,
                "amount": f"{r.amount:.2f}" if r.amount is not None else None,
                "error_codes": [m["code"] for m in r.messages if m["level"] == "error"],
                "warning_codes": [m["code"] for m in r.messages if m["level"] == "warning"],
            }
            for r in plan.rows
        ]

        expected_results[fname] = {
            "rows_total": plan.rows_total,
            "rows_ok": plan.rows_ok,
            "rows_warning": plan.rows_warning,
            "rows_duplicate": plan.rows_duplicate,
            "rows_error": plan.rows_error,
            "will_import": plan.will_import,
            "plan_fingerprint": plan.plan_fingerprint,
            "extra_columns": parsed.extra_columns,
            "funds_count": plan.funds_count,
            "date_range": plan.date_range,
            "totals": plan.totals,
            "rows": rows_summary,
        }

    return expected_results


def main() -> None:
    print("Generating Phase 4 Excel import fixtures...")
    generate_worked_example()
    generate_with_errors()
    generate_duplicates_in_file()
    generate_formats()
    generate_isin()
    generate_headers_only()
    generate_missing_header()
    generate_extra_columns()

    expected = compute_expected_for_fixtures()
    expected_path = FIXTURES_DIR / "expected.json"
    expected_path.write_text(json.dumps(expected, indent=2), encoding="utf-8")
    print(f"Generated 8 fixtures + expected.json in {FIXTURES_DIR}")


if __name__ == "__main__":
    main()
