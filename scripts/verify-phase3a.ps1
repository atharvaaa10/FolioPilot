# scripts/verify-phase3a.ps1
# FolioPilot Phase 3A: Comprehensive Verification Script
param(
    [switch]$IncludeGuardTest
)

$ErrorActionPreference = "Continue"

$evidenceDir = "E:\USER\Projects\_evidence"
if (-not (Test-Path $evidenceDir)) {
    New-Item -ItemType Directory -Path $evidenceDir -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logFile = Join-Path $evidenceDir "verify-phase3a-$timestamp.txt"

Write-Host "FolioPilot Phase 3A Verification running..." -ForegroundColor Cyan
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
# SECTION A: GIT
# ==============================================================================
Write-Host "`n--- SECTION A: Git Repository State ---" -ForegroundColor Magenta

Run-Step -Title "Git Status Short" -CommandLine "git status --short" -Action {
    git status --short
}

Run-Step -Title "Git Current HEAD" -CommandLine "git rev-parse HEAD" -Action {
    git rev-parse HEAD
}

Run-Step -Title "Git Branches" -CommandLine "git branch -a" -Action {
    git branch -a
}

Run-Step -Title "Git Remotes" -CommandLine "git remote -v" -Action {
    git remote -v
}

Run-Step -Title "Git Recent Commits Log" -CommandLine "git log --oneline --all --graph -30" -Action {
    git log --oneline --all --graph -30
}

Run-Step -Title "Git Reflog Recent" -CommandLine "git reflog -40" -Action {
    git reflog -40
}

Run-Step -Title "Git Reflog origin/main" -CommandLine "git reflog show origin/main" -Action {
    git reflog show origin/main
}

Run-Step -Title "Git Check Historical Hashes" -CommandLine "git cat-file -t cb4d129 8aebe7b 3165ae4 837ddaa 4ad4e82 9d8b809" -Action {
    $hashes = @("cb4d129", "8aebe7b", "3165ae4", "837ddaa", "4ad4e82", "9d8b809")
    foreach ($h in $hashes) {
        $t = git cat-file -t $h 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "$h : $t"
        } else {
            Write-Host "$h : missing"
        }
    }
}

Run-Step -Title "Git Line Endings (EOL) for Scripts and Dockerfiles" -CommandLine "git ls-files --eol" -Action {
    git ls-files --eol | Select-String -Pattern "\.sh|Dockerfile|Makefile"
}

# ==============================================================================
# SECTION B: DATABASE SCHEMA & DATA DISTRIBUTION
# ==============================================================================
Write-Host "`n--- SECTION B: Database Schema & Distribution ---" -ForegroundColor Magenta

Run-Sql -Title "Table Schema: funds" -Sql "\d funds"
Run-Sql -Title "Table Schema: nav_history" -Sql "\d nav_history"
Run-Sql -Title "Table Schema: portfolios" -Sql "\d portfolios"
Run-Sql -Title "Table Schema: portfolio_targets" -Sql "\d portfolio_targets"
Run-Sql -Title "Table Schema: transactions" -Sql "\d transactions"

Run-Sql -Title "Funds Distribution by Asset Class and Source" `
    -Sql "SELECT asset_class, classification_source, count(*) FROM funds GROUP BY asset_class, classification_source ORDER BY asset_class, classification_source;"

Run-Sql -Title "Funds Distribution by Canonical Sub Category" `
    -Sql "SELECT sub_category, count(*) FROM funds GROUP BY sub_category ORDER BY count(*) DESC;"

# Facts and Regression Funds expected-vs-actual comparison
Run-Sql -Title "Facts and 18 Regression Funds Expected vs Actual" -Sql @"
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
    substring(f.category_raw from 1 for 25) AS category_raw,
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

Run-Sql -Title "30 Random Gold Funds" `
    -Sql "SELECT scheme_code, substring(name from 1 for 40) AS name, asset_class, sub_category FROM funds WHERE asset_class = 'gold' ORDER BY random() LIMIT 30;"

Run-Sql -Title "All Bank of India Funds" `
    -Sql "SELECT scheme_code, substring(name from 1 for 40) AS name, category_raw, asset_class, sub_category FROM funds WHERE name ILIKE '%Bank of India%' ORDER BY scheme_code;"

