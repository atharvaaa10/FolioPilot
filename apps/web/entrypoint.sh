#!/bin/sh
set -e

LOCK_FILE="/app/package-lock.json"
HASH_FILE="/app/node_modules/.lock-hash"

if [ -f "$LOCK_FILE" ]; then
  CURRENT_HASH=$(sha256sum "$LOCK_FILE" | cut -d' ' -f1)
  INSTALLED_HASH=""
  if [ -f "$HASH_FILE" ]; then
    INSTALLED_HASH=$(cat "$HASH_FILE" 2>/dev/null || true)
  fi

  if [ "$CURRENT_HASH" != "$INSTALLED_HASH" ] || [ ! -d "/app/node_modules/react-hook-form" ] || [ ! -d "/app/node_modules/next" ]; then
    echo "[entrypoint] Dependency drift or missing package detected. Running npm ci..."
    npm ci
    echo "$CURRENT_HASH" > "$HASH_FILE"
    echo "[entrypoint] Dependencies synced successfully."
  fi
fi

exec "$@"
