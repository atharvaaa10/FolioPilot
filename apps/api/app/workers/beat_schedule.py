"""Celery Beat schedule configuration for periodic background jobs."""

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE: dict[str, dict[str, object]] = {
    "purge-expired-refresh-tokens-daily": {
        "task": "purge_expired_refresh_tokens",
        "schedule": crontab(hour=22, minute=0),  # 03:30 Asia/Kolkata (IST) in UTC
    },
}
