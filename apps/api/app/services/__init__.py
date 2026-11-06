"""Business services package for FolioPilot.

Convention:
-----------
Functions here must be pure where possible:
- Take typed input data and return computed data.
- Never accept FastAPI Request or Response objects.
- Do not accept or manage SQLAlchemy sessions directly inside pure calculation functions.
- Database retrieval belongs in separate query/repository helpers.

This design enables the same business algorithms (XIRR, capital gains tax, rebalancing)
to be invoked by FastAPI routes, Celery background workers, and future LLM tool agents.
"""
