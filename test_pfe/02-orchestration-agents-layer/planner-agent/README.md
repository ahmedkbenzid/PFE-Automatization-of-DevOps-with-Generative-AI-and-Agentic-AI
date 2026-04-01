# Planner Agent

AI-powered strategic planning agent that decomposes complex DevOps requests into executable task plans.

## Overview

The Planner Agent acts as a strategic advisor to the Orchestrator. When faced with complex multi-step requests, the Orchestrator consults the Planner to create an optimal execution plan with proper task dependencies and ordering.

## Responsibilities

- **Complexity Analysis**: Determine if a request needs strategic planning
- **Task Decomposition**: Break complex requests into discrete tasks
- **Dependency Management**: Identify task dependencies and execution order
- **Agent Selection**: Choose appropriate worker agents for each task
- **Context Enrichment**: Enhance task inputs based on repository context

## Architecture

```
Orchestrator → Planner Agent → Execution Plan
                    ↓
              Agent Registry
              (Knows all workers)
```

## Features

- **Intelligent Planning**: Uses LLM to understand complex multi-step requests
- **Dependency Resolution**: Builds task dependency graphs using topological sort
- **Parallel Optimization**: Identifies tasks that can run in parallel
- **Agent Registry**: Maintains catalog of all worker agents and their capabilities

## Usage

The Planner is invoked by the Orchestrator when complexity threshold is exceeded:

```python
# Simple request (no planner needed)
"Create a Dockerfile" → Direct to docker-agent

# Complex request (planner needed)
"Deploy my microservices to AWS with CI/CD" → Planner creates plan → Execute
```

## Configuration

- **LLM Model**: `glm-5:cloud` (configurable in config.py)
- **Complexity Threshold**: 4 (configurable)
- **Temperature**: 0.1 (low for consistent planning)
