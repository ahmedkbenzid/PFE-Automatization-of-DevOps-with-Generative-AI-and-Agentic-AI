# Quick Git Cleanup for __pycache__

This repository contains scripts to remove `__pycache__` files from git history.

## Quick Start

### Option 1: Batch Script (Windows)
```bash
cleanup_pycache.bat
```

### Option 2: PowerShell Script (Cross-platform)
```powershell
.\cleanup_pycache.ps1
```

### Option 3: Manual Commands

```bash
# 1. Remove from current index
git rm -r --cached **/__pycache__/
git rm -r --cached **/*.pyc

# 2. Remove from history
git filter-branch --force --index-filter \
  "git rm -r --cached --ignore-unmatch '**/__pycache__/' '**/*.pyc'" \
  --prune-empty --tag-name-filter cat -- --all

# 3. Clean up
git for-each-ref --format="%(refname)" refs/original/ | xargs -n 1 git update-ref -d
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# 4. Force push (if already pushed to remote)
git push origin --force --all
git push origin --force --tags
```

## Alternative: Using BFG Repo-Cleaner (Recommended for Large Repos)

BFG is faster and safer than `git filter-branch`:

```bash
# 1. Download BFG
# Visit: https://rtyley.github.io/bfg-repo-cleaner/

# 2. Run BFG
java -jar bfg.jar --delete-folders __pycache__ .

# 3. Clean up
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# 4. Force push
git push --force
```

## What Gets Removed

- All `__pycache__/` directories
- All `*.pyc` files
- All `*.pyo` files

## Safety Notes

⚠️ **WARNING: This rewrites git history!**

- Backup your repository first
- Coordinate with your team
- All contributors need to re-clone or rebase
- Use `--force` push carefully

## Verification

After cleanup, verify:
```bash
git ls-files | grep __pycache__
# Should return nothing
```

## .gitignore

Make sure your `.gitignore` includes:
```
__pycache__/
*.pyc
*.pyo
*.pyd
```

## Troubleshooting

### "refusing to update checked out branch"
```bash
git checkout --orphan temp
git branch -D main
git branch -m main
```

### Still seeing __pycache__ after cleanup
```bash
# They may be in working directory (not git)
find . -type d -name "__pycache__" -exec rm -rf {} +
```

### Team members getting conflicts
They need to:
```bash
git fetch origin
git reset --hard origin/main
```
