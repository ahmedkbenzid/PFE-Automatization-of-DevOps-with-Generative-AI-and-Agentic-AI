# System Architecture - ASCII Diagram

## Overall System Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                                                                            │
│                    USER & INTERFACES LAYER                                │
│              (Web UI, REST API, WebSocket/SSE Logs)                       │
│                                                                            │
│                         Natural Language Request                           │
│                                                                            │
└────────────────────────────────┬─────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                                                                            │
│                ORCHESTRATION & AGENTS LAYER                               │
│                   (8 Specialized Agents)                                  │
│                                                                            │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                    Orchestrator Agent                              │  │
│  │                  (FR1: Routing & State)                            │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Planner    │  │  CI/CD Agent │  │  IaC Agent   │  │   Docker     │ │
│  │ FR1: K8s DAG │  │ FR2,FR6,FR7  │  │ FR4,FR6,FR7  │  │  FR3,FR7     │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                                            │
│  ┌──────────────┐  ┌──────────────┐                                      │
│  │     K8s      │  │  Execution   │                                      │
│  │  FR3,FR7     │  │ FR5: Sandbox │                                      │
│  └──────────────┘  └──────────────┘                                      │
│                                                                            │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │        Knowledge Ingestion (FR8: Document Refresh)               │  │
│  │                                                                  │  │
│  │        LlamaIndex Knowledge Base                                │  │
│  │        (Neo4j: graph + Qdrant: vector)                         │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  ┌──────────────────────────┐  ┌──────────────────────────────────────┐  │
│  │     State Store          │  │      Observability                   │  │
│  │  Redis + PostgreSQL      │  │   Prom/Grafana/ELK                 │  │
│  └──────────────────────────┘  └──────────────────────────────────────┘  │
│                                                                            │
│  Coordination: LangGraph • Self-repair, retry loops (≤2 attempts)        │
│                                                                            │
└────────────────────────────────┬─────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                                                                            │
│           EXECUTION & INFRASTRUCTURE LAYER                                │
│         (Isolated Sandbox & Production Targets)                           │
│                                                                            │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐       │
│  │  Sandbox Cluster │  │ Platform Cluster │  │Target Production │       │
│  │  (DinD, Kind)    │  │ (Agents, APIs)   │  │  (User clusters) │       │
│  │  Ephemeral       │  │  Monitoring      │  │  Gated Apply     │       │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘       │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