Run-Sql -Title "Other/Unknown Funds Grouped by Category Raw" `
    -Sql "SELECT category_raw, count(*) FROM funds WHERE asset_class = 'other' AND sub_category = 'unknown' GROUP BY category_raw ORDER BY count(*) DESC;"

Run-Sql -Title "Fund 122639 Latest NAV and History Points" `
    -Sql "SELECT h.nav_date, h.nav, f.latest_nav, f.latest_nav_date FROM nav_history h JOIN funds f ON f.scheme_code = h.scheme_code WHERE f.scheme_code = 122639 ORDER BY h.nav_date DESC LIMIT 3;"

Run-Sql -Title "Max Decimal Places Observed in NAV Values" `
    -Sql "SELECT max(length(split_part(latest_nav::text, '.', 2))) AS max_dec_latest_nav FROM funds;"

Run-Sql -Title "Count of Distinct category_raw Values" `
    -Sql "SELECT count(DISTINCT category_raw) AS distinct_categories FROM funds;"

Run-Sql -Title "Tracked Funds vs Funds with Historical NAV Records" `
    -Sql "SELECT (SELECT count(DISTINCT scheme_code) FROM nav_history) AS funds_with_history, (SELECT count(*) FROM funds WHERE is_tracked = true) AS tracked_funds;"

Run-Sql -Title "Last 5 NAV Sync Runs" `
    -Sql "SELECT id, status, schemes_parsed, schemes_upserted, created_at, finished_at FROM nav_sync_runs ORDER BY id DESC LIMIT 5;"

# ==============================================================================
# SECTION C: SYNC-NAV IDEMPOTENCY & LOCKING
# ==============================================================================
Write-Host "`n--- SECTION C: NAV Sync Triggering ---" -ForegroundColor Magenta

Run-Step -Title "Trigger First NAV Sync (make sync-nav)" -CommandLine "make sync-nav" -Action {
    docker compose exec api python -m app.cli sync-nav
}
Run-Sql -Title "Last 3 Sync Runs After Run 1" -Sql "SELECT id, status, schemes_parsed, schemes_upserted, created_at FROM nav_sync_runs ORDER BY id DESC LIMIT 3;"

Run-Step -Title "Trigger Second NAV Sync (make sync-nav)" -CommandLine "make sync-nav" -Action {
    docker compose exec api python -m app.cli sync-nav
}
Run-Sql -Title "Last 3 Sync Runs After Run 2" -Sql "SELECT id, status, schemes_parsed, schemes_upserted, created_at FROM nav_sync_runs ORDER BY id DESC LIMIT 3;"

# ==============================================================================
# SECTION D: API CONTRACT & HEADERS
# ==============================================================================
Write-Host "`n--- SECTION D: API Contract & Routing ---" -ForegroundColor Magenta

Run-Step -Title "OpenAPI Filtered Routes (Portfolios, Funds, NAV)" -CommandLine "curl.exe -s http://localhost:8000/openapi.json" -Action {
    $openapi = curl.exe -s http://localhost:8000/openapi.json | ConvertFrom-Json
    foreach ($prop in $openapi.paths.PSObject.Properties) {
        $p = $prop.Name
        if ($p -match "portfolios|funds|nav") {
            foreach ($m in $prop.Value.PSObject.Properties) {
                Write-Host "$($m.Name.ToUpper()) $p"
            }
        }
    }
}

Run-Step -Title "Celery Registered Tasks in Worker Container" -CommandLine "docker compose exec worker celery -A app.workers.celery_app inspect registered" -Action {
    docker compose exec -T worker celery -A app.workers.celery_app inspect registered
}

Run-Step -Title "GET /api/v1/nav/status" -CommandLine "curl.exe -s http://localhost:8000/api/v1/nav/status" -Action {
    curl.exe -s http://localhost:8000/api/v1/nav/status
}

Run-Step -Title "GET /api/v1/health/ready (with headers)" -CommandLine "curl.exe -i -s http://localhost:8000/api/v1/health/ready" -Action {
    curl.exe -i -s http://localhost:8000/api/v1/health/ready
}

Run-Step -Title "CORS Preflight OPTIONS /api/v1/users/me" -CommandLine "curl.exe -i -s -X OPTIONS http://localhost:8000/api/v1/users/me" -Action {
    curl.exe -i -s -X OPTIONS http://localhost:8000/api/v1/users/me `
        -H "Origin: http://localhost:3000" `
        -H "Access-Control-Request-Method: GET" `
        -H "Access-Control-Request-Headers: authorization,content-type"
}

