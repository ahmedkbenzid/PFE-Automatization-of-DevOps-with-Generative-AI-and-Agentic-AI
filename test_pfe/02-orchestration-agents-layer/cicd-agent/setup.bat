@echo off
REM CI/CD Agent - Windows Initialization Script

echo.
echo ========================================
echo CI/CD Agent Setup
echo ========================================
echo.

REM Check if .env exists
if not exist .env (
    echo Creating .env from .env.example...
    copy .env.example .env
    echo.
    echo NOTE: Edit .env and add your GROQ_API_KEY
    echo Get it from: https://console.groq.com/keys
    echo.
)

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Please install Python 3.9+
    exit /b 1
)

echo Python: 
python --version

REM Check if venv exists
if not exist venv (
    echo.
    echo Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
) else (
    call venv\Scripts\activate.bat
)

echo.
echo Installing dependencies...
pip install -r requirements.txt

echo.
echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo To test the pipeline, run:
echo   python test_pipeline.py
echo.
