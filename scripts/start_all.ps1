Write-Host "EduAgent Start (6 services)" -ForegroundColor Green

$root = "D:\EduAgent"

# DeepTutor
Start-Process powershell -ArgumentList "-NoExit -Command & {cd $root; .\venv\Scripts\activate; python scripts\run_deeptutor.py}"

# Socratic Profiler
Start-Process powershell -ArgumentList "-NoExit -Command & {cd $root; .\venv\Scripts\activate; python -m uvicorn external_agents.socratic_profiler.app:app --host 0.0.0.0 --port 8001}"

# GRADE Agent
Start-Process powershell -ArgumentList "-NoExit -Command & {cd $root; .\venv\Scripts\activate; python -m uvicorn external_agents.grade_agent.app:app --host 0.0.0.0 --port 8002}"

# OpenMAIC
Start-Process powershell -ArgumentList "-NoExit -Command & {cd $root\external_agents\openmaic; pnpm run dev -- -p 8003}"

# Backend
Start-Process powershell -ArgumentList "-NoExit -Command & {cd $root\backend; ..\venv\Scripts\activate; python -m uvicorn app.main:app --host 0.0.0.0 --port 8080}"

# Frontend
Start-Process powershell -ArgumentList "-NoExit -Command & {cd $root\frontend; npm run dev}"

Write-Host "Done. http://localhost:5173" -ForegroundColor Green
