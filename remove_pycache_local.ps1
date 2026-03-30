# Remove __pycache__ from working directory (not git history)
Write-Host "Searching for __pycache__ directories..." -ForegroundColor Cyan
Write-Host ""

Set-Location "c:\test-pfe"

$pycache_dirs = Get-ChildItem -Path . -Filter "__pycache__" -Recurse -Directory -ErrorAction SilentlyContinue

if ($pycache_dirs.Count -eq 0) {
    Write-Host "No __pycache__ directories found!" -ForegroundColor Green
    exit 0
}

Write-Host "Found $($pycache_dirs.Count) __pycache__ directories:" -ForegroundColor Yellow
$pycache_dirs | ForEach-Object { Write-Host "  $($_.FullName)" -ForegroundColor Gray }
Write-Host ""

$confirm = Read-Host "Delete all __pycache__ directories? (Y/N)"

if ($confirm -eq 'Y' -or $confirm -eq 'y') {
    Write-Host ""
    Write-Host "Deleting __pycache__ directories..." -ForegroundColor Yellow
    
    $pycache_dirs | ForEach-Object {
        try {
            Remove-Item -Path $_.FullName -Recurse -Force
            Write-Host "✓ Deleted: $($_.FullName)" -ForegroundColor Green
        } catch {
            Write-Host "✗ Failed to delete: $($_.FullName)" -ForegroundColor Red
            Write-Host "  Error: $_" -ForegroundColor Red
        }
    }
    
    Write-Host ""
    Write-Host "Done! All __pycache__ directories removed." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Cancelled. No files deleted." -ForegroundColor Yellow
}

Write-Host ""
