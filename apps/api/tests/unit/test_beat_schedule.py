"""Unit tests for Celery Beat schedule configuration."""

from celery.schedules import crontab

from app.workers.beat_schedule import (
    CELERY_BEAT_SCHEDULE,
    PURGE_TOKENS_HOUR_UTC,
    PURGE_TOKENS_MINUTE_UTC,
    SYNC_EVENING_HOUR_UTC,
    SYNC_EVENING_MINUTE_UTC,
    SYNC_MORNING_HOUR_UTC,
    SYNC_MORNING_MINUTE_UTC,
)


def test_beat_schedule_named_constants() -> None:
    # 21:30 Asia/Kolkata (IST) = 16:00 UTC
    assert SYNC_EVENING_HOUR_UTC == 16
    assert SYNC_EVENING_MINUTE_UTC == 0

    # 06:00 Asia/Kolkata (IST) = 00:30 UTC
    assert SYNC_MORNING_HOUR_UTC == 0
    assert SYNC_MORNING_MINUTE_UTC == 30

    # 03:30 Asia/Kolkata (IST) = 22:00 UTC
    assert PURGE_TOKENS_HOUR_UTC == 22
    assert PURGE_TOKENS_MINUTE_UTC == 0


def test_beat_schedule_entries() -> None:
    assert "sync-amfi-nav-evening" in CELERY_BEAT_SCHEDULE
    evening_entry = CELERY_BEAT_SCHEDULE["sync-amfi-nav-evening"]
    assert evening_entry["task"] == "sync_amfi_nav"
    evening_sched = evening_entry["schedule"]
    assert isinstance(evening_sched, crontab)
    assert 16 in evening_sched.hour
    assert 0 in evening_sched.minute

    assert "sync-amfi-nav-morning" in CELERY_BEAT_SCHEDULE
    morning_entry = CELERY_BEAT_SCHEDULE["sync-amfi-nav-morning"]
    assert morning_entry["task"] == "sync_amfi_nav"
    morning_sched = morning_entry["schedule"]
    assert isinstance(morning_sched, crontab)
    assert 0 in morning_sched.hour
    assert 30 in morning_sched.minute
