from app.workers.celery_app import celery_app


@celery_app.task(name="ping")  # type: ignore[untyped-decorator]
def ping() -> str:
    """Trivial ping task to verify Celery worker connectivity."""
    return "pong"
