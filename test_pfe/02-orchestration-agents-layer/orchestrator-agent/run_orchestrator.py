from pathlib import Path
import argparse
import json
import os
import sys
from typing import Any, Dict, Optional, Set


def _ensure_utf8_output() -> None:
    """
    On Windows the default console encoding may reject emoji/special chars.
    Reconfigure stdout/stderr to UTF-8 with replacement to avoid crashes.
    """
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        # Best effort; ignore if reconfigure is unavailable
        pass


def _get_agent_output(state: Dict[str, Any], agent_name: str) -> Optional[Dict[str, Any]]:
    agent_outputs = state.get("agent_outputs", {}) if isinstance(state, dict) else {}
    output = agent_outputs.get(agent_name)
    return output if isinstance(output, dict) else None


def _infer_requested_artifacts_with_llm(user_prompt: str, state: Dict[str, Any]) -> Set[str]:
    """
    Use LLM to understand which artifacts the user is requesting.

    This is more intelligent than keyword matching - it understands the intent
    even when the user uses different terms or paraphrases.
    """
    try:
        from src.config import OrchestratorConfig
        from langchain_groq import ChatGroq
        from langchain_core.prompts import PromptTemplate
        from pydantic import SecretStr

        config = OrchestratorConfig()
        api_key = config.LLM_API_KEY

        if not api_key:
            return _infer_requested_artifacts_with_keywords(user_prompt, state)

        llm = ChatGroq(
            api_key=SecretStr(api_key),
            model=config.MODEL_NAME,
            temperature=0
        )

        artifact_prompt = PromptTemplate.from_template(
            "Analyze the user request and determine which DevOps artifacts they are asking for.\n\n"
            "Available artifacts:\n"
            "- yaml: GitHub Actions workflows, CI/CD pipelines, Jenkins pipelines (YAML format)\n"
            "- dockerfile: Dockerfile, container configurations, Docker Compose\n"
            "- terraform: Terraform HCL scripts, Infrastructure-as-Code, cloud resources (AWS, Azure, GCP)\n\n"
            "User Request: {user_prompt}\n\n"
            "Respond ONLY with a JSON object:\n"
            '{{\n'
            '  "requested_artifacts": ["artifact1", "artifact2"],\n'
            '  "reasoning": "Why these artifacts were selected"\n'
            '}}\n\n'
            "If no specific artifacts are mentioned, return an empty array."
        )

        chain = artifact_prompt | llm
        response = chain.invoke({"user_prompt": user_prompt})

        raw_content = response.content
        if isinstance(raw_content, str):
            content = raw_content.strip()
        elif isinstance(raw_content, list):
            content = "".join(
                part if isinstance(part, str) else str(part.get("text", ""))
                for part in raw_content
            ).strip()
        else:
            content = str(raw_content).strip()

        if content.startswith("```json"):
            content = content[7:-3]
        elif content.startswith("```"):
            content = content[3:-3]

        result = json.loads(content.strip())
        requested_artifacts = result.get("requested_artifacts", [])
        requested = set(requested_artifacts)

        # If still empty, fallback to agent-based inference
        if not requested:
            target_agents = state.get("target_agents", []) if isinstance(state, dict) else []
            if "cicd-agent" in target_agents:
                requested.add("yaml")
            if "docker-agent" in target_agents:
                requested.add("dockerfile")
            if "iac-agent" in target_agents:
                requested.add("terraform")

        return requested

    except Exception as e:
        print(f"[Warning] LLM artifact detection failed: {e}. Using keyword fallback.")
        return _infer_requested_artifacts_with_keywords(user_prompt, state)


def _infer_requested_artifacts_with_keywords(user_prompt: str, state: Dict[str, Any]) -> Set[str]:
    """
    Fallback: Use keyword matching when LLM is unavailable.
    """
    prompt = user_prompt.lower()
    requested: Set[str] = set()

    yaml_tokens = ["yaml", "yml", "workflow", "github actions", "gha", "ci", "pipeline"]
    docker_tokens = ["docker", "dockerfile", "container", "image", "compose"]
    terraform_tokens = ["terraform", "hcl", "iac", "infrastructure", "ec2", "s3", "vpc", "aws", "azure", "gcp"]

    if any(token in prompt for token in yaml_tokens):
        requested.add("yaml")
    if any(token in prompt for token in docker_tokens):
        requested.add("dockerfile")
    if any(token in prompt for token in terraform_tokens):
        requested.add("terraform")

    if not requested:
        target_agents = state.get("target_agents", []) if isinstance(state, dict) else []
        if "cicd-agent" in target_agents:
            requested.add("yaml")
        if "docker-agent" in target_agents:
            requested.add("dockerfile")
        if "iac-agent" in target_agents:
            requested.add("terraform")

    return requested


def _infer_requested_artifacts(user_prompt: str, state: Dict[str, Any]) -> Set[str]:
    """
    Main entry point: Try LLM first, fallback to keywords.
    """
    return _infer_requested_artifacts_with_llm(user_prompt, state)


