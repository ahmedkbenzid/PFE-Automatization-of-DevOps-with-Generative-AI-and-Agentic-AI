# Testing GitHub Actions Workflow Generation

This document explains how to test the orchestrator to generate GitHub Actions workflows for any GitHub repository.

## Quick Start

### Method 1: Direct Command (Recommended)

```bash
cd orchestrator-agent

# Generate workflow for a repository
python run_orchestrator.py \
  --github-url "https://github.com/spring-projects/spring-boot" \
  --prompt "Generate a GitHub Actions workflow that tests and builds the project"
```

### Method 2: Python Test Wrapper

```bash
cd orchestrator-agent

# Default (Spring Boot)
python test_gha.py

# Custom repository
python test_gha.py "https://github.com/owner/repo"
```

### Method 3: Bash Script

```bash
cd orchestrator-agent

# Default (Spring Boot)
bash test_gha_generation.sh

# Custom repository
bash test_gha_generation.sh "https://github.com/owner/repo"
```

## How It Works

1. **Repository Analysis (MCP Mode)**
   - Uses GitHub MCP server to analyze the repository
   - Detects: languages, frameworks, build systems, package managers
   - No cloning required - reads via GitHub API
   - Does NOT require Docker (unless you want the full MCP server)

2. **Prompt Analysis**
   - Orchestrator routes to CICD agent for GitHub Actions workflows
   - Analyzes the prompt to understand what the user wants
   - Extracts build/test/deploy requirements

3. **Workflow Generation**
   - CICD agent generates GitHub Actions YAML
   - Uses repository context (languages, frameworks, dependencies)
   - Creates complete workflow with:
     - Dependency installation
     - Build steps
     - Test execution
     - Result reporting

## Example Repositories to Test

### Java/Maven Projects
```bash
python run_orchestrator.py \
  --github-url "https://github.com/spring-projects/spring-boot" \
  --prompt "github actions workflow for maven build and test"
```

### Python Projects
```bash
python run_orchestrator.py \
  --github-url "https://github.com/pallets/flask" \
  --prompt "github actions for python testing"
```

### Node.js Projects
```bash
python run_orchestrator.py \
  --github-url "https://github.com/facebook/react" \
  --prompt "github actions workflow for npm test and build"
```

### Go Projects
```bash
python run_orchestrator.py \
  --github-url "https://github.com/golang/go" \
  --prompt "github actions for go test and build"
```

## Arguments

### Essential Arguments

- **`--prompt`** (string)
  - User's request for workflow generation
  - Examples:
    - "github actions workflow for test and build"
    - "CI/CD pipeline that runs tests and builds docker image"
    - "generate GitHub Actions with maven"

- **`--github-url`** (string)
  - GitHub repository URL to analyze
  - Formats:
    - `https://github.com/owner/repo`
    - `https://github.com/owner/repo.git`
    - `https://github.com/owner/repo/tree/branch`

### Optional Arguments

- **`--output-scope`** (asked | all)
  - `asked`: Show only artifacts mentioned in prompt (default)
  - `all`: Show all generated artifacts (YAML, Dockerfile, Terraform)

- **`--repo-path`** (string)
  - Local repository path (alternative to --github-url)
  - Used for local analysis instead of GitHub API

## Environment Setup

### Required

1. **GROQ_API_KEY** in `orchestrator-agent/.env`
   ```
   GROQ_API_KEY=your_groq_api_key_here
   ```

### Optional (for Phase 2+ features)

1. **GITHUB_TOKEN** in `orchestrator-agent/.env`
   ```
   GITHUB_TOKEN=ghp_your_personal_access_token_here
   ```

2. **GITHUB_PERSONAL_ACCESS_TOKEN** (for MCP Docker mode)
   ```
   GITHUB_PERSONAL_ACCESS_TOKEN=ghp_your_token_here
   ```

## Output

The orchestrator will output:

```
=== Orchestration Summary ===
Status: success

=== Agent Artifacts ===

--- GitHub Actions Workflow (.yaml) ---
name: CI

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up JDK 17
        uses: actions/setup-java@v3
        with:
          java-version: '17'
      ...
```

## Troubleshooting

### "GROQ_API_KEY is not set"
```bash
# Create .env file in orchestrator-agent/
cat > .env << 'EOF'
GROQ_API_KEY=your_key_here
EOF
```

### "Auth error: GITHUB_PERSONAL_ACCESS_TOKEN is not set"
This occurs when using Docker-based MCP server. Option A: Set the token:
```bash
export GITHUB_PERSONAL_ACCESS_TOKEN=your_token_here
```

Option B: Use the fallback (no Docker required):
- The system will attempt to work without the MCP Docker server
- It will use git clone for analysis instead

### "Could not parse GitHub owner/repo from URL"
Ensure the URL format is correct:
- ✓ `https://github.com/spring-projects/spring-boot`
- ✗ `github.com/spring-projects/spring-boot` (missing https://)
- ✗ `https://github.com/spring-projects` (missing repo name)

### "No workflow YAML returned"
- Check that your prompt includes keywords like "github actions", "workflow", "CI/CD", "pipeline"
- Ensure GROQ_API_KEY is set and valid
- Try a more specific prompt: "Generate a GitHub Actions workflow for Maven build"

## Next Steps

After testing GHA generation, you can:

1. **Phase 2**: Add change detection to automatically update workflows when code changes
2. **Phase 3**: Set up GitHub Webhooks to trigger automatic regeneration on push
3. **Phase 4**: Store generated artifacts in SQLite database with version history

See `docs/GITHUB_MCP_SETUP.md` for advanced configuration.
