"""Unit tests for mfapi.in historical NAV payload parser."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.services.mfapi_parser import parse_mfapi_history


def test_parse_mfapi_fixture() -> None:
    fixture_path = Path(__file__).parent.parent / "fixtures" / "mfapi_122639_sample.json"
    with open(fixture_path, encoding="utf-8") as f:
        payload = json.load(f)

    result = parse_mfapi_history(payload)

    assert result.total_points == 30
    assert result.skipped_points == 0
    assert len(result.points) == 30

    # First point
    first_pt = result.points[0]
    assert first_pt.nav_date == date(2026, 11, 5)
    assert first_pt.nav == Decimal("92.70550")

    # Last point
    last_pt = result.points[-1]
    assert last_pt.nav_date == date(2026, 9, 23)
    assert last_pt.nav == Decimal("90.34030")


def test_parse_mfapi_bad_points_skipped() -> None:
    payload = {
        "status": "SUCCESS",
        "data": [
            {"date": "06-11-2026", "nav": "89.0416"},  # valid
            {"date": "invalid-date", "nav": "89.00"},  # bad date
            {"date": "05-11-2026", "nav": "not-a-number"},  # bad nav
            {"date": None, "nav": "88.00"},  # missing date
            "not a dict",  # bad row
            {"date": "04-11-2026", "nav": "88.1234"},  # valid
        ],
    }
    result = parse_mfapi_history(payload)

    assert result.total_points == 6
    assert result.skipped_points == 4
    assert len(result.points) == 2
    assert result.points[0].nav_date == date(2026, 11, 6)
    assert result.points[1].nav_date == date(2026, 11, 4)