def _print_agent_artifacts(result: Dict[str, Any], user_prompt: str, output_scope: str) -> None:
    state = result.get("state", {}) if isinstance(result, dict) else {}

    cicd = _get_agent_output(state, "cicd-agent")
    docker = _get_agent_output(state, "docker-agent")
    iac = _get_agent_output(state, "iac-agent")
    requested = _infer_requested_artifacts(user_prompt, state)

    print("\n=== Agent Artifacts ===")

    should_print_yaml = output_scope == "all" or "yaml" in requested
    should_print_docker = output_scope == "all" or "dockerfile" in requested
    should_print_terraform = output_scope == "all" or "terraform" in requested

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

    if should_print_terraform:
        if iac and iac.get("status") == "success":
            iac_data = iac.get("data", {})
            if isinstance(iac_data, dict):
                terraform_config = iac_data.get("terraform_config", {})
                if isinstance(terraform_config, dict):
                    # Try to get combined HCL or individual files
                    combined_hcl = terraform_config.get("combined_hcl") or terraform_config.get("get_combined_hcl()")

                    print("\n--- Terraform HCL Scripts ---")

                    # Display individual files if available
                    if terraform_config.get("providers_tf"):
                        print("\n# providers.tf")
                        print(terraform_config.get("providers_tf"))

                    if terraform_config.get("variables_tf"):
                        print("\n# variables.tf")
                        print(terraform_config.get("variables_tf"))

                    if terraform_config.get("main_tf"):
                        print("\n# main.tf")
                        print(terraform_config.get("main_tf"))

                    if terraform_config.get("outputs_tf"):
                        print("\n# outputs.tf")
                        print(terraform_config.get("outputs_tf"))

                    # Display metadata
                    provider = terraform_config.get("provider")
                    resources = terraform_config.get("resources", [])
                    is_valid = terraform_config.get("is_valid", False)

                    print(f"\n--- Terraform Metadata ---")
                    print(f"Provider: {provider}")
                    print(f"Resources: {', '.join(resources) if resources else 'None'}")
                    print(f"Valid: {is_valid}")
                else:
                    print("\n--- Terraform HCL Scripts ---")
                    print("No terraform_config returned by iac-agent.")
            else:
                print("\n--- Terraform HCL Scripts ---")
                print("No data returned by iac-agent.")
        elif iac:
            print("\n--- Terraform HCL Scripts ---")
            print(f"iac-agent did not succeed: {iac.get('message', iac.get('status', 'unknown'))}")

    if output_scope != "all" and not should_print_yaml and not should_print_docker and not should_print_terraform:
        print("No specific artifact requested in prompt; nothing to display.")
    elif not cicd and not docker and not iac:
        print("No agent artifacts found in orchestrator output.")


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
        "--github-url",
        type=str,
        default="",
        help="GitHub repository URL to clone and analyze (optional)",
    )
    parser.add_argument(
        "--output-scope",
        type=str,
        choices=["asked", "all"],
        default="asked",
        help="Show only artifacts asked in prompt (default) or all available artifacts",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        default=False,
        help="Only generate plan, do not execute agents (for human-in-the-loop approval)",
    )
    parser.add_argument(
        "--skip-planner",
        action="store_true",
        default=False,
        help="Skip planner and execute agents directly",
    )
    parser.add_argument(
        "--execute-plan",
        type=str,
        default="",
        help="Execute agents according to provided plan (JSON string from approved plan)",
    )
    # PR creation arguments (optional)
    parser.add_argument(
        "--create-pr",
        action="store_true",
        default=False,
        help="Create a pull request with generated artifacts",
    )
    parser.add_argument(
        "--branch-name",
        type=str,
        default="",
        help="Branch name for the pull request (required if --create-pr is used)",
    )
    parser.add_argument(
        "--pr-title",
        type=str,
        default="Auto-generated changes from Orchestrator",
        help="Pull request title",
    )
    parser.add_argument(
        "--pr-body",
        type=str,
        default="Generated by Orchestrator Agent with AI-powered DevOps automation",
        help="Pull request description/body",
    )
    args = parser.parse_args()

    _ensure_utf8_output()

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
    github_url = args.github_url.strip() if args.github_url.strip() else None

    print("=== Testing Orchestrator (root launcher) ===")
    print(f"Prompt: '{user_prompt}'")
    if repo_path:
        print(f"Repository Path: '{repo_path}'")
    if github_url:
        print(f"GitHub URL: '{github_url}'")
    if args.create_pr:
        print(f"Create PR: Yes")
        print(f"  Branch: '{args.branch_name}'")
        print(f"  Title: '{args.pr_title}'")
    print()

    try:
        orchestrator = Orchestrator()
        
        # Parse execution plan if provided
        execution_plan = None
        if args.execute_plan:
            try:
                execution_plan = json.loads(args.execute_plan)
            except json.JSONDecodeError:
                print("Error: Invalid execution plan JSON")
                return 1
        
        result = orchestrator.process_request(
            user_prompt,
            repository_path=repo_path,
            github_url=github_url,
            create_pr=args.create_pr,
            branch_name=args.branch_name,
            pr_title=args.pr_title,
            pr_body=args.pr_body,
            plan_only=args.plan_only,
            skip_planner=args.skip_planner,
            execution_plan=execution_plan,
        )
        status = result.get("status", "unknown") if isinstance(result, dict) else "unknown"
        errors = result.get("state", {}).get("errors", []) if isinstance(result, dict) else []
        
        # Output full result as JSON for Streamlit parsing
        print("\n=== JSON OUTPUT ===")
        print(json.dumps(result, default=str))
        print("=== END JSON OUTPUT ===")
        
        print("\n=== Orchestration Summary ===")
        print(f"Status: {status}")
        if result.get("plan_only"):
            print("Mode: Plan Only (awaiting approval)")
        if result.get("used_planner"):
            print(f"Planner: Used (complexity: {result.get('complexity_score', 0)})")
        else:
            print(f"Planner: Not used (complexity: {result.get('complexity_score', 0)})")
        if errors:
            print(f"Errors: {len(errors)}")
            for err in errors[:5]:
                print(f"- {err}")

        if not args.plan_only:
            _print_agent_artifacts(result, user_prompt=user_prompt, output_scope=args.output_scope)
        return 0
    except ValueError as error:
        print(f"Configuration Error: {error}")
        print("Please set GROQ_API_KEY in orchestrator-agent/.env")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
