"""Celery application configuration for FolioPilot asynchronous tasks.

Timezone Policy:
----------------
Celery worker and beat instances run with timezone="UTC" (enable_utc=True).
All schedule triggers and stored timestamps use UTC.
When adding periodic schedules for Indian market operations (such as daily AMFI NAV
fetches published at ~23:00 IST or transaction cutoff rules at 15:00 IST), configure
cron expressions corresponding to 'Asia/Kolkata' or convert to their equivalent UTC offsets.
"""

from celery import Celery

from app.core.config import get_settings
from app.workers.beat_schedule import CELERY_BEAT_SCHEDULE

settings = get_settings()

celery_app = Celery(
    "foliopilot",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    worker_prefetch_multiplier=1,
    beat_schedule=CELERY_BEAT_SCHEDULE,
)

# Auto-discover tasks within workers package
celery_app.autodiscover_tasks(["app.workers"])

# Alias for standard Celery discovery (-A app.workers.celery_app)
app = celery_app
