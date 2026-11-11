"""Unit tests for the official Excel import template."""

import datetime as dt
import io

import openpyxl
import pytest

from app.core.errors import ImportEmptyError
from app.services.import_file import inspect_and_read_workbook
from app.services.import_template import TEMPLATE_HEADERS, build_template


def test_build_template_structure() -> None:
    content = build_template()
    assert isinstance(content, bytes)
    assert len(content) > 0

    wb = openpyxl.load_workbook(io.BytesIO(content))
    assert wb.properties.creator == "FolioPilot"
    assert "Transactions" in wb.sheetnames
    assert "Instructions" in wb.sheetnames

    ws_txns = wb["Transactions"]
    assert ws_txns.max_row == 1

    headers = [ws_txns.cell(row=1, column=c).value for c in range(1, len(TEMPLATE_HEADERS) + 1)]
    assert headers == TEMPLATE_HEADERS

    # Verify data validation objects are attached to sheet
    assert len(ws_txns.data_validations.dataValidation) >= 3

    ws_inst = wb["Instructions"]
    assert ws_inst.max_row > 10


def test_empty_template_raises_import_empty() -> None:
    content = build_template()
    with pytest.raises(ImportEmptyError):
        inspect_and_read_workbook(content, "template.xlsx")


def test_template_roundtrip_with_row() -> None:
    content = build_template()
    wb = openpyxl.load_workbook(io.BytesIO(content))
    ws_txns = wb["Transactions"]
    # Append valid row: txn_date, scheme_code, isin, txn_type, units, nav, amount, notes, fund_name
    ws_txns.append(
        [
            dt.date(2025, 1, 15),
            122639,
            "INF879O01018",
            "buy",
            100.0,
            50.0,
            5000.0,
            "Test notes",
            "Parag Parikh Flexi Cap Fund",
        ]
    )
    buf = io.BytesIO()
    wb.save(buf)

    parsed = inspect_and_read_workbook(buf.getvalue(), "template.xlsx")
    assert len(parsed.raw_rows) == 1
    row = parsed.raw_rows[0]
    assert row.row_number == 2
    assert row.cells["txn_type"] == "buy"
    assert row.cells["scheme_code"] == 122639
    assert row.cells["isin"] == "INF879O01018"
