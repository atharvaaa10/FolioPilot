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
- **Classification & Taxonomy**:
  - Deterministic table-driven mapping for all known AMFI scheme categories into standard `asset_class` (`equity`, `debt`, `hybrid`, `gold`, `other`) and canonical `sub_category` tuples. See [docs/classification.md](docs/classification.md) for full taxonomy specification and distribution metrics.
  - Multi-tier name heuristics for ambiguous categories (`Index Funds`, `Other ETFs`, `FoF Overseas`) with strict precedence (Debt -> Gold/Silver -> International -> Equity index). AMFI category classifications are never overridden by name rules.
  - Robust fallback to `asset_class="other"`, `sub_category="unknown"` for unrecognized schemes.
- **Sync Write Efficiency & Write-Through**:
  - `upsert_funds_batch` uses PostgreSQL `ON CONFLICT DO UPDATE ... WHERE` evaluating `is_distinct_from` across payload columns and NAV values, eliminating whole-table rewrites when data is unchanged.
  - `last_seen_at` is updated without row-churn via throttled touches (>=12h interval).
  - Tracked fund daily NAVs write through directly to `nav_history`, ensuring historical timeseries never lags latest AMFI points.
- **Distributed Ingestion Lock**:
  - Celery sync tasks (`sync_amfi_nav`) acquire a distributed Redis lock (`lock:sync_amfi_nav`) with a Lua owner check before running.
  - If a sync is already running, concurrent triggers gracefully yield and record a `SKIPPED` status in `nav_sync_runs`.
- **Sanity Guard Thresholds**:
  - Daily AMFI sync aborts without mutating records if parsed fund count < 5,000 or drops below 70% of previously active funds, or if content validation fails (e.g. AMFI returns an HTML error page).
- **Historical Backfill**:
  - Backfilling historical NAV uses `mfapi.in` with a 1-second polite rate limit, idempotently upserting into `nav_history`.

## 12. Portfolio Ledger & Derived Positions Architecture
- **Ledger as Source of Truth**:
  - The `transactions` table is the immutable, append-only source of truth.
  - Positions, cost basis, invested capital, current valuation, and realized/unrealized gains are **never** stored as mutable columns in separate tables; all are derived deterministically on read by in-memory chronological replay. Full architectural details in [docs/ledger.md](docs/ledger.md).
- **Deterministic Ordering Key**:
  - Transactions for a scheme are ordered by `(txn_date ASC, type_rank ASC, created_at ASC, id ASC)`.
  - Intraday precedence: `BUY` (`type_rank=0`) evaluates before `SELL` (`type_rank=1`) on the same date, avoiding false oversell rejections on intraday trades.
- **Strict Positive Sign Convention**:
  - `units > 0`, `nav > 0`, and `amount > 0` are mandatory on both `BUY` and `SELL` transactions. Redemptions are denoted solely by `txn_type = "SELL"`, never negative numbers.
- **Decimals as Strings**:
  - Scales: `units` numeric(18, 4), `nav` numeric(18, 8), `amount` numeric(18, 2), `target_pct` numeric(5, 2).
  - All decimal amounts in API payloads are serialized as strings. The frontend parses them using `decimal.js` for exact arithmetic ($33.33 + 33.33 + 33.34 = 100.00$).
- **Ownership 404 Rule**:
  - Looking up, updating, or deleting another user's portfolio or transaction returns `HTTP 404 NOT_FOUND` (`PORTFOLIO_NOT_FOUND` / `TRANSACTION_NOT_FOUND`), never `HTTP 403`, eliminating resource enumeration.
- **Portfolio-Row Lock for Ledger Mutations**:
  - Transaction mutations begin a transaction and acquire a row-level lock on the parent portfolio (`SELECT id FROM portfolios WHERE id = ... FOR UPDATE`), ensuring serialized ledger validation and preventing concurrent oversell races.
- **Average Cost Method (FIFO in Future Phase)**:
  - Positions are derived using Weighted Average Cost Basis (`units`, `avg_cost_nav`, `total_invested`, `realized_gain`). FIFO tax lot matching is reserved for a future phase.
- **New Error Codes**:
  - `PORTFOLIO_NOT_FOUND` (HTTP 404): Portfolio does not exist or belongs to another user (Ownership 404 rule).
  - `PORTFOLIO_NAME_TAKEN` (HTTP 409): Duplicate portfolio name for user.
  - `PORTFOLIO_LIMIT_REACHED` (HTTP 409): User portfolio count exceeds `MAX_PORTFOLIOS_PER_USER` (20).
  - `TARGETS_INVALID` (HTTP 422): Target allocations exceed 5 rows, duplicate classes, or sum != 100.00% (details: `{"sum": str}`).
  - `TRANSACTION_NOT_FOUND` (HTTP 404): Transaction does not exist or belongs to another user's portfolio.
  - `FUND_NOT_FOUND` (HTTP 404): Mutual fund scheme code does not exist or is inactive.
  - `INSUFFICIENT_UNITS` (HTTP 409): Selling more units than available at transaction date (details: `{"available_units": str, "date": str}`).
  - `LEDGER_INCONSISTENT` (HTTP 409): Ledger mutation violates historical consistency or constraints (details: `{"fund": str, "date": str}`).
  - `AMOUNT_MISMATCH` (HTTP 422): Provided amount differs from units * NAV beyond allowable tolerance (details: `{"expected": str, "given": str}`).
  - `TRANSACTION_LIMIT_REACHED` (HTTP 409): Transactions in portfolio exceed `MAX_TRANSACTIONS_PER_PORTFOLIO` (10,000).

