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

CELERY_BEAT_SCHEDULE: dict[str, dict[str, object]] = {
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
}
