# CI/CD Agent Dataset Ingestion

This directory contains tools for ingesting real GitHub Actions workflows from Zenodo datasets into the PageIndex knowledge base.

## Datasets

### 1. Workflow Histories (2.8 GB) ⭐ **Recommended**
- **URL**: https://zenodo.org/records/17301952
- **Content**: 3M+ workflow files from 49.2K repos
- **Files**: workflows.csv.gz (257.7 MB metadata)
- **Features**: Valid YAML flags, git history, repo metadata

### 2. GHALogs (143.4 GB) **Advanced**
- **URL**: https://zenodo.org/records/10154920
- **Content**: 116k workflows, 513k runs, 2.3M steps
- **Files**: runs.json.gz (1.1 GB), github_run_logs.zip (142.3 GB)
- **Features**: Full execution logs, success rates, performance metrics

## Quick Start

### Install Dependencies
```bash
pip install pyyaml
```

### Run Ingestion (Workflow Histories)
```bash
cd /c/test-pfe/test_pfe/02-orchestration-agents-layer/cicd-agent
python -m src.datasets.ingest_zenodo_datasets --max-workflows 500
```

This will:
1. Download workflows.csv.gz (257.7 MB) to `src/datasets/cache/`
2. Parse and filter for valid workflows
3. Sample 500 diverse workflows across languages/repos
4. Fetch actual YAML content from GitHub
5. Analyze each workflow (language, framework, patterns)
6. Build hierarchical PageIndex structure
7. Save to `src/datasets/knowledge_base/`

### Options
```bash
# Ingest more workflows
python -m src.datasets.ingest_zenodo_datasets --max-workflows 1000

# Use cached download
python -m src.datasets.ingest_zenodo_datasets --skip-download
```

## PageIndex Structure

The ingestion creates a hierarchical PageIndex:

```
Root (CI/CD Knowledge Base)
├── Workflow Examples
│   ├── Python
│   │   ├── Django Test Workflow (zenodo-abc123-1)
│   │   ├── Flask CI Pipeline (zenodo-def456-2)
│   │   └── ...
│   ├── Java
│   │   ├── Spring Boot Build (zenodo-ghi789-3)
│   │   ├── Maven Multi-Module (zenodo-jkl012-4)
│   │   └── ...
│   ├── JavaScript
│   │   ├── React Build and Test (zenodo-mno345-5)
│   │   ├── Node.js Express App (zenodo-pqr678-6)
│   │   └── ...
│   └── ...
└── Datasets (metadata placeholder)
```

### Correct start_index/end_index

Each node has proper index ranges:
- **Root**: `start_index=1, end_index=500` (spans all pages)
- **Category** (Workflow Examples): `start_index=1, end_index=500`
- **Language** (Java): `start_index=150, end_index=220` (70 Java workflows)
- **Leaf** (individual workflow): `start_index=175, end_index=175`

## Verification

### Check PageIndex
```bash
python -c "
from src.datasets.dataset_manager import DatasetManager
dm = DatasetManager()
results = dm.retrieve_knowledge('spring boot sonarqube maven', top_k=5)
for r in results:
    print(f\"{r['title']} (score={r['score']})\")
"
```

### Inspect Structure
```bash
cat src/datasets/knowledge_base/page_index.json | python -m json.tool | less
```

## Architecture

### Before (Hardcoded)
- 6 workflow examples (hardcoded in dataset_manager.py)
- Flat PageIndex (all start_index=end_index)
- No real data, just placeholders

### After (Real Data)
- 500+ real workflows from Zenodo
- Hierarchical PageIndex (proper start/end ranges)
- Language detection, framework analysis, pattern extraction
- Diverse sampling across repos and tech stacks

## Troubleshooting

### Rate Limiting
If you hit GitHub rate limits when fetching workflow content:
```bash
# Reduce max-workflows
python -m src.datasets.ingest_zenodo_datasets --max-workflows 200

# Or add GitHub token (higher rate limit)
export GITHUB_TOKEN=ghp_your_token_here
```

### Download Fails
If Zenodo download fails:
```bash
# Manual download
wget https://zenodo.org/records/17301952/files/workflows.csv.gz -O src/datasets/cache/workflows.csv.gz

# Then run with skip-download
python -m src.datasets.ingest_zenodo_datasets --skip-download
```

### Memory Issues
For large imports:
```bash
# Process in smaller batches
python -m src.datasets.ingest_zenodo_datasets --max-workflows 100
python -m src.datasets.ingest_zenodo_datasets --max-workflows 100  # runs again, adds more
```

## Next Steps

1. **Test Retrieval**: Run queries to verify PageIndex quality
2. **Expand**: Increase to 1000+ workflows for better coverage
3. **GHALogs**: Integrate execution logs for success rates
4. **Embeddings**: Optional - add vector search for semantic similarity
