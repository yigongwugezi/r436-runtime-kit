$root = "D:\EduAgent"

Write-Host "=== EduAgent Start ===" -ForegroundColor Green

# Load env
Get-Content "$root\.env" | ForEach-Object {
    $line = $_.Trim()
    if ($line -and ($line[0] -ne '#') -and $line.Contains('=')) {
        $parts = $line.Split('=', 2)
        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
}

# Pass to DeepTutor
[Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $env:LLM_API_KEY, 'Process')
[Environment]::SetEnvironmentVariable('OPENAI_BASE_URL', $env:LLM_BASE_URL, 'Process')
[Environment]::SetEnvironmentVariable('DEEPTUTOR_HOME', "$root\runtime_data", 'Process')

Write-Host ""
Write-Host "Starting 7 services in new windows:" -ForegroundColor Cyan
Write-Host "  1. DeepTutor          :8000"
Write-Host "  2. Socratic Profiler  :8001"
Write-Host "  3. GRADE Agent        :8002"
Write-Host "  4. OpenMAIC           :8003"
Write-Host "  5. OpenClaw           :8400"
Write-Host "  6. Backend            :8080"
Write-Host "  7. Frontend           :5173"

Start-Process powershell -ArgumentList '-NoExit -Command "cd D:\EduAgent; .\.venv\Scripts\activate; python scripts\run_deeptutor.py"'
Start-Process powershell -ArgumentList '-NoExit -Command "cd D:\EduAgent; .\.venv\Scripts\activate; python -m uvicorn external_agents.socratic_profiler.app:app --host 0.0.0.0 --port 8001"'
Start-Process powershell -ArgumentList '-NoExit -Command "cd D:\EduAgent; .\.venv\Scripts\activate; python -m uvicorn external_agents.grade_agent.app:app --host 0.0.0.0 --port 8002"'
Start-Process powershell -ArgumentList '-NoExit -Command "cd D:\EduAgent\external_agents\openmaic; npm run dev -- -p 8003"'
Start-Process powershell -ArgumentList '-NoExit -Command "cd D:\EduAgent\external_agents\openclaw_workspace; node server.js"'
Start-Process powershell -ArgumentList '-NoExit -Command "cd D:\EduAgent\backend; ..\venv\Scripts\activate; python -m uvicorn app.main:app --host 0.0.0.0 --port 8080"'
Start-Process powershell -ArgumentList '-NoExit -Command "cd D:\EduAgent\frontend; npm run dev"'

Write-Host ""
Write-Host "Done. Open http://localhost:5173" -ForegroundColor Green
