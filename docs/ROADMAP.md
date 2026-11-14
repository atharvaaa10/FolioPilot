# FolioPilot: Project Context and Roadmap

Last updated: 2026-11-10

## 1. What we are building

FolioPilot is a personal finance web app for Indian mutual fund investors. A user records what they invest (SIPs and one-off buys and sells), and the app answers three questions:

1. What do I own, and how is it doing? (positions, valuation, XIRR)
2. Is it the right mix, and am I on track? (rebalancing, risk score, goals)
3. What should I understand or do next? (AI assistant with sourced answers, alerts)

It is the successor to SIP Tracker & Smart Rebalancer (React/Node/Prisma). It keeps every SIP Tracker feature and fixes that project's structural gaps: no real SIP entity, no transaction history, a flat 12% return assumption, and manually chosen fund categories.

## 2. Goals

- Build a real, deployable product with a trustworthy data model, not a demo.
- One project that supports two career stories by swapping resume bullets per job description:
  - SDE: API design, auth and sessions, concurrency, background jobs, testing, CI, deployment.
  - AI engineer: tool-calling over deterministic engines, RAG with citations, evaluation, cost and latency tracking.
- Every claim we make about the project must be backed by evidence we can reproduce (see "How we work").

## 3. Non-goals

- Not investment advice. The app is informational only, and the assistant says so.
- No trading, order placement or bank/broker connectivity.
- INR only. Mutual funds only (no direct equity, crypto, or insurance).
- No real user financial data in the repo, tests or demos. Use synthetic or anonymized data.
- No mobile app, no multi-tenant organizations, no advisor role.

## 4. Engineering principles

1. The transaction ledger is the single source of truth. Holdings are always derived, never stored.
2. Deterministic engines calculate; the LLM only explains. Drift, risk, XIRR and projections are pure functions that the HTTP routes, Celery tasks and the AI tool layer all call.
3. Pure services take data and return data. DB access lives in thin repository functions.
4. Money is `Decimal` in Python and `NUMERIC` in the database, never float. API money and units are JSON strings. Inputs with too many decimals are rejected, never silently rounded.
5. NAV dates and transaction dates are `DATE` (IST calendar dates). Audit timestamps are timezone-aware UTC.
6. Another user's resource returns 404, never 403.
7. Every ledger mutation takes a row lock on the portfolio. A mutation check proves the lock is needed.
8. Every response uses the envelope `{success, data}` or `{success:false, error:{code,message,details}}`. Error codes are UPPER_SNAKE_CASE and documented.
9. Logs never contain passwords, tokens or secrets.
10. The frontend validates API responses at runtime and tests against fixtures generated from the real API, so the two sides cannot drift apart.

## 4b. Non-negotiable AI rules (for Phases 7 to 9)

- Tools wrap existing pure services and are scoped to the authenticated user.
- Answers from documents cite their source, and the assistant refuses when retrieval finds nothing.
- Text from ingested documents is treated as data, never as instructions.
- Token usage, latency and cost are logged per request.
- An evaluation harness gates changes to prompts, chunking and retrieval.

## 5. Stack and environment

- Backend: Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, Celery + Redis, structlog, uv.
- Database: PostgreSQL 16 with pgvector and pg_trgm.
- Frontend: Next.js (App Router), TypeScript strict, Tailwind, shadcn/ui, TanStack Query, zod, Recharts.
- Quality: ruff, mypy strict (app and tests), pytest (+ hypothesis) against real Postgres and Redis, Vitest, Playwright, GitHub Actions.
- Infra: Docker Compose locally; AWS for deployment (Phase 14).
- Dev machine: Windows (PowerShell). Repo at `E:\USER\Projects\FolioPilot`. Docker's disk is on `D:\DockerDesktopWSL`, package caches on `D:\caches`, Playwright browsers on `D:\caches\playwright`, evidence output at `E:\USER\Projects\_evidence`. Keep C: free.

## 6. Architecture at a glance

