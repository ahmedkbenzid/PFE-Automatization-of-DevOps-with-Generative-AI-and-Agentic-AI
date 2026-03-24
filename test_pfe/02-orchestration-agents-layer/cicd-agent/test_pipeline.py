#!/usr/bin/env python3
"""
Example test script for CI/CD Agent Pipeline
This demonstrates how to use the pipeline with the Groq LLM
"""

import sys
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.config import Config
from src.models.types import UserRequest, RequestType
from src.pipeline import CICDPipeline

def print_result(result):
    """Pretty print pipeline result"""
    print("\n" + "="*80)
    print("WORKFLOW GENERATION RESULT")
    print("="*80)
    
    if result.success:
        print("\n✓ SUCCESS\n")
        
        print("Generated Workflow YAML:")
        print("-" * 80)
        print(result.workflow_yaml)
        print("-" * 80)
        
        if result.validation_result:
            print(f"\nValidation Status: {'PASSED' if result.validation_result.is_valid else 'FAILED'}")
            if result.validation_result.warnings:
                print(f"Warnings: {len(result.validation_result.warnings)}")
                for warning in result.validation_result.warnings[:5]:
                    print(f"  - {warning}")
            if result.validation_result.suggestions:
                print(f"Suggestions: {len(result.validation_result.suggestions)}")
                for suggestion in result.validation_result.suggestions[:3]:
                    print(f"  - {suggestion}")
        
        if result.security_audit:
            print(f"\nSecurity Audit: {'SAFE' if result.security_audit.is_safe else 'RISKS FOUND'}")
            if result.security_audit.risks:
                print(f"Risks: {len(result.security_audit.risks)}")
                for risk in result.security_audit.risks[:3]:
                    severity = risk.get('severity', 'unknown').upper()
                    desc = risk.get('description', 'Unknown')
                    print(f"  [{severity}] {desc}")
        
        if result.lock_file:
            print(f"\n✓ Lock file generated")
            print(f"  Workflow: {result.lock_file.workflow_name}")
            print(f"  Checksum: {result.lock_file.checksum[:12]}...")
            print(f"  Dependencies: {len(result.lock_file.dependencies)}")
        
        print(f"\nMetrics:")
        print(f"  Generation Latency: {result.generation_latency_ms:.0f}ms")
        print(f"  Attempts: {result.attempts}")
    
    else:
        print("\n✗ FAILED\n")
        print("Errors:")
        for error in result.errors:
            print(f"  - {error}")

def test_python_workflow():
    """Test with a Python project request"""
    print("\n" + "="*80)
    print("TEST 1: Python Project - Generate Testing Workflow")
    print("="*80)
    
    request = UserRequest(
        text="I need a CI/CD workflow that runs pytest on Python code, tests on multiple Python versions (3.9 and 3.11), and caches pip dependencies",
        request_type=RequestType.CREATE_WORKFLOW,
    )
    
    pipeline = CICDPipeline()
    
    result = pipeline.process_request(request)
    print_result(result)
    
    return result

def test_nodejs_workflow():
    """Test with a Node.js project request"""
    print("\n" + "="*80)
    print("TEST 2: Node.js Project - Generate Testing & Build Workflow")
    print("="*80)
    
    request = UserRequest(
        text="Create a GitHub Actions workflow that tests a Node.js application on multiple Node versions (16, 18, 20), runs linting, and caches node_modules",
        request_type=RequestType.CREATE_WORKFLOW,
    )
    
    pipeline = CICDPipeline()
    
    result = pipeline.process_request(request)
    print_result(result)
    
    return result

def test_docker_workflow():
    """Test with Docker deployment request"""
    print("\n" + "="*80)
    print("TEST 3: Docker - Build and Push Workflow")
    print("="*80)
    
    request = UserRequest(
        text="Generate a workflow that builds a Docker image on every push to main and pushes it to a registry",
        request_type=RequestType.CREATE_WORKFLOW,
    )
    
    pipeline = CICDPipeline()
    
    result = pipeline.process_request(request)
    print_result(result)
    
    return result

