import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))






def read_pipeline_file(name: str) -> str:
    path = PROJECT_ROOT / "pipeline" / name

    if not path.exists():
        return f"[{name} not found]"

    return path.read_text(encoding="utf-8")


def format_result(result: dict) -> str:
    return f"""
COMMAND: {result["command"]}
RETURN CODE: {result["returncode"]}

STDOUT:
{result["stdout"]}

STDERR:
{result["stderr"]}
""".strip()


def main():
    from orchestrator.run import run_agent
    from orchestrator.repo_tools import repo_tree
    from orchestrator.command_tools import run_safe_command

    # Context
    handoff = read_pipeline_file("HANDOFF.md")
    spec = read_pipeline_file("spec.md")
    changes = read_pipeline_file("changes.md")
    tree = repo_tree(max_depth=3)

    # Controlled test execution
    typecheck_result = run_safe_command(
        ["npm", "run", "ts:check"]
    )

    test_result = run_safe_command(
        ["npm", "test"]
    )

    prompt = f"""
    You are the Tester agent for Trayne.

    This is a TESTER COMMAND-CAPABILITY VERIFICATION.

    You are receiving:
    1. The Trayne engineering handoff
    2. The current Planner spec
    3. The current changes log
    4. The real Trayne repository tree
    5. Results from approved commands executed by the orchestrator

    IMPORTANT:

    The orchestrator executed the commands.
    You did NOT receive arbitrary shell access.

    Do not:
    - modify files
    - write implementation code
    - act as Reviewer
    - invent test results
    - claim commands were executed unless their output appears below

    Inspect the supplied command results.

    If:
    - you can understand the command outputs,
    - the commands clearly ran against Trayne,
    - and you can use these results for future testing,

    respond with exactly:

    TESTER_COMMAND_EXECUTION_OK

    If not, respond:

    TESTER_COMMAND_EXECUTION_FAIL

    and briefly explain why.


    ===== HANDOFF.md =====

    {handoff}


    ===== spec.md =====

    {spec}


    ===== changes.md =====

    {changes}


    ===== REPOSITORY TREE =====

    {tree}


    ===== TYPESCRIPT CHECK =====

    {format_result(typecheck_result)}


    ===== TEST SUITE =====

    {format_result(test_result)}
    """

    response = run_agent("tester", prompt)

    print("\n=== TESTER COMMAND EXECUTION TEST ===\n")
    print(response)

    print("\n=== TYPESCRIPT RESULT ===")
    print(format_result(typecheck_result))

    print("\n=== TEST RESULT ===")
    print(format_result(test_result))


if __name__ == "__main__":
    main()
