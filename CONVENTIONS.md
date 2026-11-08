# FolioPilot Engineering Conventions

Contract for all build phases. Adherence is mandatory.

## 1. Architecture & Folder Responsibilities
- `apps/api/app/core/`: Application infrastructure (config, logging, error hierarchy, DB engine, Redis client).
- `apps/api/app/api/`: Thin HTTP layer. Serializes/deserializes requests, delegates to services, returns envelopes.
- `apps/api/app/models/`: SQLAlchemy 2.0 models inheriting from `Base`. No business logic.
- `apps/api/app/schemas/`: Pydantic models for request/response validation and serialization.
- `apps/api/app/repositories/`: Thin wrappers over SQLAlchemy queries, returning domain models or scalars, never constructing HTTP responses.
- `apps/api/app/services/`: Pure business logic functions taking data in and returning data out. No HTTP objects (no Request/Response), no direct DB sessions inside pure calculation functions. DB access belongs in thin query/repository helpers so services can be shared across HTTP endpoints, Celery workers, and AI tools.
- `apps/api/app/workers/`: Celery application, task definitions, and periodic beat schedules.
- `apps/api/app/ai/`: LLM tool definitions, agents, and RAG pipelines (reserved for later phases).
- `apps/web/src/`: Next.js App Router frontend with typed API client and TanStack Query data fetching.

## 2. Naming & Case Conventions
- **JSON**: All JSON keys across API requests and responses use `snake_case`.
- **Database**: Table names, column names, constraints, and indexes use `snake_case`.
- **Python**: Variables and functions use `snake_case`; classes use `PascalCase`; constants use `SCREAMING_SNAKE_CASE`.
- **TypeScript**: Variables and functions use `camelCase`; types and components use `PascalCase`.

## 3. Standard Response Envelope
All API responses must strictly follow the standard envelope:
- **Success**:
  ```json
  { "success": true, "data": <payload> }
  ```
- **Failure**:
  ```json
  {
    "success": false,
    "error": {
      "code": "STRING_CODE",
      "message": "Human-readable description",
      "details": null
    }
  }
  ```

## 4. Error Hierarchy & Codes
- `NotFoundError`:
  - `NOT_FOUND` (HTTP 404)
  - `FUND_NOT_FOUND` (HTTP 404) - Mutual fund scheme code does not exist or is inactive
- `ValidationError` -> `VALIDATION_ERROR` (HTTP 422)
- `UnauthorizedError`:
  - `UNAUTHORIZED` (HTTP 401)
  - `INVALID_CREDENTIALS` (HTTP 401) - Bad email or password
  - `TOKEN_EXPIRED` (HTTP 401) - Expired JWT or refresh token
  - `INVALID_TOKEN` (HTTP 401) - Malformed, forged, or unknown token
  - `REFRESH_TOKEN_REUSED` (HTTP 401) - Token family reuse / theft breach
- `ForbiddenError` -> `FORBIDDEN` (HTTP 403)
- `ConflictError`:
  - `CONFLICT` (HTTP 409)
  - `EMAIL_TAKEN` (HTTP 409) - Email already registered
- `RateLimitedError` -> `RATE_LIMITED` (HTTP 429) - Exceeded fixed window rate limit; sends `Retry-After` header.
- Internal unexpected failures -> `INTERNAL_SERVER_ERROR` (HTTP 500). Stack traces must never leak to clients in production.

## 5. Authentication & Security Architecture
- **Passwords**: Hashed with Argon2id. Checked with dummy constant-time verification when email is not found to prevent timing side-channel attacks. Minimum length 8, maximum length 128 characters.
- **Access Tokens**: Short-lived (15 min) JWT signed with HMAC-SHA256. Kept exclusively in-memory on the frontend, never stored in `localStorage` or `sessionStorage` (XSS mitigation).
- **Refresh Tokens**: Long-lived (7 days) cryptographically random urlsafe strings stored only as SHA-256 hashes in the database. Delivered exclusively through HttpOnly, SameSite=Lax cookie `fp_refresh` with `Path=/api/v1/auth`.
- **Token Family Rotation**: Every refresh rotates the token under pessimistic database row lock (`with_for_update()`).
  - Active unused token: Rotates cleanly, issues new access token, sets new cookie, links successor.
  - Token used within grace window (10s): Concurrent multi-tab request. Issues access token only, without setting new cookie.
  - Token reused past grace window: Token theft breach detected. Revokes entire family immediately, clears cookie, logs security event, returns 401 `REFRESH_TOKEN_REUSED`.
