$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

$python = "python"
foreach ($candidate in @(
    (Join-Path $backend ".venv\Scripts\python.exe"),
    (Join-Path $root ".venv\Scripts\python.exe")
)) {
    if (Test-Path $candidate) {
        $python = $candidate
        break
    }
}

function Start-EduService {
    param(
        [string]$Title,
        [string]$WorkDir,
        [string]$Command
    )
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "& { Set-Location '$WorkDir'; $Command }"
    ) | Out-Null
    Write-Host "started: $Title" -ForegroundColor Green
}

Write-Host "EduAgent starting from $root" -ForegroundColor Cyan

Start-EduService "Backend :8000" $backend "& '$python' -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
Start-EduService "Socratic Profiler :8001" $root "& '$python' -m uvicorn external_agents.socratic_profiler.app:app --host 127.0.0.1 --port 8001"
Start-EduService "GRADE Agent :8002" $root "& '$python' -m uvicorn external_agents.grade_agent.app:app --host 127.0.0.1 --port 8002"

$openmaic = Join-Path $root "external_agents\openmaic"
if ((Test-Path (Join-Path $openmaic "package.json")) -and (Get-Command pnpm -ErrorAction SilentlyContinue)) {
    Start-EduService "OpenMAIC :8003" $openmaic "pnpm run dev -- -p 8003"
} else {
    Write-Host "skipped: OpenMAIC (package or pnpm missing)" -ForegroundColor Yellow
}

if (Test-Path (Join-Path $frontend "node_modules")) {
    Start-EduService "Frontend :5173" $frontend "npm run dev -- --host 127.0.0.1 --port 5173"
} else {
    Write-Host "frontend dependencies missing; run: cd frontend; npm install" -ForegroundColor Yellow
}

Write-Host "Open http://127.0.0.1:5173" -ForegroundColor Cyan
