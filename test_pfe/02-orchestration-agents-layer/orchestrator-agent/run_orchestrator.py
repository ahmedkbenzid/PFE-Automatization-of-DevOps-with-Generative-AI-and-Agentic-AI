from pathlib import Path
import argparse
import os
import sys
from typing import Any, Dict, Optional, Set


def _get_agent_output(state: Dict[str, Any], agent_name: str) -> Optional[Dict[str, Any]]:
    agent_outputs = state.get("agent_outputs", {}) if isinstance(state, dict) else {}
    output = agent_outputs.get(agent_name)
    return output if isinstance(output, dict) else None


def _infer_requested_artifacts(user_prompt: str, state: Dict[str, Any]) -> Set[str]:
    prompt = user_prompt.lower()
    requested: Set[str] = set()

    yaml_tokens = ["yaml", "yml", "workflow", "github actions", "gha", "ci", "pipeline"]
    docker_tokens = ["docker", "dockerfile", "container", "image", "compose"]

    if any(token in prompt for token in yaml_tokens):
        requested.add("yaml")
    if any(token in prompt for token in docker_tokens):
        requested.add("dockerfile")

    # If prompt is ambiguous, infer from routed target agents.
    if not requested:
        target_agents = state.get("target_agents", []) if isinstance(state, dict) else []
        if "cicd-agent" in target_agents:
            requested.add("yaml")
        if "docker-agent" in target_agents:
            requested.add("dockerfile")

    return requested


def _print_agent_artifacts(result: Dict[str, Any], user_prompt: str, output_scope: str) -> None:
    state = result.get("state", {}) if isinstance(result, dict) else {}

    cicd = _get_agent_output(state, "cicd-agent")
    docker = _get_agent_output(state, "docker-agent")
    requested = _infer_requested_artifacts(user_prompt, state)

    print("\n=== Agent Artifacts ===")

    should_print_yaml = output_scope == "all" or "yaml" in requested
    should_print_docker = output_scope == "all" or "dockerfile" in requested

    if should_print_yaml:
        if cicd and cicd.get("status") == "success":
            cicd_data = cicd.get("data", {})
            workflow_yaml = cicd_data.get("workflow_yaml")
            if isinstance(workflow_yaml, str) and workflow_yaml.strip():
                print("\n--- GitHub Actions Workflow (.yaml) ---")
                print(workflow_yaml)
            else:
                print("\n--- GitHub Actions Workflow (.yaml) ---")
                print("No workflow YAML returned by cicd-agent.")
        elif cicd:
            print("\n--- GitHub Actions Workflow (.yaml) ---")
            print(f"cicd-agent did not succeed: {cicd.get('message', cicd.get('status', 'unknown'))}")

    if should_print_docker:
        if docker and docker.get("status") == "success":
            docker_data = docker.get("data", {})
            dockerfile_text = (
                docker_data.get("configuration", {}).get("dockerfile_content")
                if isinstance(docker_data, dict)
                else None
            )
            if isinstance(dockerfile_text, str) and dockerfile_text.strip():
                print("\n--- Dockerfile (.txt) ---")
                print(dockerfile_text)
            else:
                print("\n--- Dockerfile (.txt) ---")
                print("No Dockerfile content returned by docker-agent.")
        elif docker:
            print("\n--- Dockerfile (.txt) ---")
            print(f"docker-agent did not succeed: {docker.get('message', docker.get('status', 'unknown'))}")

    if output_scope != "all" and not should_print_yaml and not should_print_docker:
        print("No specific artifact requested in prompt; nothing to display.")
    elif not cicd and not docker:
        print("No cicd-agent or docker-agent artifacts found in orchestrator output.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the orchestrator with a user prompt")
    parser.add_argument("--prompt", type=str, default="", help="User prompt to route through orchestrator")
    parser.add_argument(
        "--repo-path",
        type=str,
        default="",
        help="Target repository path used by downstream agents",
    )
    parser.add_argument(
        "--output-scope",
        type=str,
        choices=["asked", "all"],
        default="asked",
        help="Show only artifacts asked in prompt (default) or all available artifacts",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    os.chdir(project_root)

    from src.orchestrator import Orchestrator

    user_prompt = args.prompt.strip()
    if not user_prompt:
        print("Enter your prompt for the orchestrator:")
        user_prompt = input("> ").strip()

    if not user_prompt:
        print("No prompt provided. Exiting.")
        return 1

    repo_path = args.repo_path.strip() if args.repo_path.strip() else None

    print("=== Testing Orchestrator (root launcher) ===")
    print(f"Prompt: '{user_prompt}'")
    if repo_path:
        print(f"Repository Path: '{repo_path}'")
    print()

    try:
        orchestrator = Orchestrator()
        result = orchestrator.process_request(user_prompt, repository_path=repo_path)
        status = result.get("status", "unknown") if isinstance(result, dict) else "unknown"
        errors = result.get("state", {}).get("errors", []) if isinstance(result, dict) else []
        print("\n=== Orchestration Summary ===")
        print(f"Status: {status}")
        if errors:
            print(f"Errors: {len(errors)}")
            for err in errors[:5]:
                print(f"- {err}")

        _print_agent_artifacts(result, user_prompt=user_prompt, output_scope=args.output_scope)
        return 0
    except ValueError as error:
        print(f"Configuration Error: {error}")
        print("Please set GROQ_API_KEY in orchestrator-agent/.env")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
