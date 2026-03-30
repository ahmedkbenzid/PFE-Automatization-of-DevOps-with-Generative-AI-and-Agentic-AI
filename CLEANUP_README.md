# ✅ Git History Cleanup - Remove __pycache__ Files

I've created comprehensive scripts to remove `__pycache__` files from your git commit history.

## 📦 Files Created

1. **`cleanup_pycache.bat`** - Windows batch script
2. **`cleanup_pycache.ps1`** - PowerShell script (cross-platform)
3. **`cleanup_pycache.sh`** - Bash script (Linux/Mac/Git Bash)
4. **`GIT_CLEANUP_GUIDE.md`** - Detailed documentation

## 🚀 Quick Start

### Windows Users

**Option 1: Double-click**
```
cleanup_pycache.bat
```

**Option 2: PowerShell**
```powershell
.\cleanup_pycache.ps1
```

### Linux/Mac/Git Bash Users
```bash
chmod +x cleanup_pycache.sh
./cleanup_pycache.sh
```

## 🔧 What the Scripts Do

1. **Remove from index**: Untrack __pycache__ files currently in git
2. **Remove from history**: Use git filter-branch to purge from all commits
3. **Clean up refs**: Remove backup references
4. **Garbage collect**: Reclaim disk space
5. **Verify**: Check that cleanup succeeded
6. **Update .gitignore**: Ensure future prevention

## ⚠️ Important Warnings

### This Rewrites History!

- **Backup first**: `git clone . ../backup`
- **Coordinate with team**: Everyone needs to know
- **Force push required**: After cleanup, you must force push
- **Team must re-sync**: Others need to re-clone or hard reset

### Commands to Run After Cleanup

If you have a remote repository:

```bash
# Push the cleaned history
git push origin --force --all
git push origin --force --tags
```

### For Team Members

After you force push, team members need to:

```bash
git fetch origin
git reset --hard origin/main
# Or simply re-clone:
# git clone <repo-url>
```

## 🎯 What Gets Removed

- All `__pycache__/` directories
- All `*.pyc` files  
- All `*.pyo` files
- All `*.pyd` files

## ✅ Current Status

Your `.gitignore` already includes:
```
__pycache__/
*.pyc
*.pyo
*.pyd
```

So future commits won't track these files.

## 📊 Better Alternative: git-filter-repo

For large repositories, use `git-filter-repo` (faster and safer):

### Install
```bash
pip install git-filter-repo
```

### Usage
```bash
# Backup first!
git clone . ../backup

# Remove __pycache__ from history
git filter-repo --path-glob '**/__pycache__/**' --invert-paths --force
git filter-repo --path-glob '**/*.pyc' --invert-paths --force

# Force push
git push origin --force --all
```

## 🔍 Verification

After running the cleanup:

```bash
# Should return nothing
git ls-files | grep __pycache__

# Check repo size reduction
du -sh .git
```

## 🆘 Troubleshooting

### Issue: "refusing to update checked out branch"
```bash
git checkout --orphan temp
git branch -D main  
git branch -m main
```

### Issue: Still seeing __pycache__ in working directory
```bash
# These are local files, not in git
# Remove them:
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null

# Windows:
Get-ChildItem -Path . -Filter __pycache__ -Recurse -Directory | Remove-Item -Recurse -Force
```

### Issue: Team member getting conflicts
```bash
git fetch origin
git reset --hard origin/main
# This discards local changes - commit/stash first!
```

## 📝 Manual Method

If scripts don't work, run manually:

```bash
# 1. Remove from index
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

# 4. Force push
git push origin --force --all
git push origin --force --tags
```

## 🎁 Benefits

After cleanup:
- ✅ Smaller repository size
- ✅ Cleaner git history
- ✅ Faster clones
- ✅ No binary cache pollution

## 📚 Resources

- [Git Filter-Repo Documentation](https://github.com/newren/git-filter-repo)
- [BFG Repo-Cleaner](https://rtyley.github.io/bfg-repo-cleaner/)
- [Git Documentation - Rewriting History](https://git-scm.com/book/en/v2/Git-Tools-Rewriting-History)

---

**Ready to clean?** Run one of the scripts above! 🧹
