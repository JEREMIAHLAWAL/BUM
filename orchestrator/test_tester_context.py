import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestrator.run import run_agent
from orchestrator.repo_tools import repo_tree


def read_pipeline_file(name: str) -> str:
    path = PROJECT_ROOT / "pipeline" / name

    if not path.exists():
        return f"[{name} not found]"

    return path.read_text(encoding="utf-8")


handoff = read_pipeline_file("HANDOFF.md")
spec = read_pipeline_file("spec.md")
changes = read_pipeline_file("changes.md")
tree = repo_tree(max_depth=3)

prompt = f"""
This is a READ-ONLY repository context connection test.

You are the Tester agent for Trayne.

You have been given:
1. The Trayne engineering handoff
2. The current Planner spec
3. The current changes log
4. The actual Trayne repository tree

Your task is ONLY to verify that you can understand the real Trayne project context.

DO NOT:
- write code
- propose implementation changes
- modify files
- run tests
- act as Reviewer
- invent files, frameworks, routes, APIs, or architecture

Review the supplied context and repository tree.

If you understand the real Trayne project and can use this context for future tester work, respond with exactly:

TESTER_REPO_CONTEXT_OK

If the context is insufficient, respond with:

TESTER_REPO_CONTEXT_FAIL

and briefly state what is missing.


===== HANDOFF.md =====

{handoff}


===== spec.md =====

{spec}


===== changes.md =====

{changes}


===== TRAYNE REPOSITORY TREE =====

{tree}
"""

response = run_agent("tester", prompt)

print("\n=== TESTER CONTEXT TEST ===\n")
print(response)
