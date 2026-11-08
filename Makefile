.PHONY: up down logs migrate makemigration test test-api test-web lint format typecheck shell-api psql rebuild-web rebuild-python smoke sync-nav backfill-nav reclassify

# Default docker compose command
DC = docker compose

up:
	$(DC) up -d

down:
	$(DC) down

sync-nav:
	$(DC) exec api python -m app.cli sync-nav

backfill-nav:
	$(DC) exec api python -m app.cli backfill-nav $(CODE)

reclassify:
	$(DC) exec api python -m app.cli reclassify

rebuild-web:
	$(DC) up -d --build --no-deps -V web

rebuild-python:
	$(DC) up -d --build --no-deps -V api worker beat

smoke:
	powershell -ExecutionPolicy Bypass -File scripts/smoke.ps1

logs:
	$(DC) logs -f

migrate:
	$(DC) exec api alembic upgrade head

makemigration:
	$(DC) exec api alembic revision --autogenerate -m "$(m)"

test: test-api test-web

test-api:
	cd apps/api && pytest

test-web:
	cd apps/web && npm test

lint:
	cd apps/api && ruff check .
	cd apps/web && npm run lint

format:
	cd apps/api && ruff format .
	cd apps/web && npm run format

typecheck:
	cd apps/api && mypy app tests
	cd apps/web && npm run typecheck

shell-api:
	$(DC) exec api /bin/bash

psql:
	$(DC) exec db psql -U foliopilot -d foliopilot

