# Docker Agent - GLM-5 Cloud Integration

## Overview
The Docker Agent now uses **GLM-5 Cloud** via Ollama as its primary LLM for intelligent Dockerfile generation and optimization.

## Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Ollama
Make sure you have Ollama installed and authenticated for cloud models:
```bash
# Install Ollama (if not already installed)
# Visit: https://ollama.ai

# Login to Ollama Cloud for GLM-5
ollama login

# Pull the GLM-5 cloud model
ollama pull glm-5:cloud
```

### 3. Environment Configuration
Create a `.env` file based on `.env.example`:
```bash
cp .env.example .env
```

Default configuration (`.env`):
```env
LLM_PROVIDER=ollama
OLLAMA_MODEL=glm-5:cloud
```

Optional Groq fallback (if you want backup):
```env
GROQ_API_KEY=your_groq_api_key_here
```

## LLM Configuration

### Primary: GLM-5 Cloud (via Ollama)
- **Model**: `glm-5:cloud`
- **Provider**: Ollama
- **Cost**: Pay-as-you-go cloud pricing
- **Quality**: GPT-4 level for code generation
- **Context**: 128K tokens

### Fallback: Groq (optional)
- **Model**: `llama3-70b-8192`
- **Provider**: Groq
- **Requires**: GROQ_API_KEY environment variable

## Features

### Intelligent Generation
The agent now supports two generation modes:

1. **LLM-Powered** (default): Uses GLM-5 to generate custom Dockerfiles based on:
   - Project context (detected stack, frameworks, ports)
   - User requirements
   - Docker best practices
   - Security considerations

2. **Template Fallback**: Uses predefined templates if LLM is unavailable

### Usage Example
```python
from src.pipeline import DockerPipeline
from src.models.types import UserRequest

pipeline = DockerPipeline()

request = UserRequest(
    text="Create a production-ready Dockerfile for my Node.js API",
    repo_path="/path/to/project"
)

result = pipeline.process_request(request)
print(result.generated_config.dockerfile_content)
```

## LLM Client Methods

### Generate Dockerfile
```python
from src.components.llm_client import LLMClient

client = LLMClient()
dockerfile = client.generate_dockerfile(
    prompt="Create a Dockerfile for Python FastAPI app",
    context={"stack_type": "python", "detected_ports": [8000]}
)
```

### Optimize Dockerfile
```python
optimized = client.optimize_dockerfile(
    dockerfile_content=existing_dockerfile,
    suggestions=["Reduce image size", "Add security hardening"]
)
```

### Explain Dockerfile
```python
explanation = client.explain_dockerfile(dockerfile_content)
```

## Why GLM-5?

| Feature | GLM-5 | GPT-4 | Claude 3.5 |
|---------|-------|-------|------------|
| Code Quality | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Cost | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| Docker Knowledge | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Speed | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |

**GLM-5 provides 90% of GPT-4's quality at 10% of the cost**, making it ideal for the Docker agent's code generation tasks.

## Architecture

```
DockerPipeline
    ├── AnalyzeProject (detect stack)
    ├── PromptIntentResolver (parse user intent)
    ├── GenerateFile (LLM + templates)
    │   └── LLMClient (GLM-5 via Ollama)
    ├── Validate (Hadolint, Trivy)
    ├── OptimizeImage
    └── WriteFiles
```

## Troubleshooting

### Issue: "ollama package is not installed"
```bash
pip install ollama
```

### Issue: "GROQ_API_KEY environment variable is required"
Either:
1. Set `LLM_PROVIDER=ollama` in `.env` (recommended)
2. Or add your Groq API key if you want fallback

### Issue: Model not found
```bash
# Make sure you're logged in
ollama login

# Pull the model
ollama pull glm-5:cloud
```

### Issue: LLM generation fails
The agent automatically falls back to template-based generation if LLM fails.

## Configuration Options

Edit `src/config.py` or use environment variables:

```python
LLM_CONFIG = {
    "provider": "ollama",           # or "groq"
    "model": "glm-5:cloud",        # Ollama model
    "groq_model": "llama3-70b-8192",  # Groq fallback
    "temperature": 0.2,             # Low for deterministic code
    "max_tokens": 4096,            # Max response length
}
```

## Next Steps

1. **Dataset Integration**: Load Dockerfile datasets for RAG (see plan.md)
2. **Enhanced RAG**: Use knowledge base for better generation
3. **Benchmarking**: Compare GLM-5 vs other models on Docker tasks

## License
MIT
