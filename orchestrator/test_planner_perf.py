import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))





PIPELINE_DIR = PROJECT_ROOT / "pipeline"


def read_pipeline_file(name: str) -> str:
    path = PIPELINE_DIR / name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def run_planner_perf_test():
    from orchestrator.run import run_agent
    from orchestrator.repo_tools import repo_tree

    handoff = read_pipeline_file("HANDOFF.md")
    tree = repo_tree()

    shared_context = f"""
TRAYNE ENGINEERING HANDOFF:

{handoff}

CURRENT TRAYNE REPOSITORY TREE:

{tree}
"""

    task = "Create a simple placeholder Profile screen for Trayne."

    planner_prompt = f"""
{shared_context}

USER TASK:

{task}

Create the implementation specification for this task.

Respect the actual Trayne architecture.
Do not invent unsupported infrastructure.

Return the complete contents that should be stored in:

pipeline/spec.md
"""

    handoff_chars = len(handoff)
    tree_chars = len(tree)
    prompt_chars = len(planner_prompt)

    print("=== PLANNER PERFORMANCE MEASUREMENT ===")
    print(f"HANDOFF.md characters: {handoff_chars}")
    print(f"Repository tree characters: {tree_chars}")
    print(f"Total prompt characters: {prompt_chars}")

    print("\nPLANNER_STARTED", flush=True)
    t0 = time.time()
    try:
        response = run_agent("planner", planner_prompt)
        duration = time.time() - t0
        resp_chars = len(response)
        print("PLANNER_COMPLETE", flush=True)
        print(f"\nPlanner execution duration: {duration:.2f}s")
        print(f"Response character count: {resp_chars}")
        print("Exit status: SUCCESS (0)")
    except Exception as exc:
        duration = time.time() - t0
        print(f"\nPLANNER_FAILED after {duration:.2f}s", flush=True)
        print(f"Error: {exc}")
        print("Exit status: ERROR (1)")
        sys.exit(1)


def main():
    run_planner_perf_test()


if __name__ == "__main__":
    main()