## 13. Contract Validation, Testing & Real-Browser E2E
- **Zod Runtime Validation at API Boundary**:
  - All responses consumed from backend endpoints are validated through Zod schemas (`apps/web/src/lib/schemas/contract.ts`).
  - Mismatches throw typed `ApiContractError` (`CONTRACT_MISMATCH`) identifying the failing field path.
- **Contract Fixtures Rule**:
  - Frontend page and integration tests must strictly use committed backend contract fixtures (`apps/web/src/test/fixtures/contract/*.json`) generated via `make contract`.
  - Hand-written API mock shapes for backend-owned data structures are strictly forbidden.
- **Real-Browser E2E Gate**:
  - Playwright browser tests (`apps/web/e2e/portfolio-e2e.spec.ts`) run against the live local stack via `make e2e` (`npm run e2e`).
  - Browser binaries must strictly reside on `D:\caches\playwright` (`PLAYWRIGHT_BROWSERS_PATH=D:\caches\playwright`).
  - Every UI and ledger mutation change must pass the E2E verification before commit.

## 14. Systematic Investment Plans (SIPs) & Managed Transactions Architecture
- **Rule, Installment, and Transaction Separation**:
  - SIPs define recurring investment rules, generate `sip_installments`, and execute ordinary `buy` transactions in the Phase 3A ledger. Full architectural spec in [docs/sips.md](docs/sips.md).
- **Managed Transaction Invariant**:
  - Ledger transactions created by SIP installments have `sip_installment_id` set (FK with `ON DELETE SET NULL`, unique index).
  - Managed transactions cannot be edited or deleted directly via transaction endpoints; direct attempts return `HTTP 409 Conflict` (`TRANSACTION_MANAGED_BY_SIP`).
  - Removal is executed exclusively through `POST /sips/{sip_id}/installments/{inst_id}/skip`.
- **Skip Semantics & Ledger Protection**:
  - Skipping an executed installment deletes its linked ledger transaction under the portfolio row lock. If subsequent redemptions rely on those units, skip is aborted with `HTTP 409 Conflict` (`LEDGER_INCONSISTENT`).
- **Schedule, Step-Up & Pause Mathematics**:
  - Frequency is monthly on `day_of_month` (1..28, eliminating month-end and leap-year edge cases).
  - Annual step-up increases amount by $s\%$ ($A_k = \text{round}(A_0 \cdot (1 + s/100)^k, 2)$ where $k = \lfloor (m-1)/12 \rfloor$).
  - Pausing skips installment generation during the pause window without shifting anniversary months ($k$ counts from initial schedule origin).
- **Execution & NAV Selection**:
  - Scheduled Celery beat runs at 22:15 IST (16:45 UTC) and 06:30 IST (01:00 UTC).
  - Installments execute lazily up to current date.
  - NAV selection picks `due_date` NAV or most recent prior trading day NAV; forward-looking NAV is never used.
  - Installment execution takes portfolio and installment row locks in isolated transactions, preventing concurrent double-execution.
- **SIP Error Codes**:
  - `SIP_NOT_FOUND` (HTTP 404): SIP does not exist or belongs to another user.
  - `INSTALLMENT_NOT_FOUND` (HTTP 404): Installment does not exist or does not belong to the SIP.
  - `FUND_INACTIVE` (HTTP 409): Target mutual fund is inactive.
  - `SIP_LIMIT_REACHED` (HTTP 409): Portfolio has reached limit of 50 active/scheduled SIPs.
  - `SIP_ALREADY_PAUSED` (HTTP 409): Attempting to pause a SIP with an existing open pause.
  - `SIP_NOT_PAUSED` (HTTP 409): Attempting to resume a SIP that is not paused.
  - `SIP_ALREADY_ENDED` (HTTP 409): Attempting to mutate an ended SIP.
  - `SIP_INVALID_SCHEDULE` (HTTP 422): Schedule produces no valid execution dates.
  - `INSTALLMENT_NOT_SKIPPABLE` (HTTP 409): Installment has already been skipped.
  - `TRANSACTION_MANAGED_BY_SIP` (HTTP 409): Direct mutation attempted on managed transaction.

