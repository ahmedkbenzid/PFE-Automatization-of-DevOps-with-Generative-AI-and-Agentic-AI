# CI/CD Agent - GitHub Actions Workflow Generator

Complete implementation of a CI/CD agent that generates GitHub Actions workflows using the Groq LLM API. This project implements the full pipeline architecture shown in the design specification.

## Architecture Overview

### Components

1. **Intent Layer** - Extracts user intent and builds metadata using markdown builder
2. **Context Collector** - Analyzes repository to detect languages, build systems, frameworks
3. **LLM Client** - Integration with Groq API for intelligent workflow generation
4. **Template Manager** - Manages workflow templates and GitHub Actions schemas
5. **YAML Generator** - Generates and validates GitHub Actions YAML
6. **Schema Validator** - Validates workflows against GitHub Actions specifications
7. **Security Guardrails** - Performs security audits and enforces best practices
8. **Workflow Compiler** - Compiles workflows and generates reproducible lock files
9. **GitHub Integration** - Handles PR creation, commits, and workflow management

### Datasets

The agent leverages three key datasets:

1. **gha-dataset** - Collection of 10k real GitHub Actions workflows from popular repositories
2. **GitHub Actions Workflow Histories** - 100k execution records with success/failure metrics
3. **EBAMIC** - 5k workflows migrated from Jenkins, Travis CI, CircleCI, etc.

## Installation

### Prerequisites