Tables so far (migrations in `apps/api/alembic/versions`):
- 0001 extensions (vector, pgcrypto)
- 0002 users, refresh_tokens
- 0003 funds, nav_history, nav_sync_runs (+ pg_trgm)
- 0004 portfolios, portfolio_targets, transactions
- 0005 transaction type constraint (lowercase)
- 0006 sips, sip_pauses, sip_installments (Phase 3B)
- 0007 transaction_imports, transaction_import_rows (+ transaction.import_id) (Phase 4)

Key flows:
- Daily AMFI `NAVAll.txt` sync (21:30 and 06:00 IST) updates the fund master and every fund's latest NAV. NAV history is stored only for tracked funds, backfilled from mfapi.in.
- A transaction (manual, imported, or generated from a SIP installment) goes through one function, `apply_transactions`, which locks the portfolio, validates the full ledger, writes, and triggers tracking of the fund.
- Positions are computed on read from the ledger using the average cost method.

## 7. Key decisions log

| Area | Decision |
| --- | --- |
| Auth | Access JWT (15 min) kept in memory only. Refresh token is opaque, stored as a SHA-256 hash, delivered in an httpOnly cookie, rotated on every use, grouped in families. Reuse after a 10-second grace window revokes the family. The grace window makes multi-tab use safe; the tradeoff is documented. |
| Rate limiting | Redis fixed windows on login and register. 429 with Retry-After. |
| Funds | AMFI file is the master. A sanity guard aborts a sync that looks truncated. Funds missing 30+ days are deactivated, not deleted. |
| Classification | Conservative, table-driven. Category decides first; name rules only for ambiguous index/ETF headings. Canonical hyphenated values live in `docs/classification.json`. Unknown stays `other`. |
| Cost method | Average cost now. FIFO lots arrive with tax (Phase 13). |
| SIPs | A SIP generates installments; an executed installment is an ordinary buy. SIP parameters are immutable (end it and create a new one to change). Status is derived, never stored. Managed transactions can only be undone by skipping the installment. |
| Concurrency | Portfolio row lock for all ledger mutations; Redis locks for sync and execution tasks. |
| Frontend | Contract fixtures generated by the backend. Hydration rules enforced by lint. Playwright test fails on any console warning. |

## 8. Roadmap and status

| # | Phase | Status |
| --- | --- | --- |
| 0 | Foundation: repo, Docker Compose, API/web skeletons, CI | Done |
| 1 | Auth: rotation, reuse detection, grace window, rate limits | Done; browser-checked by owner |
| 2 | AMFI fund master, NAV sync, fund search | Done; classification query check still to be reviewed |
| 3A | Portfolios, targets, transaction ledger, derived positions | Built; owner to run verify scripts, then push |
| 3B | SIPs: schedule, pauses, step-up, automatic installments | Done |
| 4 | Excel import of transactions | Built; owner to run verify-phase4 |
| 5 | Valuation, XIRR, dashboard | Built; owner to run verify-phase5 |
| 6 | Rebalancing, risk score, goals, history | Planned |
| 7 | AI: tool-calling assistant | Planned |
| 8 | AI: RAG over factsheets with citations | Planned |
| 9 | AI: evaluation harness | Planned |
| 10 | SIP health, benchmark comparison, overlap and cost drag, Monte Carlo goals | Planned |
| 11 | Alerts | Planned |
| 12 | CAS PDF import | Planned |
| 13 | Capital gains and tax | Planned (riskiest, may be cut) |
| 14 | AWS deployment | Planned |

Update this table at the end of every phase.

## 9. What each remaining phase delivers

**Phase 4: Excel import.** Template download with an Instructions sheet, upload, a preview with row-level errors and warnings, then an all-or-nothing commit through `apply_transactions`. Funds are resolved by scheme code or ISIN from the fund master. Re-uploading the same file must not duplicate transactions. Row cap, size cap, `.xlsx` only, parsed with openpyxl in memory.

**Phase 5: Valuation, XIRR, dashboard.** A pure valuation function (latest NAV, cost fallback marked clearly), XIRR per fund, portfolio and overall from actual cash flows, a dashboard where every page shows identical totals, and "as of" dates everywhere.

