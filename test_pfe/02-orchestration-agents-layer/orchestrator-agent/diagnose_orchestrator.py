#!/usr/bin/env python3
"""
Diagnostic: Test orchestrator components separately to find bottleneck.
"""

import sys
import time
from pathlib import Path

orchestrator_path = Path(__file__).parent
sys.path.insert(0, str(orchestrator_path / "src"))

from src.guardrails import Guardrails
from src.intent_router import IntentRouter
from src.config import OrchestratorConfig

def test_guardrails():
    """Test guardrails component."""
    config = OrchestratorConfig()
    print("Testing Guardrails...")
    start = time.time()

    guardrails = Guardrails(api_key=config.LLM_API_KEY, model_name=config.MODEL_NAME)
    result = guardrails.validate_input("github actions workflow for build and test")

    elapsed = time.time() - start
    print(f"  ✓ Guardrails: {elapsed:.1f}s - {result['is_allowed']}")
    return elapsed

def test_intent_router():
    """Test intent router."""
    config = OrchestratorConfig()
    print("Testing Intent Router...")
    start = time.time()

    router = IntentRouter(api_key=config.LLM_API_KEY, model_name=config.MODEL_NAME)
    result = router.route("github actions workflow for build and test")

    elapsed = time.time() - start
    print(f"  ✓ Intent Router: {elapsed:.1f}s - Primary: {result['primary_agent']}")
    return elapsed

def test_repo_analysis():
    """Test repository analysis (GitHub API)."""
    from src.repo_analyzer import RepoAnalyzer

    print("Testing Repository Analysis...")
    start = time.time()

    analyzer = RepoAnalyzer()
    ctx = analyzer.analyze(github_url="https://github.com/onsnasri/ImmoApp")

    elapsed = time.time() - start
    print(f"  ✓ Repo Analysis: {elapsed:.1f}s - Languages: {ctx.languages}")
    return elapsed

def main():
    print("\n" + "=" * 60)
    print("Orchestrator Component Diagnostics")
    print("=" * 60 + "\n")

    try:
        t1 = test_guardrails()
        print()
        t2 = test_intent_router()
        print()
        t3 = test_repo_analysis()

        print("\n" + "=" * 60)
        print("Performance Summary:")
        print(f"  Guardrails:       {t1:.1f}s")
        print(f"  Intent Router:    {t2:.1f}s")
        print(f"  Repo Analysis:    {t3:.1f}s")
        print(f"  Total (no CICD):  {t1+t2+t3:.1f}s")
        print("=" * 60)
        print("\nNote: CICD agent execution NOT tested (add 120s+ more)")
        print("\n")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