## CI/CD Agent Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          USER REQUEST (NL)                              │
│        "Generate a Python testing workflow with pytest and caching"    │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
        ┌──────────────────────────────────────────┐
        │      INTENT LAYER                        │ ┐
        │  Metadata + Markdown Builder             │ │ Intent Processing
        ├──────────────────────────────────────────┤ │ Phase
        │ • Extract intent                         │ │
        │ • Keywords: [pytest, Python, caching]   │ │
        │ • Request type: CREATE_WORKFLOW          │ │
        │ • Confidence: 0.95                       │ │
        │ • Required tools: [template, validator] │ │
        └──────────────────────────────────────────┘ ┘
                               │
                               ▼
        ┌──────────────────────────────────────────┐
        │    CONTEXT COLLECTOR                     │ ┐
        │   (Repo Tree, Code Analysis)             │ │
        ├──────────────────────────────────────────┤ │ Context Phase
        │ • Detect languages: [Python, YAML]       │ │
        │ • Build system: Poetry/pip               │ │
        │ • Package managers: [pip, poetry]        │ │
        │ • Existing workflows: []                 │ │
        │ • Important files: [setup.py, pyproject] │ │
        └──────────────────────────────────────────┘ ┘
                               │
                               ▼
        ┌──────────────────────────────────────────┐
        │    DATASET MANAGER                       │ ┐
        │  (3 Datasets: GHA, Histories, EBAMIC)   │ │
        ├──────────────────────────────────────────┤ │ Example Phase
        │ Found similar examples:                 │ │
        │ • Python-test (success_rate: 95%)       │ │
        │ • Python-coverage (success_rate: 92%)   │ │
        └──────────────────────────────────────────┘ ┘
                               │
                               ▼
        ┌──────────────────────────────────────────────────┐
        │    LLM CODING AGENT ENGINE                       │ ┐
        │   (Groq API - Mixtral 8x7b-32768)              │ │
        ├──────────────────────────────────────────────────┤ │
        │ Prompt:                                         │ │
        │ "Generate a Python workflow using the context  │ │
        │  and examples provided..."                      │ │
        │                                                  │ │
        │ Output:                                         │ │ Generation
        │ ├─ name: Python Tests                           │ │ Phase
        │ ├─ on: [push, pull_request]                    │ │ (with
        │ ├─ jobs:                                        │ │ auto-retry
        │ │  └─ test:                                     │ │ ≤3 times)
        │ │     ├─ runs-on: ubuntu-latest                │ │
        │ │     ├─ strategy: {matrix: {python: [...]}}   │ │
        │ │     └─ steps: [checkout, setup-python, ...] │ │
        └──────────────────────────────────────────────────┘ ┘
                               │
                    (Max 3 attempts with fixes)
                               │
                   ╔═══════════╩═══════════╗
                   │                       │
        ┌──────────▼──────────┐  ┌────────▼────────┐
        │  Syntax Valid? YES  │  │  Syntax Valid? NO
        │                     │  │  │
        │  Continue ─→        │  │  └─→ [AUTO-FIX]
        │                     │  │      └─→ Retry
        └──────────┬──────────┘  └─────────────────┘
                   │
                   ▼
        ┌──────────────────────────────────────────┐
        │    YAML GENERATOR                        │ ┐
        │   (Parse, Format, Merge)                 │ │
        ├──────────────────────────────────────────┤ │ Parsing &
        │ • Parse YAML content                    │ │ Formatting
        │ • Validate syntax                       │ │ Phase
        │ • Format with proper indentation         │ │
        │ • Expand action shortcuts                │ │
        │ • Add metadata comments                  │ │
        └──────────────────────────────────────────┘ ┘
                               │
                               ▼
        ┌──────────────────────────────────────────┐
        │    TEMPLATE MANAGER                      │ ┐
        │  (Action Schemas, YAML Templates)       │ │
        ├──────────────────────────────────────────┤ │ Template &
        │ • Validate action schemas                │ │ Schema Phase
        │ • Check github-suggested formats        │ │
        │ • Expand template shortcuts              │ │
        │ • Get validation schema                  │ │
        └──────────────────────────────────────────┘ ┘
                               │
                               ▼
        ┌──────────────────────────────────────────┐
        │    SCHEMA VALIDATOR                      │ ┐
        │  (GitHub Actions Syntax Check)           │ │
        ├──────────────────────────────────────────┤ │ Validation &
        │ ✓ Check required fields                  │ │ Safety Layer
        │ ✓ Check 'on' triggers                    │ │
        │ ✓ Check jobs structure                   │ │
        │ ✓ Check steps definitions                │ │
        │ ✓ Validate run-ons                       │ │
        │                                           │ │
        │ Results:                                 │ │
        │ • is_valid: true                         │ │
        │ • warnings: [1 suggestion]                │ │
        │ • suggestions: [add caching]             │ │
        └──────────────────────────────────────────┘ ┘
                               │
                               ▼
        ┌──────────────────────────────────────────┐
        │    SECURITY GUARDRAILS                   │ ┐
        │  (Sandboxing, Safe Outputs)              │ │
        ├──────────────────────────────────────────┤ │ Security
        │ Checks:                                  │ │ Audit Phase
        │ ✓ Dangerous pattern detection            │ │
        │ ✓ Action verification (safe sources)     │ │
        │ ✓ Secret exposure detection              │ │
        │ ✓ Permission audit (minimal principle)   │ │
        │ ✓ External URL safety check              │ │
        │                                           │ │
        │ Result: SAFE (0 critical risks)          │ │
        └──────────────────────────────────────────┘ ┘
                               │
                               ▼
        ┌──────────────────────────────────────────┐
        │    WORKFLOW COMPILER                     │ ┐
        │  (Markdown → YAML + Lock File)           │ │
        ├──────────────────────────────────────────┤ │ Compilation &
        │ • Normalize workflow structure           │ │ Reproducibility
        │ • Extract dependencies                   │ │ Phase
        │ • Generate SHA256 checksum               │ │
        │ • Create lock file with metadata         │ │
        │                                           │ │
        │ Lock File Contents:                      │ │
        │ • Version: 1.0.0                         │ │
        │ • Checksum: a1b2c3d4e5f6...             │ │
        │ • Dependencies: {actions/setup-py: v4}  │ │
        │ • Reproducible: true                     │ │
        └──────────────────────────────────────────┘ ┘
                               │
                               ▼
        ┌──────────────────────────────────────────────────┐
        │    GITHUB INTEGRATION                            │ ┐
        │  (PR, Commit, Write Actions)                    │ │
        ├──────────────────────────────────────────────────┤ │ GitHub
        │ Options:                                         │ │ Integration
        │ • Create PR with workflow                        │ │ Phase
        │ • Commit to branch                               │ │
        │ • Comment on PR with details                    │ │
        │ • Preview in UI                                  │ │
        └──────────────────────────────────────────────────┘ ┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    GENERATED GITHUB ACTIONS WORKFLOW                     │
