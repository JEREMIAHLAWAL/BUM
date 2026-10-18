"""Real BUM-05 preparation smoke; NOT console/FS-011 readiness evidence.

Run only after committing this runner and all BUM source changes. Requires explicit
scratch/output paths and exact expected BUM/FinderShip HEADs. Uses the unmodified
owning worktree API (including its frozen, lifecycle-disabled pnpm bootstrap).
Only this invocation's fresh run is eligible for cleanup; never sweeps old runs.
No providers, .env loading, feature implementation, merge, reset, or git clean.

Canonical tracked .env.example is a public template: fingerprint bytes only, never
load it. Any other tracked credential-like path blocks the run before creation.
Dependency CONTENT preservation is a separate coordinator gate, not claimed here.
Python finally cannot survive forced termination/power loss; retain the report's
run_id/path/branch for explicitly authorized recovery in that case.
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
from unittest.mock import patch

BUM = Path(__file__).resolve().parents[3]
RUNNER = Path(__file__).resolve()
FINDER = BUM.parent / "FinderShip"
SCRATCH_BASE = Path("C:/Users/2880441/AppData/Local/hermes/cache/scratch")
RUNTIME = SCRATCH_BASE / "fs011-runtime/node-v24.22.0-win-x64"
BASELINE = RUNNER.parent / "preservation-before.json"
ROLES = ("planner", "frontend", "backend", "tester", "reviewer")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, label):
    if not condition:
        raise GateFailure(label)


class GateFailure(RuntimeError):
    """Messages must be fixed labels, never subprocess output or env values."""


def stamp():
    return datetime.now(timezone.utc).isoformat()


def normal(path):
    return os.path.normcase(os.path.abspath(path))


def no_redirect(path):
    for part in (path, *path.parents):
        require(not part.is_symlink() and not part.is_junction(), "redirected_path")


def credential_path(rel):
    # Only the exact committed public template is permitted for fingerprinting.
    if rel == ".env.example":
        return False
    return any(p.lower() == ".env" or p.lower().startswith(".env.") or
               p.lower() in {".ssh", ".aws", ".azure", "credentials", "credentials.json",
                             "id_rsa", "id_ed25519", "token.json"} for p in Path(rel).parts)


def command(argv, cwd, timeout=60):
    return subprocess.run([str(x) for x in argv], cwd=cwd, capture_output=True,
                          timeout=timeout, check=False, shell=False)


def git(root, *args, allowed=(0,)):
    result = command(["git", "--no-optional-locks", *args], root)
    require(result.returncode in allowed, "read_only_git_failed")
    return result


def git_text(root, *args):
    return git(root, *args).stdout.decode("utf-8", errors="strict").strip()


def tracked(root):
    return sorted(p for p in git(root, "ls-files", "-z").stdout.decode().split("\0") if p)


def fingerprint(root, rels):
    result = {}
    for rel in rels:
        require(not credential_path(rel), "tracked_credential_path_refused")
        path = root / rel
        require(path.resolve().is_relative_to(root.resolve()), "fingerprint_outside_root")
        no_redirect(path)
        require(path.is_file(), "fingerprint_missing_regular_file")
        data = path.read_bytes()  # complete contents, not stat/inode/status alone
        result[rel] = {"sha256": sha(data), "bytes": len(data)}
    return result


def registry():
    fields = git(FINDER, "worktree", "list", "--porcelain", "-z").stdout.decode().split("\0")
    entries, entry = [], {}
    for field in fields:
        if not field:
            if entry:
                entries.append(entry)
                entry = {}
        else:
            key, _, value = field.partition(" ")
            entry[key] = normal(value) if key == "worktree" else value
    if entry:
        entries.append(entry)
    return sorted(entries, key=lambda e: e.get("worktree", ""))


def branches():
    return git_text(FINDER, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads")


def source_identity():
    blob = git(BUM, "rev-parse", "HEAD:" + RUNNER.relative_to(BUM).as_posix(), allowed=(0, 128))
    return {"head": git_text(BUM, "rev-parse", "HEAD"),
            "status": git(BUM, "status", "--porcelain=v1", "--untracked-files=all").stdout.decode(),
            "diff_sha256": sha(git(BUM, "diff", "--binary", "HEAD").stdout),
            "runner_sha256": sha(RUNNER.read_bytes()),
            "runner_head_blob": blob.stdout.decode().strip() if blob.returncode == 0 else None,
            "implementation": fingerprint(BUM, [p for p in tracked(BUM) if p.startswith("orchestrator/") and p.endswith(".py")]),
            "python_executable": sys.executable, "python_version": sys.version}


def preservation(baseline):
    rels = tracked(FINDER)
    return {"head": git_text(FINDER, "rev-parse", "HEAD"),
            "status": git(FINDER, "status", "--porcelain=v1", "--untracked-files=all").stdout.decode(),
            "tracked": fingerprint(FINDER, rels),
            "source_inputs": fingerprint(FINDER, sorted(baseline["source_hashes"])),
            "untracked_inputs": fingerprint(FINDER, sorted(baseline["untracked_hashes"])),
            "roles_and_instructions": fingerprint(BUM, ["config/agents.yaml"] + [r + "/instructions.md" for r in ROLES]),
            "baseline_sha256": sha(BASELINE.read_bytes())}


def sanitized_env(original, private, hooks):
    # Deliberate allowlist: do not inherit provider keys, npm tokens, proxy
    # credentials, NODE_OPTIONS, PYTHONPATH, or Git command/config overrides.
    names = {"systemroot", "windir", "comspec", "pathext", "path", "processor_architecture",
             "number_of_processors", "os"}
    env = {k: v for k, v in original.items() if k.casefold() in names}
    env.update({"PATH": str(RUNTIME / "node_modules/.bin") + os.pathsep + str(RUNTIME) + os.pathsep + env.get("PATH", ""),
                "HOME": str(private), "USERPROFILE": str(private), "APPDATA": str(private / "appdata"),
                "LOCALAPPDATA": str(private / "localappdata"), "TEMP": str(private), "TMP": str(private), "TMPDIR": str(private),
                "PYTHONDONTWRITEBYTECODE": "1", "PYTHON_DOTENV_DISABLED": "1",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0",
                "GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": str(hooks),
                "GIT_CONFIG_KEY_1": "core.fsmonitor", "GIT_CONFIG_VALUE_1": "false",
                "COREPACK_ENABLE_ENV_FILE": "0", "COREPACK_ENABLE_NETWORK": "0",
                "COREPACK_ENABLE_PROJECT_SPEC": "0", "COREPACK_ENABLE_DOWNLOAD_PROMPT": "0",
                "npm_config_userconfig": os.devnull, "npm_config_globalconfig": os.devnull,
                "npm_config_ignore_scripts": "true", "npm_config_ignore_pnpmfile": "true",
                "npm_config_manage_package_manager_versions": "false", "CI": "true"})
    return env


def run(args):
    run_id = "run_bum05_prep_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex
    report = {"schema": "BUM-05-real-preparation-v1", "run_id": run_id, "started_utc": stamp(),
              "success": False, "errors": [], "commands": [], "checks": {},
              "scope": "real preparation smoke only; not loaded-console or FS-011 readiness",
              "limitations": ["No canonical node_modules content fingerprint; separate coordinator gate required",
                              "Manifest pnpm check NOT executed; pnpm run lint is a distinct smoke gate",
                              "Forced process termination/power loss can prevent finally cleanup",
                              "Child tools are trusted, not an OS sandbox; bootstrap may fetch packages"]}
    output = Path(args.output).absolute()
    scratch = Path(args.scratch).absolute()
    # Validate output before creating anything; refuse overwrite/redirects.
    require(scratch.is_dir() and scratch.resolve().is_relative_to(SCRATCH_BASE.resolve()), "invalid_explicit_scratch")
    no_redirect(scratch)
    no_redirect(output)
    require(output.parent.is_dir() and output.resolve().is_relative_to(scratch.resolve()), "output_not_in_scratch")
    require(not output.exists(), "output_already_exists")
    with output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    before = identity = baseline = tools = None
    attempted = False
    expected_path = BUM / ".bum/worktrees" / run_id
    expected_branch = "bum-run/" + run_id
    private = scratch / (run_id + "_environment")
    report.update(output=str(output), scratch=str(scratch), runtime=str(RUNTIME),
                  owning_repository=str(FINDER), worktree_path=str(expected_path), branch=expected_branch,
                  expected_bum_head=args.expected_bum_head, expected_finder_head=args.expected_finder_head)
    original_env = os.environ.copy()
    try:
        require(sys.platform == "win32" and hasattr(Path, "is_junction"), "requires_windows_python312_or_newer")
        require(all(re.fullmatch(r"[0-9a-f]{40}", value) for value in (args.expected_bum_head, args.expected_finder_head)), "invalid_expected_head")
        no_redirect(private)
        private.mkdir(exist_ok=False)
        hooks = private / "empty-hooks"
        hooks.mkdir()
        os.environ.clear()
        os.environ.update(sanitized_env(original_env, private, hooks))
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(BUM))
        require((RUNTIME / "node.exe").is_file() and (RUNTIME / "node_modules/.bin/pnpm.cmd").is_file(), "runtime_missing")
        no_redirect(RUNTIME)
        no_redirect(RUNTIME / "node.exe")
        no_redirect(RUNTIME / "node_modules/.bin/pnpm.cmd")
        identity = source_identity()
        report["source_before"] = identity
        require(identity["head"] == args.expected_bum_head and not identity["status"], "bum_not_clean_expected_committed_head")
        require(RUNNER.relative_to(BUM).as_posix() in tracked(BUM), "runner_not_committed")
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        require(len(baseline["source_hashes"]) == 15 and len(baseline["untracked_hashes"]) == 4, "baseline_input_count_mismatch")
        before = preservation(baseline)
        report["preservation_before"] = before
        require(before["head"] == args.expected_finder_head, "finder_head_mismatch")
        require(git(FINDER, "merge-base", "--is-ancestor", baseline["finder_head"], args.expected_finder_head, allowed=(0, 1)).returncode == 0,
                "historical_finder_checkpoint_not_preserved")
        report["historical_finder_head"] = baseline["finder_head"]
        report["authorized_documentation_successor"] = args.expected_finder_head != baseline["finder_head"]
        successor_paths = git_text(FINDER, 'diff', '--name-only', baseline['finder_head'], args.expected_finder_head).splitlines()
        require(set(successor_paths).issubset({'docs/WORK_STATUS.md'}), 'unexpected_finder_successor_paths')
        report['authorized_successor_paths'] = successor_paths
        for group, baseline_key in (("source_inputs", "source_hashes"), ("untracked_inputs", "untracked_hashes")):
            require({p: v["sha256"] for p, v in before[group].items()} == baseline[baseline_key], "historical_input_baseline_mismatch")
        require(before["roles_and_instructions"]["config/agents.yaml"]["sha256"] == baseline["role_config_hash"], "role_config_baseline_mismatch")
        untracked = set(git(FINDER, "ls-files", "--others", "--exclude-standard", "-z").stdout.decode().split("\0"))
        require(set(baseline["untracked_hashes"]).issubset(untracked), "transfer_inputs_not_untracked")
        report["checks"]["historical_inputs_and_role_config"] = True
        # Patch only dotenv loading, never Git, bootstrap, or owning cleanup.
        import dotenv
        with patch.object(dotenv, "load_dotenv", return_value=False), patch.object(dotenv, "find_dotenv", return_value=""):
            from orchestrator import worktree_tools as tools
            from orchestrator import repo_tools
            from orchestrator.manifest import BumManifest, find_manifest, load_manifest
        report["api_sources"] = {"worktree_tools": str(Path(tools.__file__).resolve()), "repo_tools": str(Path(repo_tools.__file__).resolve())}
        require(Path(tools.__file__).resolve() == BUM / "orchestrator/worktree_tools.py", "unexpected_worktree_api")
        require(Path(repo_tools.__file__).resolve() == BUM / "orchestrator/repo_tools.py", "unexpected_repo_api")
        manifest_path = find_manifest(FINDER)
        require(manifest_path == (FINDER / "bum.config.json").resolve(), "unexpected_manifest_path")
        manifest = BumManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        require(manifest.worktree.bootstrap == "pnpm-frozen", "frozen_bootstrap_not_selected")
        report["manifest"] = {"path": str(manifest_path), "sha256": sha(manifest_path.read_bytes()),
                              "bootstrap": manifest.worktree.bootstrap, "verification": manifest.verification.model_dump(),
                              "lint_smoke_is_not_manifest_check": manifest.verification.lint_cmd != "pnpm run lint"}
        require(manifest.verification.typecheck_cmd == "pnpm run typecheck" and manifest.verification.lint_cmd == "pnpm check", "unexpected_manifest_gates")
        require(tools.worktree_root_dir(FINDER) / run_id == expected_path, "unexpected_managed_path")
        no_redirect(expected_path)
        report["registry_before"] = registry()
        report["branches_before"] = branches()
        require(not expected_path.exists() and all(e.get("worktree") != normal(expected_path) for e in report["registry_before"]), "fresh_path_collision")
        require(git(FINDER, "show-ref", "--verify", "--quiet", "refs/heads/" + expected_branch, allowed=(0, 1)).returncode == 1, "fresh_branch_collision")
        node, pnpm = shutil.which("node"), shutil.which("pnpm")
        require(node and pnpm and normal(node) == normal(RUNTIME / "node.exe") and normal(pnpm) == normal(RUNTIME / "node_modules/.bin/pnpm.cmd"), "runtime_resolution_mismatch")
        report["executables"] = {"node": node, "pnpm": pnpm, "node_sha256": sha(Path(node).read_bytes()), "pnpm_wrapper_sha256": sha(Path(pnpm).read_bytes())}

        def smoke(argv, cwd, expected=None, timeout=180):
            completed = command(argv, cwd, timeout)
            item = {"argv": [str(x) for x in argv], "cwd": str(cwd), "exit_code": completed.returncode,
                    "stdout_sha256": sha(completed.stdout), "stdout_bytes": len(completed.stdout),
                    "stderr_sha256": sha(completed.stderr), "stderr_bytes": len(completed.stderr)}
            report["commands"].append(item)
            require(completed.returncode == 0, "smoke_command_failed")
            if expected is not None:
                version = completed.stdout.decode().strip()
                item["expected_version"] = expected
                item["version_matches"] = version == expected
                if version == expected:
                    item["verified_version"] = version
                require(version == expected, "runtime_version_mismatch")

        smoke([node, "--version"], FINDER, "v24.22.0")
        smoke([pnpm, "--version"], FINDER, "10.9.0")
        require(source_identity() == identity and preservation(baseline) == before, "precreate_source_changed")
        # Set before API call so partial creation/exceptions still get cleanup.
        attempted = True
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
            created = tools.create_run_worktree(run_id, FINDER)
        report["create"] = {"success": created.get("success") is True,
                            "expected_path": normal(created.get("worktree_path") or "") == normal(expected_path),
                            "expected_branch": created.get("branch") == expected_branch,
                            "diagnostics_present": bool(created.get("error")), "captured_output_sha256": sha(capture.getvalue().encode())}
        require(all(report["create"][k] for k in ("success", "expected_path", "expected_branch")), "real_worktree_creation_failed")
        require(git_text(expected_path, "rev-parse", "HEAD") == args.expected_finder_head, "worktree_head_mismatch")
        owning = git_text(FINDER, "rev-parse", "--path-format=absolute", "--git-common-dir")
        require(git_text(expected_path, "rev-parse", "--path-format=absolute", "--git-common-dir") == owning, "wrong_owning_registry")
        entries = [e for e in registry() if e.get("worktree") == normal(expected_path)]
        require(len(entries) == 1 and entries[0].get("branch") == "refs/heads/" + expected_branch and entries[0].get("HEAD") == args.expected_finder_head, "owning_registration_mismatch")
        require(load_manifest(expected_path).model_dump() == manifest.model_dump(), "manifest_snapshot_mismatch")
        repo_tools.set_active_project_path(FINDER)
        repo_tools.set_run_worktree_override(expected_path)
        require(repo_tools.resolve_repo_root() == (expected_path.resolve(), "run_worktree"), "repo_override_mismatch")
        report["checks"]["exact_head_manifest_and_owning_registry"] = True
        isolation = {}
        for rel in ("node_modules", "apps/web/node_modules", "packages/shared/node_modules"):
            candidate, canonical = expected_path / rel, FINDER / rel
            good = candidate.is_dir() and not candidate.is_symlink() and not candidate.is_junction()
            good = good and candidate.resolve().is_relative_to(expected_path.resolve())
            if good and canonical.exists():
                good = not os.path.samefile(candidate, canonical)
            isolation[rel] = {"isolated": good, "canonical_path": str(canonical)}
        report["dependency_isolation"] = isolation
        require(all(v["isolated"] for v in isolation.values()), "dependency_isolation_failed")
        smoke([node, "--version"], expected_path, "v24.22.0")
        smoke([pnpm, "--version"], expected_path, "10.9.0")
        smoke([pnpm, "exec", "node", "--version"], expected_path, "v24.22.0")
        report["checks"]["versions"] = True
        smoke([pnpm, "run", "typecheck"], expected_path)
        report["checks"]["typecheck"] = True
        smoke([pnpm, "run", "lint"], expected_path)
        report["checks"]["lint_smoke_not_pnpm_check"] = True
        report["checks"]["dependency_isolation"] = True
    except BaseException as exc:
        report["errors"].append({"stage": "preparation", "type": type(exc).__name__,
                                 "label": str(exc) if isinstance(exc, GateFailure) else "details_omitted_to_avoid_credentials"})
    finally:
        if attempted and tools is not None:
            try:
                # Only our collision-checked unique run; actual owning API, no
                # registry pruning, old-tree sweep, fallback rmtree, or retries.
                capture = io.StringIO()
                with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
                    cleaned = tools.discard_run_worktree(run_id, FINDER)
                report["cleanup_api"] = {"worktree_removed": cleaned.get("worktree_removed") is True,
                                         "branch_deleted": cleaned.get("branch_deleted") is True,
                                         "diagnostics_present": bool(cleaned.get("error")),
                                         "captured_output_sha256": sha(capture.getvalue().encode())}
                after_registry, after_branches = registry(), branches()
                report["registry_after"] = after_registry
                report["branches_after"] = after_branches
                report["cleanup_readback"] = {"path_absent": not expected_path.exists() and not expected_path.is_symlink(),
                    "registration_absent": all(e.get("worktree") != normal(expected_path) for e in after_registry),
                    "branch_absent": git(FINDER, "show-ref", "--verify", "--quiet", "refs/heads/" + expected_branch, allowed=(0, 1)).returncode == 1,
                    "other_registrations_unchanged": after_registry == report["registry_before"],
                    "other_branches_unchanged": after_branches == report["branches_before"]}
                report["checks"]["cleanup"] = all(report["cleanup_readback"].values()) and all(report["cleanup_api"][k] for k in ("worktree_removed", "branch_deleted")) and not report["cleanup_api"]["diagnostics_present"]
            except BaseException as exc:
                report["errors"].append({"stage": "cleanup", "type": type(exc).__name__})
                report["checks"]["cleanup"] = False
        else:
            report["cleanup_api"] = {"not_attempted": True, "reason": "no_new_worktree_creation_attempt"}
            report["checks"]["cleanup"] = False
        try:
            if before is not None:
                report["preservation_after"] = preservation(baseline)
                report["checks"]["content_preservation"] = report["preservation_after"] == before
            if identity is not None:
                report["source_after"] = source_identity()
                report["checks"]["source_identity_preserved"] = report["source_after"] == identity
        except BaseException as exc:
            report["errors"].append({"stage": "preservation", "type": type(exc).__name__})
        required = {"historical_inputs_and_role_config", "exact_head_manifest_and_owning_registry", "versions", "typecheck",
                    "lint_smoke_not_pnpm_check", "dependency_isolation", "cleanup", "content_preservation", "source_identity_preserved"}
        report["success"] = not report["errors"] and all(report["checks"].get(k) is True for k in required)
        report["finished_utc"] = stamp()
        # Keep scratch environment for audit (contains no copied credentials).
        # Report always written for every post-validation failure, even imports.
        os.environ.clear()
        os.environ.update(original_env)
        with output.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(json.dumps({"success": report["success"], "report": str(output), "run_id": run_id}))
    return 0 if report["success"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", required=True, help="Existing directory beneath the Hermes scratch root")
    parser.add_argument("--output", required=True, help="New JSON file beneath --scratch; never overwritten initially")
    parser.add_argument("--expected-bum-head", required=True)
    parser.add_argument("--expected-finder-head", required=True)
    args = parser.parse_args()
    try:
        return run(args)
    except BaseException as exc:
        # Invalid/unwritable output cannot safely receive a report; do not leak
        # exception messages (which may include user-supplied sensitive text).
        print(json.dumps({"success": False, "stage": "report_setup_or_write", "type": type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
