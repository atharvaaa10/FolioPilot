# scripts/verify-phase5.ps1
# FolioPilot Phase 5: Comprehensive Verification Script
# Evaluates Valuation, Realized & Unrealized Gains, XIRR, Value Series,
# Investor Dashboard, Step 0 carry-over checks, and quality gates.

$ErrorActionPreference = "Continue"

$evidenceDir = "E:\USER\Projects\_evidence"
if (-not (Test-Path $evidenceDir)) {
    New-Item -ItemType Directory -Path $evidenceDir -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logFile = Join-Path $evidenceDir "verify-phase5-$timestamp.txt"

Write-Host "FolioPilot Phase 5 Verification running..." -ForegroundColor Cyan
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
# SECTION A: STEP 0 CARRY-OVER CHECKS
# ==============================================================================
Write-Host "`n--- SECTION A: Step 0 Carry-Over Checks ---" -ForegroundColor Magenta

Run-Step -Title "Git Status Short & Branch" -CommandLine "git status -sb" -Action {
    git status -sb
}

Run-Step -Title "Git Log Recent 20 Commits" -CommandLine "git log --oneline -20" -Action {
    git log --oneline -20
}

Run-Step -Title "Git Branch All" -CommandLine "git branch -a" -Action {
    git branch -a
}

Run-Step -Title "Git Remote Verbose" -CommandLine "git remote -v" -Action {
    git remote -v
}

Run-Step -Title "Verify .env Present, Untracked, and Access Restricted" -CommandLine "Check .env properties and git tracking" -Action {
    $envPath = ".env"
    $envExists = Test-Path $envPath
    $tracked = git ls-files .env
    $acl = (Get-Acl $envPath).AccessToString
    Write-Host "Expected .env Exists: True | Actual: $envExists"
    Write-Host "Expected .env Untracked: True | Actual Untracked: $([string]::IsNullOrEmpty($tracked))"
    Write-Host "File Access Permissions: $acl"
}

Run-Step -Title "Verify No .xlsx Files Tracked by Git" -CommandLine "git ls-files '*.xlsx'" -Action {
    $trackedXlsx = git ls-files "*.xlsx"
    Write-Host "Expected Tracked .xlsx: 0 | Actual: $(if ([string]::IsNullOrEmpty($trackedXlsx)) { '0' } else { $trackedXlsx })"
}

Run-Sql -Title "Classification: 26 Reference Funds Table (No Expected Column)" -Sql @"
SELECT
    scheme_code,
    asset_class,
    sub_category,
    classification_source AS source,
    substring(name from 1 for 40) AS name
FROM funds
WHERE scheme_code IN (
    122639, 118989, 111954, 113434, 152957, 113049, 154294,
    153425, 153838, 154723, 154862, 154674, 149454, 150035,
    150085, 150086, 120505, 120503, 120828, 120830, 100033,
    100035, 100037, 100038, 100041, 100042
)
ORDER BY scheme_code;
"@

Run-Step -Title "Phase 4 Worked-Example Exact Holdings Verification (120 units, 6400 cost basis, 53.3333 avg cost)" -CommandLine "python -c 'verify worked-example holdings'" -Action {
    & $DC exec -T api python -c "
import asyncio
from decimal import Decimal
from pathlib import Path
from app.core.db import get_session_factory
from app.models.portfolio import Portfolio
from app.models.user import User
from app.repositories.transactions import get_portfolio_holdings
from app.services.import_file import inspect_and_read_workbook
from app.services.import_service import ImportService

async def verify():
    factory = get_session_factory()
    async with factory() as session:
        user = User(email='verify_phase5_step0@example.com', password_hash='fake_hash')
        session.add(user)
        await session.flush()
        portfolio = Portfolio(user_id=user.id, name='Step 0 Worked Example Test')
        session.add(portfolio)
        await session.flush()

        path = Path('tests/fixtures/imports/worked-example.xlsx')
        content = path.read_bytes()
        parsed = inspect_and_read_workbook(content, path.name)

        svc = ImportService(session)
        preview = await svc.preview(portfolio.id, user.id, parsed)
        summary = await svc.commit(portfolio.id, user.id, preview.id, preview.plan_fingerprint, False)

        holdings = await get_portfolio_holdings(session, portfolio.id)
        assert len(holdings.items) == 1
        h = holdings.items[0]

        print('=== STEP 0 WORKED-EXAMPLE COMPARISON (Expected vs Actual) ===')
        print(f'Units:        Expected: 120.0000       | Actual: {h.units:.4f}')
        print(f'Cost Basis:   Expected: 6400.00        | Actual: {h.cost_basis:.2f}')
        print(f'Avg Cost NAV: Expected: 53.3333        | Actual: {h.avg_cost_nav:.4f}')

        await session.rollback()

asyncio.run(verify())
"
}

# ==============================================================================
# SECTION B: API SPECIFICATION & CACHE-CONTROL HEADERS
# ==============================================================================
Write-Host "`n--- SECTION B: OpenAPI Spec & Cache-Control Headers ---" -ForegroundColor Magenta

Run-Step -Title "OpenAPI Schema Valuation Endpoints Inspection" -CommandLine "curl.exe -s http://localhost:8000/openapi.json" -Action {
    $openapi = curl.exe -s http://localhost:8000/openapi.json | ConvertFrom-Json
    $valuationPaths = $openapi.paths.PSObject.Properties | Where-Object { $_.Name -like "*valuation*" -or $_.Name -like "*value-series*" }
    foreach ($p in $valuationPaths) {
        Write-Host "Path: $($p.Name)"
        $methods = $p.Value.PSObject.Properties | Select-Object -ExpandProperty Name
        Write-Host "  Methods: $($methods -join ', ')"
    }
}

Run-Step -Title "Verify Cache-Control: no-store on Valuation Summary (Raw Curl -i)" -CommandLine "curl.exe -i http://localhost:8000/api/v1/valuation/summary" -Action {
    # Generate fresh temp user and token via API
    $token = & $DC exec -T api python -c "
import uuid, httpx
uid = uuid.uuid4().hex[:8]
r = httpx.post('http://localhost:8000/api/v1/auth/register', json={'email': f'cache_hdr_{uid}@example.com', 'password': 'Password123!'})
print(r.json()['data']['access_token'])
"
    $token = $token.Trim()
    curl.exe -i -s -H "Authorization: Bearer $token" http://localhost:8000/api/v1/valuation/summary
}

# ==============================================================================
# SECTION C: LIVE END-TO-END THROUGH RUNNING STACK
# ==============================================================================
Write-Host "`n--- SECTION C: Live End-to-End Test Suite ---" -ForegroundColor Magenta

Run-Step -Title "Live End-to-End: Users A & B Portfolios, Valuation, Series, Summary, Isolation" -CommandLine "docker-compose exec api python scripts/verify_phase5_live.py" -Action {
    & $DC exec -T api python scripts/verify_phase5_live.py
}

# ==============================================================================
# SECTION D: QUALITY GATES & TEST SUITES
# ==============================================================================
Write-Host "`n--- SECTION D: Quality Gates & Verification ---" -ForegroundColor Magenta

Run-Step -Title "Python Lint Check (Ruff)" -CommandLine "docker-compose exec api ruff check ." -Action {
    & $DC exec -T api ruff check .
}

Run-Step -Title "Python Format Check (Ruff)" -CommandLine "docker-compose exec api ruff format --check ." -Action {
    & $DC exec -T api ruff format --check .
}

Run-Step -Title "Python Type Check (Mypy Strict)" -CommandLine "docker-compose exec api mypy --strict app tests" -Action {
    & $DC exec -T api mypy --strict app tests
}

Run-Step -Title "Pytest Collect-Only Counts" -CommandLine "docker-compose exec api pytest --collect-only -q" -Action {
    & $DC exec -T api pytest --collect-only -q
}

Run-Step -Title "Full Pytest Suite" -CommandLine "docker-compose exec api pytest -v" -Action {
    & $DC exec -T api pytest -v
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

Run-Step -Title "Web Vitest Suite" -CommandLine "cd apps/web; npx vitest run" -Action {
    Push-Location apps/web
    try {
        npx vitest run
    } finally {
        Pop-Location
    }
}

Run-Step -Title "Web Next.js Production Build with Route Table" -CommandLine "cd apps/web; npm run build" -Action {
    Push-Location apps/web
    try {
        npm run build
    } finally {
        Pop-Location
    }
}

Run-Step -Title "Contract Fixtures Drift Check" -CommandLine "docker-compose exec api pytest tests/integration/test_contract_fixtures.py && git status --short" -Action {
    & $DC exec -T api pytest tests/integration/test_contract_fixtures.py -v
    git status --short tests/fixtures/contract/
}

# ==============================================================================
# SECTION E: DISK SPACE & DOCKER SYSTEM HEALTH
# ==============================================================================
Write-Host "`n--- SECTION E: Disk Space & System Health ---" -ForegroundColor Magenta

Run-Step -Title "Windows Drive Free Space (C: and D:)" -CommandLine "Get-PSDrive C, D" -Action {
    Get-PSDrive C, D | Select-Object Name, Used, Free, @{Name="FreeGB";Expression={[math]::Round($_.Free/1GB, 2)}}
}

Run-Step -Title "Docker System Disk Usage" -CommandLine "docker system df" -Action {
    docker system df
}

Write-Host "`nFolioPilot Phase 5 Verification Finished." -ForegroundColor Green
Write-Host "Evidence log written to: $logFile" -ForegroundColor Green
