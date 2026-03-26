#!/bin/bash
# Test GitHub Actions workflow generation for a repository

# Default GitHub URL (Spring Boot project as example)
GITHUB_URL="${1:-https://github.com/spring-projects/spring-boot}"

echo "=========================================="
echo "GitHub Actions Workflow Generator Test"
echo "=========================================="
echo ""
echo "Repository: $GITHUB_URL"
echo ""

# Navigate to orchestrator directory
cd "$(dirname "$0")"

# Generate GitHub Actions workflow (test and build)
python run_orchestrator.py \
  --github-url "$GITHUB_URL" \
  --prompt "Generate a GitHub Actions workflow that tests and builds the project. Include dependency installation, build, and test execution." \
  --output-scope asked

exit_code=$?

echo ""
echo "=========================================="
if [ $exit_code -eq 0 ]; then
    echo "✓ Test completed successfully"
else
    echo "✗ Test failed with exit code: $exit_code"
fi
echo "=========================================="

exit $exit_code