# Register fresh user to test actual CORS request and response headers
# Clear test registration rate limits in Redis so back-to-back verification runs never get blocked
docker compose exec -T redis redis-cli EVAL "for _,k in ipairs(redis.call('keys','rl:reg_ip*')) do redis.call('del',k) end" 0 2>$null | Out-Null

$rnd = Get-Random -Minimum 100000 -Maximum 999999
$emailA = "verify_user_a_$rnd@example.com"
$pwdA = "SuperSecret123!"

$regRespRaw = curl.exe -s -X POST http://localhost:8000/api/v1/auth/register `
    -H "Content-Type: application/json" `
    -d "{\`"email\`": \`"$emailA\`", \`"password\`": \`"$pwdA\`"}"

Run-Step -Title "Register Fresh User A (Raw Body)" -CommandLine "curl.exe -s -X POST http://localhost:8000/api/v1/auth/register" -Action {
    $regRespRaw
}

$regResp = $regRespRaw | ConvertFrom-Json
$tokenA = $regResp.data.access_token

Run-Step -Title "GET /api/v1/users/me with Origin and Auth Token" -CommandLine "curl.exe -i -s http://localhost:8000/api/v1/users/me" -Action {
    curl.exe -i -s http://localhost:8000/api/v1/users/me `
        -H "Origin: http://localhost:3000" `
        -H "Authorization: Bearer $tokenA"
}

Run-Step -Title "Request returning 404 (Assert X-Request-ID present)" -CommandLine "curl.exe -i -s http://localhost:8000/api/v1/nonexistent-route" -Action {
    curl.exe -i -s http://localhost:8000/api/v1/nonexistent-route
}

# ==============================================================================
# SECTION E: END-TO-END LEDGER WITH FUND 122639
# ==============================================================================
Write-Host "`n--- SECTION E: End-to-End Ledger Flow ---" -ForegroundColor Magenta

# Register User B
$emailB = "verify_user_b_$rnd@example.com"
$regRespB = curl.exe -s -X POST http://localhost:8000/api/v1/auth/register `
    -H "Content-Type: application/json" `
    -d "{\`"email\`": \`"$emailB\`", \`"password\`": \`"$pwdA\`"}" | ConvertFrom-Json
$tokenB = $regRespB.data.access_token

$hAuthA = @{
    "Authorization" = "Bearer $tokenA"
    "Content-Type" = "application/json"
}

# 1. User A creates portfolio
$createPortResp = curl.exe -s -w "`nHTTP %{http_code}`n" -X POST http://localhost:8000/api/v1/portfolios `
    -H "Authorization: Bearer $tokenA" `
    -H "Content-Type: application/json" `
    -d "{\`"name\`": \`"Verification Portfolio\`", \`"description\`": \`"Phase 3A E2E test\`"}"
Run-Step -Title "Create Portfolio for User A" -CommandLine "POST /portfolios" -Action { $createPortResp }

$portfolioId = ($createPortResp -split "`n")[0] | ConvertFrom-Json | Select-Object -ExpandProperty data | Select-Object -ExpandProperty id

