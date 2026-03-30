#!/bin/bash
# Remove __pycache__ from Git History
# Works on Linux/Mac/Git Bash on Windows

set -e

echo "========================================="
echo "Git History Cleanup for __pycache__"
echo "========================================="
echo ""

cd "$(dirname "$0")"

# Check if git-filter-repo is available
if command -v git-filter-repo &> /dev/null; then
    echo "✓ git-filter-repo found (recommended method)"
    echo ""
    
    echo "Creating backup..."
    git clone . ../test-pfe-backup
    echo "✓ Backup created at ../test-pfe-backup"
    echo ""
    
    echo "Running git-filter-repo to remove __pycache__..."
    git filter-repo --path-glob '**/__pycache__/**' --invert-paths --force
    git filter-repo --path-glob '**/*.pyc' --invert-paths --force
    
    echo ""
    echo "✓ Cleanup complete with git-filter-repo!"
    
else
    echo "⚠ git-filter-repo not found, using git filter-branch (slower)"
    echo "To install git-filter-repo: pip install git-filter-repo"
    echo ""
    
    echo "Step 1: Remove from current index"
    git rm -r --cached '**/__pycache__/' 2>/dev/null || true
    git rm -r --cached '**/*.pyc' 2>/dev/null || true
    echo "✓ Removed from index"
    echo ""
    
    echo "Step 2: Remove from git history"
    echo "This may take several minutes for large repositories..."
    git filter-branch --force --index-filter \
        "git rm -r --cached --ignore-unmatch '**/__pycache__/' '**/*.pyc' '**/*.pyo'" \
        --prune-empty --tag-name-filter cat -- --all
    echo "✓ Removed from history"
    echo ""
    
    echo "Step 3: Clean up references"
    git for-each-ref --format="%(refname)" refs/original/ | while read ref; do
        git update-ref -d "$ref"
    done
    echo "✓ Cleaned up refs"
    echo ""
    
    echo "Step 4: Garbage collection"
    git reflog expire --expire=now --all
    git gc --prune=now --aggressive
    echo "✓ Garbage collected"
    echo ""
fi

echo "Step 5: Verify cleanup"
if git ls-files | grep -q "__pycache__"; then
    echo "⚠ Warning: Some __pycache__ files still in git"
    git ls-files | grep "__pycache__"
else
    echo "✓ Success! No __pycache__ files in git"
fi
echo ""

echo "Step 6: Update .gitignore"
if ! grep -q "__pycache__" .gitignore 2>/dev/null; then
    echo "__pycache__/" >> .gitignore
    echo "*.pyc" >> .gitignore
    echo "*.pyo" >> .gitignore
    git add .gitignore
    git commit -m "chore: add __pycache__ to .gitignore" || true
    echo "✓ Updated .gitignore"
else
    echo "✓ .gitignore already contains __pycache__"
fi
echo ""

echo "========================================="
echo "Cleanup Complete!"
echo "========================================="
echo ""
echo "Repository size before/after:"
du -sh .git 2>/dev/null || echo "(size check not available)"
echo ""

echo "IMPORTANT NEXT STEPS:"
echo "--------------------"
echo "If you have a remote repository:"
echo ""
echo "  git push origin --force --all"
echo "  git push origin --force --tags"
echo ""
echo "⚠ WARNING: This rewrites history!"
echo "   - Team members need to re-clone or:"
echo "     git fetch origin"
echo "     git reset --hard origin/main"
echo ""
