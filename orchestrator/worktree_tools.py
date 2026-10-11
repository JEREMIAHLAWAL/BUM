"""
Per-run git worktree isolation.

Root cause this closes: the pipeline used to run every stage directly against
the real target repo checkout, and a startup `git reset --hard` / `git clean
-fd` wiped any uncommitted work before each run (this destroyed history.tsx
and analytics.tsx permanently — see MASTER_TODO.md). A later fix taught the
startup reset to salvage uncommitted work first, but the real checkout was
still being destructively touched every run.

This module removes that risk structurally: each pipeline run gets its own
disposable `git worktree` checked out on a throwaway branch. The real
checkout is never reset, cleaned, or otherwise destructively touched by a
pipeline run. The worktree starts from a clean HEAD by construction, so no
startup reset is needed at all. On a human-approved run, the throwaway
branch is fast-forward merged into the real checkout's current branch — the
only write path into the real repo. On any other outcome (reject / blocked /
failed / cancelled / crash), the worktree and its branch are just deleted;
the real checkout was never touched.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

WORKTREE_BRANCH_PREFIX = "bum-run/"
_VALID_RUN_ID_RE = re.compile(r"^run_[a-zA-Z0-9_\-]+$")


def _assert_valid_run_id(run_id: str) -> None:
    """Defense in depth: this module shells out to git with run_id embedded
    in paths and branch names. The HTTP layer already validates run_id
    format, but never trust that invariant silently across module
    boundaries."""
    if not run_id or not _VALID_RUN_ID_RE.match(run_id):
        raise ValueError(f"Invalid run_id format for worktree operations: {run_id!r}")


def _run_git(args: list[str], cwd: Path, timeout: int = 60) -> dict:
    """Run a raw git command against an explicit cwd. Not routed through
    run_safe_git_command's allowlist/get_repo_root, because worktree setup
    and teardown must operate on the REAL checkout path explicitly, before
    (or after) any run-scoped repo_root override is active."""
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "command": "git " + " ".join(args),
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": "git " + " ".join(args),
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "timed_out": True,
        }


def worktree_root_dir(real_repo_root: Path) -> Path:
    """Directory under the orchestrator's own .bum state dir (not inside the
    target repo, and not synced/committed) where run worktrees live."""
    agents_root = Path(__file__).resolve().parent.parent
    return agents_root / ".bum" / "worktrees"


def branch_name(run_id: str) -> str:
    return f"{WORKTREE_BRANCH_PREFIX}{run_id}"


def create_run_worktree(run_id: str, real_repo_root: Path) -> dict:
    """
    Create an isolated git worktree for this run, checked out on a fresh
    throwaway branch from the real checkout's current HEAD.

    Returns {"success": bool, "worktree_path": Path | None, "branch": str,
    "error": str | None}. On any failure, no partial worktree is left
    registered against the real repo (best-effort cleanup).
    """
    _assert_valid_run_id(run_id)
    branch = branch_name(run_id)
    wt_root = worktree_root_dir(real_repo_root)
    wt_root.mkdir(parents=True, exist_ok=True)
    wt_path = wt_root / run_id

    if wt_path.exists():
        shutil.rmtree(wt_path, ignore_errors=True)

    # Capture current branch so merge-back later targets the right ref.
    head_res = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=real_repo_root)
    base_branch = (head_res.get("stdout") or "").strip()
    if not base_branch or base_branch == "HEAD":
        return {
            "success": False,
            "worktree_path": None,
            "branch": branch,
            "base_branch": None,
            "error": f"Could not resolve a base branch for the real checkout (detached HEAD?): {head_res}",
        }

    add_res = _run_git(
        ["worktree", "add", "-b", branch, str(wt_path), "HEAD"],
        cwd=real_repo_root,
    )
    if add_res.get("returncode") != 0:
        # Clean up any half-created state before surfacing the error.
        _run_git(["worktree", "remove", "--force", str(wt_path)], cwd=real_repo_root)
        _run_git(["branch", "-D", branch], cwd=real_repo_root)
        shutil.rmtree(wt_path, ignore_errors=True)
        return {
            "success": False,
            "worktree_path": None,
            "branch": branch,
            "base_branch": base_branch,
            "error": f"git worktree add failed: {add_res.get('stderr') or add_res.get('stdout')}",
        }

    # node_modules is gitignored and not worth reinstalling per run; link it
    # in read/write from the real checkout if present. This is the ONE
    # exception to "never touch the real checkout" and it's safe: it's a
    # symlink into existing installed packages, not a write into the repo's
    # tracked/uncommitted content.
    real_node_modules = real_repo_root / "node_modules"
    wt_node_modules = wt_path / "node_modules"
    if real_node_modules.is_dir() and not wt_node_modules.exists():
        try:
            if sys.platform == "win32":
                # Directory symlinks need elevated privileges on some Windows
                # setups; junctions do not.
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(wt_node_modules), str(real_node_modules)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            else:
                wt_node_modules.symlink_to(real_node_modules, target_is_directory=True)
        except Exception as exc:
            print(f"[WARN] Could not link node_modules into worktree: {exc}", file=sys.stderr, flush=True)

    return {
        "success": True,
        "worktree_path": wt_path,
        "branch": branch,
        "base_branch": base_branch,
        "error": None,
    }


def merge_run_worktree(run_id: str, real_repo_root: Path) -> dict:
    """
    Human-approved outcome: fast-forward merge the run's throwaway branch
    into the real checkout's currently checked-out branch, then tear the
    worktree down.

    This is the ONLY path by which a pipeline run's changes reach the real
    checkout. If the merge is not a clean fast-forward (the real checkout
    moved on since the worktree was created), this FAILS LOUD rather than
    force-merging or resetting anything — the caller must resolve manually.
    """
    _assert_valid_run_id(run_id)
    branch = branch_name(run_id)
    wt_path = worktree_root_dir(real_repo_root) / run_id

    head_res = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=real_repo_root)
    base_branch = (head_res.get("stdout") or "").strip()
    if not base_branch or base_branch == "HEAD":
        return {
            "success": False,
            "error": f"Could not resolve the real checkout's current branch (detached HEAD?): {head_res}",
        }

    branch_exists_res = _run_git(["rev-parse", "--verify", "--quiet", branch], cwd=real_repo_root)
    if not wt_path.exists() and branch_exists_res.get("returncode") != 0:
        # No worktree and no branch for this run_id — nothing to merge. This
        # happens for runs that predate worktree isolation, or synthetic/
        # test runs with no real pipeline execution behind them. Treat as a
        # benign no-op rather than failing the whole approval.
        return {
            "success": True,
            "merged_branch": None,
            "base_branch": base_branch,
            "note": f"No worktree or branch found for run '{run_id}' — nothing to merge.",
        }

    # Ensure the worktree's own changes are committed (defensive: the
    # pipeline's micro-commit step should already have done this on APPROVE,
    # but never merge uncommitted content).
    status_res = _run_git(["status", "--short"], cwd=wt_path if wt_path.exists() else real_repo_root)
    if wt_path.exists() and status_res.get("stdout", "").strip():
        return {
            "success": False,
            "error": (
                "Worktree has uncommitted changes at merge time — refusing to merge or discard. "
                "This should not happen (reviewer APPROVE should have triggered a micro-commit). "
                "Uncommitted content: " + status_res["stdout"]
            ),
        }

    merge_res = _run_git(["merge", "--ff-only", branch], cwd=real_repo_root)
    if merge_res.get("returncode") != 0:
        # Do NOT clean up the worktree/branch on failure — preserve it so the
        # work is not lost and can be merged manually.
        return {
            "success": False,
            "error": (
                f"Fast-forward merge of '{branch}' into '{base_branch}' failed: "
                f"{merge_res.get('stderr') or merge_res.get('stdout')}. "
                f"Worktree preserved at {wt_path} / branch '{branch}' for manual resolution."
            ),
        }

    cleanup = _teardown_worktree(run_id, real_repo_root)
    return {
        "success": True,
        "merged_branch": branch,
        "base_branch": base_branch,
        "cleanup": cleanup,
    }


def discard_run_worktree(run_id: str, real_repo_root: Path) -> dict:
    """
    Any non-approved terminal outcome (reject / blocked / failed / cancelled
    / crash): delete the worktree and its branch. The real checkout was
    never touched by this run, so there is nothing to roll back there.
    """
    return _teardown_worktree(run_id, real_repo_root)


def _teardown_worktree(run_id: str, real_repo_root: Path) -> dict:
    _assert_valid_run_id(run_id)
    branch = branch_name(run_id)
    wt_path = worktree_root_dir(real_repo_root) / run_id

    branch_exists_res = _run_git(["rev-parse", "--verify", "--quiet", branch], cwd=real_repo_root)
    if not wt_path.exists() and branch_exists_res.get("returncode") != 0:
        # Nothing to tear down for this run_id (no worktree, no branch) —
        # benign no-op, e.g. legacy/pre-isolation runs or synthetic test runs.
        return {
            "worktree_removed": True,
            "branch_deleted": True,
            "note": f"No worktree or branch found for run '{run_id}' — nothing to discard.",
        }

    remove_res = _run_git(["worktree", "remove", "--force", str(wt_path)], cwd=real_repo_root)
    if wt_path.exists():
        shutil.rmtree(wt_path, ignore_errors=True)

    prune_res = _run_git(["worktree", "prune"], cwd=real_repo_root)
    branch_del_res = _run_git(["branch", "-D", branch], cwd=real_repo_root)

    return {
        "worktree_removed": remove_res.get("returncode") == 0 or not wt_path.exists(),
        "branch_deleted": branch_del_res.get("returncode") == 0,
        "details": {
            "remove": remove_res,
            "prune": prune_res,
            "branch_delete": branch_del_res,
        },
    }


def list_stale_worktrees(real_repo_root: Path, active_run_ids: Optional[set] = None) -> list[dict]:
    """List registered worktrees under our managed root that aren't the
    currently-active run(s) — useful for a cleanup sweep after crashes."""
    active_run_ids = active_run_ids or set()
    wt_root = worktree_root_dir(real_repo_root)
    if not wt_root.exists():
        return []
    stale = []
    for item in wt_root.iterdir():
        if item.is_dir() and item.name not in active_run_ids:
            stale.append({"run_id": item.name, "path": str(item)})
    return stale
