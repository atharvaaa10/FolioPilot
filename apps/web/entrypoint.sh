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
    echo "[entrypoint] Dependency drift or missing package detected. Repairing node_modules..."
    # 1. Clear contents of /app/node_modules without unlinking the mount point
    find /app/node_modules -mindepth 1 -delete 2>/dev/null || rm -rf /app/node_modules/* /app/node_modules/.[!.]* 2>/dev/null || true

    # 2. Install exactly what package-lock.json specifies and verify it remains untouched
    PRE_HASH=$(sha256sum "$LOCK_FILE" | cut -d' ' -f1)
    npm ci --prefer-offline --no-audit --no-fund || {
      echo "[entrypoint ERROR] npm ci failed during repair!" >&2
      exit 1
    }
    POST_HASH=$(sha256sum "$LOCK_FILE" | cut -d' ' -f1)
    if [ "$PRE_HASH" != "$POST_HASH" ]; then
      echo "[entrypoint ERROR] package-lock.json was modified during repair!" >&2
      exit 1
    fi

    # 3. Verify depth-0 installed packages against lockfile
    npm ls --depth=0 next react react-hook-form zod @tanstack/react-query || {
      echo "[entrypoint ERROR] Installed package verification failed!" >&2
      exit 1
    }

    echo "$CURRENT_HASH" > "$HASH_FILE"
    echo "[entrypoint] Web dependencies repaired and verified successfully."
  fi
fi

exec "$@"
