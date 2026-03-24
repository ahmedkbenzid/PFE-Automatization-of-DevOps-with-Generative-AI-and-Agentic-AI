"""Dataset management for CI/CD Agent."""
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.datasets.pageindex_knowledge_base import KnowledgePage, PageIndexKnowledgeBase


@dataclass
class WorkflowExample:
    """Example workflow from dataset."""

    id: str
    name: str
    trigger: str
    yaml_content: str
    language: str
    source: str
    success_rate: float


class DatasetManager:
    """Manage training/reference datasets and indexed knowledge pages."""

    def __init__(self):
        self.datasets: Dict[str, Dict[str, Any]] = {}
        self.examples: Dict[str, WorkflowExample] = {}
        knowledge_dir = os.path.join(os.path.dirname(__file__), "knowledge_base")
        self.knowledge_base = PageIndexKnowledgeBase(knowledge_dir)
        self._initialize_datasets()

    def _initialize_datasets(self) -> None:
        """Initialize dataset references and examples."""
        self.datasets["gha-dataset"] = {
            "name": "GitHub Actions Workflows Dataset",
            "description": "Collection of real GitHub Actions workflows from popular repositories",
            "size": "10k workflows",
            "source": "GitHub public repositories",
            "languages": ["Python", "JavaScript", "Java", "Go", "Ruby", "Rust"],
            "categories": ["test", "build", "deploy", "release"],
        }

        self.datasets["workflow-histories"] = {
            "name": "GitHub Actions Workflow Histories",
            "description": "Historical execution data of workflows with success/failure metrics",
            "size": "100k execution records",
            "source": "GitHub Actions API logs",
            "metrics": ["execution_time", "success_rate", "retry_count"],
            "date_range": "2020-2024",
        }

        self.datasets["ebamic"] = {
            "name": "Example-Based Automatic Migration of Continuous Integration Systems (EBAMIC)",
            "description": "Workflows migrated from other CI/CD platforms to GitHub Actions",
            "size": "5k workflow migrations",
            "source": "CI/CD system migration studies",
            "platforms": ["Jenkins", "Travis CI", "CircleCI", "GitLab CI", "Azure Pipelines"],
            "patterns": ["build", "test", "deploy", "security_scan"],
        }

        self._load_sample_examples()
        self.scrape_and_index_datasets()

    def _load_sample_examples(self) -> None:
        """Load sample workflow examples."""
        self.examples["python-test"] = WorkflowExample(
            id="py-test-001",
            name="Python Unit Tests",
            trigger="push,pull_request",
            yaml_content="""name: Python Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.9', '3.11']
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
      - run: pip install -e '.[test]'
      - run: pytest --cov""",
            language="Python",
            source="gha-dataset",
            success_rate=0.95,
        )

        self.examples["nodejs-test"] = WorkflowExample(
            id="js-test-001",
            name="Node.js Tests",
            trigger="push,pull_request",
            yaml_content="""name: Node.js Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        node-version: ['16', '18', '20']
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node-version }}
          cache: npm
      - run: npm ci
      - run: npm test""",
            language="JavaScript",
            source="gha-dataset",
            success_rate=0.92,
        )

        self.examples["docker-build"] = WorkflowExample(
            id="docker-001",
            name="Docker Build and Push",
            trigger="push",
            yaml_content="""name: Docker Build
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v2
      - uses: docker/build-push-action@v4
        with:
          context: .
          push: false
          tags: myapp:latest""",
            language="Docker",
            source="gha-dataset",
            success_rate=0.88,
        )

        self.examples["jenkins-migration"] = WorkflowExample(
            id="migrate-jenkins-001",
            name="Migrated from Jenkins Pipeline",
            trigger="push,pull_request",
            yaml_content="""name: Migrated CI
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: chmod +x scripts/build.sh && scripts/build.sh
  test:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: chmod +x scripts/test.sh && scripts/test.sh
  deploy:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: chmod +x scripts/deploy.sh && scripts/deploy.sh""",
            language="Mixed",
            source="ebamic",
            success_rate=0.85,
        )

        self.examples["springboot-sonarqube"] = WorkflowExample(
            id="java-sonar-001",
            name="Spring Boot Build, Test and SonarQube Analysis",
            trigger="push,pull_request",
            yaml_content="""name: Spring Boot CI
on: [push, pull_request]
jobs:
  build-test-sonar:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          java-version: '17'
          distribution: temurin
          cache: maven
      - name: Build and test
        run: mvn -B clean verify
      - name: SonarQube scan
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ secrets.SONAR_HOST_URL }}
        run: mvn -B sonar:sonar -Dsonar.host.url=$SONAR_HOST_URL -Dsonar.token=$SONAR_TOKEN""",
            language="Java",
            source="gha-dataset",
            success_rate=0.93,
        )

        self.examples["springboot-full-cd-monitoring"] = WorkflowExample(
            id="java-cd-ansible-k8s-001",
            name="Spring Boot CI/CD with SonarQube, Ansible, Kubernetes, Prometheus and Grafana",
            trigger="push",
            yaml_content="""name: Spring Boot CI/CD
on:
  push:
    branches: [main]
jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          java-version: '17'
          distribution: temurin
          cache: maven
      - run: mvn -B clean verify
      - uses: SonarSource/sonarqube-scan-action@v5
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ secrets.SONAR_HOST_URL }}
      - uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ secrets.DOCKERHUB_USERNAME }}/spring-boot-microservice:latest
  deploy:
    needs: ci
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install ansible
      - run: ansible-playbook deploy/ansible/deploy-k8s.yml -e image=${{ secrets.DOCKERHUB_USERNAME }}/spring-boot-microservice:latest
  monitoring:
    needs: deploy
    runs-on: ubuntu-latest
    steps:
      - uses: azure/setup-helm@v4
      - run: |
          helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
          helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack --namespace monitoring --create-namespace""",
            language="Java",
            source="gha-dataset",
            success_rate=0.9,
        )

    def get_dataset(self, dataset_name: str) -> Optional[Dict[str, Any]]:
        return self.datasets.get(dataset_name)

    def get_all_datasets(self) -> Dict[str, Dict[str, Any]]:
        return self.datasets

    def get_example(self, example_key: str) -> Optional[WorkflowExample]:
        return self.examples.get(example_key)

    def find_similar_examples(self, language: str, trigger: Optional[str] = None) -> List[WorkflowExample]:
        results: List[WorkflowExample] = []
        for example in self.examples.values():
            if language.lower() in example.language.lower():
                if trigger is None or trigger in example.trigger:
                    results.append(example)
        return results

    def get_dataset_statistics(self) -> Dict[str, Any]:
        return {
            "total_datasets": len(self.datasets),
            "total_examples": len(self.examples),
            "datasets_info": list(self.datasets.keys()),
            "example_languages": list({ex.language for ex in self.examples.values()}),
            "example_sources": list({ex.source for ex in self.examples.values()}),
        }

    def get_examples_by_pattern(self, pattern: str) -> List[WorkflowExample]:
        query_tokens = self._tokenize(pattern)
        if not query_tokens:
            return []

        scored: List[tuple[int, WorkflowExample]] = []
        for example in self.examples.values():
            searchable = f"{example.name} {example.language} {example.trigger} {example.yaml_content}"
            example_tokens = self._tokenize(searchable)
            overlap = len(query_tokens.intersection(example_tokens))
            if overlap > 0:
                scored.append((overlap, example))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [example for _, example in scored]

    def _tokenize(self, text: str) -> set[str]:
        return set(re.findall(r"[a-zA-Z0-9_\-.]+", text.lower()))

    def scrape_and_index_datasets(self) -> None:
        """Scrape dataset metadata/examples and save to page-index knowledge base."""
        pages: List[KnowledgePage] = []

        for dataset_key, dataset_info in self.datasets.items():
            pages.append(
                KnowledgePage(
                    page_id=f"dataset-{dataset_key}",
                    page_type="dataset",
                    title=dataset_info.get("name", dataset_key),
                    source=dataset_key,
                    tags=[dataset_key, "dataset", "metadata"],
                    content=json.dumps(dataset_info, indent=2),
                    metadata={"dataset_key": dataset_key},
                )
            )

        for example_key, example in self.examples.items():
            content = (
                f"name: {example.name}\n"
                f"trigger: {example.trigger}\n"
                f"language: {example.language}\n"
                f"source: {example.source}\n"
                f"success_rate: {example.success_rate}\n\n"
                f"yaml:\n{example.yaml_content}"
            )
            tags = [
                "workflow-example",
                example.language.lower(),
                example.source,
                *[token.strip() for token in example.trigger.split(",") if token.strip()],
            ]
            pages.append(
                KnowledgePage(
                    page_id=f"example-{example_key}",
                    page_type="workflow_example",
                    title=example.name,
                    source=example.source,
                    tags=tags,
                    content=content,
                    metadata={
                        "example_id": example.id,
                        "language": example.language,
                        "trigger": example.trigger,
                        "success_rate": example.success_rate,
                    },
                )
            )

        self.knowledge_base.save_pages(pages)

    def retrieve_knowledge(self, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Retrieve relevant snippets from page-index knowledge base."""
        return self.knowledge_base.query(query_text, top_k=top_k)
