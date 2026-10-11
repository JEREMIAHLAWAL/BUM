import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from orchestrator.git_tools import run_safe_git_command
from orchestrator.repo_tools import get_repo_root


def get_current_head_sha() -> str:
    """Get the current commit SHA of the repository."""
    res = run_safe_git_command(["git", "rev-parse", "HEAD"])
    return res.get("stdout", "").strip()


def create_micro_commit(
    stage: str,
    cycle: int = 0,
    summary: str = "checkpoint",
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Create an atomic micro-commit savepoint after verified stage transitions.
    Format: `bum: [stage=<stage> cycle=<cycle>] <summary>`
    """
    if repo_root is None:
        try:
            repo_root = get_repo_root()
        except Exception:
            repo_root = Path.cwd()

    status_res = run_safe_git_command(["git", "status", "--short"])
    if not status_res.get("stdout", "").strip():
        # No uncommitted changes to save
        return {
            "created": False,
            "reason": "clean_worktree",
            "sha": get_current_head_sha(),
        }

    # Stage changes
    run_safe_git_command(["git", "add", "-A"])

    commit_msg = f"bum: [{stage} c{cycle}] {summary}"

    # Commit securely using subprocess
    try:
        proc = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=repo_root,
            shell=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            sha = get_current_head_sha()
            return {
                "created": True,
                "stage": stage,
                "cycle": cycle,
                "sha": sha,
                "message": commit_msg,
            }
        else:
            return {
                "created": False,
                "reason": proc.stderr,
                "sha": get_current_head_sha(),
            }
    except Exception as exc:
        return {
            "created": False,
            "error": str(exc),
            "sha": get_current_head_sha(),
        }


def rollback_to_micro_commit(target_sha: str, repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Roll back worktree to a previous micro-commit savepoint."""
    if repo_root is None:
        try:
            repo_root = get_repo_root()
        except Exception:
            repo_root = Path.cwd()

    try:
        proc = subprocess.run(
            ["git", "reset", "--hard", target_sha],
            cwd=repo_root,
            shell=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        run_safe_git_command(["git", "clean", "-fd"])
        return {
            "success": proc.returncode == 0,
            "target_sha": target_sha,
            "stderr": proc.stderr,
        }
    except Exception as exc:
        return {
            "success": False,
            "target_sha": target_sha,
            "error": str(exc),
        }
