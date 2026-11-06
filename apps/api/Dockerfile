# Multi-stage Dockerfile for FolioPilot API service using uv

# Base image with Python 3.12 and uv pre-installed
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# --- Development stage ---
FROM base AS development

# Copy dependency specifications
COPY pyproject.toml uv.lock /app/

# Install all dependencies including dev tools
RUN uv sync --no-install-project

# Copy project files
COPY . /app

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# --- Production Builder stage ---
FROM base AS builder

COPY pyproject.toml uv.lock /app/

# Install only production dependencies
RUN uv sync --no-dev --no-install-project

# Copy project files
COPY . /app

# --- Production Final stage ---
FROM python:3.12-slim-bookworm AS production

WORKDIR /app

# Create a non-root system user and group
RUN groupadd -g 10001 foliopilot && \
    useradd -u 10001 -g foliopilot -s /bin/bash -m foliopilot

# Copy the virtual environment from builder
COPY --from=builder --chown=foliopilot:foliopilot /app/.venv /app/.venv
COPY --from=builder --chown=foliopilot:foliopilot /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER foliopilot

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