**Phase 6: Rebalancing, risk, goals.** Carried over from SIP Tracker as pure functions that work on in-memory positions:
- Drift = sum of absolute (current % minus target %) divided by 2. Suggestions ignore differences under 500 INR or 1 percentage point.
- Risk score, 0 to 100: equity share (40), small-cap share (25), concentration (20), category volatility (15). Under 34 is Conservative, 34 to 66 Moderate, 67 and above Aggressive. Volatility weights are remapped to the canonical sub-categories.
- Goals: future value at a fixed 12% (kept as the simple mode), required SIP and shortfall; goals link to portfolios and SIPs.
- Rebalance runs are saved as history.

**Phase 7: AI assistant.** Tool calling over the pure engines (positions, valuation, XIRR, drift, risk, goals), streaming responses, per-request cost and latency logging, an "informational, not advice" guardrail, and structured-output goal setup ("50 lakh in 12 years, 15k a month").

**Phase 8: RAG.** Ingest fund factsheets with separate handling for tables and prose, store in pgvector, hybrid retrieval (keyword plus vector), citations to the exact page, and refusal when nothing relevant is found.

**Phase 9: Evaluation.** A 30 to 50 question set with metrics for retrieval hit rate, faithfulness, numeric accuracy and tool-call accuracy, runnable in CI, with results recorded per change.

**Phase 10: Analytics.** SIP health (missed or paused detection, step-up, "what if I stopped for 6 months"), benchmark comparison on the same cash flows, fund overlap and expense-ratio cost drag, Monte Carlo goal probability.

**Phase 11: Alerts.** Drift above a threshold, missed SIP, goal off track, delivered by email or webhook through Celery with de-duplication.

**Phase 12: CAS import.** CAMS/KFintech consolidated statement PDFs into transactions, with a preview step. Synthetic test files only.

**Phase 13: Tax.** FIFO lots, short- and long-term classification, harvesting hints. Rules are intricate and change, so this is optional and must cite its rule sources.

**Phase 14: Deployment.** AWS, CI/CD, secrets handling, backups, health checks and basic observability.

## 10. Quality bar (every phase)

- `ruff check`, `ruff format --check`, `mypy --strict` on app and tests.
- `pytest` unit and integration against real Postgres and Redis, with a separate `_test` database that tests refuse to run without.
- Frontend lint (including the hydration rule), typecheck, Vitest, `next build`.
- `make smoke`, `make contract` (no fixture drift) and `make e2e` (Playwright in a real browser).
- Migration roundtrip with data in the tables.
- Concurrency features have a mutation check proving the lock or constraint matters.
- Docs updated: this file, CONVENTIONS.md, README, and the topic docs under `docs/`.

## 11. How we work

- One phase at a time. Each phase is a prompt for Antigravity, then a report, then review.
- Antigravity builds and may commit locally. It never pushes, never reads `.env`, never runs destructive Docker commands, and never rewrites history unless the owner explicitly asks.
- Evidence comes from scripts the owner runs (`scripts/verify-phase*.ps1`, mutation scripts, `make e2e`). Reports from the tool are treated as claims until the scripts agree.
- The owner pushes to GitHub after the evidence matches and `git ls-files | findstr /i "\.env"` lists only `.env.example` files.
- The owner tests every new page in a real browser. Tools cannot see one.
- Keep an eye on disk: run `docker builder prune -f` regularly and keep C: above 20 GB free.

## 12. Open decisions

- LLM provider and embedding model (Phase 7). Put them behind a small client interface so tests never call the network.
- Benchmark data source (Phase 10): likely the NAV of a Nifty 50 index fund from the fund master as a proxy, to avoid index licensing.
- Expense ratio and top-holdings data (Phase 10): the source and refresh method are not yet chosen.
- Email provider for alerts (Phase 11).
- AWS shape: single EC2 with Compose versus ECS (Phase 14).

## 13. Known gaps and debt

- GitHub Actions has not run yet. First push may need fixes (services, Windows-only workarounds).
- Phase 3A evidence has not been reproduced by the owner. Fund classification results have not been reviewed against the expected list.
- About 29 legacy funds with an empty AMFI category remain `other/unknown` by design.
- Some NAV history lags AMFI by a day. Backfill writes the AMFI latest NAV so history and "latest" agree.
- No password reset, email verification, MFA or session list (needs email infrastructure).