│                       (YAML + lock.yml)                                  │
│                                                                          │
│  📄 python-test.yml       - Complete workflow                          │
│  📄 python-test.lock.yml  - Reproducibility metadata                   │
│  📄 .metadata.json        - Generation context                         │
│                                                                          │
│  Metrics:                                                              │
│  • Generation latency: 8.5s                                            │
│  • Attempts: 1                                                         │
│  • Syntax validity: ✓ PASS                                            │
│  • Security audit: ✓ SAFE                                             │
│  • Validation: ✓ PASS                                                 │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Component Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        PIPELINE ORCHESTRATOR                             │
│                    (CICDPipeline class)                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │ 1. Request Processing                                           │ │
│  │    Input: UserRequest (natural language)                        │ │
│  │                                                                  │ │
│  │    ├─→ IntentLayer.process_request()                           │ │
│  │    │   └─→ GroqLLMClient.extract_intent()                      │ │
│  │    │       Output: IntentMetadata                              │ │
│  │    │                                                             │ │
│  │    └─→ ContextCollector.collect()                              │ │
│  │        Output: RepositoryContext                               │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │ 2. Dataset Enrichment                                           │ │
│  │                                                                  │ │
│  │    └─→ DatasetManager.find_similar_examples()                  │ │
│  │        Output: List[WorkflowExample]                           │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │ 3. Generation Loop (with retry)                                 │ │
│  │    Attempts: 1 to MAX_RETRIES                                   │ │
│  │                                                                  │ │
│  │    ├─→ IntentLayer.build_context_prompt()                      │ │
│  │    │   (combines intent + context + examples)                  │ │
│  │    │                                                             │ │
│  │    ├─→ GroqLLMClient.generate_workflow_yaml()                  │ │
│  │    │   Output: YAML string                                     │ │
│  │    │                                                             │ │
│  │    ├─→ YAMLGenerator.parse_yaml()                              │ │
│  │    │   └─→ YAMLGenerator.validate_yaml_syntax()                │ │
│  │    │       Output: bool, error_message                         │ │
│  │    │                                                             │ │
│  │    ├─→ TemplateManager.get_validation_schema()                 │ │
│  │    │   └─→ SchemaValidator.validate_workflow()                 │ │
│  │    │       Output: ValidationResult                            │ │
│  │    │                                                             │ │
│  │    └─→ [If invalid, retry with auto-fix]                      │ │
│  │        └─→ YAMLGenerator.auto_fix_common_issues()              │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │ 4. Security Audit                                               │ │
│  │                                                                  │ │
│  │    └─→ SecurityGuardrails.audit_workflow()                     │ │
│  │        Output: SecurityAuditResult                             │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │ 5. Compilation                                                  │ │
│  │                                                                  │ │
│  │    └─→ WorkflowCompiler.compile_workflow()                     │ │
│  │        ├─→ normalize()                                         │ │
│  │        ├─→ extract_dependencies()                              │ │
│  │        ├─→ generate_checksum()                                 │ │
│  │        └─→ Output: (compiled_yaml, lock_file)                  │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │ 6. Output Assembly                                              │ │
│  │                                                                  │ │
│  │    └─→ PipelineResult(                                         │ │
│  │        success=True,                                           │ │
│  │        workflow_yaml=...,                                      │ │
│  │        lock_file=...,                                          │ │
│  │        validation_result=...,                                  │ │
│  │        security_audit=...,                                     │ │
│  │        generation_latency_ms=...,                              │ │
│  │        attempts=X,                                              │ │
│  │    )                                                            │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Data Flow Diagram

