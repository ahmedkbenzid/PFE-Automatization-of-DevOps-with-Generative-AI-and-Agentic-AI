# Remove __pycache__ from Git History
# Cross-platform PowerShell script

Write-Host "Starting git history cleanup for __pycache__ files..." -ForegroundColor Cyan
Write-Host ""

Set-Location "c:\test-pfe"

Write-Host "Step 1: Check current status" -ForegroundColor Yellow
git status
Write-Host ""

Write-Host "Step 2: Remove __pycache__ from git cache (if currently tracked)" -ForegroundColor Yellow
git rm -r --cached **/__pycache__/ 2>$null
git rm -r --cached **/*.pyc 2>$null
Write-Host ""

Write-Host "Step 3: Remove __pycache__ from git history" -ForegroundColor Yellow
Write-Host "Using BFG Repo Cleaner is recommended for large repos, but using git filter-branch here..." -ForegroundColor Gray
Write-Host ""

# Method 1: Simple removal from index (works if not deeply in history)
Write-Host "Attempting simple cleanup..." -ForegroundColor Gray
git filter-branch --force --index-filter `
    "git rm -r --cached --ignore-unmatch '**/__pycache__/' '**/*.pyc' '**/*.pyo'" `
    --prune-empty --tag-name-filter cat -- --all

Write-Host ""
Write-Host "Step 4: Clean up references" -ForegroundColor Yellow
git for-each-ref --format="%(refname)" refs/original/ | ForEach-Object {
    git update-ref -d $_
}

Write-Host ""
Write-Host "Step 5: Expire reflog and garbage collect" -ForegroundColor Yellow
git reflog expire --expire=now --all
git gc --prune=now --aggressive

Write-Host ""
Write-Host "Step 6: Verify cleanup" -ForegroundColor Yellow
$pycache_files = git ls-files | Select-String -Pattern "__pycache__"
if ($pycache_files) {
    Write-Host "Warning: Some __pycache__ files still found:" -ForegroundColor Red
    $pycache_files
} else {
    Write-Host "Success! No __pycache__ files found in git." -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Cleanup complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "IMPORTANT: If you've already pushed to a remote repository:" -ForegroundColor Yellow
Write-Host "1. Backup your work first" -ForegroundColor White
Write-Host "2. Run: git push origin --force --all" -ForegroundColor White
Write-Host "3. Run: git push origin --force --tags" -ForegroundColor White
Write-Host ""
Write-Host "Note: This rewrites history. Coordinate with your team before force-pushing!" -ForegroundColor Red
Write-Host ""
