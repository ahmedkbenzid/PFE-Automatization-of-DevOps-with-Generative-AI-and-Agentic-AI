@echo off
cd /d c:\test-pfe
echo Checking git status...
git status
echo.
echo Listing tracked __pycache__ files...
git ls-files | findstr /i __pycache__
echo.
echo Removing __pycache__ from git cache...
git rm -r --cached **/__pycache__/ 2>nul
git rm --cached **/*.pyc 2>nul
echo.
echo Removing from git history...
git filter-branch --force --index-filter "git rm -r --cached --ignore-unmatch **/__pycache__/ **/*.pyc **/*.pyo" --prune-empty --tag-name-filter cat -- --all
echo.
echo Cleaning up references...
for /f "tokens=*" %%i in ('git for-each-ref --format="%(refname)" refs/original/') do git update-ref -d %%i
echo.
echo Garbage collecting...
git reflog expire --expire=now --all
git gc --prune=now --aggressive
echo.
echo Verification...
git ls-files | findstr /i __pycache__
echo.
echo DONE! If output above is empty, cleanup succeeded.
echo.
echo IMPORTANT: Run these commands to push:
echo   git push origin --force --all
echo   git push origin --force --tags
