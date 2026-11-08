"""Pure parser for mfapi.in historical NAV payload."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True)
class MfapiPoint:
    """Historical NAV point."""

    nav_date: date
    nav: Decimal


@dataclass
class MfapiParseResult:
    """Result of parsing historical NAV payload from mfapi.in."""

    points: list[MfapiPoint]
    total_points: int
    skipped_points: int


def parse_mfapi_history(payload: dict[str, Any]) -> MfapiParseResult:
    """Parse mfapi.in response JSON into structured historical NAV points.

    Dates are in DD-MM-YYYY format.
    Invalid dates or non-decimal NAV points are skipped and counted.
    """
    raw_data = payload.get("data")
    if not isinstance(raw_data, list):
        return MfapiParseResult(points=[], total_points=0, skipped_points=0)

    points: list[MfapiPoint] = []
    skipped_points = 0
    total_points = len(raw_data)

    for item in raw_data:
        if not isinstance(item, dict):
            skipped_points += 1
            continue

        raw_date = item.get("date")
        raw_nav = item.get("nav")

        if not raw_date or not raw_nav:
            skipped_points += 1
            continue

        try:
            nav_date = datetime.strptime(str(raw_date).strip(), "%d-%m-%Y").date()
            nav = Decimal(str(raw_nav).strip())
            points.append(MfapiPoint(nav_date=nav_date, nav=nav))
        except (ValueError, InvalidOperation, TypeError):
            skipped_points += 1

    return MfapiParseResult(
        points=points,
        total_points=total_points,
        skipped_points=skipped_points,
    )
