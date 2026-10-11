import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from orchestrator.repo_tools import get_repo_root, read_file
from orchestrator.git_tools import run_safe_git_command


def _hash_file_content(content: str) -> str:
    """Return SHA256 hex digest of a string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _get_file_snapshot(rel_path: str) -> Optional[Dict[str, Any]]:
    """Capture snapshot of a relative path if it exists as a file."""
    repo_root = get_repo_root()
    full_path = (repo_root / rel_path).resolve()
    if full_path.exists() and full_path.is_file():
        try:
            content = read_file(rel_path)
            return {
                "path": rel_path.replace("\\", "/"),
                "exists": True,
                "sha256": _hash_file_content(content),
                "content": content,
            }
        except Exception:
            return None
    return None


def capture_git_baseline() -> Dict[str, Any]:
    """
    Capture read-only baseline state of the Git working tree before pipeline changes.
    Tracks:
    - raw git status / diff outputs
    - list of pre-existing modified, staged, deleted, and untracked files
    - content snapshots / SHA256 hashes of pre-existing dirty and untracked files
    """
    repo_root = get_repo_root()
    status_res = run_safe_git_command(["git", "status", "--short"])
    diff_stat_res = run_safe_git_command(["git", "diff", "--stat"])
    diff_head_res = run_safe_git_command(["git", "diff", "HEAD"])

    tracked_modified: List[str] = []
    tracked_deleted: List[str] = []
    tracked_staged: List[str] = []
    untracked_files: List[str] = []
    snapshots: Dict[str, Dict[str, Any]] = {}

    status_lines = status_res.get("stdout", "").splitlines()
    for line in status_lines:
        if len(line) < 3:
            continue
        index_status = line[0]
        worktree_status = line[1]
        raw_path = line[3:].strip().strip("\"'")
        clean_path = raw_path.replace("\\", "/")

        if index_status == "?" and worktree_status == "?":
            # Untracked path (could be file or directory)
            target = (repo_root / clean_path).resolve()
            is_escaping_symlink = (repo_root / clean_path).is_symlink() and not (
                target == repo_root or target.is_relative_to(repo_root)
            )
            if is_escaping_symlink:
                # e.g. node_modules symlinked back to the real checkout outside this
                # worktree — do not walk into it; relative_to(repo_root) would raise.
                untracked_files.append(clean_path)
            elif target.exists() and target.is_dir():
                for subfile in target.rglob("*"):
                    if subfile.is_file():
                        try:
                            sub_rel = str(subfile.relative_to(repo_root)).replace("\\", "/")
                        except ValueError:
                            continue
                        untracked_files.append(sub_rel)
                        snap = _get_file_snapshot(sub_rel)
                        if snap:
                            snapshots[sub_rel] = snap
            else:
                untracked_files.append(clean_path)
                snap = _get_file_snapshot(clean_path)
                if snap:
                    snapshots[clean_path] = snap
        else:
            if index_status != " " and index_status != "?":
                tracked_staged.append(clean_path)
            if worktree_status == "D" or index_status == "D":
                tracked_deleted.append(clean_path)
            else:
                tracked_modified.append(clean_path)
                snap = _get_file_snapshot(clean_path)
                if snap:
                    snapshots[clean_path] = snap

    return {
        "status_short": status_res.get("stdout", ""),
        "diff_stat": diff_stat_res.get("stdout", ""),
        "diff_head": diff_head_res.get("stdout", ""),
        "tracked_modified": sorted(list(set(tracked_modified))),
        "tracked_deleted": sorted(list(set(tracked_deleted))),
        "tracked_staged": sorted(list(set(tracked_staged))),
        "untracked_files": sorted(list(set(untracked_files))),
        "snapshots": snapshots,
    }


def compute_run_git_attribution(baseline: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute task-scoped Git attribution by comparing current repository state
    against the captured baseline.
    Returns:
    - pre_existing: changes/files that existed before this run
    - run_delta: newly created, modified, deleted, or pre-existing files modified again
    - current_untracked_contents: formatted contents of all current untracked files
    - run_untracked_contents: formatted contents of untracked files created during this run
    """
    repo_root = get_repo_root()
    curr_status_res = run_safe_git_command(["git", "status", "--short"])
    curr_diff_stat_res = run_safe_git_command(["git", "diff", "--stat"])
    curr_diff_res = run_safe_git_command(["git", "diff"])
    curr_diff_head_res = run_safe_git_command(["git", "diff", "HEAD"])

    curr_tracked_modified: Set[str] = set()
    curr_tracked_deleted: Set[str] = set()
    curr_tracked_staged: Set[str] = set()
    curr_untracked_files: Set[str] = set()

    for line in curr_status_res.get("stdout", "").splitlines():
        if len(line) < 3:
            continue
        idx_s = line[0]
        wt_s = line[1]
        raw_p = line[3:].strip().strip("\"'")
        clean_p = raw_p.replace("\\", "/")

        if idx_s == "?" and wt_s == "?":
            target = (repo_root / clean_p).resolve()
            is_escaping_symlink = (repo_root / clean_p).is_symlink() and not (
                target == repo_root or target.is_relative_to(repo_root)
            )
            if is_escaping_symlink:
                curr_untracked_files.add(clean_p)
            elif target.exists() and target.is_dir():
                for subfile in target.rglob("*"):
                    if subfile.is_file():
                        try:
                            sub_rel = str(subfile.relative_to(repo_root)).replace("\\", "/")
                        except ValueError:
                            continue
                        curr_untracked_files.add(sub_rel)
            else:
                curr_untracked_files.add(clean_p)
        else:
            if idx_s != " " and idx_s != "?":
                curr_tracked_staged.add(clean_p)
            if wt_s == "D" or idx_s == "D":
                curr_tracked_deleted.add(clean_p)
            else:
                curr_tracked_modified.add(clean_p)

    base_modified = set(baseline.get("tracked_modified", []))
    base_deleted = set(baseline.get("tracked_deleted", []))
    base_staged = set(baseline.get("tracked_staged", []))
    base_untracked = set(baseline.get("untracked_files", []))
    base_snapshots = baseline.get("snapshots", {})

    # Newly created files (untracked now, but not at baseline)
    run_created = sorted(list(curr_untracked_files - base_untracked))

    # Newly deleted files (deleted now, but not deleted at baseline)
    run_deleted = sorted(list(curr_tracked_deleted - base_deleted))

    # Newly modified tracked files (modified now, but not at baseline)
    run_new_modified = sorted(list(curr_tracked_modified - base_modified))

    # Files modified further during run (dirty at baseline, but content changed during run)
    preexisting_modified_again: List[str] = []
    preexisting_unmodified: List[str] = []

    for path in (base_modified | base_untracked):
        base_snap = base_snapshots.get(path)
        curr_snap = _get_file_snapshot(path)

        if base_snap and curr_snap:
            if base_snap.get("sha256") != curr_snap.get("sha256"):
                preexisting_modified_again.append(path)
            else:
                preexisting_unmodified.append(path)
        elif not curr_snap and path in base_untracked:
            # An untracked baseline file was deleted during the run
            run_deleted.append(path)

    run_modified_all = sorted(list(set(run_new_modified + preexisting_modified_again)))

    # Collect untracked contents
    current_untracked_parts = []
    run_untracked_parts = []
    for path in sorted(list(curr_untracked_files)):
        try:
            content = read_file(path)
            block = f"FILE: {path}\n```\n{content}\n```"
            current_untracked_parts.append(block)
            if path in run_created:
                run_untracked_parts.append(block)
        except Exception:
            pass

    return {
        "pre_existing": {
            "tracked_modified": sorted(list(base_modified - set(preexisting_modified_again))),
            "tracked_deleted": sorted(list(base_deleted)),
            "tracked_staged": sorted(list(base_staged)),
            "untracked_files": sorted(list(base_untracked - set(run_created))),
            "summary_count": len(base_modified) + len(base_untracked) + len(base_deleted),
        },
        "run_delta": {
            "created": sorted(run_created),
            "modified": sorted(run_modified_all),
            "deleted": sorted(run_deleted),
            "preexisting_modified_again": sorted(preexisting_modified_again),
            "is_clean": (len(run_created) + len(run_modified_all) + len(run_deleted)) == 0,
        },
        "current_git_state": {
            "status_short": curr_status_res.get("stdout", ""),
            "diff_stat": curr_diff_stat_res.get("stdout", ""),
            "diff": curr_diff_res.get("stdout", ""),
            "diff_head": curr_diff_head_res.get("stdout", ""),
            "untracked_files": sorted(list(curr_untracked_files)),
        },
        "current_untracked_contents": "\n\n".join(current_untracked_parts),
        "run_untracked_contents": "\n\n".join(run_untracked_parts),
    }


