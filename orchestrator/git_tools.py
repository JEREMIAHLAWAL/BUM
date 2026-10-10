import subprocess

from orchestrator.repo_tools import get_repo_root


ALLOWED_GIT_COMMANDS = {
    ("git", "status", "--short"),
    ("git", "diff"),
    ("git", "diff", "--stat"),
    ("git", "diff", "--name-only"),
    ("git", "diff", "HEAD"),
    ("git", "reset", "--hard", "HEAD"),
    ("git", "reset", "--hard"),
    ("git", "clean", "-fd"),
}


def run_safe_git_command(command: list[str]) -> dict:
    command_tuple = tuple(command)

    if command_tuple not in ALLOWED_GIT_COMMANDS:
        raise PermissionError(
            f"Git command is not allowed: {' '.join(command)}"
        )

    repo_root = get_repo_root()

    try:
        result = subprocess.run(
            command,
            cwd=repo_root,
            shell=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "command": " ".join(command),
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "timed_out": True,
        }

    return {
        "command": " ".join(command),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "timed_out": False,
    }
