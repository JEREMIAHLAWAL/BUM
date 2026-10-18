"""
Manual recovery utility for resuming Tester and Reviewer evaluation after manual intervention.
NOTE: This is a manual recovery utility and must not be automatically re-invoked
after the main pipeline reaches its retry limit (MAX_REVIEW_CYCLES_EXCEEDED).
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestrator.run import run_agent
from orchestrator.repo_tools import (
    get_repo_root,
    repo_tree,
    read_file,
    file_exists,
)
from orchestrator.command_tools import run_safe_command
from orchestrator.git_tools import run_safe_git_command
from orchestrator.pipeline import (
    get_untracked_files_content,
    format_command_result,
    format_git_result,
)


def read_pipeline_file(name: str) -> str:
    path = PROJECT_ROOT / "pipeline" / name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def run_test_and_review():
    raise RuntimeError(
        "Legacy resume is disabled: shared artifacts and the discarded worktree cannot be "
        "safely restored. Use the run's /retry endpoint for a new isolated full pipeline run."
    )
    print("=== RESUMING PIPELINE: TESTER & REVIEWER EVALUATION ===")

    spec = read_pipeline_file("spec.md")
    changes = read_pipeline_file("changes.md")
    handoff = read_pipeline_file("HANDOFF.md")
    current_tree = repo_tree()

    # 1. Run safe test commands
    print("\n[1/2] RUNNING TEST COMMANDS FOR TESTER...", flush=True)
    test_commands = [
        ["npm", "run", "ts:check"],
        ["npm", "test"],
    ]

    command_results = []
    for cmd in test_commands:
        cmd_str = " ".join(cmd)
        print(f"Executing: {cmd_str} ...", flush=True)
        res = run_safe_command(cmd)
        res["timed_out"] = False
        command_results.append(res)
        print(f"  Command: {res['command']} | Return Code: {res['returncode']} | Timed Out: {res['timed_out']}", flush=True)

    command_outputs_formatted = "\n\n".join(format_command_result(r) for r in command_results)

    # 2. Call Tester
    print("\n[1/2] TESTER EVALUATION STARTED...", flush=True)
    tester_prompt = f"""
TRAYNE ENGINEERING HANDOFF:
{handoff}

TRAYNE REPOSITORY TREE AFTER IMPLEMENTATION:
{current_tree}

PLANNER SPEC:
{spec}

PROPOSED CHANGES (pipeline/changes.md):
{changes}

FRESH COMMAND EXECUTION RESULTS:
{command_outputs_formatted}

IMPORTANT INSTRUCTIONS FOR TESTER:
- This is a RE-EVALUATION after repairing the `expo-router` dependency/configuration blocker.
- Files have been written to disk by Frontend and minimal Expo configuration was set up.
- You do NOT have arbitrary shell access; the above commands were executed in a controlled sandbox by the orchestrator.
- Do NOT fabricate PASS.
- Clearly note that `npm run ts:check` returned code 0 and `npm test` returned code 0 (237/237 tests).
- Specifically check whether the previous `expo-router` module-resolution error is resolved.
- Compare actual implementation files against the Planner acceptance criteria.

Provide your evaluation using this exact structure:

STATUS: PASS / FAIL / UNVERIFIABLE
FINDINGS:
...
BLOCKERS:
...
"""

    t0 = time.time()
    tester_result = run_agent("tester", tester_prompt)
    t_tester = time.time() - t0

    print(f"[1/2] TESTER COMPLETE ({t_tester:.2f}s)", flush=True)
    print("\n=== TESTER REPORT ===")
    print(tester_result)

    # 3. Safe Git inspection & Untracked file contents
    print("\n[2/2] RUNNING GIT INSPECTION FOR REVIEWER...", flush=True)
    git_commands = [
        ["git", "status", "--short"],
        ["git", "diff", "--stat"],
        ["git", "diff", "--name-only"],
        ["git", "diff"],
        ["git", "diff", "HEAD"],
    ]

    git_results = []
    for gcmd in git_commands:
        gres = run_safe_git_command(gcmd)
        git_results.append(gres)
        print(f"  Command: {gres['command']} | Return Code: {gres['returncode']} | Timed Out: {gres['timed_out']}", flush=True)

    git_outputs_formatted = "\n\n".join(format_git_result(r) for r in git_results)
    untracked_contents_formatted = get_untracked_files_content()

    # 4. Call Reviewer
    print("\n[2/2] REVIEWER EVALUATION STARTED...", flush=True)
    reviewer_prompt = f"""
TRAYNE ENGINEERING HANDOFF:
{handoff}

TRAYNE REPOSITORY TREE AFTER IMPLEMENTATION:
{current_tree}

PLANNER SPEC:
{spec}

CHANGES (pipeline/changes.md):
{changes}

NEW TESTER REPORT:
{tester_result}

GIT INSPECTION RESULTS:
{git_outputs_formatted}

ACTUAL UNTRACKED IMPLEMENTATION FILE CONTENTS (Read via Safe Repo Layer):
{untracked_contents_formatted}

IMPORTANT INSTRUCTIONS FOR REVIEWER:
- This is the review cycle following the resolution of the `expo-router` dependency/configuration blocker.
- Review the actual implementation changes made and the untracked file contents provided above.
- Verify whether the changes fulfill the Planner spec and acceptance criteria.
- Check that the test suite passes (237/237 tests) and TypeScript check passes (`npm run ts:check` -> return code 0).
- Confirm that Git inspection reflects expected, scoped, uncommitted changes.
- You do NOT have direct shell access; all command results and file contents were provided via the safe orchestrator layer.

Please evaluate:
1. Was the Planner spec grounded in the actual Trayne architecture?
2. Did Frontend and Backend stay within their assigned responsibilities?
3. Did the code satisfy the acceptance criteria?
4. Did the test suite and type check pass?
5. Does Git inspection confirm clean, expected, uncommitted changes?

Return one of:
APPROVE
or
CHANGES REQUIRED

followed by a detailed explanation.
"""

    t0 = time.time()
    reviewer_result = run_agent("reviewer", reviewer_prompt)
    t_reviewer = time.time() - t0

    print(f"\n[2/2] REVIEWER COMPLETE ({t_reviewer:.2f}s)", flush=True)
    print("\n=== REVIEWER REPORT ===")
    print(reviewer_result)


if __name__ == "__main__":
    run_test_and_review()
