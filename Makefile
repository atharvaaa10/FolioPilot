.PHONY: up down logs migrate makemigration test test-api test-web lint format typecheck shell-api psql

# Default docker compose command
DC = docker compose

up:
	$(DC) up -d

down:
	$(DC) down

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
	cd apps/api && mypy app
	cd apps/web && npm run typecheck

shell-api:
	$(DC) exec api /bin/bash

psql:
	$(DC) exec db psql -U foliopilot -d foliopilot

