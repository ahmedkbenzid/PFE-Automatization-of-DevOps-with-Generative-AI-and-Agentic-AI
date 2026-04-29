# Startup script for Orchestrator Platform
# Usage: .\start-dev.ps1

# Set execution policy for this session
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process -Force

# Activate virtual environment
Write-Host "[*] Activating virtual environment..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1

Write-Host "`n[+] Starting Orchestrator Platform (Dev Mode)`n" -ForegroundColor Green

# Create signal file directory if it doesn't exist
if (-not (Test-Path ".orchestrator-cwd")) {
    New-Item -ItemType Directory -Path ".orchestrator-cwd" | Out-Null
    Write-Host "[OK] Created .orchestrator-cwd directory" -ForegroundColor Green
}

# Check if backend dependencies are installed
$fastapiInstalled = pip list | Select-String "fastapi"
if (-not $fastapiInstalled) {
    Write-Host "[*] Installing backend dependencies..." -ForegroundColor Yellow
    pip install -r backend/requirements.txt
    Write-Host "[OK] Backend dependencies installed" -ForegroundColor Green
}

# Check if frontend dependencies are installed
if (-not (Test-Path "frontend/node_modules")) {
    Write-Host "[*] Installing frontend dependencies..." -ForegroundColor Yellow
    cd frontend
    npm install
    cd ..
    Write-Host "[OK] Frontend dependencies installed" -ForegroundColor Green
}

Write-Host "`n=====================================================" -ForegroundColor Cyan

# Start backend in a new window
Write-Host "`n[*] Starting FastAPI backend on port 8000..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd '$PWD'; & .\.venv\Scripts\Activate.ps1; python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000"
)
Start-Sleep -Seconds 2

# Start frontend in a new window
Write-Host "[*] Starting Angular frontend on port 4200..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd '$PWD/frontend'; & ..\.venv\Scripts\Activate.ps1; npm start"
)

Write-Host "`n=====================================================" -ForegroundColor Cyan
Write-Host "`n[OK] Both servers should start in new windows...`n" -ForegroundColor Green

Write-Host "[+] URLs:" -ForegroundColor Cyan
Write-Host "    Frontend:  http://localhost:4200" -ForegroundColor White
Write-Host "    Backend:   http://localhost:8000" -ForegroundColor White
Write-Host "    API Docs:  http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "[+] Tips:" -ForegroundColor Cyan
Write-Host "    - Check browser console (F12) for any errors" -ForegroundColor White
Write-Host "    - Backend logs show in first new window" -ForegroundColor White
Write-Host "    - Frontend logs show in second new window" -ForegroundColor White
Write-Host "    - Changes auto-reload in both servers" -ForegroundColor White
Write-Host ""