def format_git_attribution_context(attribution: Dict[str, Any]) -> str:
    """Format structured Git attribution for Tester and Reviewer prompts."""
    pre = attribution["pre_existing"]
    delta = attribution["run_delta"]
    curr = attribution["current_git_state"]

    pre_mod_str = ", ".join(pre["tracked_modified"]) if pre["tracked_modified"] else "None"
    pre_untracked_str = ", ".join(pre["untracked_files"]) if pre["untracked_files"] else "None"
    pre_del_str = ", ".join(pre["tracked_deleted"]) if pre["tracked_deleted"] else "None"

    delta_created_str = ", ".join(delta["created"]) if delta["created"] else "None"
    delta_modified_str = ", ".join(delta["modified"]) if delta["modified"] else "None"
    delta_deleted_str = ", ".join(delta["deleted"]) if delta["deleted"] else "None"
    delta_mod_again_str = ", ".join(delta["preexisting_modified_again"]) if delta["preexisting_modified_again"] else "None"

    return f"""==================================================
TASK-SCOPED GIT WORKTREE ATTRIBUTION
==================================================

1. PRE-EXISTING WORKTREE STATE (Existed BEFORE this task started):
- Pre-existing Tracked Modified: {pre_mod_str}
- Pre-existing Untracked Files: {pre_untracked_str}
- Pre-existing Deleted Files: {pre_del_str}
[NOTICE: These pre-existing changes belong to prior baseline/scaffolding work. DO NOT flag or fail the current task merely because pre-existing changes exist.]

2. CURRENT RUN DELTA (Changes introduced during THIS pipeline execution):
- Files Created: {delta_created_str}
- Files Modified: {delta_modified_str}
- Files Deleted: {delta_deleted_str}
- Pre-existing Files Modified Again by Run: {delta_mod_again_str}
[NOTICE: This Current Run Delta represents the actual work performed for the current task. Evaluate scope and acceptance criteria primarily against this delta.]

3. CURRENT RAW GIT STATUS & DIFF:
--- git status --short ---
{curr['status_short'] or '(clean)'}

--- git diff --stat ---
{curr['diff_stat'] or '(no diff)'}
"""
