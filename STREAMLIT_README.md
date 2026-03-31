# Multi-Agent DevOps Orchestrator - Streamlit Interface

## 🚀 Quick Start Guide

### Prerequisites
- Python 3.9 or higher
- Git
- GROQ API Key (get from [https://console.groq.com](https://console.groq.com))
- Optional: Ollama installed locally for GLM-5 model

### Installation

1. **Clone the repository** (if not already done):
```bash
cd c:\test-pfe
```

2. **Install Streamlit dependencies**:
```bash
pip install -r streamlit-requirements.txt
```

3. **Install agent dependencies**:
```bash
# Install orchestrator dependencies
cd test_pfe\02-orchestration-agents-layer\orchestrator-agent
pip install -r requirements.txt

# Install CI/CD agent dependencies
cd ..\cicd-agent
pip install -r requirements.txt

# Install Docker agent dependencies
cd ..\docker-agent
pip install -r requirements.txt

# Return to project root
cd ..\..\..
```

4. **Configure environment variables**:

Create a `.env` file in the project root (`c:\test-pfe\.env`):
```env
# Required: GROQ API Key for orchestrator
GROQ_API_KEY=your_groq_api_key_here

# Optional: GitHub token for PR creation
GITHUB_TOKEN=your_github_token_here

# Optional: LLM Configuration
LLM_PROVIDER=ollama
OLLAMA_MODEL=glm-5:cloud
LLM_TEMPERATURE=0.3
LLM_MAX_TOKENS=3000
```

5. **Run the Streamlit app**:
```bash
streamlit run app.py
```

The app should open in your default browser at `http://localhost:8501`.

---

## 🎯 Features

### 1. **Multi-Agent Orchestration**
- **CI/CD Agent**: Generates GitHub Actions workflows
- **Docker Agent**: Creates optimized Dockerfiles  
- **IaC Agent**: Produces Terraform/Infrastructure as Code

### 2. **Intelligent Routing**
- LangGraph-based orchestrator analyzes your request
- Automatically routes to appropriate agents
- Parallel agent execution for efficiency

### 3. **Input Modes**
- **Natural Language**: Describe what you need in plain English
- **GitHub Repository**: Provide a GitHub URL for analysis
- **Local Repository**: Point to your local project directory

### 4. **Interactive UI**
- Real-time progress tracking
- Agent execution status visualization
- Downloadable artifacts (YAML, Dockerfile, Terraform)
- Execution history tracking

### 5. **Advanced Options**
- **Pull Request Creation**: Automatically create PRs with generated artifacts
- **Output Scope**: Show only requested artifacts or all generated content
- **Branch Management**: Specify target branches for PRs

---

## 📖 Usage Examples

### Example 1: Generate CI/CD Pipeline for Python Project
```
Input Mode: Natural Language Prompt
Prompt: "Create a CI/CD pipeline for my Python Flask application with pytest"
```
**Output**: GitHub Actions workflow with Python setup, dependency installation, testing, and deployment steps.

### Example 2: Complete DevOps Setup
```
Input Mode: GitHub Repository
GitHub URL: https://github.com/username/spring-boot-app
Prompt: "Generate complete DevOps configuration"
```
**Output**: CI/CD workflow, Dockerfile, and optional Terraform configuration.

### Example 3: Docker Configuration for Java
```
Input Mode: Local Repository Path
Path: C:\projects\my-java-app
Prompt: "Create a multi-stage Dockerfile for Maven project"
```
**Output**: Optimized multi-stage Dockerfile with Maven build and JRE runtime.

---

## 🔧 Troubleshooting

### Issue: "GROQ_API_KEY not found"
**Solution**: Make sure you've created a `.env` file in the project root with your GROQ API key.

### Issue: "Module not found" errors
**Solution**: Ensure all dependencies are installed:
```bash
pip install -r streamlit-requirements.txt
```

### Issue: "Orchestrator initialization failed"
**Solution**: 
1. Check that your GROQ API key is valid
2. Verify internet connectivity
3. Check if the orchestrator agent dependencies are installed

### Issue: Agents not executing
**Solution**:
1. Verify agent dependencies are installed in their respective directories
2. Check the system status in the sidebar (expand "🔍 System Status")
3. Review error messages in the UI

### Issue: "Path not found" for local repositories
**Solution**: Use absolute paths (e.g., `C:\projects\myapp`) not relative paths.

---

## 🏗️ Architecture Overview

```
Streamlit UI (app.py)
    ↓
Orchestrator Agent (LangGraph)
    ↓
┌─────────────┬──────────────┬─────────────┐
│  CI/CD      │   Docker     │    IaC      │
│  Agent      │   Agent      │   Agent     │
│  (GLM-5)    │   (GLM-5)    │   (Groq)    │
└─────────────┴──────────────┴─────────────┘
```

### Components:
- **app.py**: Main Streamlit interface
- **Orchestrator**: Routes requests and coordinates agents
- **CI/CD Agent**: Generates GitHub Actions workflows using GLM-5
- **Docker Agent**: Creates Dockerfiles using templates + GLM-5
- **IaC Agent**: Generates Terraform configurations

---

## 📊 Configuration Options

### Environment Variables (.env)
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GROQ_API_KEY` | ✅ Yes | - | API key for orchestrator LLM |
| `GITHUB_TOKEN` | ❌ No | - | For PR creation |
| `LLM_PROVIDER` | ❌ No | `ollama` | LLM provider (ollama/groq) |
| `OLLAMA_MODEL` | ❌ No | `glm-5:cloud` | Ollama model name |
| `LLM_TEMPERATURE` | ❌ No | `0.3` | LLM temperature (0.0-1.0) |
| `LLM_MAX_TOKENS` | ❌ No | `3000` | Max response tokens |

### UI Settings (Sidebar)
- **Input Mode**: Choose how to provide project information
- **Create Pull Request**: Auto-create PR with artifacts
- **Branch Name**: Target branch for PR
- **Output Scope**: Show requested or all artifacts

---

## 🎨 UI Components

### Main Sections:
1. **Configuration Sidebar**: System status, input mode selection, advanced options
2. **Request Input**: Natural language prompt or repository specification
3. **Agent Status**: Real-time execution status for each agent
4. **Generated Artifacts**: Tabbed view of YAML, Dockerfile, Terraform
5. **Execution History**: Last 5 orchestration runs

### Color Coding:
- 🟢 Green: CI/CD Agent
- 🔵 Blue: Docker Agent
- 🟠 Orange: IaC Agent

---

## 🚦 Status Indicators

| Indicator | Meaning |
|-----------|---------|
| ✅ Success | Agent executed successfully |
| ❌ Failed | Agent encountered an error |
| ⏸️ Pending | Agent not executed or waiting |
| 🚫 Blocked | Request blocked by guardrails |

---

## 📝 Advanced Usage

### Programmatic Access
You can also use the agents programmatically without the UI:

```python
from src.orchestrator import Orchestrator

orchestrator = Orchestrator()
result = orchestrator.process_request(
    "Generate CI/CD pipeline for Python",
    repository_path="C:\\path\\to\\repo"
)

print(result["status"])
print(result["state"]["agent_outputs"])
```

### Custom Prompts
The orchestrator understands context and intent. Be specific:
- ✅ Good: "Create a Spring Boot CI/CD pipeline with Maven, SonarQube, and Docker deployment"
- ❌ Bad: "I need some DevOps stuff"

---

## 🔒 Security Notes

1. **API Keys**: Never commit `.env` files to version control
2. **Secrets**: Use GitHub Secrets for sensitive values in generated workflows
3. **Guardrails**: The orchestrator includes security guardrails to block malicious requests
4. **Local Execution**: All processing happens locally (except LLM API calls)

---

## 📚 Additional Resources

### Documentation
- **Orchestrator README**: `test_pfe/02-orchestration-agents-layer/orchestrator-agent/README.md`
- **CI/CD Agent**: `test_pfe/02-orchestration-agents-layer/cicd-agent/`
- **Docker Agent**: `test_pfe/02-orchestration-agents-layer/docker-agent/DOCKER_AGENT_README.md`

### API Documentation
- **GROQ**: https://console.groq.com/docs
- **Ollama**: https://ollama.ai/docs
- **LangGraph**: https://python.langchain.com/docs/langgraph

---

## 🐛 Known Issues

1. **Windows Path Handling**: Use double backslashes (`C:\\path\\to\\repo`) or forward slashes (`C:/path/to/repo`)
2. **Large Repositories**: Analysis may take longer for repos with many files
3. **Network Latency**: LLM API calls depend on internet connection speed

---

## 🤝 Contributing

To modify the Streamlit interface:
1. Edit `app.py`
2. Add new features in the appropriate sections
3. Test with various inputs
4. Update this README

---

## 📞 Support

For issues or questions:
1. Check the "🔍 System Status" in the UI sidebar
2. Review error messages in the UI
3. Check orchestrator logs in the terminal
4. Consult agent-specific READMEs

---

## 🎉 Success Criteria

Your setup is working correctly if:
- ✅ System Status shows all components as available
- ✅ You can submit a prompt and see agent execution
- ✅ Artifacts are generated and downloadable
- ✅ No red error messages appear

---

**Happy Orchestrating! 🚀**
