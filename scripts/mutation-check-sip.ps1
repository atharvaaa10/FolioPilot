# scripts/mutation-check-sip.ps1
# FolioPilot Phase 3B: Concurrency SIP executor row-lock verification script
# Demonstrates behavior when installment row-lock (re-select FOR UPDATE) is removed,
# and deterministic consistency with row-lock restored.

$ErrorActionPreference = "Continue"

$svcPath = "apps/api/app/services/sip_executor.py"
$bakPath = "apps/api/app/services/sip_executor.py.bak"

Write-Host "=========================================================="
Write-Host "FolioPilot SIP Executor Mutation Lock Verification"
Write-Host "=========================================================="

if (-not (Test-Path $svcPath)) {
    Write-Error "Cannot locate $svcPath. Run from repository root."
    exit 1
}

# (a) Back up sip_executor.py
Write-Host "`n[Step 1] Backing up $svcPath to $bakPath..."
Copy-Item -Path $svcPath -Destination $bakPath -Force

try {
    # (b) Mutate: replace get_installment_for_update with get_installment_by_id (remove installment row lock)
    Write-Host "`n[Step 2] Removing installment row-level lock (replacing get_installment_for_update with get_installment_by_id)..."
    $content = Get-Content -Path $svcPath -Raw
    $mutated = $content -replace "SipRepository\.get_installment_for_update", "SipRepository.get_installment_by_id"
    Set-Content -Path $svcPath -Value $mutated -NoNewline

    Write-Host "Diff of mutated service:"
    git diff --stat -- $svcPath

    # (c) Run concurrent executor test 10 times WITHOUT installment row lock
    Write-Host "`n[Step 3] Running test_idempotent_execution_and_concurrent_skip 10 times WITHOUT installment row lock..."
    for ($i = 1; $i -le 10; $i++) {
        Write-Host "`n--- Iteration $i / 10 (WITHOUT INSTALLMENT LOCK) ---"
        docker compose exec api uv run pytest tests/integration/test_sips_api.py -k test_idempotent_execution_and_concurrent_skip
    }
}
finally {
    # (d) ALWAYS restore file from backup
    Write-Host "`n[Step 4] Restoring original sip_executor.py..."
    if (Test-Path $bakPath) {
        Copy-Item -Path $bakPath -Destination $svcPath -Force
        Remove-Item -Path $bakPath -Force
        Write-Host "Restoration complete."
    }
}

# (e) Run concurrent test 10 times WITH installment row lock restored
Write-Host "`n[Step 5] Running test_idempotent_execution_and_concurrent_skip 10 times WITH installment row lock RESTORED..."
for ($i = 1; $i -le 10; $i++) {
    Write-Host "`n--- Iteration $i / 10 (WITH INSTALLMENT LOCK RESTORED) ---"
    docker compose exec api uv run pytest tests/integration/test_sips_api.py -k test_idempotent_execution_and_concurrent_skip
}

# (f) Verify git diff proves nothing is left over
Write-Host "`n[Step 6] Verifying working tree cleanliness for $svcPath..."
git diff --stat -- $svcPath
Write-Host "`nSIP mutation check complete."
