# scripts/mutation-check-xirr.ps1
# FolioPilot Phase 5: Mutation Check for XIRR & Valuation Tests
# Evaluates test sensitivity against deliberate mutations:
#   Mutation 1: DAYS_PER_YEAR changed from 365 to 360
#   Mutation 2: DIVIDEND_REINVEST_IS_CASH_FLOW flipped from False to True

$ErrorActionPreference = "Continue"

$DC = if (Get-Command "docker-compose" -ErrorAction SilentlyContinue) { "docker-compose" } else { "docker compose" }

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " FolioPilot Phase 5: XIRR & Valuation Mutation Check    " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

# ==============================================================================
# MUTATION 1: DAYS_PER_YEAR 365 -> 360 in app/core/constants.py
# ==============================================================================
Write-Host "`n>>> [MUTATION 1] DAYS_PER_YEAR: 365 -> 360 in apps/api/app/core/constants.py" -ForegroundColor Yellow
$constantsPath = "apps/api/app/core/constants.py"
$constantsBackup = "$constantsPath.bak"

Copy-Item -Path $constantsPath -Destination $constantsBackup -Force

try {
    $content = Get-Content -Path $constantsPath -Raw
    if ($content -notmatch "DAYS_PER_YEAR:\s*int\s*=\s*365") {
        Write-Error "Could not find DAYS_PER_YEAR = 365 in $constantsPath"
    }
    $mutated = $content -replace "DAYS_PER_YEAR:\s*int\s*=\s*365", "DAYS_PER_YEAR: int = 360"
    Set-Content -Path $constantsPath -Value $mutated -NoNewline

    Write-Host "--- Git Diff for Mutation 1 ---" -ForegroundColor Gray
    git diff --stat $constantsPath
    git diff $constantsPath

    Write-Host "`n--- Running Tests with Mutation 1 (EXPECTED TO FAIL) ---" -ForegroundColor Yellow
    & $DC exec -T api pytest tests/unit/test_xirr.py tests/unit/test_valuation.py
    $mutation1ExitCode = $LASTEXITCODE

    Write-Host "`nMutation 1 Test Exit Code: Expected non-zero (failed) | Actual: $mutation1ExitCode" -ForegroundColor Gray
}
finally {
    Write-Host "`n--- Restoring $constantsPath ---" -ForegroundColor Cyan
    Copy-Item -Path $constantsBackup -Destination $constantsPath -Force
    Remove-Item -Path $constantsBackup -Force

    Write-Host "--- Git Diff after restore (should be empty) ---" -ForegroundColor Gray
    git diff --stat $constantsPath

    Write-Host "`n--- Rerunning Tests after Restore (EXPECTED TO PASS) ---" -ForegroundColor Green
    & $DC exec -T api pytest tests/unit/test_xirr.py tests/unit/test_valuation.py
    $restore1ExitCode = $LASTEXITCODE
    Write-Host "Restored Test Exit Code: Expected 0 (passed) | Actual: $restore1ExitCode" -ForegroundColor Gray
}

# ==============================================================================
# MUTATION 2: DIVIDEND_REINVEST_IS_CASH_FLOW False -> True in app/services/valuation.py
# ==============================================================================
Write-Host "`n>>> [MUTATION 2] DIVIDEND_REINVEST_IS_CASH_FLOW: False -> True in apps/api/app/services/valuation.py" -ForegroundColor Yellow
$valuationPath = "apps/api/app/services/valuation.py"
$valuationBackup = "$valuationPath.bak"

Copy-Item -Path $valuationPath -Destination $valuationBackup -Force

try {
    $content = Get-Content -Path $valuationPath -Raw
    if ($content -notmatch "DIVIDEND_REINVEST_IS_CASH_FLOW:\s*bool\s*=\s*False") {
        Write-Error "Could not find DIVIDEND_REINVEST_IS_CASH_FLOW = False in $valuationPath"
    }
    $mutated = $content -replace "DIVIDEND_REINVEST_IS_CASH_FLOW:\s*bool\s*=\s*False", "DIVIDEND_REINVEST_IS_CASH_FLOW: bool = True"
    Set-Content -Path $valuationPath -Value $mutated -NoNewline

    Write-Host "--- Git Diff for Mutation 2 ---" -ForegroundColor Gray
    git diff --stat $valuationPath
    git diff $valuationPath

    Write-Host "`n--- Running Tests with Mutation 2 (EXPECTED TO FAIL) ---" -ForegroundColor Yellow
    & $DC exec -T api pytest tests/unit/test_valuation.py
    $mutation2ExitCode = $LASTEXITCODE

    Write-Host "`nMutation 2 Test Exit Code: Expected non-zero (failed) | Actual: $mutation2ExitCode" -ForegroundColor Gray
}
finally {
    Write-Host "`n--- Restoring $valuationPath ---" -ForegroundColor Cyan
    Copy-Item -Path $valuationBackup -Destination $valuationPath -Force
    Remove-Item -Path $valuationBackup -Force

    Write-Host "--- Git Diff after restore (should be empty) ---" -ForegroundColor Gray
    git diff --stat $valuationPath

    Write-Host "`n--- Rerunning Tests after Restore (EXPECTED TO PASS) ---" -ForegroundColor Green
    & $DC exec -T api pytest tests/unit/test_valuation.py
    $restore2ExitCode = $LASTEXITCODE
    Write-Host "Restored Test Exit Code: Expected 0 (passed) | Actual: $restore2ExitCode" -ForegroundColor Gray
}

Write-Host "`n========================================================" -ForegroundColor Cyan
Write-Host " Mutation Checks Completed Successfully                " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
