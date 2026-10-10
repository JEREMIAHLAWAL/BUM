import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Set, Tuple

from orchestrator.repo_tools import get_repo_root, get_active_manifest


DEFAULT_ALLOWED_COMMANDS: Set[Tuple[str, ...]] = {
    ("npm", "test"),
    ("npm", "run", "test"),
    ("npm", "run", "ts:check"),
}


def get_allowed_commands() -> Set[Tuple[str, ...]]:
    """
    Get the set of allowed verification commands.
    Merges default safe commands with verification commands specified
    in the active workspace manifest (bum.config.json).
    """
    allowed = set(DEFAULT_ALLOWED_COMMANDS)
    try:
        manifest = get_active_manifest()
        if manifest and manifest.verification:
            for cmd_str in [
                manifest.verification.typecheck_cmd,
                manifest.verification.test_cmd,
                manifest.verification.lint_cmd,
                manifest.verification.build_cmd,
            ]:
                if cmd_str and cmd_str.strip():
                    parts = tuple(shlex.split(cmd_str.strip()))
                    if parts:
                        allowed.add(parts)
    except Exception:
        pass
    return allowed


def run_safe_command(command: list[str], cwd: Optional[str] = None, timeout: int = 300) -> dict:
    """
    Run an approved development/test command inside the active repository.

    Commands are executed without shell=True and the working directory
    defaults to the active repo root.
    """
    if not isinstance(command, list) or not command:
        raise ValueError("Command must be a non-empty list of strings.")

    if not all(isinstance(part, str) for part in command):
        raise TypeError("Every command argument must be a string.")

    command_tuple = tuple(command)
    allowed_commands = get_allowed_commands()

    if command_tuple not in allowed_commands:
        raise PermissionError(
            f"Command is not allowed: {' '.join(command)}"
        )

    repo = Path(cwd) if cwd else get_repo_root()

    executable = shutil.which(command[0])
    if not executable:
        raise FileNotFoundError(f"Executable not found on PATH: {command[0]}")

    exec_command = [executable] + command[1:]

    result = subprocess.run(
        exec_command,
        cwd=repo,
        capture_output=True,
        text=True,
        shell=False,
        timeout=timeout,
    )

    return {
        "command": " ".join(command),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
