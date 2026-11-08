"""Application constants for FolioPilot."""

from datetime import date
from decimal import Decimal

# Auth
PASSWORD_MIN_LENGTH: int = 8
PASSWORD_MAX_LENGTH: int = 128

# Portfolios & Ledger (Phase 3A)
MAX_PORTFOLIOS_PER_USER: int = 20
MAX_TRANSACTIONS_PER_PORTFOLIO: int = 10000
MAX_TARGET_ROWS: int = 5
AMOUNT_TOLERANCE_ABSOLUTE: Decimal = Decimal("1.00")
AMOUNT_TOLERANCE_RELATIVE: Decimal = Decimal("0.002")
LEDGER_DATE_FLOOR: date = date(1990, 1, 1)
