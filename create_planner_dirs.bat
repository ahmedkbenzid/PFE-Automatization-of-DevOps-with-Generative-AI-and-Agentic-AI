@echo off
REM Create planner-agent directory structure

cd /d c:\test-pfe\test_pfe\02-orchestration-agents-layer\planner-agent

mkdir src 2>nul
mkdir src\components 2>nul
mkdir tests 2>nul

echo Planner-agent directory structure created!
echo.
echo Created:
echo   - src/
echo   - src/components/
echo   - tests/
