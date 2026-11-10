# scripts/verify-phase3b.ps1
# FolioPilot Phase 3B: Comprehensive Verification Script
# Evaluates SIPs, schedules, pauses, step-up, automatic installment execution,
# ledger protection, carry-over checks, and quality gates.

$ErrorActionPreference = "Continue"

$evidenceDir = "E:\USER\Projects\_evidence"
if (-not (Test-Path $evidenceDir)) {
    New-Item -ItemType Directory -Path $evidenceDir -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logFile = Join-Path $evidenceDir "verify-phase3b-$timestamp.txt"

Write-Host "FolioPilot Phase 3B Verification running..." -ForegroundColor Cyan
Write-Host "Log output will be saved to: $logFile" -ForegroundColor Cyan

$global:CheckIndex = 0

function Run-Step {
    param(
        [string]$Title,
        [scriptblock]$Action,
        [string]$CommandLine
    )
    $global:CheckIndex++
    $header = "=== $global:CheckIndex. $Title ==="
    Write-Host $header -ForegroundColor Yellow
    Add-Content -Path $logFile -Value $header

    $cmdLineText = "Command: $CommandLine"
    Write-Host $cmdLineText -ForegroundColor Gray
    Add-Content -Path $logFile -Value $cmdLineText

    $startCode = $LASTEXITCODE
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
        docker compose exec -T db env /bin/sh -c "psql -U `"`$POSTGRES_USER`" -d `"`$POSTGRES_DB`" -c `"$Sql`""
    }
}

# ==============================================================================
# SECTION A: STEP 0 CARRY-OVER FROM PHASE 3A
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

Run-Sql -Title "Count of FoF and Solution Oriented Funds Not Classified as Other" `
    -Sql "SELECT count(*) AS invalid_fof_count FROM funds WHERE (category_raw ILIKE '%fof%' OR category_raw ILIKE '%fund of funds%' OR category_raw ILIKE '%solution%') AND asset_class != 'other';"

Run-Sql -Title "All Bank of India Funds and Their Asset Classes" `
    -Sql "SELECT scheme_code, substring(name from 1 for 40) AS name, category_raw, asset_class, sub_category FROM funds WHERE name ILIKE '%Bank of India%' ORDER BY scheme_code;"

# Error details check via isolated test execution
Run-Step -Title "INSUFFICIENT_UNITS Raw Error Envelope (available_units and date)" -CommandLine "docker compose exec api pytest tests/integration/test_transactions_api.py -k test_sell_more_units_than_available_fails" -Action {
    docker compose exec -T api uv run pytest tests/integration/test_transactions_api.py -k test_sell_more_units_than_available_fails -v -s
}

Run-Step -Title "LEDGER_INCONSISTENT Raw Error Envelope (fund and failing date)" -CommandLine "docker compose exec api pytest tests/integration/test_transactions_api.py -k test_backdated_sell_causing_negative_balance_fails" -Action {
    docker compose exec -T api uv run pytest tests/integration/test_transactions_api.py -k test_backdated_sell_causing_negative_balance_fails -v -s
}

# Header verification
Run-Step -Title "X-Request-ID Headers on 200, 401, 404, 429 Responses" -CommandLine "curl.exe -i on health, auth, missing route, and rate limit" -Action {
    Write-Host "--- 200 OK Response ---"
    curl.exe -i -s http://localhost:8000/api/v1/health/ready | Select-String -Pattern "HTTP|X-Request-ID"
    Write-Host "`n--- 401 Unauthorized Response ---"
    curl.exe -i -s http://localhost:8000/api/v1/users/me | Select-String -Pattern "HTTP|X-Request-ID"
    Write-Host "`n--- 404 Not Found Response ---"
    curl.exe -i -s http://localhost:8000/api/v1/nonexistent-route-404 | Select-String -Pattern "HTTP|X-Request-ID"
}

Run-Step -Title "CORS Preflight Headers (Retry-After, X-Request-ID Expose)" -CommandLine "curl.exe -i -X OPTIONS http://localhost:8000/api/v1/users/me" -Action {
    curl.exe -i -s -X OPTIONS http://localhost:8000/api/v1/users/me `
        -H "Origin: http://localhost:3000" `
        -H "Access-Control-Request-Method: GET" `
        -H "Access-Control-Request-Headers: authorization,content-type" | Select-String -Pattern "HTTP|Access-Control-"
}

# Carry-over table schemas
Run-Sql -Title "Table Schema: funds" -Sql "\d funds"
Run-Sql -Title "Table Schema: nav_history" -Sql "\d nav_history"
Run-Sql -Title "Table Schema: portfolios" -Sql "\d portfolios"
Run-Sql -Title "Table Schema: portfolio_targets" -Sql "\d portfolio_targets"
Run-Sql -Title "Table Schema: transactions" -Sql "\d transactions"

# ==============================================================================
# SECTION B: GIT REPOSITORY STATE
# ==============================================================================
Write-Host "`n--- SECTION B: Git Repository State ---" -ForegroundColor Magenta

Run-Step -Title "Git Status Short" -CommandLine "git status --short" -Action {
    git status --short
}

Run-Step -Title "Git Current HEAD" -CommandLine "git rev-parse HEAD" -Action {
    git rev-parse HEAD
}

Run-Step -Title "Git Branch Listing" -CommandLine "git branch -a" -Action {
    git branch -a
}

Run-Step -Title "Git Reflog (last 30 entries)" -CommandLine "git reflog -30" -Action {
    git reflog -30
}

Run-Step -Title "Git Log Graph (last 25 entries)" -CommandLine "git log --oneline --all --graph -25" -Action {
    git log --oneline --all --graph -25
}

# ==============================================================================
# SECTION C: DATABASE PHASE 3B SCHEMAS & CONSTRAINTS
# ==============================================================================
Write-Host "`n--- SECTION C: Phase 3B Schemas & Constraints ---" -ForegroundColor Magenta

Run-Sql -Title "Table Schema: sips" -Sql "\d sips"
Run-Sql -Title "Table Schema: sip_pauses" -Sql "\d sip_pauses"
Run-Sql -Title "Table Schema: sip_installments" -Sql "\d sip_installments"
Run-Sql -Title "Table Schema: transactions (with sip_installment_id FK)" -Sql "\d transactions"

Run-Sql -Title "SIP Check Constraints & Unique Indexes" -Sql @"
SELECT conname, pg_get_constraintdef(c.oid)
FROM pg_constraint c
JOIN pg_class t ON c.conrelid = t.oid
WHERE t.relname IN ('sips', 'sip_pauses', 'sip_installments', 'transactions')
ORDER BY t.relname, conname;
"@

# ==============================================================================
# SECTION D: API ROUTING & WORKERS
# ==============================================================================
Write-Host "`n--- SECTION D: API Routing & Celery Workers ---" -ForegroundColor Magenta

Run-Step -Title "OpenAPI Filtered Routes for SIPs" -CommandLine "curl.exe -s http://localhost:8000/openapi.json" -Action {
    $openapi = curl.exe -s http://localhost:8000/openapi.json | ConvertFrom-Json
    foreach ($prop in $openapi.paths.PSObject.Properties) {
        $p = $prop.Name
        if ($p -match "sips") {
            foreach ($m in $prop.Value.PSObject.Properties) {
                Write-Host "$($m.Name.ToUpper()) $p"
            }
        }
    }
}

Run-Step -Title "Celery Registered Tasks in Worker Container" -CommandLine "docker compose exec worker celery -A app.workers.celery_app inspect registered" -Action {
    docker compose exec -T worker celery -A app.workers.celery_app inspect registered
}

Run-Step -Title "Celery Beat Schedule Definitions" -CommandLine "docker compose exec api python -c 'import app.workers.beat_schedule...'" -Action {
    docker compose exec -T api python -c "from app.workers.beat_schedule import CELERY_BEAT_SCHEDULE; import pprint; pprint.pprint(CELERY_BEAT_SCHEDULE)"
}

Run-Step -Title "Beat Container Recent Logs" -CommandLine "docker compose logs --tail=30 beat" -Action {
    docker compose logs --tail=30 beat
}

# ==============================================================================
# SECTION E: LIVE END-TO-END THROUGH RUNNING STACK
# ==============================================================================
Write-Host "`n--- SECTION E: Live End-to-End Stack Verification ---" -ForegroundColor Magenta

$user1Timestamp = Get-Date -Format "yyyyMMddHHmmss"
$user1Email = "verify_sip_u1_$user1Timestamp@example.com"
$user2Email = "verify_sip_u2_$user1Timestamp@example.com"
$testPass = "Password123!"

Run-Step -Title "Live E2E: Register User 1 & Create Portfolio" -CommandLine "POST /api/v1/auth/register & POST /api/v1/portfolios" -Action {
    # 1. Register User 1
    $regBody = @{ email = $user1Email; password = $testPass } | ConvertTo-Json
    $regRes = curl.exe -s -X POST http://localhost:8000/api/v1/auth/register -H "Content-Type: application/json" -d $regBody | ConvertFrom-Json
    $global:User1Token = $regRes.data.access_token

    # 2. Create Portfolio
    $portBody = @{ name = "Live SIP Portfolio $user1Timestamp" } | ConvertTo-Json
    $portRes = curl.exe -s -X POST http://localhost:8000/api/v1/portfolios `
        -H "Content-Type: application/json" `
        -H "Authorization: Bearer $global:User1Token" `
        -d $portBody | ConvertFrom-Json
    $global:User1PortfolioId = $portRes.data.id

    Write-Host "Created Portfolio: $global:User1PortfolioId"
}

Run-Step -Title "Live E2E: Preview Schedule for Fund 122639" -CommandLine "POST /api/v1/portfolios/{id}/sips/preview" -Action {
    $previewBody = @{
        scheme_code = 122639
        amount = "1000.00"
        day_of_month = 10
        start_date = "2025-01-05"
        step_up_percent = "0"
    } | ConvertTo-Json

    $previewRes = curl.exe -s -X POST "http://localhost:8000/api/v1/portfolios/$global:User1PortfolioId/sips/preview" `
        -H "Content-Type: application/json" `
        -H "Authorization: Bearer $global:User1Token" `
        -d $previewBody
    Write-Host $previewRes
}

Run-Step -Title "Live E2E: Create SIP on Fund 122639" -CommandLine "POST /api/v1/portfolios/{id}/sips" -Action {
    $sipBody = @{
        scheme_code = 122639
        amount = "1000.00"
        day_of_month = 10
        start_date = "2025-01-05"
        step_up_percent = "0"
    } | ConvertTo-Json

    $sipRes = curl.exe -s -X POST "http://localhost:8000/api/v1/portfolios/$global:User1PortfolioId/sips" `
        -H "Content-Type: application/json" `
        -H "Authorization: Bearer $global:User1Token" `
        -d $sipBody | ConvertFrom-Json
    $global:User1SipId = $sipRes.data.id
    Write-Host "Created SIP: $global:User1SipId with status: $($sipRes.data.status)"
}

Run-Step -Title "Live E2E: Trigger make run-sips" -CommandLine "make run-sips" -Action {
    docker compose exec -T api python -m app.cli run-sips
}

Run-Step -Title "Live E2E: Inspect SIP Installments & Holdings" -CommandLine "GET /sips/{id}/installments & GET /holdings" -Action {
    Write-Host "--- Installments for SIP $global:User1SipId ---"
    $instRes = curl.exe -s "http://localhost:8000/api/v1/portfolios/$global:User1PortfolioId/sips/$global:User1SipId/installments" `
        -H "Authorization: Bearer $global:User1Token"
    Write-Host $instRes

    Write-Host "`n--- Holdings for Portfolio $global:User1PortfolioId ---"
    $holdingsRes = curl.exe -s "http://localhost:8000/api/v1/portfolios/$global:User1PortfolioId/holdings" `
        -H "Authorization: Bearer $global:User1Token"
    Write-Host $holdingsRes
}

Run-Step -Title "Live E2E: Pause and Resume SIP" -CommandLine "POST /pause & POST /resume" -Action {
    Write-Host "--- Pausing SIP ---"
    $pauseRes = curl.exe -s -X POST "http://localhost:8000/api/v1/portfolios/$global:User1PortfolioId/sips/$global:User1SipId/pause" `
        -H "Authorization: Bearer $global:User1Token"
    Write-Host $pauseRes

    Write-Host "`n--- Resuming SIP ---"
    $resumeRes = curl.exe -s -X POST "http://localhost:8000/api/v1/portfolios/$global:User1PortfolioId/sips/$global:User1SipId/resume" `
        -H "Authorization: Bearer $global:User1Token"
    Write-Host $resumeRes
}

Run-Step -Title "Live E2E: Attempt to Modify/Delete Managed Transaction (assert 409)" -CommandLine "PATCH /transactions/{id}" -Action {
    # Check if any transaction has sip_installment_id
    $txnsRes = curl.exe -s "http://localhost:8000/api/v1/portfolios/$global:User1PortfolioId/transactions" `
        -H "Authorization: Bearer $global:User1Token" | ConvertFrom-Json
    $managedTxn = $txnsRes.data.items | Where-Object { $_.sip_installment_id } | Select-Object -First 1

    if ($managedTxn) {
        Write-Host "Found managed transaction: $($managedTxn.id)"
        $patchBody = @{ notes = "Attempted edit" } | ConvertTo-Json
        $patchRes = curl.exe -s -X PATCH "http://localhost:8000/api/v1/portfolios/$global:User1PortfolioId/transactions/$($managedTxn.id)" `
            -H "Content-Type: application/json" `
            -H "Authorization: Bearer $global:User1Token" `
            -d $patchBody
        Write-Host "PATCH response: $patchRes"

        $delRes = curl.exe -s -X DELETE "http://localhost:8000/api/v1/portfolios/$global:User1PortfolioId/transactions/$($managedTxn.id)" `
            -H "Authorization: Bearer $global:User1Token"
        Write-Host "DELETE response: $delRes"
    } else {
        Write-Host "No managed transactions executed yet (fund NAV history may be pending backfill)."
    }
}

Run-Step -Title "Live E2E: User 2 Ownership Isolation (assert 404)" -CommandLine "User 2 attempting User 1 SIP routes" -Action {
    $regBody2 = @{ email = $user2Email; password = $testPass } | ConvertTo-Json
    $regRes2 = curl.exe -s -X POST http://localhost:8000/api/v1/auth/register -H "Content-Type: application/json" -d $regBody2 | ConvertFrom-Json
    $user2Token = $regRes2.data.access_token

    Write-Host "--- User 2 GET User 1 SIPs ---"
    curl.exe -i -s "http://localhost:8000/api/v1/portfolios/$global:User1PortfolioId/sips" `
        -H "Authorization: Bearer $user2Token" | Select-String -Pattern "HTTP|PORTFOLIO_NOT_FOUND"

    Write-Host "--- User 2 POST User 1 SIP Pause ---"
    curl.exe -i -s -X POST "http://localhost:8000/api/v1/portfolios/$global:User1PortfolioId/sips/$global:User1SipId/pause" `
        -H "Authorization: Bearer $user2Token" | Select-String -Pattern "HTTP|PORTFOLIO_NOT_FOUND"
}

# ==============================================================================
# SECTION F: QUALITY GATES
# ==============================================================================
Write-Host "`n--- SECTION F: Quality Gates ---" -ForegroundColor Magenta

Run-Step -Title "Ruff Check" -CommandLine "docker compose exec api ruff check ." -Action {
    docker compose exec -T api uv run ruff check .
}

Run-Step -Title "Ruff Format Check" -CommandLine "docker compose exec api ruff format --check ." -Action {
    docker compose exec -T api uv run ruff format --check .
}

Run-Step -Title "Mypy Strict (App and Tests)" -CommandLine "docker compose exec api mypy --strict app tests" -Action {
    docker compose exec -T api uv run mypy --strict app tests
}

Run-Step -Title "Pytest Collect Only (Test Counts)" -CommandLine "docker compose exec api pytest --collect-only" -Action {
    docker compose exec -T api uv run pytest --collect-only
}

Run-Step -Title "Pytest Full Suite" -CommandLine "docker compose exec api pytest -v" -Action {
    docker compose exec -T api uv run pytest -v
}

Run-Step -Title "Web Lint" -CommandLine "npm --prefix apps/web run lint" -Action {
    npm --prefix apps/web run lint
}

Run-Step -Title "Web Typecheck" -CommandLine "npm --prefix apps/web run typecheck" -Action {
    npm --prefix apps/web run typecheck
}

Run-Step -Title "Vitest Full Suite" -CommandLine "npm --prefix apps/web test" -Action {
    npm --prefix apps/web test
}

Run-Step -Title "Next.js Build with Route Table" -CommandLine "npm --prefix apps/web run build" -Action {
    npm --prefix apps/web run build
}

Run-Step -Title "Make Smoke Test" -CommandLine "make smoke" -Action {
    powershell -ExecutionPolicy Bypass -File scripts/smoke.ps1
}

Run-Step -Title "Make Contract Synchronization" -CommandLine "make contract" -Action {
    docker compose exec -T api python scripts/generate_contract_fixtures.py
}

Run-Step -Title "Git Status Working Tree Cleanliness" -CommandLine "git status --short" -Action {
    git status --short
}

# ==============================================================================
# SECTION G: DISK CHECKS
# ==============================================================================
Write-Host "`n--- SECTION G: Disk & Container Footprint ---" -ForegroundColor Magenta

Run-Step -Title "PowerShell PSDrive C: and D: Available Space" -CommandLine "Get-PSDrive C, D" -Action {
    Get-PSDrive C, D | Select-Object Name, Used, Free, @{Name="FreeGB";Expression={[math]::Round($_.Free/1GB, 2)}}
}

Run-Step -Title "Docker System Disk Footprint" -CommandLine "docker system df" -Action {
    docker system df
}

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "FolioPilot Phase 3B Verification complete." -ForegroundColor Green
Write-Host "Full evidence log saved to: $logFile" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