- Python 3.9+
- Groq API key (get from https://console.groq.com/keys)

### Setup

```bash
# Clone repository
cd cicd-agent

# Install dependencies
pip install -r requirements.txt

# Configure Groq API
cp .env.example .env
# Edit .env and add your GROQ_API_KEY
```

## Usage

### Basic Workflow Generation

```python
from src.models.types import UserRequest, RequestType
from src.pipeline import CICDPipeline

# Create pipeline
pipeline = CICDPipeline()

# Create a user request
request = UserRequest(
    text="Generate a Python testing workflow with pytest and multiple Python versions",
    request_type=RequestType.CREATE_WORKFLOW
)

# Process request
result = pipeline.process_request(request)

# Access generated workflow
if result.success:
    print(result.workflow_yaml)
```

### Running Test Suite

```bash
# Run example tests
python test_pipeline.py
```

### With Repository Analysis

```python
# Analyze a real repository
result = pipeline.process_request(
    request=request,
    repo_path="/path/to/repo"  # Optional: provides context
)
```

## Pipeline Workflow

```
User Request (NL)
    ↓
[1] Intent Layer → Extract intent, keywords, request type
    ↓
[2] Context Collector → Detect languages, build systems
    ↓
[3] Dataset Manager → Find relevant examples
    ↓
[4] Template Manager + LLM → Generate YAML (with retries)
    ↓
[5] Schema Validator → Validate GitHub Actions syntax
    ↓
[6] Security Guardrails → Audit for security risks
    ↓
[7] Workflow Compiler → Generate lock file for reproducibility
    ↓
Generated Workflow YAML + Lock File + Metadata
```

## Features

### ✓ Intelligent Generation
- Uses Groq LLM (Mixtral 8x7b) for high-quality workflows
- Leverages dataset examples for better context
- Extracts intent from natural language requests

### ✓ Comprehensive Validation
- GitHub Actions syntax validation
- Schema validation against official spec
- Best practices checking
- Performance suggestions

### ✓ Security-First
- Security audit with risk identification
- Detection of dangerous patterns
- Safe action verification
- Secret exposure detection

### ✓ Reproducibility
- Lock file generation for deterministic execution
- Checksum validation
- Dependency tracking

### ✓ GitHub Integration
- PR creation support
- Commit workflow changes
- Workflow dispatch support
- Action usage statistics

### ✓ Metrics & Monitoring
- Generation latency tracking
- Success rate calculation
- Attempt counting
- Dataset statistics

## Configuration

### Environment Variables

```env
# Required
GROQ_API_KEY=your_api_key

# Optional (for GitHub integration)
GITHUB_TOKEN=your_github_token
GITHUB_REPO_OWNER=owner
GITHUB_REPO_NAME=repo
```

### Pipeline Configuration

Edit `src/config.py`:

```python
# LLM Settings
GROQ_MODEL = "mixtral-8x7b-32768"  # Available: mixtral-8x7b, llama2-70b
GROQ_MAX_TOKENS = 2048
GROQ_TEMPERATURE = 0.3

# Pipeline Settings
MAX_RETRIES = 3
ENABLE_SCHEMA_VALIDATION = True
ENABLE_SECURITY_CHECK = True
```

## Metrics

The pipeline tracks:

- **Syntax validity rate** - % of workflows passing actionlint
- **Pipeline execution success rate** - Runs without human edits
- **Generation latency** - Time to generate workflow (ms)
- **Avg attempts to first successful run** - Number of retries needed

## Examples

### Generate Python Testing Workflow

```
Input: "Run pytest tests on Python 3.9 and 3.11 with dependency caching"

Output: A complete GitHub Actions workflow that:
- Checks out code
- Sets up Python with caching
- Installs dependencies
- Runs pytest with coverage
```

### Generate Docker Build & Push

```
Input: "Build and push Docker image on every push to main"

Output: A workflow that:
- Checks out code
- Sets up Docker buildx
- Builds multi-architecture images
- Pushes to registry
```

### Migrate from Jenkins

```
Input: "I have a Jenkins pipeline, convert it to GitHub Actions"

Output: Converted workflow using EBAMIC dataset patterns
```

## Project Structure

```
cicd-agent/
├── src/
│   ├── config.py                 # Configuration
│   ├── pipeline.py               # Main pipeline
│   ├── components/
│   │   ├── llm_client.py        # Groq LLM integration
│   │   ├── intent_layer.py      # Intent extraction
│   │   ├── context_collector.py # Repository analysis
│   │   ├── template_manager.py  # Template management
│   │   ├── yaml_generator.py    # YAML generation
│   │   ├── schema_validator.py  # Validation
│   │   ├── security_guardrails.py # Security
│   │   ├── workflow_compiler.py # Compilation
│   │   └── github_integration.py # GitHub API
│   ├── models/
│   │   └── types.py             # Data types
│   └── datasets/
│       └── dataset_manager.py   # Dataset management
├── test_pipeline.py             # Test suite
├── requirements.txt             # Dependencies
├── .env.example                 # Environment template
└── README.md                    # This file
```

## Design Decisions

### LLM Choice: Groq API
- **Why?** Fast inference, good quality, easy integration
- **Model:** Mixtral 8x7b-32768 (balanced performance/speed)
- **Why not local?** API provides better stability for production

### Template-Based Approach
- Pre-defined action schemas ensure consistency
- Templates serve as examples for LLM
- Extensible for custom organizations

### Multi-Layer Validation
- YAML syntax → Schema compliance → Security audit
- Auto-fix attempts before failure
- Comprehensive error reporting

### Lock Files for Reproducibility
- SHA256 checksums of workflows
- Track action versions/dependencies
- Enable rollback if needed

## Future Enhancements

- [ ] Support for other CI/CD platforms (GitLab CI, Jenkins)
- [ ] Advanced performance optimization
- [ ] Multi-language workflow orchestration
- [ ] Custom action recommendation
- [ ] Cost estimation for CI/CD runs
- [ ] Workflow debugging assistance
- [ ] Historical trend analysis

## Testing

Run the test suite:

```bash
python test_pipeline.py
```

The test suite demonstrates:
1. Dataset exploration
2. Workflow generation (requires API key)
3. Metrics collection
4. Error handling

## Performance

- **Generation latency:** 5-15 seconds (LLM API latency)
- **Validation:** <100ms
- **Security audit:** <50ms
- **Overall pipeline:** ~10-20 seconds for complete workflow

## Limitations

- Large workflows may exceed token limits
- Complex build logic may require human review
- LLM hallucinations possible (mitigated by validation)
- GitHub integration is mock (requires PyGithub for production)

## Contributing

Issues and improvements welcome! Please ensure:
- Code follows Python standards (PEP 8)
- Tests pass before submitting
- Documentation is updated

## License

MIT License - See LICENSE file for details

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Groq API Documentation](https://console.groq.com/docs)
- Dataset Papers:
  - "Example-Based Automatic Migration of Continuous Integration Systems"
  - "GitHub Actions: Understanding CI/CD Workflows at Scale"

## Support

For issues or questions:
1. Check existing documentation
2. Review test examples
3. Check GitHub Issues
4. Open a new issue with details

---

**Last Updated:** March 2026
