import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestrator.git_tools import run_safe_git_command
from orchestrator.run import run_agent


print("=== REVIEWER GIT CAPABILITY TEST ===")


print("\n1. Testing forbidden Git command...")

try:
    run_safe_git_command(["git", "reset", "--hard"])
    print("ERROR: Forbidden command was allowed")
except PermissionError as exc:
    print("FORBIDDEN_COMMAND_BLOCKED")
    print(exc)


print("\n2. Testing allowed Git command...")

git_result = run_safe_git_command(
    ["git", "status", "--short"]
)

print("COMMAND:", git_result["command"])
print("RETURN CODE:", git_result["returncode"])
print("TIMED OUT:", git_result["timed_out"])
print("STDOUT:")
print(git_result["stdout"])
print("STDERR:")
print(git_result["stderr"])


reviewer_prompt = f"""
This is a capability test only.

You are the Reviewer for the Trayne project.

You have been given structured output from a safe, read-only Git inspection command executed by the orchestrator.

Git result:

{git_result}

Do not perform a full code review.
Do not invent implementation changes.

Confirm that:
1. You understand the Git command that was executed.
2. You can interpret its structured output.
3. This information could be used later during a real implementation review.

If everything is understandable, respond with exactly:

REVIEWER_GIT_CONTEXT_OK
"""


print("\n3. Sending Git context to Reviewer...")

response = run_agent(
    "reviewer",
    reviewer_prompt,
)

print("\nREVIEWER RESPONSE:")
print(response)
