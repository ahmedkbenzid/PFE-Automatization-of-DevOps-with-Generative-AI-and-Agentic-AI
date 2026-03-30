@echo off
REM Remove __pycache__ files from git history
echo Starting git history cleanup for __pycache__ files...
echo.

cd /d c:\test-pfe

echo Step 1: Check current status
git status
echo.

echo Step 2: Remove __pycache__ from git cache (if currently tracked)
git rm -r --cached **/__pycache__/ 2>nul
git rm -r --cached **/*.pyc 2>nul
echo.

echo Step 3: Remove __pycache__ from git history using filter-branch
echo This may take a few minutes...
git filter-branch --force --index-filter "git rm -r --cached --ignore-unmatch **/__pycache__/" --prune-empty --tag-name-filter cat -- --all
echo.

echo Step 4: Clean up references
git for-each-ref --format="%(refname)" refs/original/ | ForEach-Object { git update-ref -d $_ }
echo.

echo Step 5: Expire reflog and garbage collect
git reflog expire --expire=now --all
git gc --prune=now --aggressive
echo.

echo Step 6: Commit .gitignore update (if needed)
git add .gitignore
git commit -m "chore: update .gitignore to exclude __pycache__" 2>nul
echo.

echo ========================================
echo Cleanup complete!
echo ========================================
echo.
echo IMPORTANT: If you've already pushed to a remote repository:
echo 1. Backup your work first
echo 2. Run: git push origin --force --all
echo 3. Run: git push origin --force --tags
echo.
echo Note: This rewrites history. Coordinate with your team before force-pushing!
echo.

pause