# 2. PUT targets 60/30/10
Run-Step -Title "Configure Target Allocations 60/30/10" -CommandLine "PUT /portfolios/$portfolioId/targets" -Action {
    curl.exe -s -w "`nHTTP %{http_code}`n" -X PUT "http://localhost:8000/api/v1/portfolios/$portfolioId/targets" `
        -H "Authorization: Bearer $tokenA" `
        -H "Content-Type: application/json" `
        -d "{\`"targets\`": [{\`"asset_class\`": \`"equity\`", \`"target_pct\`": \`"60.00\`"}, {\`"asset_class\`": \`"debt\`", \`"target_pct\`": \`"30.00\`"}, {\`"asset_class\`": \`"gold\`", \`"target_pct\`": \`"10.00\`"}]}"
}

# 3. PUT targets 33.33/33.33/33.33 (expect 422 TARGETS_INVALID)
Run-Step -Title "PUT Targets Invalid Sum (33.33 * 3 = 99.99)" -CommandLine "PUT /portfolios/$portfolioId/targets (expect 422)" -Action {
    curl.exe -s -w "`nHTTP %{http_code}`n" -X PUT "http://localhost:8000/api/v1/portfolios/$portfolioId/targets" `
        -H "Authorization: Bearer $tokenA" `
        -H "Content-Type: application/json" `
        -d "{\`"targets\`": [{\`"asset_class\`": \`"equity\`", \`"target_pct\`": \`"33.33\`"}, {\`"asset_class\`": \`"debt\`", \`"target_pct\`": \`"33.33\`"}, {\`"asset_class\`": \`"gold\`", \`"target_pct\`": \`"33.33\`"}]}"
}

# 4. POST buy 2025-01-10 units 100 nav 50 amount 5000
$rBuy1 = curl.exe -s -w "`nHTTP %{http_code}`n" -X POST "http://localhost:8000/api/v1/portfolios/$portfolioId/transactions" `
    -H "Authorization: Bearer $tokenA" `
    -H "Content-Type: application/json" `
    -d "{\`"scheme_code\`": 122639, \`"txn_type\`": \`"buy\`", \`"txn_date\`": \`"2025-01-10\`", \`"units\`": \`"100.0000\`", \`"nav\`": \`"50.00000000\`", \`"amount\`": \`"5000.00\`"}"
Run-Step -Title "Add Buy Txn 1: 100 units @ 50 on 2025-01-10" -CommandLine "POST /transactions (buy 1)" -Action { $rBuy1 }
$t1Id = ($rBuy1 -split "`n")[0] | ConvertFrom-Json | Select-Object -ExpandProperty data | Select-Object -ExpandProperty id

# 5. POST buy 2025-02-10 units 50 nav 60 amount 3000
$rBuy2 = curl.exe -s -w "`nHTTP %{http_code}`n" -X POST "http://localhost:8000/api/v1/portfolios/$portfolioId/transactions" `
    -H "Authorization: Bearer $tokenA" `
    -H "Content-Type: application/json" `
    -d "{\`"scheme_code\`": 122639, \`"txn_type\`": \`"buy\`", \`"txn_date\`": \`"2025-02-10\`", \`"units\`": \`"50.0000\`", \`"nav\`": \`"60.00000000\`", \`"amount\`": \`"3000.00\`"}"
Run-Step -Title "Add Buy Txn 2: 50 units @ 60 on 2025-02-10" -CommandLine "POST /transactions (buy 2)" -Action { $rBuy2 }
$t2Id = ($rBuy2 -split "`n")[0] | ConvertFrom-Json | Select-Object -ExpandProperty data | Select-Object -ExpandProperty id

# 6. POST sell 2025-03-10 units 30 nav 70 amount 2100
$rSell1 = curl.exe -s -w "`nHTTP %{http_code}`n" -X POST "http://localhost:8000/api/v1/portfolios/$portfolioId/transactions" `
    -H "Authorization: Bearer $tokenA" `
    -H "Content-Type: application/json" `
    -d "{\`"scheme_code\`": 122639, \`"txn_type\`": \`"sell\`", \`"txn_date\`": \`"2025-03-10\`", \`"units\`": \`"30.0000\`", \`"nav\`": \`"70.00000000\`", \`"amount\`": \`"2100.00\`"}"
Run-Step -Title "Add Sell Txn 3: 30 units @ 70 on 2025-03-10" -CommandLine "POST /transactions (sell 1)" -Action { $rSell1 }

# 7. GET holdings: compare with worked example expected numbers
Run-Step -Title "GET Holdings and Assert Calculated Position" -CommandLine "GET /portfolios/$portfolioId/holdings" -Action {
    $raw = curl.exe -s "http://localhost:8000/api/v1/portfolios/$portfolioId/holdings" -H "Authorization: Bearer $tokenA"
    Write-Host "Raw holdings response: $raw"
    $obj = $raw | ConvertFrom-Json
    $item = $obj.data.items[0]

    Write-Host "`n--- Holdings Expected vs Actual Comparison ---"
    $metrics = @(
        [PSCustomObject]@{ Metric = "units"; Expected = "120.0000"; Actual = $item.units },
        [PSCustomObject]@{ Metric = "cost_basis"; Expected = "6400.00"; Actual = $item.cost_basis },
        [PSCustomObject]@{ Metric = "avg_cost"; Expected = "53.3333"; Actual = $item.avg_cost },
        [PSCustomObject]@{ Metric = "total_bought"; Expected = "8000.00"; Actual = $item.total_bought },
        [PSCustomObject]@{ Metric = "total_sold"; Expected = "2100.00"; Actual = $item.total_sold },
        [PSCustomObject]@{ Metric = "txn_count"; Expected = 3; Actual = $item.txn_count },
        [PSCustomObject]@{ Metric = "first_txn_date"; Expected = "2025-01-10"; Actual = $item.first_txn_date },
        [PSCustomObject]@{ Metric = "last_txn_date"; Expected = "2025-03-10"; Actual = $item.last_txn_date },
        [PSCustomObject]@{ Metric = "has_amc"; Expected = $true; Actual = ($null -ne $item.fund.amc) },
        [PSCustomObject]@{ Metric = "has_plan_type"; Expected = $true; Actual = ($null -ne $item.fund.plan_type) },
        [PSCustomObject]@{ Metric = "has_option_type"; Expected = $true; Actual = ($null -ne $item.fund.option_type) },
        [PSCustomObject]@{ Metric = "has_latest_nav"; Expected = $true; Actual = ($null -ne $item.fund.latest_nav) },
        [PSCustomObject]@{ Metric = "has_latest_nav_date"; Expected = $true; Actual = ($null -ne $item.fund.latest_nav_date) }
    )
    $metrics | Format-Table -AutoSize
}