def test_with_datasets():
    """Test dataset functionality"""
    print("\n" + "="*80)
    print("TEST 4: Dataset Exploration")
    print("="*80)
    
    pipeline = CICDPipeline()
    dataset_manager = pipeline.dataset_manager
    
    print("\nAvailable Datasets:")
    all_datasets = dataset_manager.get_all_datasets()
    for name, info in all_datasets.items():
        print(f"\n✓ {name}")
        print(f"  Description: {info.get('description', 'N/A')}")
        print(f"  Size: {info.get('size', 'N/A')}")
        print(f"  Source: {info.get('source', 'N/A')}")
    
    print("\n\nDataset Statistics:")
    stats = dataset_manager.get_dataset_statistics()
    print(json.dumps(stats, indent=2))
    
    print("\n\nSample Workflow Examples:")
    for example_id, example in list(dataset_manager.examples.items())[:3]:
        print(f"\n  - {example.name} (ID: {example_id})")
        print(f"    Language: {example.language}")
        print(f"    Source: {example.source}")
        print(f"    Success Rate: {example.success_rate:.0%}")

def test_custom_prompt_interactive():
    """Ask user for a custom prompt and run the agent."""
    print("\n" + "="*80)
    print("TEST 5: Custom Prompt (Interactive)")
    print("="*80)

    use_custom_prompt = input("Do you want to send a custom prompt to the agent? (y/n): ").strip().lower()
    if use_custom_prompt not in {"y", "yes"}:
        print("Skipping custom prompt test.")
        return None

    user_text = input("Enter your CI/CD request: ").strip()
    if not user_text:
        print("No prompt entered. Skipping custom prompt test.")
        return None

    request = UserRequest(
        text=user_text,
        request_type=RequestType.CREATE_WORKFLOW,
    )

    pipeline = CICDPipeline()
    result = pipeline.process_request(request)
    print_result(result)
    return result

def print_metrics(pipeline):
    """Print pipeline metrics"""
    metrics = pipeline.get_metrics()
    
    print("\n" + "="*80)
    print("PIPELINE METRICS")
    print("="*80)
    
    print(f"\nTotal Requests Processed: {metrics['total_requests']}")
    print(f"Successful Workflows: {metrics['successful_workflows']}")
    print(f"Failed Workflows: {metrics['failed_workflows']}")
    print(f"Success Rate: {metrics['success_rate']:.1%}")
    print(f"Average Generation Latency: {metrics['avg_generation_latency_ms']:.0f}ms")
    print(f"Avg Attempts per Request: {metrics['total_attempts'] / max(metrics['total_requests'], 1):.1f}")

def main():
    """Main test function"""
    has_api_key = bool(Config.GROQ_API_KEY)
    
    print("\n" + "="*80)
    print("CI/CD AGENT PIPELINE - TEST SUITE")
    print("="*80)
    print(f"\nConfiguration:")
    print(f"  LLM Model: {Config.GROQ_MODEL}")
    print(f"  Max Tokens: {Config.GROQ_MAX_TOKENS}")
    print(f"  Temperature: {Config.GROQ_TEMPERATURE}")
    print(f"  GROQ_API_KEY set: {'Yes' if has_api_key else 'No'}")
    
    try:
        # Run tests
        print("\n" + "="*80)
        print("Running Tests...")
        print("="*80)
        
        # Test 1: Explore datasets
        test_with_datasets()

        if has_api_key:
            # Uncomment these when you want full generation tests
            result1 = test_python_workflow()
            # result2 = test_nodejs_workflow()
            # result3 = test_docker_workflow()
            test_custom_prompt_interactive()
            print("\nGROQ_API_KEY detected. You can uncomment generation tests in main().")
        else:
            print("\nWARNING: GROQ_API_KEY not set. Running dataset-only tests.")
            print("Set key in .env to enable LLM workflow generation tests:")
            print("  GROQ_API_KEY=your_api_key_here")
        
        print("\n" + "="*80)
        print("Tests completed!")
        print("="*80)
        
        print("\n💡 TIP: To test workflow generation, uncomment the test functions")
        print("   in main() and ensure you have a valid GROQ_API_KEY.")
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
