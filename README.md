# FolioPilot

FolioPilot is a full-stack personal finance platform engineered specifically for Indian mutual fund investors.

This repository holds the Phase 0 foundational architecture upon which all future investment analysis, synchronization, portfolio tracking, and AI capabilities are built.

---

## Prerequisites
- **Docker & Docker Compose** (Docker Desktop with Compose v2)
- **Python 3.12+** and **uv** (for local backend development)
- **Node.js 20+** and **npm** (for local frontend development)
- **Make** (optional, for convenience commands)

---

## Quickstart

### 1. Clone & Configure Environment
```bash
cp .env.example .env
```
*(Review and customize any placeholder values in `.env` as needed)*

### 2. Start Services via Docker Compose
```bash
make up
# or: docker compose up -d
```

### 3. Run Database Migrations
```bash
make migrate
# or: docker compose exec api alembic upgrade head
```

### 4. Access Services
- **Frontend Web Application**: [http://localhost:3000](http://localhost:3000)
- **Backend API Liveness**: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)
- **Backend API Readiness**: [http://localhost:8000/api/v1/health/ready](http://localhost:8000/api/v1/health/ready)
- **API Documentation (Dev only)**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Makefile Targets

| Target | Description |
|---|---|
| `make up` | Start all Docker services (DB, Redis, API, Worker, Beat, Web) |
| `make down` | Stop and tear down all Docker containers |
| `make logs` | Tail logs across all running containers |
| `make migrate` | Run pending Alembic migrations on the PostgreSQL database |
| `make makemigration m="name"` | Autogenerate a new Alembic migration |
| `make test` | Run test suites across both API (pytest) and Web (vitest) |
| `make test-api` | Run backend tests using pytest |
| `make test-web` | Run frontend tests using vitest |
| `make lint` | Run Ruff linter on backend and ESLint on frontend |
| `make format` | Format backend with Ruff and frontend with Prettier |
| `make typecheck` | Run mypy strict on backend and TypeScript compiler on web |
| `make shell-api` | Open a bash shell in the running API container |
| `make psql` | Open a PostgreSQL shell connected to the database |

---

## Project Structure

```
.
├── apps/
│   ├── api/                  # FastAPI backend service
│   │   ├── app/
│   │   │   ├── main.py       # Application factory, middleware & routing
│   │   │   ├── core/         # Config, logging, error handling, DB & Redis
│   │   │   ├── api/          # HTTP routers (v1 prefix)
│   │   │   ├── models/       # SQLAlchemy 2.0 models & Base
│   │   │   ├── schemas/      # Pydantic schemas & response envelopes
│   │   │   ├── services/     # Pure business logic
│   │   │   ├── workers/      # Celery worker application & tasks
│   │   │   └── ai/           # AI & RAG tooling (reserved for later phases)
│   │   ├── alembic/          # Database migrations & env.py
│   │   ├── tests/            # Unit & integration test suites
│   │   ├── pyproject.toml    # Dependency & tool configurations
│   │   └── Dockerfile        # Multi-stage production container
│   └── web/                  # Next.js App Router frontend
│       ├── src/
│       │   ├── app/          # App Router layouts & pages
│       │   ├── components/   # UI components (shadcn/ui style) & providers
│       │   └── lib/          # Typed API client, TanStack Query, utils
│       └── Dockerfile        # Web container
├── docker-compose.yml        # Local multi-service infrastructure
├── Makefile                  # Developer workflow commands
├── .pre-commit-config.yaml   # Pre-commit hooks
├── .github/workflows/ci.yml  # GitHub Actions CI pipeline
├── .env.example              # Environment template
├── CONVENTIONS.md            # Architecture & engineering contract
└── README.md
```

---

## Roadmap

- **Phase 0**: Architecture foundation & conventions (Current)
- **Phase 1**: Authentication (JWT with refresh rotation)
- **Phase 2**: AMFI Mutual Fund Master & NAV synchronization
- **Phase 3**: Portfolios, SIPs & transaction ledger
- **Phase 4**: Statement imports (Excel & Consolidated Account Statement / CAS PDF)
- **Phase 5**: Valuation engine (XIRR) & capital gains tax calculation
- **Phase 6**: Rebalancing, risk profiling & Monte Carlo goal simulation
- **Phase 7**: Investor alerts & notifications
- **Phase 8**: AI investment assistant & factsheet RAG (pgvector)
- **Phase 9**: Evaluation harness & system verification

