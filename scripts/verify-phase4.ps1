# scripts/verify-phase4.ps1
# FolioPilot Phase 4: Comprehensive Verification Script
# Evaluates Excel transaction imports, previews, duplicate detection,
# all-or-nothing commit under row lock, undo, Step 0 carry-over checks, and quality gates.

$ErrorActionPreference = "Continue"

$evidenceDir = "E:\USER\Projects\_evidence"
if (-not (Test-Path $evidenceDir)) {
    New-Item -ItemType Directory -Path $evidenceDir -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logFile = Join-Path $evidenceDir "verify-phase4-$timestamp.txt"

Write-Host "FolioPilot Phase 4 Verification running..." -ForegroundColor Cyan
Write-Host "Log output will be saved to: $logFile" -ForegroundColor Cyan

$DC = if (Get-Command "docker-compose" -ErrorAction SilentlyContinue) { "docker-compose" } else { "docker compose" }

$global:CheckIndex = 0

function Run-Step {
    param(
        [string]$Title,
        [scriptblock]$Action,
        [string]$CommandLine
    )
    $global:CheckIndex++
    $header = "`n=== $global:CheckIndex. $Title ==="
    Write-Host $header -ForegroundColor Yellow
    Add-Content -Path $logFile -Value $header

    $cmdLineText = "Command: $CommandLine"
    Write-Host $cmdLineText -ForegroundColor Gray
    Add-Content -Path $logFile -Value $cmdLineText

    $out = & $Action 2>&1 | Out-String

    # Redact sensitive JWT tokens, passwords, and cookies
    $redacted = $out -replace "eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[REDACTED_JWT]"
    $redacted = $redacted -replace 'fp_refresh=[^;\s]+', 'fp_refresh=[REDACTED_COOKIE]'
    $redacted = $redacted -replace '("password"\s*:\s*)"[^"]+"', '$1"[REDACTED_PASSWORD]"'

    Write-Host $redacted
    Add-Content -Path $logFile -Value $redacted

    $code = $LASTEXITCODE
    $exitCodeText = "exit code: $code`n"
    Write-Host $exitCodeText
    Add-Content -Path $logFile -Value $exitCodeText
}

function Run-Sql {
    param(
        [string]$Title,
        [string]$Sql
    )
    Run-Step -Title $Title -CommandLine "psql: $Sql" -Action {
        $Sql | & $DC exec -T db env /bin/sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
    }
}

# ==============================================================================
# SECTION A: STEP 0 CARRY-OVER CHECKS (FROM 3A AND 3B)
# ==============================================================================
Write-Host "`n--- SECTION A: Step 0 Carry-Over Checks ---" -ForegroundColor Magenta

Run-Sql -Title "Classification: Asset Class x Source Counts" `
    -Sql "SELECT asset_class, classification_source, count(*) FROM funds GROUP BY asset_class, classification_source ORDER BY asset_class, classification_source;"

Run-Sql -Title "Classification: Sub-Category Distribution Counts" `
    -Sql "SELECT sub_category, count(*) FROM funds GROUP BY sub_category ORDER BY count(*) DESC;"

Run-Sql -Title "Classification: 26 Facts and Regression Funds Expected vs Actual" -Sql @"
WITH expected_data (code, exp_name, exp_class, exp_sub) AS (
    VALUES
        (122639, 'Parag Parikh Flexi Cap Fund', 'equity', 'flexi-cap'),
        (118989, 'HDFC NIFTY 50 Index Fund', 'equity', 'index'),
        (111954, 'SBI Gold ETF', 'gold', 'gold-etf'),
        (113434, 'Axis Gold ETF', 'gold', 'gold-etf'),
        (152957, 'Groww Gold ETF', 'gold', 'gold-etf'),
        (113049, 'HDFC Gold ETF', 'gold', 'gold-etf'),
        (154294, 'HSBC Gold ETF', 'gold', 'gold-etf'),
        (153425, 'Regression fund 153425', 'equity', 'index'),
        (153235, 'Regression fund 153235', 'debt', 'index-debt'),
        (153234, 'Regression fund 153234', 'debt', 'index-debt'),
        (153838, 'Regression fund 153838', 'equity', 'index'),
        (154723, 'Regression fund 154723', 'equity', 'index'),
        (154503, 'Regression fund 154503', 'equity', 'index'),
        (153212, 'Regression fund 153212', 'equity', 'index'),
        (152306, 'Regression fund 152306', 'equity', 'index'),
        (153346, 'Regression fund 153346', 'equity', 'index'),
        (149786, 'Regression fund 149786', 'equity', 'index'),
        (152127, 'Regression fund 152127', 'equity', 'index'),
        (154752, 'Regression fund 154752', 'equity', 'index'),
        (152482, 'Regression fund 152482', 'equity', 'index'),
        (114984, 'Regression fund 114984', 'equity', 'international'),
        (154332, 'Regression fund 154332', 'debt', 'index-debt'),
        (148382, 'Regression fund 148382', 'equity', 'international'),
        (153434, 'Regression fund 153434', 'equity', 'index'),
        (153683, 'Regression fund 153683', 'debt', 'index-debt'),
        (149221, 'Regression fund 149221', 'equity', 'international')
)
SELECT
    f.scheme_code,
    substring(f.name from 1 for 35) AS name,
    e.exp_class || '/' || e.exp_sub AS expected,
    f.asset_class || '/' || f.sub_category AS actual,
    f.classification_source AS source,
    CASE WHEN f.asset_class = e.exp_class AND f.sub_category = e.exp_sub THEN 'MATCH' ELSE 'MISMATCH' END AS status
FROM funds f
JOIN expected_data e ON f.scheme_code = e.code
ORDER BY f.scheme_code;
"@

Run-Sql -Title "Count of FoF and Solution Oriented Funds Not Classified as Other (Expected: 0)" `
    -Sql "SELECT count(*) AS actual_invalid_fof_count, 0 AS expected_invalid_fof_count FROM funds WHERE (category_raw ILIKE '%fof%' OR category_raw ILIKE '%fund of funds%' OR category_raw ILIKE '%solution%') AND asset_class != 'other';"

Run-Step -Title "SIP Execution Triggers (NAV Backfill and SIP Creation Enqueue Checks)" -CommandLine "python -c 'inspect triggers'" -Action {
    & $DC exec -T api python -c "
import inspect
from app.services.sip_service import SipService
from app.services.nav_backfill import backfill_fund_nav_history

print('Checking SipService.create_sip execution trigger:')
sip_src = inspect.getsource(SipService.create_sip)
has_sip_trigger = 'execute_pending_for_fund.delay' in sip_src
print(f'Expected enqueue: True | Actual enqueue present: {has_sip_trigger}')

print('Checking nav_backfill completion trigger:')
backfill_src = inspect.getsource(backfill_fund_nav_history)
has_backfill_trigger = 'execute_pending_for_fund.delay' in backfill_src
print(f'Expected enqueue: True | Actual enqueue present: {has_backfill_trigger}')
"
}

Run-Step -Title "SIP Unit & Integration Test Suite (pytest -v)" -CommandLine "docker-compose exec api pytest tests/unit/test_sip_*.py tests/integration/test_sips_*.py -v" -Action {
    & $DC exec -T api pytest tests/unit/test_sip_schedule.py tests/unit/test_sip_step_up.py tests/integration/test_sips_api.py tests/integration/test_sip_execution.py -v
}

# ==============================================================================
# SECTION B: EXCEL IMPORT FIXTURES & PREVIEW VERIFICATION
# ==============================================================================
Write-Host "`n--- SECTION B: Excel Import Fixtures Verification ---" -ForegroundColor Magenta

Run-Step -Title "Generate Import Fixtures (.xlsx and expected.json)" -CommandLine "python scripts/generate_import_fixtures.py" -Action {
    & $DC exec -T api python scripts/generate_import_fixtures.py
}

Run-Step -Title "Verify Import Fixtures Against Expected Previews" -CommandLine "pytest tests/integration/test_imports_api.py -k test_import_fixtures_previews" -Action {
    & $DC exec -T api pytest tests/integration/test_imports_api.py -k test_import_fixtures_previews_and_worked_example_commit -v -s
}

# ==============================================================================
# SECTION C: WORKED-EXAMPLE EXACT HOLDINGS VERIFICATION
# ==============================================================================
Write-Host "`n--- SECTION C: Worked-Example Exact Holdings Verification ---" -ForegroundColor Magenta

Run-Step -Title "Worked-Example Exact Math Verification (120 units, 6400 cost basis, 53.3333 avg cost)" -CommandLine "python -c 'verify worked-example holdings'" -Action {
    & $DC exec -T api python -c "
import asyncio
from decimal import Decimal
from app.core.database import async_session_factory
from app.repositories.transactions import get_portfolio_holdings
from app.models.portfolio import Portfolio
from app.models.user import User
from app.services.import_service import ImportService
from app.services.import_file import inspect_and_read_workbook
from pathlib import Path

async def verify():
    async with async_session_factory() as session:
        # Create test user and portfolio
        user = User(email='worked_example_script@example.com', hashed_password='fake')
        session.add(user)
        await session.flush()
        portfolio = Portfolio(user_id=user.id, name='Worked Example Script Test')
        session.add(portfolio)
        await session.flush()

        # Read fixture worked-example.xlsx
        path = Path('tests/fixtures/imports/worked-example.xlsx')
        content = path.read_bytes()
        parsed = inspect_and_read_workbook(content, path.name)

        svc = ImportService(session)
        preview = await svc.preview(portfolio.id, user.id, parsed)
        summary = await svc.commit(portfolio.id, user.id, preview.id, preview.plan_fingerprint, False)

        holdings = await get_portfolio_holdings(session, portfolio.id)
        assert len(holdings.items) == 1
        h = holdings.items[0]

        print('=== WORKED-EXAMPLE COMPARISON (Expected vs Actual) ===')
        print(f'Units:        Expected: 120.000        | Actual: {h.units:.3f}')
        print(f'Cost Basis:   Expected: 6400.00        | Actual: {h.cost_basis:.2f}')
        print(f'Avg Cost NAV: Expected: 53.3333        | Actual: {h.avg_cost_nav:.4f}')
        print(f'Total Bought: Expected: 8000.00        | Actual: {h.total_invested:.2f}')
        print(f'Total Sold:   Expected: 2100.00        | Actual: {h.total_realized_gain + (Decimal(30) * h.avg_cost_nav):.2f}')

        await session.rollback()

asyncio.run(verify())
"
}

# ==============================================================================
# SECTION D: MIGRATION 0007 ROUND-TRIP VERIFICATION
# ==============================================================================
Write-Host "`n--- SECTION D: Migration 0007 Round-Trip ---" -ForegroundColor Magenta

Run-Sql -Title "Table Schema: transaction_imports" -Sql "\d transaction_imports"
Run-Sql -Title "Table Schema: transaction_import_rows" -Sql "\d transaction_import_rows"
Run-Sql -Title "Column & FK Check: transactions.import_id" -Sql "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'import_id';"

Run-Step -Title "Migration 0007 Upgrade & Downgrade Roundtrip Test" -CommandLine "pytest tests/integration/test_migration_0007_roundtrip.py" -Action {
    & $DC exec -T api pytest tests/integration/test_migration_0007_roundtrip.py -v
}

# ==============================================================================
# SECTION E: UNIT & INTEGRATION TEST SUITES
# ==============================================================================
Write-Host "`n--- SECTION E: Unit & Integration Test Suites ---" -ForegroundColor Magenta

Run-Step -Title "Import Unit Tests (file, rows, template, planner)" -CommandLine "pytest tests/unit/test_import_*.py" -Action {
    & $DC exec -T api pytest tests/unit/test_import_file.py tests/unit/test_import_rows.py tests/unit/test_import_template.py tests/unit/test_import_planner.py -v
}

Run-Step -Title "Import Integration Tests (API, tasks, concurrency, guards)" -CommandLine "pytest tests/integration/test_import_*.py" -Action {
    & $DC exec -T api pytest tests/integration/test_import_tasks.py tests/integration/test_imports_api.py -v
}

Run-Step -Title "Celery Beat Purge Task Schedule Verification" -CommandLine "pytest tests/integration/test_import_tasks.py -k test_import_purge_beat_schedule_times" -Action {
    & $DC exec -T api pytest tests/integration/test_import_tasks.py -k test_import_purge_beat_schedule_times -v
}

# ==============================================================================
# SECTION F: FRONTEND TESTS & PLAYWRIGHT REAL-BROWSER E2E
# ==============================================================================
Write-Host "`n--- SECTION F: Frontend Tests & Real-Browser E2E ---" -ForegroundColor Magenta

Run-Step -Title "Frontend Contract Fixtures Validation (Vitest)" -CommandLine "cd apps/web; npx vitest run src/test/contract-fixtures.test.ts" -Action {
    Push-Location apps/web
    try {
        npx vitest run src/test/contract-fixtures.test.ts
    } finally {
        Pop-Location
    }
}

Run-Step -Title "Frontend UI & SSR Hydration Tests (Vitest)" -CommandLine "cd apps/web; npx vitest run src/test/imports-ui.test.tsx src/test/imports-ssr-hydration.test.tsx" -Action {
    Push-Location apps/web
    try {
        npx vitest run src/test/imports-ui.test.tsx src/test/imports-ssr-hydration.test.tsx
    } finally {
        Pop-Location
    }
}

Run-Step -Title "Playwright Real-Browser E2E Import Tests" -CommandLine "npm --prefix apps/web run e2e e2e/import-e2e.spec.ts" -Action {
    $env:PLAYWRIGHT_BROWSERS_PATH = "D:\caches\playwright"
    npm --prefix apps/web run e2e e2e/import-e2e.spec.ts
}

# ==============================================================================
# SECTION G: GIT REPOSITORY STATE & CODE QUALITY GATES
# ==============================================================================
Write-Host "`n--- SECTION G: Git Repository State & Quality Bar ---" -ForegroundColor Magenta

Run-Step -Title "Git Status Short" -CommandLine "git status --short" -Action {
    git status --short
}

Run-Step -Title "Git Log Recent 10 Commits" -CommandLine "git log -n 10 --oneline" -Action {
    git log -n 10 --oneline
}

Run-Step -Title "Python Lint Check (Ruff)" -CommandLine "docker-compose exec api ruff check ." -Action {
    & $DC exec -T api ruff check .
}

Run-Step -Title "Python Format Check (Ruff)" -CommandLine "docker-compose exec api ruff format --check ." -Action {
    & $DC exec -T api ruff format --check .
}

Run-Step -Title "Python Type Check (Mypy)" -CommandLine "docker-compose exec api mypy app tests" -Action {
    & $DC exec -T api mypy app tests
}

Run-Step -Title "Web TypeScript Type Check" -CommandLine "cd apps/web; npm run typecheck" -Action {
    Push-Location apps/web
    try {
        npm run typecheck
    } finally {
        Pop-Location
    }
}

Run-Step -Title "Web ESLint Check" -CommandLine "cd apps/web; npm run lint" -Action {
    Push-Location apps/web
    try {
        npm run lint
    } finally {
        Pop-Location
    }
}

Run-Step -Title "Web Next.js Production Build" -CommandLine "cd apps/web; npm run build" -Action {
    Push-Location apps/web
    try {
        npm run build
    } finally {
        Pop-Location
    }
}

Write-Host "`nFolioPilot Phase 4 Verification Finished." -ForegroundColor Green
Write-Host "Evidence log written to: $logFile" -ForegroundColor Green
