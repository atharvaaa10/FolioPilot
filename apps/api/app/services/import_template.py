"""Excel template builder for FolioPilot transaction imports."""

import io

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

TEMPLATE_HEADERS = [
    "txn_date",
    "scheme_code",
    "isin",
    "txn_type",
    "units",
    "nav",
    "amount",
    "notes",
    "fund_name",
]

COLUMN_WIDTHS = {
    "A": 16,  # txn_date
    "B": 16,  # scheme_code
    "C": 18,  # isin
    "D": 16,  # txn_type
    "E": 16,  # units
    "F": 16,  # nav
    "G": 18,  # amount
    "H": 30,  # notes
    "I": 35,  # fund_name
}


def build_template() -> bytes:
    """Generate the official FolioPilot transaction import Excel template."""
    wb = openpyxl.Workbook()
    wb.properties.creator = "FolioPilot"

    # --- Sheet 1: Transactions ---
    ws_txns = wb.active
    ws_txns.title = "Transactions"
    ws_txns.views.sheetView[0].showGridLines = True
    ws_txns.freeze_panes = "A2"

    header_font = Font(name="Calibri", size=11, bold=True, color="1F2937")
    header_fill = PatternFill(start_color="F3F4F6", end_color="F3F4F6", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for col_idx, header_text in enumerate(TEMPLATE_HEADERS, start=1):
        cell = ws_txns.cell(row=1, column=col_idx, value=header_text)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align

    # Column widths
    for col_letter, width in COLUMN_WIDTHS.items():
        ws_txns.column_dimensions[col_letter].width = width

    # Data validation: txn_type dropdown
    dv_type = DataValidation(
        type="list",
        formula1='"buy,sell,dividend_reinvest"',
        allow_blank=True,
    )
    dv_type.error = "Transaction type must be buy, sell, or dividend_reinvest"
    dv_type.errorTitle = "Invalid Transaction Type"
    dv_type.prompt = "Select transaction type"
    dv_type.promptTitle = "Transaction Type"
    ws_txns.add_data_validation(dv_type)
    dv_type.add("D2:D5001")

    # Data validation: units > 0
    dv_units = DataValidation(
        type="decimal",
        operator="greaterThan",
        formula1="0",
        allow_blank=True,
    )
    dv_units.error = "Units must be a positive number (up to 4 decimal places)"
    dv_units.errorTitle = "Invalid Units"
    ws_txns.add_data_validation(dv_units)
    dv_units.add("E2:E5001")

    # Data validation: nav > 0
    dv_nav = DataValidation(
        type="decimal",
        operator="greaterThan",
        formula1="0",
        allow_blank=True,
    )
    dv_nav.error = "NAV must be a positive number (up to 8 decimal places)"
    dv_nav.errorTitle = "Invalid NAV"
    ws_txns.add_data_validation(dv_nav)
    dv_nav.add("F2:F5001")

    # Data validation: amount > 0
    dv_amount = DataValidation(
        type="decimal",
        operator="greaterThan",
        formula1="0",
        allow_blank=True,
    )
    dv_amount.error = "Amount must be a positive number (up to 2 decimal places)"
    dv_amount.errorTitle = "Invalid Amount"
    ws_txns.add_data_validation(dv_amount)
    dv_amount.add("G2:G5001")

    # --- Sheet 2: Instructions ---
    ws_inst = wb.create_sheet(title="Instructions")
    ws_inst.views.sheetView[0].showGridLines = True

    title_font = Font(name="Calibri", size=14, bold=True, color="111827")
    section_font = Font(name="Calibri", size=11, bold=True, color="1F2937")
    body_font = Font(name="Calibri", size=10, color="374151")
    code_font = Font(name="Consolas", size=10, color="111827")
    table_header_fill = PatternFill(start_color="E5E7EB", end_color="E5E7EB", fill_type="solid")

    ws_inst.cell(
        row=1, column=1, value="FolioPilot - Excel Transaction Import Guide"
    ).font = title_font
    ws_inst.cell(
        row=2,
        column=1,
        value=(
            "Fill in your mutual fund transactions on the 'Transactions' sheet. "
            "Upload this file to preview and import."
        ),
    ).font = body_font

    # Column Specifications Table
    headers = ["Column", "Required?", "Accepted Formats & Description", "Example"]
    for col_idx, h_text in enumerate(headers, start=1):
        cell = ws_inst.cell(row=4, column=col_idx, value=h_text)
        cell.font = section_font
        cell.fill = table_header_fill

    rows_info = [
        (
            "txn_date",
            "Required",
            (
                "Real Excel date cell or text in YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY. "
                "Must be between 1990-01-01 and today (Asia/Kolkata)."
            ),
            "2025-01-15",
        ),
        (
            "scheme_code",
            "Required*",
            (
                "AMFI numeric code (digits only, e.g. 122639, '122639', 122639.0). "
                "*At least one of scheme_code or isin is required."
            ),
            "122639",
        ),
        (
            "isin",
            "Required*",
            (
                "12-character Indian ISIN matching regex ^IN[A-Z0-9]{10}$. "
                "*At least one of scheme_code or isin is required."
            ),
            "INF879O01018",
        ),
        (
            "txn_type",
            "Required",
            (
                "Case-insensitive: buy, sell, dividend_reinvest. Aliases: purchase -> buy; "
                "redemption, redeem -> sell; dividend reinvestment -> dividend_reinvest."
            ),
            "buy",
        ),
        (
            "units",
            "Required**",
            (
                "Positive number, up to 4 decimal places. "
                "**At least two of units, nav, amount are required per row."
            ),
            "100.5420",
        ),
        (
            "nav",
            "Required**",
            (
                "Positive number, up to 8 decimal places. "
                "**At least two of units, nav, amount are required per row."
            ),
            "52.3450",
        ),
        (
            "amount",
            "Required**",
            (
                "Positive number, up to 2 decimal places. "
                "**At least two of units, nav, amount are required per row."
            ),
            "5262.88",
        ),
        (
            "notes",
            "Optional",
            (
                "Plain text notes, up to 200 characters. "
                "Control characters are stripped. Never truncated."
            ),
            "Monthly lumpsum top-up",
        ),
        (
            "fund_name",
            "Optional",
            (
                "Fund name for your reference. Not used for matching; "
                "echoed in preview to verify resolved fund."
            ),
            "Parag Parikh Flexi Cap Fund",
        ),
    ]

    for row_offset, row_data in enumerate(rows_info, start=5):
        for col_idx, val in enumerate(row_data, start=1):
            cell = ws_inst.cell(row=row_offset, column=col_idx, value=val)
            cell.font = code_font if col_idx in (1, 4) else body_font
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    # Rules & Constraints section
    rule_start = 16
    ws_inst.cell(row=rule_start, column=1, value="Rules & Constraints").font = section_font
    rules = [
        (
            "1. Math resolution: At least two of units, nav, amount must be given. "
            "The missing third value is derived automatically "
            "(tolerance: absolute 1.00 INR or 0.2%)."
        ),
        (
            "2. Strict decimals: units <= 4 decimals, amount <= 2 decimals, nav <= 8 decimals. "
            "Numbers with excess decimals are rejected without silent rounding."
        ),
        (
            "3. Duplicate multiset rule: Rows matching (fund, date, type, units, amount) that "
            "already exist in your portfolio ledger are marked 'duplicate' and skipped."
        ),
        (
            "4. All-or-nothing commit: If any row has errors, commit is blocked unless you tick "
            "'Skip invalid rows'. A committed import can be undone from the import history."
        ),
        (
            "5. File limits: Max file size 2 MB (.xlsx only), max 5,000 data rows. "
            "Macros, external links, and encrypted files are rejected."
        ),
    ]
    for idx, rule in enumerate(rules, start=rule_start + 1):
        cell = ws_inst.cell(row=idx, column=1, value=rule)
        cell.font = body_font

    ws_inst.column_dimensions["A"].width = 16
    ws_inst.column_dimensions["B"].width = 14
    ws_inst.column_dimensions["C"].width = 50
    ws_inst.column_dimensions["D"].width = 25

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
