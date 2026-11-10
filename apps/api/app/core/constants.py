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

# Systematic Investment Plans (SIPs - Phase 3B)
MAX_SIPS_PER_PORTFOLIO: int = 50
SIP_MIN_AMOUNT: Decimal = Decimal("100.00")
SIP_MAX_AMOUNT: Decimal = Decimal("10000000.00")
SIP_DAY_MAX: int = 28
SIP_START_MAX_FUTURE_DAYS: int = 366
MAX_PREVIEW_COUNT: int = 60
MAX_INSTALLMENTS_PER_GENERATION: int = 600

# Celery Beat SIP schedule constants (IST and corresponding UTC)
SIP_BEAT_EVENING_HOUR_IST: int = 22
SIP_BEAT_EVENING_MINUTE_IST: int = 15
SIP_BEAT_EVENING_HOUR_UTC: int = 16
SIP_BEAT_EVENING_MINUTE_UTC: int = 45

SIP_BEAT_MORNING_HOUR_IST: int = 6
SIP_BEAT_MORNING_MINUTE_IST: int = 30
SIP_BEAT_MORNING_HOUR_UTC: int = 1
SIP_BEAT_MORNING_MINUTE_UTC: int = 0
