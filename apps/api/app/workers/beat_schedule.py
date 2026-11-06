"""Celery Beat schedule configuration for periodic background jobs.

Periodic tasks (e.g., daily AMFI NAV sync, weekly portfolio rebalance checks)
will be registered here in later phases.

Example future schedule:
    from celery.schedules import crontab
    CELERY_BEAT_SCHEDULE = {
        "sync-amfi-nav-daily": {
            "task": "sync_amfi_nav",
            "schedule": crontab(hour=18, minute=0), # 23:30 IST in UTC
        },
    }
"""

CELERY_BEAT_SCHEDULE: dict[str, dict[str, object]] = {}
