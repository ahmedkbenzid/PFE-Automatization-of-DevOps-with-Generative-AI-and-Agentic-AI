@echo off
REM Quick Start Script for Streamlit DevOps Orchestrator
REM Windows Batch File

echo ================================================
echo  Multi-Agent DevOps Orchestrator - Quick Start
echo ================================================
echo.

REM Check Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.9+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/5] Checking Python installation...
python --version
echo.

REM Check if virtual environment exists
if not exist venv (
    echo [2/5] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
) else (
    echo [2/5] Virtual environment already exists
)
echo.

REM Activate virtual environment
echo [3/5] Activating virtual environment...
call venv\Scripts\activate.bat
echo.

REM Install dependencies
echo [4/5] Installing Streamlit dependencies...
pip install -r streamlit-requirements.txt --quiet
if errorlevel 1 (
    echo [WARNING] Some dependencies failed to install
    echo Attempting to continue...
)
echo.

REM Install agent dependencies
echo Installing agent dependencies...
cd test_pfe\02-orchestration-agents-layer\orchestrator-agent
pip install -r requirements.txt --quiet
cd ..\..\..

cd test_pfe\02-orchestration-agents-layer\cicd-agent
pip install -r requirements.txt --quiet
cd ..\..\..

cd test_pfe\02-orchestration-agents-layer\docker-agent
pip install -r requirements.txt --quiet
cd ..\..\..

echo.

REM Check for .env file
if not exist .env (
    echo [WARNING] .env file not found!
    echo.
    echo Creating template .env file...
    echo # Multi-Agent DevOps Orchestrator Configuration > .env
    echo # >> .env
    echo # Required: GROQ API Key >> .env
    echo GROQ_API_KEY=your_groq_api_key_here >> .env
    echo # >> .env
    echo # Optional: GitHub Token for PR creation >> .env
    echo GITHUB_TOKEN= >> .env
    echo # >> .env
    echo # Optional: LLM Configuration >> .env
    echo LLM_PROVIDER=ollama >> .env
    echo OLLAMA_MODEL=glm-5:cloud >> .env
    echo LLM_TEMPERATURE=0.3 >> .env
    echo LLM_MAX_TOKENS=3000 >> .env
    echo.
    echo [ACTION REQUIRED] Please edit .env file and add your GROQ_API_KEY
    echo Get your API key from: https://console.groq.com
    echo.
    pause
)

REM Launch Streamlit
echo [5/5] Launching Streamlit app...
echo.
echo ================================================
echo  Opening browser at http://localhost:8501
echo  Press Ctrl+C to stop the server
echo ================================================
echo.

streamlit run app.py

pause
