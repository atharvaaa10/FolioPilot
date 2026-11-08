$ErrorActionPreference = "Stop"

Write-Host "Running FolioPilot smoke check..." -ForegroundColor Cyan

# Check 1: Backend Readiness
Write-Host "[1/3] Checking API readiness (http://localhost:8000/api/v1/health/ready)..."
try {
    $apiResp = & curl.exe -s -w "`n%{http_code}" http://localhost:8000/api/v1/health/ready
    $lines = $apiResp -split "`n"
    $statusCode = $lines[-1].Trim()
    $body = ($lines[0..($lines.Length - 2)] -join "`n").Trim()

    if ($statusCode -ne "200") {
        Write-Error "API health check failed with HTTP status ${statusCode}. Body: ${body}"
        exit 1
    }

    if ($body -notmatch '"status"\s*:\s*"ready"') {
        Write-Error "API response does not contain '\"status\": \"ready\"'. Response: ${body}"
        exit 1
    }
    Write-Host "      API is ready (HTTP 200, status=ready)." -ForegroundColor Green
} catch {
    Write-Error "Failed to connect to API: $_"
    exit 1
}

# Check 2: Web Frontend Routes
$routes = @("/", "/login", "/register", "/dashboard", "/funds")
Write-Host "[2/3] Checking Web frontend routes..."
foreach ($route in $routes) {
    $url = "http://localhost:3000$route"
    try {
        $webResp = & curl.exe -s -w "`n%{http_code}" $url
        $lines = $webResp -split "`n"
        $statusCode = $lines[-1].Trim()
        $html = ($lines[0..($lines.Length - 2)] -join "`n")

        if ($statusCode -ne "200") {
            Write-Error "Web route ${route} failed with HTTP status ${statusCode}"
            exit 1
        }

        # Check for build error signatures in HTML
        if ($html -match "Build Error" -or $html -match "Module not found" -or $html -match "Application error") {
            Write-Error "Web route ${route} contains build/runtime error banner in HTML!"
            exit 1
        }
        Write-Host "      ${route} -> HTTP 200 (Clean HTML)" -ForegroundColor Green
    } catch {
        Write-Error "Failed to reach web route ${route}. Error: $_"
        exit 1
    }
}

# Check 3: Web Container Logs
Write-Host "[3/3] Inspecting last 100 lines of web container logs..."
try {
    $logs = & docker compose logs web --tail=100 2>&1
    $logText = $logs -join "`n"

    if ($logText -match "Module not found" -or $logText -match "Build Error") {
        Write-Error "Web container logs contain module/build errors in last 100 lines!"
        exit 1
    }
    Write-Host "      Web container logs clean." -ForegroundColor Green
} catch {
    Write-Error "Failed to inspect docker logs: $_"
    exit 1
}

Write-Host "Smoke check PASSED successfully!" -ForegroundColor Green
exit 0
