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

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import yaml
from orchestrator.manifest import BumManifest, find_manifest, worktree_manifest_snapshot

WORKTREE_BRANCH_PREFIX = "bum-run/"
_VALID_RUN_ID_RE = re.compile(r"^run_[a-zA-Z0-9_\-]+$")


def _assert_valid_run_id(run_id: str) -> None:
    """Defense in depth: this module shells out to git with run_id embedded
    in paths and branch names. The HTTP layer already validates run_id
    format, but never trust that invariant silently across module
    boundaries."""
    if not run_id or not _VALID_RUN_ID_RE.fullmatch(run_id):
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


def _bounded_output(value, limit: int = 2000) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return str(value or "")[-limit:]


def _bootstrap_command(executable: str, args: list[str], root: Path, env: dict, timeout: int) -> str:
    """Only callers below supply fixed arguments; never accepts a manifest command."""
    try:
        proc = subprocess.run([executable, *args], cwd=root, shell=False,
                              capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"pnpm bootstrap timed out after {timeout}s: {_bounded_output(exc.stderr or exc.stdout)}") from exc
    except OSError as exc:
        raise ValueError(f"Cannot execute bootstrap tool {executable}: {_bounded_output(exc)}") from exc
    if proc.returncode:
        raise ValueError(f"pnpm bootstrap {' '.join(args)} failed ({proc.returncode}): "
                         f"{_bounded_output(proc.stderr or proc.stdout)}")
    return proc.stdout.strip()


def _check_node_engine(version: str, requirement: str) -> None:
    """Conservative AND comparison subset. Unsupported semver fails closed."""
    actual = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", version)
    if not actual:
        raise ValueError(f"Invalid Node version: {_bounded_output(version, 120)}")
    current = tuple(map(int, actual.groups()))
    if not isinstance(requirement, str) or not requirement.strip():
        raise ValueError("pnpm bootstrap requires package.json engines.node (e.g. >=24 <25)")
    for constraint in requirement.split():
        match = re.fullmatch(r"(>=|<=|>|<|=)?(\d+)(?:\.(\d+))?(?:\.(\d+))?", constraint)
        if not match:
            raise ValueError(f"Unsupported engines.node range {_bounded_output(requirement, 120)!r}; use AND comparisons such as >=24 <25")
        op, *parts = match.groups()
        specified = tuple(int(part) for part in parts if part is not None)
        target = specified + (0,) * (3 - len(specified))
        # Semver >24 means >=25.0.0; <=24 means <25.0.0 (likewise minors).
        if len(specified) < 3 and op in (">", "<="):
            upper = list(target)
            upper[len(specified) - 1] += 1
            target = tuple(upper)
            op = ">=" if op == ">" else "<"
        valid = {">=": current >= target, "<=": current <= target,
                 ">": current > target, "<": current < target,
                 "=": current[:len(specified)] == specified,
                 None: current[:len(specified)] == specified}[op]
        if not valid:
            raise ValueError(f"Node {version} does not satisfy engines.node {requirement!r}; select a compatible Node on PATH before bootstrap")


def _isolated_directories(root: Path) -> None:
    """Reject shared junctions/symlinks before install, including nested workspaces."""
    for folder, dirs, files in os.walk(root, followlinks=False):
        # Broken directory symlinks appear in files, not dirs.
        for name in files:
            path = Path(folder) / name
            if name == "node_modules" and path.is_symlink():
                raise ValueError(f"Isolated pnpm bootstrap refuses shared/symlink directory: {path.relative_to(root)}")
        for name in list(dirs):
            path = Path(folder) / name
            if name == ".git":
                dirs.remove(name)
                continue
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                if name == "node_modules" or not path.resolve().is_relative_to(root.resolve()):
                    raise ValueError(f"Isolated pnpm bootstrap refuses shared/symlink directory: {path.relative_to(root)}")
                dirs.remove(name)
            elif name == "node_modules":
                dirs.remove(name)  # pnpm's internal package symlinks are expected


def _workspace_packages(root: Path) -> list[Path]:
    packages = [root]
    workspace = root / "pnpm-workspace.yaml"
    if workspace.exists():
        if workspace.is_symlink():
            raise ValueError("pnpm-workspace.yaml must not be a symlink")
        data = yaml.safe_load(workspace.read_text(encoding="utf-8")) or {}
        patterns = data.get("packages", [])
        if not isinstance(patterns, list) or not all(isinstance(p, str) for p in patterns):
            raise ValueError("pnpm workspace packages must be a list of relative globs")
        excludes = [p[1:] for p in patterns if p.startswith("!")]
        for pattern in patterns:
            clean = pattern.removeprefix("!")
            if not clean or "\\" in clean or ":" in clean or Path(clean).is_absolute() or ".." in Path(clean).parts:
                raise ValueError("pnpm workspace package globs must stay inside the isolated worktree")
            if pattern.startswith("!"):
                continue
            for path in root.glob(pattern):
                if not path.resolve().is_relative_to(root.resolve()):
                    raise ValueError("pnpm workspace package resolves outside isolated worktree")
                if (path / "package.json").is_file() and not any(path.relative_to(root).match(p) for p in excludes):
                    packages.append(path)
    return list(dict.fromkeys(packages))


