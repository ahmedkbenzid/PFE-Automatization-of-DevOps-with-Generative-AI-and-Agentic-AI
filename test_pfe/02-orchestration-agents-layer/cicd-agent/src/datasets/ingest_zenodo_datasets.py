"""
Data ingestion script for Zenodo GitHub Actions datasets.

Downloads and processes:
1. Workflow Histories (2.8 GB) - https://zenodo.org/records/17301952
2. GHALogs (143.4 GB) - https://zenodo.org/records/10154920

Run this script to populate the PageIndex knowledge base with real workflows.
"""

import csv
import gzip
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import urlretrieve

import yaml

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.datasets.pageindex_knowledge_base import KnowledgePage, PageIndexKnowledgeBase


@dataclass
class WorkflowRecord:
    """Workflow from Zenodo dataset."""
    repository: str
    file_path: str
    commit_hash: str
    valid_yaml: bool
    valid_workflow: bool
    yaml_content: Optional[str] = None
    language: Optional[str] = None
    framework: Optional[str] = None


class ZenodoDatasetIngester:
    """Ingest GitHub Actions workflows from Zenodo datasets."""

    WORKFLOW_HISTORIES_URL = "https://zenodo.org/records/17301952/files/workflows.csv.gz"
    CACHE_DIR = Path(__file__).parent / "cache"

    def __init__(self, max_workflows: int = 500):
        """
        Args:
            max_workflows: Maximum number of workflows to ingest (for sampling)
        """
        self.max_workflows = max_workflows
        self.cache_dir = self.CACHE_DIR
        self.cache_dir.mkdir(exist_ok=True)
        self.skip_github_fetch = False

        knowledge_dir = Path(__file__).parent / "knowledge_base"
        self.knowledge_base = PageIndexKnowledgeBase(str(knowledge_dir))

    def download_workflow_histories(self) -> Path:
        """Download workflows.csv.gz from Zenodo with validation."""
        cache_file = self.cache_dir / "workflows.csv.gz"

        if cache_file.exists():
            print(f"[Ingest] Validating cached file: {cache_file}")
            if self._validate_gzip_file(cache_file):
                print(f"[Ingest] [OK] Cache file is valid")
                return cache_file
            else:
                print(f"[Ingest] [FAIL] Cache file is corrupted, deleting...")
                cache_file.unlink()

        print(f"[Ingest] Downloading Workflow Histories dataset (257.7 MB)...")
        print(f"[Ingest] URL: {self.WORKFLOW_HISTORIES_URL}")
        print(f"[Ingest] This may take 5-10 minutes...")

        try:
            urlretrieve(self.WORKFLOW_HISTORIES_URL, cache_file, reporthook=self._download_progress)
            print(f"\n[Ingest] Downloaded to: {cache_file}")

            # Validate download
            if not self._validate_gzip_file(cache_file):
                print(f"[Ingest] ERROR: Downloaded file is corrupted. Try downloading manually:")
                print(f"[Ingest] wget {self.WORKFLOW_HISTORIES_URL} -O {cache_file}")
                raise RuntimeError("Downloaded file failed validation")

            return cache_file
        except Exception as e:
            print(f"[Ingest] ERROR: Failed to download dataset: {e}")
            raise

    def _validate_gzip_file(self, file_path: Path) -> bool:
        """Validate that a gzip file is not corrupted."""
        if not file_path.exists():
            return False

        try:
            with gzip.open(file_path, 'rb') as f:
                # Try to read first chunk
                chunk = f.read(1024)
                return len(chunk) > 0
        except (EOFError, gzip.BadGzipFile, OSError):
            return False

    def _download_progress(self, block_num: int, block_size: int, total_size: int):
        """Progress callback for download."""
        downloaded = block_num * block_size
        if total_size > 0:
            percent = min(downloaded * 100 / total_size, 100)
            print(f"\r[Ingest] Progress: {percent:.1f}% ({downloaded // (1024**2)} MB / {total_size // (1024**2)} MB)", end="")

    def parse_csv_gz(self, csv_file: Path) -> List[WorkflowRecord]:
        """Parse workflows.csv.gz and extract records with error handling."""
        print(f"\n[Ingest] Parsing CSV file...")

        records = []
        try:
            with gzip.open(csv_file, 'rt', encoding='utf-8', errors='ignore') as f:
                reader = csv.DictReader(f)
                for row_num, row in enumerate(reader, 1):
                    try:
                        records.append(WorkflowRecord(
                            repository=row.get('repository', ''),
                            file_path=row.get('file_path', ''),
                            commit_hash=row.get('commit_hash', ''),
                            valid_yaml=row.get('valid_yaml', '').lower() == 'true',
                            valid_workflow=row.get('valid_workflow', '').lower() == 'true',
                        ))
                    except Exception as e:
                        print(f"[Ingest] Warning: Skipping malformed row {row_num}: {e}")
                        continue

        except (EOFError, gzip.BadGzipFile) as e:
            print(f"[Ingest] ERROR: File is corrupted: {e}")
            print(f"[Ingest] Please delete and re-download:")
            print(f"[Ingest]   rm {csv_file}")
            print(f"[Ingest]   python -m src.datasets.ingest_zenodo_datasets")
            raise RuntimeError(f"Corrupted gzip file: {e}")

        print(f"[Ingest] Found {len(records):,} workflow records")
        return records

    def filter_and_sample(self, records: List[WorkflowRecord]) -> List[WorkflowRecord]:
        """Filter valid workflows and sample diverse set."""
        print(f"[Ingest] Filtering and sampling workflows...")

        # Filter for valid workflows only
        valid_records = [r for r in records if r.valid_yaml and r.valid_workflow]
        print(f"[Ingest] Valid workflows: {len(valid_records):,}")

        # Sample diverse workflows
        sampled = self._diverse_sample(valid_records, self.max_workflows)
        print(f"[Ingest] Sampled {len(sampled)} diverse workflows")

        return sampled

    def _diverse_sample(self, records: List[WorkflowRecord], target: int) -> List[WorkflowRecord]:
        """Sample workflows ensuring diversity across repos and file types."""
        repo_buckets: Dict[str, List[WorkflowRecord]] = defaultdict(list)

        for record in records:
            repo_buckets[record.repository].append(record)

        sampled = []
        repos = list(repo_buckets.keys())

        # Round-robin sampling from different repos
        idx = 0
        while len(sampled) < target and idx < max(len(bucket) for bucket in repo_buckets.values()):
            for repo in repos:
                if len(sampled) >= target:
                    break
                if idx < len(repo_buckets[repo]):
                    sampled.append(repo_buckets[repo][idx])
            idx += 1

        return sampled[:target]

    def fetch_workflow_content(self, record: WorkflowRecord) -> Optional[str]:
        """Fetch actual YAML content from GitHub for a workflow record."""
        # Extract owner/repo from repository URL
        match = re.search(r'github\.com[/:]([^/]+)/([^/\.]+)', record.repository)
        if not match:
            return None

        owner, repo = match.groups()

        # Construct raw GitHub URL
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{record.commit_hash}/{record.file_path}"

        try:
            time.sleep(0.1)  # Rate limit protection
            with urllib.request.urlopen(raw_url, timeout=5) as response:
                content = response.read().decode('utf-8', errors='ignore')
                # Validate it's actually YAML
                yaml.safe_load(content)
                return content
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, yaml.YAMLError):
            # Skip if we can't fetch (repo deleted, private, rate limit, invalid YAML, etc.)
            return None
        except Exception:
            return None

    def analyze_workflow(self, yaml_content: str) -> Dict[str, Any]:
        """Analyze workflow to extract language, framework, patterns."""
        try:
            workflow = yaml.safe_load(yaml_content)

            # Extract language/framework hints
            language = self._detect_language(workflow, yaml_content)
            framework = self._detect_framework(workflow, yaml_content)
            patterns = self._detect_patterns(workflow)

            return {
                "language": language,
                "framework": framework,
                "patterns": patterns,
            }
        except Exception:
            return {
                "language": "unknown",
                "framework": None,
                "patterns": [],
            }

    def _detect_language(self, workflow: Dict, content: str) -> str:
        """Detect primary language from workflow."""
        content_lower = content.lower()

        # Check setup actions
        if 'setup-python' in content_lower or 'pip install' in content_lower:
            return "Python"
        if 'setup-node' in content_lower or 'npm ' in content_lower or 'yarn ' in content_lower:
            return "JavaScript"
        if 'setup-java' in content_lower or 'mvn ' in content_lower or 'gradle' in content_lower:
            return "Java"
        if 'setup-go' in content_lower or 'go build' in content_lower:
            return "Go"
        if 'setup-ruby' in content_lower or 'bundle install' in content_lower:
            return "Ruby"
        if 'cargo' in content_lower or 'rustc' in content_lower:
            return "Rust"
        if 'dotnet' in content_lower or 'nuget' in content_lower:
            return "C#"
        if 'composer' in content_lower or 'php ' in content_lower:
            return "PHP"

        return "Mixed"

    def _detect_framework(self, workflow: Dict, content: str) -> Optional[str]:
        """Detect framework from workflow."""
        content_lower = content.lower()

        if 'spring' in content_lower or 'springboot' in content_lower:
            return "Spring Boot"
        if 'django' in content_lower:
            return "Django"
        if 'flask' in content_lower:
            return "Flask"
        if 'react' in content_lower:
            return "React"
        if 'vue' in content_lower:
            return "Vue"
        if 'angular' in content_lower:
            return "Angular"
        if 'express' in content_lower:
            return "Express"

        return None

    def _detect_patterns(self, workflow: Dict) -> List[str]:
        """Detect CI/CD patterns in workflow."""
        patterns = []

        jobs = workflow.get('jobs', {})
        content_str = json.dumps(workflow).lower()

        if 'test' in content_str or 'pytest' in content_str or 'jest' in content_str:
            patterns.append("testing")
        if 'build' in content_str or 'compile' in content_str:
            patterns.append("build")
        if 'deploy' in content_str:
            patterns.append("deploy")
        if 'docker' in content_str:
            patterns.append("docker")
        if 'sonar' in content_str:
            patterns.append("code-quality")
        if 'kubernetes' in content_str or 'kubectl' in content_str:
            patterns.append("kubernetes")
        if 'terraform' in content_str or 'ansible' in content_str:
            patterns.append("infrastructure")

        return patterns

    def ingest(self):
        """Main ingestion pipeline."""
        print(f"\n{'='*80}")
        print(f"Starting Zenodo Dataset Ingestion")
        print(f"Target: {self.max_workflows} workflows")
        print(f"{'='*80}\n")

        # Step 1: Download dataset
        csv_file = self.download_workflow_histories()

        # Step 2: Parse CSV
        records = self.parse_csv_gz(csv_file)

        # Step 3: Filter and sample
        sampled_records = self.filter_and_sample(records)

        # Step 4: Fetch and process workflows
        print(f"\n[Ingest] Fetching workflow content from GitHub...")
        pages = []
        success_count = 0

        for i, record in enumerate(sampled_records, 1):
            if i % 50 == 0:
                print(f"[Ingest] Progress: {i}/{len(sampled_records)} ({success_count} successful)")

            # Fetch workflow YAML if not in test mode
            if self.skip_github_fetch:
                yaml_content = None
            else:
                yaml_content = self.fetch_workflow_content(record)

            if not yaml_content and not self.skip_github_fetch:
                continue

            analysis = self.analyze_workflow(yaml_content) if yaml_content else {
                "language": "unknown",
                "framework": None,
                "patterns": [],
            }

            # Create KnowledgePage
            page = KnowledgePage(
                page_id=f"zenodo-{record.commit_hash[:8]}-{i}",
                page_type="workflow_example",
                title=record.file_path.split('/')[-1].replace('.yml', '').replace('.yaml', '').replace('_', ' ').replace('-', ' ').title(),
                source=f"zenodo-workflow-histories:{record.repository}",
                tags=[
                    "workflow-example",
                    "zenodo",
                    analysis["language"].lower(),
                    *analysis["patterns"],
                ] + ([analysis["framework"].lower().replace(' ', '-')] if analysis["framework"] else []),
                content=yaml_content[:3000] if yaml_content else f"File: {record.file_path}",
                metadata={
                    "repository": record.repository,
                    "commit_hash": record.commit_hash,
                    "file_path": record.file_path,
                    "language": analysis["language"],
                    "framework": analysis["framework"],
                    "patterns": analysis["patterns"],
                },
            )

            pages.append(page)
            success_count += 1

        print(f"\n[Ingest] Successfully processed {success_count} workflows")

        # Step 5: Save to PageIndex
        print(f"[Ingest] Saving to PageIndex knowledge base...")
        self.knowledge_base.save_pages(pages)

        print(f"\n{'='*80}")
        print(f"Ingestion Complete!")
        print(f"  Total workflows: {success_count}")
        print(f"  Knowledge base: {self.knowledge_base.base_dir}")
        print(f"{'='*80}\n")


def main():
    """Run ingestion script."""
    import argparse

    parser = argparse.ArgumentParser(description="Ingest Zenodo GitHub Actions datasets")
    parser.add_argument("--max-workflows", type=int, default=500, help="Maximum workflows to ingest")
    parser.add_argument("--skip-download", action="store_true", help="Skip download if cache exists")
    parser.add_argument("--skip-github-fetch", action="store_true", help="Skip fetching from GitHub (test mode)")

    args = parser.parse_args()

    ingester = ZenodoDatasetIngester(max_workflows=args.max_workflows)

    if args.skip_github_fetch:
        ingester.skip_github_fetch = True
        print("[Ingest] WARNING: GitHub fetch disabled - will use metadata only")

    ingester.ingest()


if __name__ == "__main__":
    main()
