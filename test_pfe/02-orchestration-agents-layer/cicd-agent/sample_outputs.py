"""Sample outputs and expected workflow examples"""

PYTHON_WORKFLOW_EXAMPLE = """name: Python Tests
on:
  push:
    branches:
      - main
      - develop
  pull_request:
    branches:
      - main
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.9', '3.11']
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
      - run: pip install -e '.[test]'
      - run: pytest --cov --cov-report=xml
      - uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
"""

NODEJS_WORKFLOW_EXAMPLE = """name: Node.js CI
on:
  push:
    branches:
      - main
      - develop
  pull_request:
    branches:
      - main
jobs:
  build:
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
      - run: npm run lint
      - run: npm test -- --coverage
      - run: npm run build
"""

DOCKER_WORKFLOW_EXAMPLE = """name: Docker Build and Push
on:
  push:
    branches:
      - main
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v2
      - uses: docker/setup-qemu-action@v2
      - uses: docker/login-action@v2
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v4
        with:
          context: .
          push: true
          tags: ghcr.io/${{ github.repository }}:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max
"""

FULL_STACK_WORKFLOW_EXAMPLE = """name: Complete CI/CD Pipeline
on:
  push:
    branches:
      - main
      - develop
  pull_request:
    branches:
      - main
env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}
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
      - run: pytest --cov --cov-report=xml
      - uses: codecov/codecov-action@v3
  
  build:
    needs: test
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v2
      - uses: docker/login-action@v2
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v4
        with:
          context: .
          push: true
          tags: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
  
  deploy-staging:
    needs: build
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v4
      - run: |
          echo "Deploying to staging..."
          echo "Image: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}"
  
  deploy-production:
    needs: build
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    steps:
      - uses: actions/checkout@v4
      - run: |
          echo "Deploying to production..."
          echo "Image: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}"
"""

LOCK_FILE_EXAMPLE = """version: '1.0.0'
workflow: create-workflow-workflow
generated: '2024-01-15T10:30:00.123456'
checksum: a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
dependencies:
  actions/checkout: v4
  actions/setup-python: v4
  actions/setup-node: v4
  docker/setup-buildx-action: v2
  codecov/codecov-action: v3
"""

VALIDATION_REPORT_EXAMPLE = """
Workflow YAML Validation Report
================================

File: test-workflow.yml
Generated: 2024-01-15 10:30:00

✓ OVERALL STATUS: PASSED

Basic Validation
- ✓ Valid YAML syntax
- ✓ Required fields present (name, on, jobs)
- ✓ At least one job defined
- ✓ All jobs have 'runs-on' or 'container'
- ✓ All jobs have 'steps' defined
- ✓ All steps have 'uses' or 'run'

Schema Validation
- ✓ 'on' triggers valid
- ✓ Job configurations valid
- ✓ Step definitions valid
- ✓ Environment variables valid

Best Practices (Warnings: 2)
- ⚠ Job 'test' should use caching for dependencies
- ⚠ Action 'setup-python@v4' should be pinned to specific SHA (following semver is acceptable)

Performance Suggestions (1)
- 💡 Consider using matrix strategy for parallel test execution

Security Audit
✓ Security Status: SAFE
- ✓ No dangerous patterns detected
- ✓ All actions from verified sources
- ✓ No secret exposure in output
- ✓ Appropriate permissions defined (contents: read)

Summary
-------
Total Steps: 5
Total Actions: 4
Estimated Execution Time: 3-5 minutes
Permissions: LIMITED (contents: read)
"""

def print_examples():
    """Print all example outputs"""
    print("\n" + "="*80)
    print("SAMPLE WORKFLOW OUTPUTS")
    print("="*80)
    
    examples = {
        "Python Testing Workflow": PYTHON_WORKFLOW_EXAMPLE,
        "Node.js Testing Workflow": NODEJS_WORKFLOW_EXAMPLE,
        "Docker Build & Push": DOCKER_WORKFLOW_EXAMPLE,
        "Complete CI/CD Pipeline": FULL_STACK_WORKFLOW_EXAMPLE,
    }
    
    for title, content in examples.items():
        print(f"\n\n{'─'*80}")
        print(f"{title}")
        print(f"{'─'*80}\n")
        print(content)
    
    print(f"\n\n{'─'*80}")
    print("Lock File Example (.lock.yml)")
    print(f"{'─'*80}\n")
    print(LOCK_FILE_EXAMPLE)
    
    print(f"\n\n{'─'*80}")
    print("Validation Report Example")
    print(f"{'─'*80}\n")
    print(VALIDATION_REPORT_EXAMPLE)

if __name__ == "__main__":
    print_examples()
