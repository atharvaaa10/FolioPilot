# scripts/mutation-check-import.ps1
# FolioPilot Phase 4: Import Commit Concurrency & Row-Lock Mutation Verification Script
# Demonstrates behavior when portfolio and import row-locks (FOR UPDATE) are removed,
# and deterministic serialization with row-locks restored.

$ErrorActionPreference = "Continue"

$svcPath = "apps/api/app/services/import_service.py"
$bakPath = "apps/api/app/services/import_service.py.bak"

$DC = if (Get-Command "docker-compose" -ErrorAction SilentlyContinue) { "docker-compose" } else { "docker compose" }

Write-Host "=========================================================="
Write-Host "FolioPilot Import Commit Mutation Lock Verification"
Write-Host "=========================================================="

if (-not (Test-Path $svcPath)) {
    Write-Error "Cannot locate $svcPath. Run from repository root."
    exit 1
}

# (a) Back up import_service.py
Write-Host "`n[Step 1] Backing up $svcPath to $bakPath..."
Copy-Item -Path $svcPath -Destination $bakPath -Force

try {
    # (b) Mutate: replace get_for_update with non-locking get_by_id in commit()
    Write-Host "`n[Step 2] Removing row-level locks (replacing get_for_update with non-locking lookups)..."
    $content = Get-Content -Path $svcPath -Raw
    $mutated = $content -replace "PortfolioRepository\.get_for_update", "PortfolioRepository.get_by_id"
    $mutated = $mutated -replace "ImportRepository\.get_for_update", "ImportRepository.get_by_id"
    Set-Content -Path $svcPath -Value $mutated -NoNewline

    Write-Host "Diff of mutated service:"
    git diff --stat -- $svcPath

    # (c) Run concurrent commit test 5 times WITHOUT row lock
    Write-Host "`n[Step 3] Running test_concurrency_double_commit 5 times WITHOUT row locks..."
    for ($i = 1; $i -le 5; $i++) {
        Write-Host "`n--- Iteration $i / 5 (WITHOUT ROW LOCKS) ---"
        & $DC exec -T api pytest tests/integration/test_imports_api.py -k test_concurrency_double_commit -v
    }
}
finally {
    # (d) ALWAYS restore file from backup
    Write-Host "`n[Step 4] Restoring original import_service.py..."
    if (Test-Path $bakPath) {
        Copy-Item -Path $bakPath -Destination $svcPath -Force
        Remove-Item -Path $bakPath -Force
        Write-Host "Restoration complete."
    }
}

# (e) Run concurrent test 5 times WITH row locks restored
Write-Host "`n[Step 5] Running test_concurrency_double_commit 5 times WITH ROW LOCKS RESTORED..."
for ($i = 1; $i -le 5; $i++) {
    Write-Host "`n--- Iteration $i / 5 (WITH ROW LOCKS RESTORED) ---"
    & $DC exec -T api pytest tests/integration/test_imports_api.py -k test_concurrency_double_commit -v
}

# (f) Verify git diff proves nothing is left over
Write-Host "`n[Step 6] Verifying working tree cleanliness for $svcPath..."
git diff --stat -- $svcPath
Write-Host "`nImport mutation check complete."