# 8. Try to sell 121 units (expect 409 INSUFFICIENT_UNITS)
Run-Step -Title "Overdraft: Sell 121 Units on 2025-03-11 (Expect 409 INSUFFICIENT_UNITS)" -CommandLine "POST /transactions (121 units)" -Action {
    curl.exe -s -w "`nHTTP %{http_code}`n" -X POST "http://localhost:8000/api/v1/portfolios/$portfolioId/transactions" `
        -H "Authorization: Bearer $tokenA" `
        -H "Content-Type: application/json" `
        -d "{\`"scheme_code\`": 122639, \`"txn_type\`": \`"sell\`", \`"txn_date\`": \`"2025-03-11\`", \`"units\`": \`"121.0000\`", \`"nav\`": \`"70.00000000\`", \`"amount\`": \`"8470.00\`"}"
}

# 9. Add sell of 100 units on 2025-04-10 (HTTP 201)
$rSell2 = curl.exe -s -w "`nHTTP %{http_code}`n" -X POST "http://localhost:8000/api/v1/portfolios/$portfolioId/transactions" `
    -H "Authorization: Bearer $tokenA" `
    -H "Content-Type: application/json" `
    -d "{\`"scheme_code\`": 122639, \`"txn_type\`": \`"sell\`", \`"txn_date\`": \`"2025-04-10\`", \`"units\`": \`"100.0000\`", \`"nav\`": \`"70.00000000\`", \`"amount\`": \`"7000.00\`"}"
Run-Step -Title "Add Sell Txn 4: 100 units on 2025-04-10 (Leaves 20 units)" -CommandLine "POST /transactions (sell 2)" -Action { $rSell2 }
$t4Id = ($rSell2 -split "`n")[0] | ConvertFrom-Json | Select-Object -ExpandProperty data | Select-Object -ExpandProperty id

# 10. Try deleting the first buy (expect 409 LEDGER_INCONSISTENT with date 2025-04-10)
Run-Step -Title "Delete First Buy (Expect 409 LEDGER_INCONSISTENT due to downstream oversell)" -CommandLine "DELETE /transactions/$t1Id" -Action {
    curl.exe -s -w "`nHTTP %{http_code}`n" -X DELETE "http://localhost:8000/api/v1/portfolios/$portfolioId/transactions/$t1Id" `
        -H "Authorization: Bearer $tokenA"
}

# 11. PATCH second buy notes (200)
Run-Step -Title "PATCH Second Buy Notes (HTTP 200)" -CommandLine "PATCH /transactions/$t2Id" -Action {
    curl.exe -s -w "`nHTTP %{http_code}`n" -X PATCH "http://localhost:8000/api/v1/portfolios/$portfolioId/transactions/$t2Id" `
        -H "Authorization: Bearer $tokenA" `
        -H "Content-Type: application/json" `
        -d "{\`"notes\`": \`"Updated investment notes\`"}"
}

# 12. PATCH second buy units to 10 (expect 409 LEDGER_INCONSISTENT)
Run-Step -Title "PATCH Second Buy Units to 10 (Expect 409 LEDGER_INCONSISTENT)" -CommandLine "PATCH /transactions/$t2Id (units=10)" -Action {
    curl.exe -s -w "`nHTTP %{http_code}`n" -X PATCH "http://localhost:8000/api/v1/portfolios/$portfolioId/transactions/$t2Id" `
        -H "Authorization: Bearer $tokenA" `
        -H "Content-Type: application/json" `
        -d "{\`"units\`": \`"10.0000\`"}"
}

# 13. Delete the 100-unit sell (success 204)
Run-Step -Title "Delete 100-Unit Sell (HTTP 204)" -CommandLine "DELETE /transactions/$t4Id" -Action {
    curl.exe -s -w "`nHTTP %{http_code}`n" -X DELETE "http://localhost:8000/api/v1/portfolios/$portfolioId/transactions/$t4Id" `
        -H "Authorization: Bearer $tokenA"
}

# 14. Delete first buy again (now succeeds because 50 bought and 30 sold stays >= 0)
Run-Step -Title "Delete First Buy Again (HTTP 204 Success Now)" -CommandLine "DELETE /transactions/$t1Id" -Action {
    curl.exe -s -w "`nHTTP %{http_code}`n" -X DELETE "http://localhost:8000/api/v1/portfolios/$portfolioId/transactions/$t1Id" `
        -H "Authorization: Bearer $tokenA"
}

# 15. GET holdings: units 20.0000, cost_basis 1200.00, avg_cost 60.0000
Run-Step -Title "GET Holdings After Deletions (20 units @ avg 60.0000)" -CommandLine "GET /portfolios/$portfolioId/holdings" -Action {
    $raw = curl.exe -s "http://localhost:8000/api/v1/portfolios/$portfolioId/holdings" -H "Authorization: Bearer $tokenA"
    $obj = $raw | ConvertFrom-Json
    $item = $obj.data.items[0]

    $metrics = @(
        [PSCustomObject]@{ Metric = "units"; Expected = "20.0000"; Actual = $item.units },
        [PSCustomObject]@{ Metric = "cost_basis"; Expected = "1200.00"; Actual = $item.cost_basis },
        [PSCustomObject]@{ Metric = "avg_cost"; Expected = "60.0000"; Actual = $item.avg_cost }
    )
    $metrics | Format-Table -AutoSize
}

# 16. User B attempts access to User A's resources (Ownership 404 rule)
Run-Step -Title "User B Queries User A Portfolio (Expect 404 PORTFOLIO_NOT_FOUND)" -CommandLine "GET /portfolios/$portfolioId (as User B)" -Action {
    curl.exe -s -w "`nHTTP %{http_code}`n" "http://localhost:8000/api/v1/portfolios/$portfolioId" -H "Authorization: Bearer $tokenB"
}
Run-Step -Title "User B Queries User A Holdings (Expect 404 PORTFOLIO_NOT_FOUND)" -CommandLine "GET /portfolios/$portfolioId/holdings (as User B)" -Action {
    curl.exe -s -w "`nHTTP %{http_code}`n" "http://localhost:8000/api/v1/portfolios/$portfolioId/holdings" -H "Authorization: Bearer $tokenB"
}
Run-Step -Title "User B Queries User A Transaction (Expect 404 PORTFOLIO_NOT_FOUND)" -CommandLine "GET /portfolios/$portfolioId/transactions/$t2Id (as User B)" -Action {
    curl.exe -s -w "`nHTTP %{http_code}`n" "http://localhost:8000/api/v1/portfolios/$portfolioId/transactions/$t2Id" -H "Authorization: Bearer $tokenB"
}

# 17. Inspect transaction response for lowercase txn_type and field names txn_type, txn_date
Run-Step -Title "Transaction Response Fields and Lowercase txn_type" -CommandLine "GET /portfolios/$portfolioId/transactions" -Action {
    curl.exe -s "http://localhost:8000/api/v1/portfolios/$portfolioId/transactions" -H "Authorization: Bearer $tokenA"
}

# ==============================================================================
# SECTION F: QUALITY GATES & SMOKE
# ==============================================================================
Write-Host "`n--- SECTION F: Quality Gates ---" -ForegroundColor Magenta

Run-Step -Title "Backend Linter (Ruff check)" -CommandLine "docker compose exec api uv run ruff check app tests" -Action {
    docker compose exec -T api uv run ruff check app tests
}

Run-Step -Title "Backend Formatter (Ruff format --check)" -CommandLine "docker compose exec api uv run ruff format --check app tests" -Action {
    docker compose exec -T api uv run ruff format --check app tests
}

Run-Step -Title "Backend Typecheck (Mypy strict)" -CommandLine "docker compose exec api uv run mypy --strict app tests" -Action {
    docker compose exec -T api uv run mypy --strict app tests
}

Run-Step -Title "Pytest Collect Only" -CommandLine "docker compose exec api uv run pytest --collect-only -q" -Action {
    docker compose exec -T api uv run pytest --collect-only -q | Select-Object -Last 5
}

Run-Step -Title "Pytest Execution" -CommandLine "docker compose exec api uv run pytest -q" -Action {
    docker compose exec -T api uv run pytest -q | Select-Object -Last 15
}

Run-Step -Title "Frontend Linter (npm run lint)" -CommandLine "npm --prefix apps/web run lint" -Action {
    npm --prefix apps/web run lint
}

Run-Step -Title "Frontend Typecheck (npm run typecheck)" -CommandLine "npm --prefix apps/web run typecheck" -Action {
    npm --prefix apps/web run typecheck
}

Run-Step -Title "Frontend Unit & Integration Tests (vitest verbose)" -CommandLine "npm --prefix apps/web run test -- --reporter=verbose" -Action {
    npm --prefix apps/web run test -- --reporter=verbose
}

Run-Step -Title "Frontend Next.js Build" -CommandLine "npm --prefix apps/web run build" -Action {
    npm --prefix apps/web run build
}

Run-Step -Title "Smoke Test Script (make smoke)" -CommandLine "make smoke" -Action {
    powershell -ExecutionPolicy Bypass -File scripts/smoke.ps1
}

# ==============================================================================
# SECTION G: OPTIONAL DRIFT GUARD TEST
# ==============================================================================
if ($IncludeGuardTest) {
    Write-Host "`n--- SECTION G: Destructive Drift Guard Repair Test ---" -ForegroundColor Magenta

    Run-Step -Title "Web Dependency Drift Repair Test" -CommandLine "Simulate drift in web container" -Action {
        Write-Host "Simulating missing dependency in web container..."
        docker compose exec -T web rm -rf /app/node_modules/react-hook-form
        docker compose exec -T web sh -c 'echo "corrupted-hash" > /app/node_modules/.lock-hash'
        Write-Host "Restarting web container..."
        docker compose restart web
        Start-Sleep -Seconds 10
        Write-Host "Last 40 lines of web container logs:"
        docker compose logs --tail=40 web
        Write-Host "Running smoke check to verify auto-repair restored web container:"
        powershell -ExecutionPolicy Bypass -File scripts/smoke.ps1
    }

    Run-Step -Title "API Dependency Drift Repair Test" -CommandLine "Simulate drift in api container" -Action {
        Write-Host "Simulating corrupt lock hash in api container..."
        docker compose exec -T api sh -c 'echo "corrupted-hash" > /app/.venv/.lock-hash'
        Write-Host "Restarting api container..."
        docker compose restart api
        Start-Sleep -Seconds 5
        Write-Host "Last 40 lines of api container logs:"
        docker compose logs --tail=40 api
        Write-Host "Testing Python imports in restored environment:"
        docker compose exec -T api python -c "import jwt, argon2; print('Python dependencies intact: jwt and argon2 import successfully')"
    }
}

# ==============================================================================
# SECTION H: DISK HEALTH & USAGE
# ==============================================================================
Write-Host "`n--- SECTION H: Disk & Docker Usage ---" -ForegroundColor Magenta

Run-Step -Title "Host Drive Free Space (C: and D:)" -CommandLine "Get-PSDrive C, D" -Action {
    Get-PSDrive C, D | Select-Object Name, @{Name="Used(GB)";Expression={[math]::round($_.Used/1GB,2)}}, @{Name="Free(GB)";Expression={[math]::round($_.Free/1GB,2)}}
}

Run-Step -Title "Docker Disk Usage" -CommandLine "docker system df" -Action {
    docker system df
}

Run-Step -Title "WSL Virtual Disk Size (docker_data.vhdx)" -CommandLine "Get-Item D:\DockerDesktopWSL\disk\docker_data.vhdx" -Action {
    Get-Item "D:\DockerDesktopWSL\disk\docker_data.vhdx" | Select-Object FullName, @{Name="Size(GB)";Expression={[math]::round($_.Length/1GB,2)}}
}

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "FolioPilot Phase 3A Verification Completed." -ForegroundColor Green
Write-Host "Evidence log written to:" -ForegroundColor Green
Write-Host "$logFile" -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Green

