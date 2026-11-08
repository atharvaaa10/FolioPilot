# scripts/mutation-check-lock.ps1
# FolioPilot Phase 3A: Concurrency row-lock verification script
# Demonstrates race condition failure without pessimistic row-lock,
# and deterministic consistency with row-lock restored.

$ErrorActionPreference = "Continue"

$svcPath = "apps/api/app/services/transaction_service.py"
$bakPath = "apps/api/app/services/transaction_service.py.bak"

Write-Host "=========================================================="
Write-Host "FolioPilot Ledger Mutation Lock Verification"
Write-Host "=========================================================="

if (-not (Test-Path $svcPath)) {
    Write-Error "Cannot locate $svcPath. Run from repository root."
    exit 1
}

# (a) Back up transaction_service.py
Write-Host "`n[Step 1] Backing up $svcPath to $bakPath..."
Copy-Item -Path $svcPath -Destination $bakPath -Force

try {
    # (b) Mutate: replace get_for_update with get_by_id (remove row lock)
    Write-Host "`n[Step 2] Removing row-level lock (replacing get_for_update with get_by_id)..."
    $content = Get-Content -Path $svcPath -Raw
    $mutated = $content -replace "PortfolioRepository\.get_for_update", "PortfolioRepository.get_by_id"
    Set-Content -Path $svcPath -Value $mutated -NoNewline

    Write-Host "Diff of mutated service:"
    git diff --stat -- $svcPath

    # (c) Run concurrent test 10 times WITHOUT row lock
    Write-Host "`n[Step 3] Running test_concurrent_transactions_acquire_lock_safely 10 times WITHOUT row lock..."
    for ($i = 1; $i -le 10; $i++) {
        Write-Host "`n--- Iteration $i / 10 (WITHOUT LOCK) ---"
        docker compose exec api uv run pytest tests/integration/test_transactions_api.py -k test_concurrent_transactions_acquire_lock_safely
    }
}
finally {
    # (d) ALWAYS restore file from backup
    Write-Host "`n[Step 4] Restoring original transaction_service.py..."
    if (Test-Path $bakPath) {
        Copy-Item -Path $bakPath -Destination $svcPath -Force
        Remove-Item -Path $bakPath -Force
        Write-Host "Restoration complete."
    }
}

# (e) Run concurrent test 10 times WITH row lock restored
Write-Host "`n[Step 5] Running test_concurrent_transactions_acquire_lock_safely 10 times WITH row lock RESTORED..."
for ($i = 1; $i -le 10; $i++) {
    Write-Host "`n--- Iteration $i / 10 (WITH LOCK RESTORED) ---"
    docker compose exec api uv run pytest tests/integration/test_transactions_api.py -k test_concurrent_transactions_acquire_lock_safely
}

# (f) Verify git diff proves nothing is left over
Write-Host "`n[Step 6] Verifying working tree cleanliness for $svcPath..."
git diff --stat -- $svcPath
Write-Host "`nMutation lock check complete."

