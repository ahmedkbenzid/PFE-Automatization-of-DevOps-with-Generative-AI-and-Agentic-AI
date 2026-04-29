# Execution Agent

The Execution Agent validates generated CI/CD workflows by running them in isolated temporary workspaces using Act.

## Purpose

After artifact generation, the Execution Agent:
- ✅ Creates a temporary isolated workspace
- ✅ Copies the repository source code
- ✅ Runs the CI/CD workflow using Act (GitHub Actions local runner)
- ✅ Reports success/failure with detailed logs

**Key Feature:** This agent only runs **after user confirmation** of the generated artifacts.

## Architecture

```
User Confirms Artifacts
        ↓
Execution Agent
        ├─ Copy Repo to Temp Workspace
        ├─ Write CI/CD Workflow  
        ├─ Act Execution (with timeout)
        └─ Return Results
```

## Realtime Sandbox Streaming API

The execution agent now exposes a realtime WebSocket API for sandbox visualization.

### Start a Run

`POST /api/execution/runs`

Request body:

```json
{
  "cicd_workflow_content": "name: CI\n...",
  "repository_path": "C:/path/to/repo",
  "dockerfile_content": "",
  "github_url": "",
  "act_timeout": 1800,
  "secrets": {
    "DOCKERHUB_USERNAME": "...",
    "DOCKERHUB_TOKEN": "..."
  }
}
```

Response:

```json
{
  "run_id": "f4d98a8fb1244e5f96fa9f4c6f74e9fa",
  "status": "started",
  "ws_path": "/ws/execution/f4d98a8fb1244e5f96fa9f4c6f74e9fa"
}
```

### Stream Logs

`WS /ws/execution/{run_id}`

Each log line is streamed as:

```json
{
  "run_id": "f4d98a8fb1244e5f96fa9f4c6f74e9fa",
  "stage": "build",
  "line": "[build] Running mvn -B -DskipTests package",
  "level": "info",
  "elapsed_ms": 12842,
  "stage_status": "running"
}
```

On stage transitions and completion, a summary event is emitted with:

```json
{
  "type": "stage_update",
  "run_id": "f4d98a8fb1244e5f96fa9f4c6f74e9fa",
  "stage": "test",
  "line": "Stage test transitioned to done",
  "level": "info",
  "elapsed_ms": 22151,
  "stage_status": "done"
}
```

### Run the API

```bash
uvicorn realtime_api:app --host 0.0.0.0 --port 8001
```

## Usage

### From Python Code

```python
from pipeline import ExecutionPipeline

pipeline = ExecutionPipeline()

result = pipeline.execute(
  dockerfile_content="",  # ignored (backward compatibility)
    cicd_workflow_content=workflow_yaml,
    repository_path="/path/to/repo",
    github_url="",  # Optional
    act_timeout=600      # 10 minutes
)

if result["status"] == "success":
    print("Execution successful!")
else:
    print(f"Execution failed: {result['message']}")
```

### From Command Line

```bash
python pipeline.py Dockerfile .github/workflows/ci.yml /path/to/repo
```

### From Orchestrator

The orchestrator calls this agent only after user confirmation:

```python
from execution_sandbox.pipeline import run_execution

result = run_execution(
    dockerfile_content=dockerfile,
    cicd_workflow_content=workflow,
    repository_path=repo_path
)
```

## Requirements

- Docker installed and running
- Act installed (`https://github.com/nektos/act`)
- Git (if cloning from GitHub URLs)

## Configuration

No configuration required - uses standard tools.

## Output Format

```json
{
  "status": "success" | "error",
  "message": "Act execution completed successfully",
  "workspace": "/tmp/exec-agent-1234567890",
  "repo_copy": {
    "copied": true,
    "source": "/path/to/repo",
    "destination": "/tmp/exec-agent-1234567890",
    "copied_entries": 25,
    "mode": "local-copy"
  },
  "docker_build": {
    "step": "docker-build",
    "command": [],
    "exit_code": 0,
    "timed_out": false,
    "logs": [{"stream": "stdout", "line": "Skipped: execution agent runs only act."}],
    "success": true,
    "skipped": true
  },
  "act": {
    "step": "act-run",
    "command": ["act", "-W", ".github/workflows/ci.yml"],
    "exit_code": 0,
    "timed_out": false,
    "logs": [...],
    "success": true
  },
  "should_self_repair": false
}
```

## Error Handling

- Timeouts: Commands that exceed timeout are killed and marked as timed out
- Copy failures: Reported with detailed error messages
- Missing tools: Subprocess errors indicate if Act is not installed

## Integration Flow

### Old Flow (Automatic Execution)
```
Generate Artifacts → Execute Immediately → Show Results
```

### New Flow (User Confirmation Required)
```
Generate Artifacts → User Reviews → User Confirms → Execution Agent → Show Results
```

## Features

✅ **Isolated Execution**: Each run uses a fresh temporary workspace
✅ **Real-time Logging**: Streams stdout/stderr as execution happens
✅ **Timeout Protection**: Hard timeouts prevent hanging builds
✅ **Detailed Results**: Full Act logs and exit codes for debugging
✅ **Cleanup**: Temporary workspaces persist for debugging
✅ **Git Support**: Can clone from GitHub URLs or copy local repos
✅ **Selective Copying**: Ignores .git, node_modules, .venv, etc.

## Timeouts

Default timeout:
- **Act execution**: 600 seconds (10 minutes)

These can be adjusted based on project size and complexity.

## Notes

- Temporary workspaces are NOT automatically cleaned up (allows post-execution debugging)
- Act requires Docker to be running (it uses Docker containers)
- Repository is copied without .git directory to save space/time

