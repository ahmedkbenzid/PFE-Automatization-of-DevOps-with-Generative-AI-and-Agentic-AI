# Quick Start Guide for CI/CD Agent

## 5-Minute Setup

### 1. Get Groq API Key
```bash
# Visit https://console.groq.com/keys
# Sign up / login
# Copy your API key
```

### 2. Configure Project
```bash
# Create .env file
echo "GROQ_API_KEY=paste_your_key_here" > .env
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Test Dataset Exploration
```bash
python test_pipeline.py
```

## Generate Your First Workflow

### Method 1: Via Python Script

```python
from src.models.types import UserRequest
from src.pipeline import CICDPipeline

pipeline = CICDPipeline()

request = UserRequest(
    text="Generate a workflow that tests Python code with pytest and multiple Python versions"
)

result = pipeline.process_request(request)

if result.success:
    print(result.workflow_yaml)
    # Save to .github/workflows/
```

### Method 2: Using CLI

```bash
# Coming soon - interactive CLI tool
```

## Common Workflows

### Python Project
```python
request = UserRequest(
    text="Test Python project with pytest, coverage, linting (flake8), "
          "and format checking (black) on Python 3.9-3.11"
)
```

### Node.js Project
```python
request = UserRequest(
    text="Test Node.js app on versions 16, 18, 20 with npm, "
          "run linting and build, cache dependencies"
)
```

### Docker Deployment
```python
request = UserRequest(
    text="Build and push Docker image on every push to main with "
          "buildx for multi-architecture support"
)
```

### Full CI/CD Stack
```python
request = UserRequest(
    text="Complete pipeline: test (pytest), build (docker), "
          "deploy to staging on PR, production on main"
)
```

## Troubleshooting

### Error: `GROQ_API_KEY not set`
- Create `.env` file with your API key
- Or set environment variable: `export GROQ_API_KEY=your_key`

### Error: `Invalid YAML generated`
- Pipeline will auto-retry (up to 3 times by default)
- Check error messages - often indentation issues
- Review validation errors in result

### LLM is slow
- Groq API can take 5-15 seconds per request
- This is normal - tradeoff for accuracy
- Consider caching results for repeated patterns

## Output Files

Generated workflows saved in `.github/workflows/`:
- `workflow-name.yml` - The GitHub Actions workflow
- `workflow-name.lock.yml` - Reproducibility lock file
- `workflow-name.metadata.json` - Generation metadata

## Metrics & Monitoring

Check pipeline metrics:
```python
metrics = pipeline.get_metrics()
print(metrics)
# Output:
# {
#   'total_requests': 5,
#   'successful_workflows': 4,
#   'failed_workflows': 1,
#   'success_rate': 0.8,
#   'avg_generation_latency_ms': 8500.0,
#   'avg_attempts': 1.2
# }
```

## Advanced Usage

### With Repository Analysis
```python
result = pipeline.process_request(
    request=request,
    repo_path="./my-repo"  # Analyzes languages, build systems, etc.
)
```

### Custom Retry Policy
```python
result = pipeline.process_request(
    request=request,
    max_retries=5  # Default is 3
)
```

### Strict Security Mode
```python
pipeline = CICDPipeline(strict_security=True)
# Will fail on any security warnings, not just critical issues
```

## Extension Points

### Custom Templates
```python
from src.models.types import WorkflowTemplate

custom = WorkflowTemplate(
    name="My Custom Workflow",
    description="...",
    triggers=["push", "pull_request"],
    jobs={"build": {...}},
)

pipeline.template_manager.add_custom_template("my-template", custom)
```

### Custom Validation Rules
```python
from src.components.schema_validator import SchemaValidator

# Extend SchemaValidator class
class CustomValidator(SchemaValidator):
    def _check_custom_rules(self, workflow):
        # Add custom validation logic
        pass
```

## Next Steps

1. ✅ Run `test_pipeline.py` to verify setup
2. 📖 Read `README.md` for full documentation
3. 🧪 Modify `test_pipeline.py` with your own requests
4. 🚀 Integrate into your project
5. 📊 Monitor metrics in `pipeline.get_metrics()`

## Architecture Visualization

```
User Request (Natural Language)
    ↓
┌─────────────────────────────────┐
│  Intent Layer                   │  Extract intent, keywords
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│  Context Collector              │  Analyze repository
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│  Dataset Manager                │  Find relevant examples
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│  LLM (Groq Mixtral)             │  Generate YAML ↻ Retries
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│  Schema Validator               │  Validate syntax & structure
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│  Security Guardrails            │  Audit for security risks
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│  Workflow Compiler              │  Generate lock file
└─────────────────────────────────┘
    ↓
Generated GitHub Actions Workflow + Lock File
```

## Tips & Tricks

- **For best results,** be specific in your request about:
  - Languages and versions to test
  - Specific frameworks or tools
  - Deployment targets
  - Security requirements

- **Reuse workflows,** store successful ones in templates for faster generation

- **Review security audit,** even if workflow is valid

- **Check metrics,** to track generation quality over time

- **Use lock files,** to ensure reproducibility across teams

---

**Happy workflow generation! 🚀**
