#!/bin/sh
set -e

LOCK_FILE="/app/uv.lock"
HASH_FILE="/app/.venv/.lock-hash"

if [ -f "$LOCK_FILE" ]; then
  CURRENT_HASH=$(sha256sum "$LOCK_FILE" | cut -d' ' -f1)
  INSTALLED_HASH=""
  if [ -f "$HASH_FILE" ]; then
    INSTALLED_HASH=$(cat "$HASH_FILE" 2>/dev/null || true)
  fi

  if [ "$CURRENT_HASH" != "$INSTALLED_HASH" ]; then
    echo "[entrypoint] Dependency drift detected in .venv. Running uv sync --frozen..."
    uv sync --frozen
    echo "$CURRENT_HASH" > "$HASH_FILE"
    echo "[entrypoint] Python dependencies synced successfully."
  fi
fi

exec "$@"

