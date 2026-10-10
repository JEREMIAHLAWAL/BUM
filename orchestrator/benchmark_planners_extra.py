import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestrator.providers import call_openrouter
from orchestrator.repo_tools import repo_tree
from orchestrator.run import load_instructions

PIPELINE_DIR = PROJECT_ROOT / "pipeline"
OUTPUT_DIR = PROJECT_ROOT / "benchmark_outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


def read_pipeline_file(name: str) -> str:
    path = PIPELINE_DIR / name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


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

instructions = load_instructions("planner/INSTRUCTIONS.md")

candidates = [
    "anthropic/claude-3.5-haiku-20241022",
    "google/gemini-2.5-flash",
]

print("=== RUNNING ADDITIONAL CANDIDATES ===")

for model in candidates:
    print(f"--> Testing model: {model} ...", flush=True)
    t0 = time.time()
    try:
        response = call_openrouter(
            model=model,
            system_prompt=instructions,
            user_prompt=planner_prompt,
        )
        duration = time.time() - t0
        chars = len(response)
        safe_name = model.replace("/", "_").replace(":", "_")
        out_file = OUTPUT_DIR / f"{safe_name}.md"
        out_file.write_text(response, encoding="utf-8")
        print(f"    SUCCESS in {duration:.2f}s ({chars} chars). Saved to {out_file.name}", flush=True)
    except Exception as e:
        duration = time.time() - t0
        print(f"    FAILED in {duration:.2f}s: {e}", flush=True)

print("\n=== COMPLETE ===")
