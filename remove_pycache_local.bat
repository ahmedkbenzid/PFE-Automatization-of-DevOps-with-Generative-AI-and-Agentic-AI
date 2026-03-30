@echo off
REM Find and remove __pycache__ directories from working directory (not git)
echo Searching for __pycache__ directories...
echo.

cd /d c:\test-pfe

echo Found __pycache__ directories:
for /f "delims=" %%i in ('dir /s /b /ad __pycache__ 2^>nul') do (
    echo %%i
)

echo.
set /p confirm="Delete all __pycache__ directories? (Y/N): "

if /i "%confirm%"=="Y" (
    echo.
    echo Deleting __pycache__ directories...
    for /f "delims=" %%i in ('dir /s /b /ad __pycache__ 2^>nul') do (
        rmdir /s /q "%%i"
        echo Deleted: %%i
    )
    echo.
    echo Done! All __pycache__ directories removed.
) else (
    echo.
    echo Cancelled. No files deleted.
)

echo.
pause