- **CSRF & CORS**: Cookie-authenticated endpoints (`/auth/refresh`, `/auth/logout`) strictly enforce `Origin` header validation against `CORS_ORIGINS`. `CORS_ORIGINS` must never contain `*` when credentials are enabled.
- **Sensitive Key Redaction**: Structlog processor automatically redacts values for keys: `password`, `token`, `access_token`, `refresh_token`, `authorization`, `cookie`, `set-cookie`, `secret`.

## 6. Financial & Numerical Precision Rules
- **Money**: Always store in PostgreSQL as `NUMERIC(15, 2)`. Always represent in Python as `decimal.Decimal`. **Never use `float`** for currency.
- **Mutual Fund Units**: Store as `NUMERIC(18, 4)`. Represent in Python as `Decimal`.
- **Net Asset Value (NAV)**: Store in PostgreSQL as `NUMERIC(20, 8)`. Represent in Python as `Decimal`. (Precision of 8 decimals avoids silent rounding on AMFI schemes such as liquid or overnight funds quoting up to 5-8 decimal places).
- **Tracked Funds Storage**: Daily NAV master records latest NAV for all active schemes; full historical daily NAV timeseries (`nav_history`) is stored strictly for tracked funds (`funds.is_tracked = True`).

## 7. Timestamps, Dates & Timezones
- All audit timestamps in the database must use `TIMESTAMP WITH TIME ZONE` (`DateTime(timezone=True)`).
- All audit timestamps must be stored and manipulated in **UTC**.
- NAV dates are discrete calendar dates (`DATE` in PostgreSQL, `datetime.date` in Python), representing the trading/NAV cutoff date without arbitrary time components.
- Celery worker/beat runs on `UTC`. When presenting dates or computing IST cutoffs (AMFI NAV publishes after 21:00 IST / 15:30 UTC), use explicit conversion to `Asia/Kolkata`.

## 8. Database Migrations
- Managed solely via Alembic with asyncpg.
- Autogenerated migrations must be inspected for accuracy before committing.
- **Migrations are immutable**: Never edit a migration once merged to main. Always create a new forward migration.

## 9. Testing & Quality Gate
- **Test Database & Redis Safety Gate**:
  - Tests must never use the development database.
  - Dedicated `TEST_DATABASE_URL` (defaulting to `foliopilot_test`) and `TEST_REDIS_URL` (redis db index 1).
  - Test runner MUST refuse to execute if the test database name does not end in `_test`, and must only flush Redis database index 1.
- Every phase must end with all quality checks passing:
  - Backend: `ruff check`, `ruff format --check`, `mypy --strict`, `pytest`
  - Frontend: `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`

## 10. Frontend SSR & Hydration Safety
- **Deterministic SSR Markup**: Server and initial client render must match identically. Never invoke `new Date()`, `Date.now()`, `Math.random()`, or read `window`/`localStorage` during render.
- **Client Timestamps**: For live or user-local timestamps, use `<LocalTime timestamp={...} />` (renders placeholder on server/initial mount, formats on client via `useSyncExternalStore`).
- **Locale & Currency**: Format dates and currency with explicit locale (`en-IN`) and timezone (`Asia/Kolkata`), or format strictly client-side to prevent UTC/IST server-client mismatches.

## 11. Fund Master & NAV Ingestion Architecture
- **Classification Philosophy**:
  - Deterministic table-driven mapping for all 104+ known AMFI scheme categories into standard `asset_class` (`equity`, `debt`, `hybrid`, `commodity`, `solution_oriented`, `other`) and `sub_category`.
  - Name-based heuristics for specialized asset sub-classes (Gold/Silver ETFs and funds, Index funds, Arbitrage, International funds).
  - Robust fallback to `asset_class="other"`, `sub_category="unknown"` to ensure ingestion never crashes on novel or unrecognized AMFI categories.
- **Distributed Ingestion Lock**:
  - Celery sync tasks (`sync_amfi_nav`) acquire a distributed Redis lock (`lock:sync_amfi_nav`) with a Lua owner check before running.
  - If a sync is already running, concurrent triggers gracefully yield and record a `SKIPPED` status in `nav_sync_runs`.
- **Sanity Guard Thresholds**:
  - Daily AMFI sync aborts without mutating records if parsed fund count < 5,000 or drops below 70% of previously active funds, or if content validation fails (e.g. AMFI returns an HTML error page).
- **Historical Backfill**:
  - Backfilling historical NAV uses `mfapi.in` with a 1-second polite rate limit, idempotently upserting into `nav_history`.