def _bootstrap_pnpm(root: Path) -> None:
    _isolated_directories(root)
    for name in ("package.json", "pnpm-lock.yaml"):
        path = root / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"pnpm bootstrap requires a committed regular {name} in worktree HEAD")
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    pin = package.get("packageManager", "")
    # Corepack integrity suffixes are allowed, but never tags, ranges or arguments.
    match = re.fullmatch(r"pnpm@(\d+\.\d+\.\d+)(?:\+sha(?:224|256|384|512)\.[a-fA-F0-9]+)?", pin) if isinstance(pin, str) else None
    if not match:
        raise ValueError("pnpm bootstrap requires an exact packageManager pin such as pnpm@10.9.0")
    packages = _workspace_packages(root)
    node = shutil.which("node")
    pnpm = shutil.which("pnpm")
    if not node or not pnpm:
        raise ValueError(f"pnpm bootstrap requires Node and pinned pnpm {match[1]} already on PATH; no tool download is performed")
    settings = {"COREPACK_ENABLE_NETWORK": "0", "COREPACK_ENABLE_DOWNLOAD_PROMPT": "0",
                "COREPACK_ENABLE_PROJECT_SPEC": "0",
                "COREPACK_ENABLE_ENV_FILE": "0", "npm_config_global": "false",
                "npm_config_manage_package_manager_versions": "false",
                "pnpm_config_pm_on_fail": "ignore",
                "npm_config_engine_strict": "true", "npm_config_ignore_scripts": "true",
                "npm_config_ignore_pnpmfile": "true", "npm_config_recursive_install": "true",
                "npm_config_production": "false", "npm_config_node_linker": "isolated",
                "npm_config_store_dir": str(root / "node_modules" / ".bum-pnpm-store"),
                "npm_config_virtual_store_dir": str(root / "node_modules" / ".pnpm"),
                "npm_config_enable_global_virtual_store": "false",
                "npm_config_modules_dir": "node_modules", "npm_config_lockfile_dir": str(root)}
    # pnpm 11+ reads pnpm_config_* instead of npm_config_*; keep the same
    # isolation regardless of which installed version is being checked.
    settings.update({key.replace("npm_config_", "pnpm_config_", 1): value
                     for key, value in list(settings.items())
                     if key.startswith("npm_config_") and key != "npm_config_manage_package_manager_versions"})
    # Windows env keys are case-insensitive. Don't retain uppercase variants
    # that could override isolation when inherited by Node/pnpm.
    controlled = {key.casefold() for key in settings}
    env = {key: value for key, value in os.environ.items() if key.casefold() not in controlled}
    env.update(settings)
    node_version = _bootstrap_command(node, ["--version"], root, env, 15)
    _check_node_engine(node_version, package.get("engines", {}).get("node", ""))
    pnpm_version = _bootstrap_command(pnpm, ["--version"], root, env, 15)
    if pnpm_version != match[1]:
        raise ValueError(f"pnpm version mismatch: packageManager pins {match[1]}, found {_bounded_output(pnpm_version, 120)!r}; select pinned pnpm on PATH")
    _bootstrap_command(pnpm, ["install", "--frozen-lockfile"], root, env, 300)
    _isolated_directories(root)
    for path in packages:
        data = json.loads((path / "package.json").read_text(encoding="utf-8"))
        if any(data.get(key) for key in ("dependencies", "devDependencies", "optionalDependencies")) and not (path / "node_modules").is_dir():
            raise ValueError(f"pnpm bootstrap left missing workspace dependencies: {path.relative_to(root)}/node_modules")


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
    # Read operator policy from the real checkout BEFORE creating HEAD-only
    # worktree. An untracked config is supported; no source/docs/secrets copied.
    manifest = None
    try:
        manifest_path = find_manifest(real_repo_root)
        if manifest_path:
            if not manifest_path.is_relative_to(real_repo_root.resolve()):
                raise ValueError("manifest must be inside the real repository")
            manifest = BumManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"success": False, "worktree_path": None, "branch": branch,
                "error": f"Invalid explicit worktree manifest: {_bounded_output(exc)}"}
    wt_root = worktree_root_dir(real_repo_root)
    wt_root.mkdir(parents=True, exist_ok=True)
    wt_path = wt_root / run_id

    if wt_path.exists() or wt_path.is_symlink():
        cleanup = _teardown_worktree(run_id, real_repo_root)
        if not (cleanup.get("worktree_removed") and cleanup.get("branch_deleted")):
            return {"success": False, "worktree_path": None, "branch": branch,
                    "cleanup": cleanup, "error": f"Existing worktree cleanup incomplete: {wt_path}"}

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
        cleanup = _teardown_worktree(run_id, real_repo_root)
        return {
            "success": False,
            "worktree_path": None,
            "branch": branch,
            "base_branch": base_branch,
            "cleanup": cleanup,
            "error": (f"git worktree add failed: {add_res.get('stderr') or add_res.get('stdout')}"
                      + (". Cleanup incomplete; inspect run path and branch before retrying."
                         if not (cleanup.get("worktree_removed") and cleanup.get("branch_deleted")) else "")),
        }

    try:
        if manifest:
            snapshot = worktree_manifest_snapshot(wt_path)
            if snapshot is None:
                raise ValueError("Cannot locate private worktree metadata for active manifest")
            snapshot.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        if manifest and manifest.worktree.bootstrap == "pnpm-frozen":
            _bootstrap_pnpm(wt_path)
    except Exception as exc:
        # No baseline/agent may run with partially bootstrapped dependencies.
        cleanup = _teardown_worktree(run_id, real_repo_root)
        error = f"Isolated worktree bootstrap failed: {_bounded_output(exc, 2400)}"
        if not (cleanup.get("worktree_removed") and cleanup.get("branch_deleted")):
            error += f". Cleanup incomplete; inspect {wt_path} and branch {branch} before retrying."
        return {"success": False, "worktree_path": None, "branch": branch,
                "base_branch": base_branch, "cleanup": cleanup, "error": error}

    # Legacy projects retain their existing shared-dependency behavior. Never
    # use this junction for opted-in installs: pnpm must own an isolated tree.
    real_node_modules = real_repo_root / "node_modules"
    wt_node_modules = wt_path / "node_modules"
    if not (manifest and manifest.worktree.bootstrap) and real_node_modules.is_dir() and not wt_node_modules.exists():
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
    wt_path = Path(os.path.abspath(worktree_root_dir(real_repo_root) / run_id))
    details = {}
    # Validate before git remove as well as before the filesystem fallback.
    # Reject redirected managed roots/run entries; never resolve then delete
    # a junction's target. Ancestors are checked without traversing children.
    try:
        for path in (wt_path, *wt_path.parents):
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise ValueError(f"Refusing cleanup through symlink/junction: {path}")
        if real_repo_root.resolve().is_relative_to(wt_path):
            raise ValueError("Refusing cleanup of real repository or its ancestor")
    except (OSError, ValueError) as exc:
        return {"worktree_removed": False, "branch_deleted": False,
                "error": _bounded_output(exc), "details": details}

    def registered():
        result = _run_git(["worktree", "list", "--porcelain", "-z"], cwd=real_repo_root)
        details["registration"] = result
        if result.get("returncode") != 0:
            raise ValueError(f"Cannot verify worktree registration: {result.get('stderr')}")
        return any(os.path.normcase(os.path.abspath(field[len('worktree '):])) == os.path.normcase(str(wt_path))
                   for field in result.get("stdout", "").split("\0") if field.startswith("worktree "))

    try:
        is_registered = registered()
        # Remove files ourselves before asking Git to unregister the path:
        # Git must never recurse through a legacy shared-dependency junction.
        if wt_path.exists():
            # Python >=3.8 rmtree unlinks Windows directory junctions rather
            # than recursing into their targets. Extended-length paths also
            # cover pnpm's deep virtual store without global Git/OS settings.
            cleanup_path = str(wt_path)
            if sys.platform == "win32" and not cleanup_path.startswith("\\\\?\\"):
                cleanup_path = ("\\\\?\\UNC\\" + cleanup_path[2:] if cleanup_path.startswith("\\\\")
                                else "\\\\?\\" + cleanup_path)
            try:
                shutil.rmtree(cleanup_path)
            except OSError as exc:
                details["filesystem_error"] = _bounded_output(exc)
        # Unregister only this path after its files are gone. Never prune
        # unrelated stale/locked worktrees or delete a registered run's branch.
        if not wt_path.exists() and is_registered:
            details["remove"] = _run_git(["worktree", "remove", "--force", str(wt_path)], cwd=real_repo_root)
        removed = not wt_path.exists() and not registered()
        if not removed:
            return {"worktree_removed": False, "branch_deleted": False,
                    "error": "Worktree cleanup incomplete; branch preserved.", "details": details}
        exists = _run_git(["rev-parse", "--verify", "--quiet", branch], cwd=real_repo_root)
        if exists.get("returncode") == 0:
            details["branch_delete"] = _run_git(["branch", "-D", branch], cwd=real_repo_root)
        verify = _run_git(["rev-parse", "--verify", "--quiet", branch], cwd=real_repo_root)
        return {"worktree_removed": True, "branch_deleted": verify.get("returncode") == 1,
                "details": details}
    except (OSError, ValueError) as exc:
        return {"worktree_removed": False, "branch_deleted": False,
                "error": _bounded_output(exc), "details": details}


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
