"""Celery Beat schedule configuration for periodic background jobs."""

from celery.schedules import crontab

# AMFI NAV Sync periodic schedule times (converted from IST to UTC):
# Primary evening run: 21:30 Asia/Kolkata (IST) -> 16:00 UTC
SYNC_EVENING_HOUR_UTC = 16
SYNC_EVENING_MINUTE_UTC = 0

# Morning catch-up run: 06:00 Asia/Kolkata (IST) -> 00:30 UTC
SYNC_MORNING_HOUR_UTC = 0
SYNC_MORNING_MINUTE_UTC = 30

# Daily token purge run: 03:30 Asia/Kolkata (IST) -> 22:00 UTC
PURGE_TOKENS_HOUR_UTC = 22
PURGE_TOKENS_MINUTE_UTC = 0

# SIP automatic installment execution schedule times:
# Evening run (after AMFI NAV sync): 22:15 Asia/Kolkata (IST) -> 16:45 UTC
SIP_EVENING_HOUR_IST = 22
SIP_EVENING_MINUTE_IST = 15
SIP_EVENING_HOUR_UTC = 16
SIP_EVENING_MINUTE_UTC = 45

# Morning run (after AMFI catch-up sync): 06:30 Asia/Kolkata (IST) -> 01:00 UTC
SIP_MORNING_HOUR_IST = 6
SIP_MORNING_MINUTE_IST = 30
SIP_MORNING_HOUR_UTC = 1
SIP_MORNING_MINUTE_UTC = 0

# Import preview purge schedule times:
# 04:00 Asia/Kolkata (IST) -> 22:30 UTC
IMPORT_PURGE_HOUR_IST = 4
IMPORT_PURGE_MINUTE_IST = 0
IMPORT_PURGE_HOUR_UTC = 22
IMPORT_PURGE_MINUTE_UTC = 30

CELERY_BEAT_SCHEDULE: dict[str, dict[str, object]] = {
    "purge-expired-import-previews-daily": {
        "task": "purge_expired_import_previews",
        "schedule": crontab(
            hour=IMPORT_PURGE_HOUR_UTC,
            minute=IMPORT_PURGE_MINUTE_UTC,
        ),
    },
    "purge-expired-refresh-tokens-daily": {
        "task": "purge_expired_refresh_tokens",
        "schedule": crontab(
            hour=PURGE_TOKENS_HOUR_UTC,
            minute=PURGE_TOKENS_MINUTE_UTC,
        ),
    },
    "sync-amfi-nav-evening": {
        "task": "sync_amfi_nav",
        "schedule": crontab(
            hour=SYNC_EVENING_HOUR_UTC,
            minute=SYNC_EVENING_MINUTE_UTC,
        ),
    },
    "sync-amfi-nav-morning": {
        "task": "sync_amfi_nav",
        "schedule": crontab(
            hour=SYNC_MORNING_HOUR_UTC,
            minute=SYNC_MORNING_MINUTE_UTC,
        ),
    },
    "execute-due-sip-installments-evening": {
        "task": "execute_due_sip_installments",
        "schedule": crontab(
            hour=SIP_EVENING_HOUR_UTC,
            minute=SIP_EVENING_MINUTE_UTC,
        ),
    },
    "execute-due-sip-installments-morning": {
        "task": "execute_due_sip_installments",
        "schedule": crontab(
            hour=SIP_MORNING_HOUR_UTC,
            minute=SIP_MORNING_MINUTE_UTC,
        ),
    },
}
