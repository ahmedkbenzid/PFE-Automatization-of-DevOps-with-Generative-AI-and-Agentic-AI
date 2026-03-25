"""
LangGraph Orchestrator - Graph Construction and Compilation.

This module builds the orchestration graph that coordinates
the flow between guardrails, routing, and agent execution.
"""

from typing import Literal
from langgraph.graph import StateGraph, START, END

from .graph_state import OrchestratorState, create_initial_state, state_to_legacy_format
from .graph_nodes import (
    guardrails_node,
    repo_analysis_node,
    routing_node,
    agent_execution_node,
    cleanup_node,
    initialize_components,
)


def should_continue_after_guardrails(state: OrchestratorState) -> Literal["repo_analysis", "cleanup"]:
    """
    Conditional edge: decide whether to continue or stop after guardrails.

    If guardrails pass, continue to repo analysis.
    If guardrails fail, skip to cleanup.
    """
    if state.get("guardrails_passed", False):
        return "repo_analysis"
    else:
        return "cleanup"


def build_orchestrator_graph() -> StateGraph:
    """
    Build the LangGraph orchestrator graph.

    Graph Structure:
    ================

                    ┌─────────────┐
                    │   START     │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ guardrails  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
           ┌────────┤  condition  ├────────┐
           │        └─────────────┘        │
           │ (passed)             (blocked)│
           │                               │
    ┌──────▼──────┐                        │
    │repo_analysis│                        │
    └──────┬──────┘                        │
           │                               │
    ┌──────▼──────┐                        │
    │   routing   │                        │
    └──────┬──────┘                        │
           │                               │
    ┌──────▼──────┐                        │
    │  execution  │                        │
    └──────┬──────┘                        │
           │                               │
           └───────────┬───────────────────┘
                       │
                ┌──────▼──────┐
                │   cleanup   │
                └──────┬──────┘
                       │
                ┌──────▼──────┐
                │     END     │
                └─────────────┘

    Returns:
        Compiled LangGraph StateGraph
    """
    # Initialize components
    initialize_components()

    # Create the graph with our state type
    graph = StateGraph(OrchestratorState)

    # Add nodes
    graph.add_node("guardrails", guardrails_node)
    graph.add_node("repo_analysis", repo_analysis_node)
    graph.add_node("routing", routing_node)
    graph.add_node("execution", agent_execution_node)
    graph.add_node("cleanup", cleanup_node)

    # Add edges
    # START -> guardrails
    graph.add_edge(START, "guardrails")

    # guardrails -> conditional branch
    graph.add_conditional_edges(
        "guardrails",
        should_continue_after_guardrails,
        {
            "repo_analysis": "repo_analysis",
            "cleanup": "cleanup",
        }
    )

    # repo_analysis -> routing -> execution -> cleanup -> END
    graph.add_edge("repo_analysis", "routing")
    graph.add_edge("routing", "execution")
    graph.add_edge("execution", "cleanup")
    graph.add_edge("cleanup", END)

    return graph


def compile_orchestrator():
    """
    Build and compile the orchestrator graph.

    Returns:
        Compiled graph ready for invocation
    """
    graph = build_orchestrator_graph()
    return graph.compile()


# Create a singleton compiled graph for efficiency
_compiled_graph = None


def get_compiled_graph():
    """
    Get the compiled graph, building it if necessary.

    This uses a singleton pattern to avoid rebuilding the graph
    on every request.
    """
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = compile_orchestrator()
    return _compiled_graph


def run_orchestrator(
    user_prompt: str,
    repository_path: str = None,
    github_url: str = None,
) -> dict:
    """
    Main entry point for running the orchestrator.

    This function creates the initial state, runs the graph,
    and returns results in the legacy format for backward compatibility.

    Args:
        user_prompt: The user's request text
        repository_path: Optional local path to repository
        github_url: Optional GitHub URL to clone

    Returns:
        Dictionary with status and state in legacy format
    """
    # Create initial state
    initial_state = create_initial_state(
        user_prompt=user_prompt,
        repository_path=repository_path,
        github_url=github_url,
    )

    # Get the compiled graph
    graph = get_compiled_graph()

    # Run the graph
    final_state = graph.invoke(initial_state)

    # Convert to legacy format for backward compatibility
    return state_to_legacy_format(final_state)


def visualize_graph():
    """
    Generate a visualization of the orchestrator graph.

    Returns:
        Mermaid diagram string (can be rendered on mermaid.live)
    """
    graph = build_orchestrator_graph()
    try:
        return graph.get_graph().draw_mermaid()
    except Exception:
        return "Graph visualization not available"


if __name__ == "__main__":
    # Test the graph visualization
    print("=== Orchestrator Graph Structure ===")
    print(visualize_graph())

    # Test basic execution
    print("\n=== Test Execution ===")
    result = run_orchestrator(
        user_prompt="Create a simple CI/CD pipeline for a Python project"
    )
    print(f"Status: {result.get('status')}")
    print(f"Errors: {result.get('state', {}).get('errors', [])}")