```
User Input
    │
    ├─ Text: "Generate Python testing workflow"
    └─ Request Type: CREATE_WORKFLOW
        │
        ▼
    [Intent Layer]
        │
        ├─ Groq LLM
        └─→ IntentMetadata
             │
             ├─ intent: "..."
             ├─ keywords: ["pytest", "python", ...]
             ├─ request_type: CREATE_WORKFLOW
             └─ confidence: 0.95
                 │
                 ▼
    [Context Collector]
        │
        ├─ File System Analysis
        └─→ RepositoryContext
             │
             ├─ languages: ["Python"]
             ├─ build_system: "poetry"
             ├─ package_managers: ["pip"]
             └─ workflows: []
                 │
                 ▼
    [Dataset Manager]
        │
        ├─ Search: Similar examples
        └─→ WorkflowExample[]
             │
             ├─ python-test.yml
             ├─ python-coverage.yml
             └─ ...
                 │
                 ▼
    [LLM Client - Groq API]
        │
        ├─ Groq API Call (Mixtral 8x7b)
        │  ├─ Model: mixtral-8x7b-32768
        │  ├─ Max Tokens: 2048
        │  └─ Temperature: 0.3
        │
        └─→ GeneratedWorkflow
             │
             ├─ yaml_content: "name: Python Tests\non: ..."
             ├─ metadata: {...}
             └─ is_valid: false (initially)
                 │
                 ▼
    [YAML Parser]
        │
        └─→ Parsed YAML (Dict)
             │
             ├─ name
             ├─ on
             ├─ jobs
             └─ ...
                 │
                 ▼
    [Schema Validator]
        │
        ├─ Grammar Check
        ├─ Structure Check
        ├─ Best Practices
        └─→ ValidationResult
             │
             ├─ is_valid: true
             ├─ warnings: [...]
             └─ suggestions: [...]
                 │
                 ▼
    [Security Guardrails]
        │
        ├─ Pattern Detection
        ├─ Action Verification
        ├─ Secret Detection
        ├─ Permission Audit
        └─→ SecurityAuditResult
             │
             ├─ is_safe: true
             ├─ risks: []
             └─ actions_used: [...]
                 │
                 ▼
    [Workflow Compiler]
        │
        ├─ Normalize
        ├─ Extract Dependencies
        ├─ Generate Checksum
        └─→ (CompiledYAML, LockFile)
             │
             ├─ workflow_name
             ├─ checksum
             └─ dependencies
                 │
                 ▼
    [Final Output]
        │
        ├─ workflow.yml
        ├─ workflow.lock.yml
        └─ metrics

    Metrics Collected:
    │
    ├─ Total Requests: 1
    ├─ Successful: 1
    ├─ Generation Latency: 8500ms
    ├─ Attempts: 1
    └─ Success Rate: 100%
```

---

**This architecture implements the complete CI/CD Agent as specified in the project requirements.**
