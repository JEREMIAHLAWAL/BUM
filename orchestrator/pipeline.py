import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestrator.run import run_agent, load_agents
from orchestrator.events import EventLogger, set_current_logger, emit_event
from orchestrator.repo_tools import (
    get_repo_root,
    get_active_manifest,
    run_preflight_check,
    repo_tree,
    read_file,
    write_file,
    delete_file,
    file_exists,
)

from orchestrator.command_tools import run_safe_command
from orchestrator.git_tools import run_safe_git_command
from orchestrator.git_attribution import (
    capture_git_baseline,
    compute_run_git_attribution,
    format_git_attribution_context,
)
from orchestrator.harness_tools import (
    extract_type_skeletons,
    sanitize_test_output,
    run_typecheck_gate,
)
from orchestrator.cancellation import CancellationToken, PipelineCancelledException
from orchestrator.providers import ProviderError, ProviderTimeoutError, ProviderAuthError, ProviderRateLimitError


AGENT_PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = AGENT_PROJECT_ROOT / "pipeline"
MAX_REVIEW_CYCLES = 3


def read_pipeline_file(name: str) -> str:
    path = PIPELINE_DIR / name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_pipeline_file(name: str, content: str) -> None:
    path = PIPELINE_DIR / name
    path.write_text(content, encoding="utf-8")


def get_salvaged_context() -> str:
    salvage_dir = PIPELINE_DIR / "salvage" / "latest"
    if not salvage_dir.exists():
        return ""
    
    files = list(salvage_dir.rglob("*"))
    parts = []
    for f in sorted(files):
        if f.is_file():
            rel_name = str(f.relative_to(salvage_dir)).replace("\\", "/")
            try:
                content = f.read_text(encoding="utf-8")
                parts.append(f"SALVAGED FILE: {rel_name}\n```\n{content}\n```")
            except Exception:
                continue
    if not parts:
        return ""
    return "\n\nSALVAGED CODE FROM PRIOR ATTEMPT (Inspect & reuse working components, discard broken imports/syntax):\n" + "\n\n".join(parts)


def salvage_unapproved_work(run_id: str) -> None:
    salvage_dir = PIPELINE_DIR / "salvage" / "latest"
    import shutil
    if salvage_dir.exists():
        shutil.rmtree(salvage_dir, ignore_errors=True)
    salvage_dir.mkdir(parents=True, exist_ok=True)

    repo_root = get_repo_root()
    status = run_safe_git_command(["git", "status", "--short"])
    lines = status["stdout"].splitlines()

    for line in lines:
        if len(line) < 4:
            continue
        raw_path = line[3:].strip()
        if (raw_path.startswith('"') and raw_path.endswith('"')) or (raw_path.startswith("'") and raw_path.endswith("'")):
            raw_path = raw_path[1:-1]
        
        target = (repo_root / raw_path).resolve()
        if target.is_file():
            dest = salvage_dir / raw_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, dest)
        elif target.is_dir():
            for subfile in target.rglob("*"):
                if subfile.is_file():
                    sub_rel = subfile.relative_to(repo_root)
                    dest = salvage_dir / sub_rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(subfile, dest)

    meta = {
        "run_id": run_id,
        "saved_at": time.time(),
    }
    (salvage_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def clear_salvaged_work() -> None:
    salvage_dir = PIPELINE_DIR / "salvage" / "latest"
    import shutil
    if salvage_dir.exists():
        shutil.rmtree(salvage_dir, ignore_errors=True)


def get_shared_context() -> str:
    handoff = read_pipeline_file("HANDOFF.md")
    tree = repo_tree()
    salvaged = get_salvaged_context()
    repo_root = get_repo_root()
    manifest = get_active_manifest()
    type_skeletons = extract_type_skeletons(repo_root, manifest=manifest) if repo_root else ""

    project_name = manifest.name.upper() if manifest else "WORKSPACE"
    parts = []

    if handoff:
        parts.append(f"{project_name} ENGINEERING HANDOFF:\n\n{handoff}")
    parts.append(f"CURRENT {project_name} REPOSITORY TREE:\n\n{tree}")

    # Inject manifest rules & constraints
    if manifest and manifest.rules:
        rule_lines = []
        if manifest.rules.forbidden_imports:
            rule_lines.append(f"- FORBIDDEN IMPORTS (Do NOT import): {', '.join(manifest.rules.forbidden_imports)}")
        if manifest.rules.required_packages:
            rule_lines.append(f"- REQUIRED / PREFERRED PACKAGES: {', '.join(manifest.rules.required_packages)}")
        if manifest.rules.forbidden_tokens:
            rule_lines.append(f"- FORBIDDEN TOKENS / PATTERNS: {', '.join(manifest.rules.forbidden_tokens)}")
        if manifest.rules.allowed_write_roots:
            rule_lines.append(f"- AUTHORIZED WRITE ROOTS: {', '.join(manifest.rules.allowed_write_roots)}")
        if manifest.rules.prohibited_files:
            rule_lines.append(f"- PROTECTED FILES (Never modify): {', '.join(manifest.rules.prohibited_files)}")

        if rule_lines:
            parts.append(f"=== PROJECT RULES & CONSTRAINTS ({manifest.name}) ===\n" + "\n".join(rule_lines) + "\n=== END RULES ===")

    if type_skeletons:
        parts.append(type_skeletons)
    if salvaged:
        parts.append(salvaged)

    return "\n\n".join(parts) + "\n"



def format_command_result(result: dict) -> str:
    stdout = result.get('stdout', '')
    stderr = result.get('stderr', '')
    cmd = result.get('command', '')

    # Apply observation sanitization on test & build commands
    if any(k in cmd for k in ["test", "jest", "vitest", "pytest", "tsc"]):
        stdout = sanitize_test_output(stdout)
        stderr = sanitize_test_output(stderr)

    return f"""COMMAND: {cmd}
RETURN CODE: {result.get('returncode', '')}
TIMED OUT: {result.get('timed_out', False)}

STDOUT:
{stdout}

STDERR:
{stderr}""".strip()


def format_git_result(result: dict) -> str:
    cmd = result.get('command', '')
    stdout = result.get('stdout', '')

    # Filter lockfile bloat from raw diff to protect LLM context windows
    if "git diff" in cmd and "--stat" not in cmd and "--name-only" not in cmd:
        filtered_lines = []
        skip_file = False
        for line in stdout.splitlines():
            if line.startswith("diff --git"):
                skip_file = any(lock in line for lock in ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", ".expo"))
            if not skip_file:
                filtered_lines.append(line)
        stdout = "\n".join(filtered_lines)

    # Safety budget cap (max 50KB stdout per git command)
    if len(stdout) > 50000:
        stdout = stdout[:50000] + "\n\n... [TRUNCATED: Remaining git diff exceeded 50KB safety limit] ..."

    return f"""COMMAND: {cmd}
RETURN CODE: {result.get('returncode', '')}
TIMED OUT: {result.get('timed_out', False)}

STDOUT:
{stdout}

STDERR:
{result.get('stderr', '')}""".strip()


class MalformedWriteError(ValueError):
    """Raised when an agent produces a malformed write block."""
    pass


def parse_and_apply_agent_file_operations(agent_output: str, role: str) -> dict:
    malformed_write = re.search(r"```write(?:\s+|$|\n)(?!:)", agent_output)
    if malformed_write:
        raise MalformedWriteError(
            f"Agent [{role}] produced a malformed write block. "
            "The syntax must be ```write:relative/path/to/file (colon immediately after write)."
        )

    malformed_delete = re.search(r"```delete(?:\s+|$|\n)(?!:)", agent_output)
    if malformed_delete:
        raise MalformedWriteError(
            f"Agent [{role}] produced a malformed delete block. "
            "The syntax must be ```delete:relative/path/to/file (colon immediately after delete)."
        )

    # Match ```write:path/to/file\n...``` while avoiding accidental immediate empty closings
    write_pattern = re.compile(r"```write:(.+?)\n(?:```\n?)?(.*?)```", re.DOTALL)
    delete_pattern = re.compile(r"```delete:(.+?)\n*```", re.DOTALL)

    parsed_actions = []
    for match in write_pattern.finditer(agent_output):
        rel_path = match.group(1).strip()
        content = match.group(2)
        parsed_actions.append(("write", rel_path, content))

    for match in delete_pattern.finditer(agent_output):
        rel_path = match.group(1).strip()
        parsed_actions.append(("delete", rel_path, None))

    created = []
    modified = []
    deleted = []

    for action_type, rel_path, content in parsed_actions:
        emit_event(
            event="file_operation_started",
            stage=role,
            payload={
                "op": action_type,
                "path": rel_path,
                "role": role,
            },
        )
        if action_type == "write":
            res = write_file(rel_path, content, role=role)
            if res["action"] == "created":
                created.append(rel_path)
            else:
                modified.append(rel_path)
            emit_event(
                event="file_operation_completed",
                stage=role,
                payload={
                    "op": action_type,
                    "path": rel_path,
                    "role": role,
                    "action": res["action"],
                    "status": "verified",
                    "bytes": len(content.encode("utf-8")) if content else 0,
                },
            )
        elif action_type == "delete":
            delete_file(rel_path, role=role)
            deleted.append(rel_path)
            emit_event(
                event="file_operation_completed",
                stage=role,
                payload={
                    "op": action_type,
                    "path": rel_path,
                    "role": role,
                    "action": "deleted",
                    "status": "verified",
                    "bytes": 0,
                },
            )

    executed_count = len(created) + len(modified) + len(deleted)
    parsed_count = len(parsed_actions)

    accounting = {
        "parsed_count": parsed_count,
        "executed_count": executed_count,
        "created": created,
        "modified": modified,
        "deleted": deleted,
    }

    emit_event(
        event="files_changed",
        stage=role,
        payload={
            "role": role,
            "parsed_count": parsed_count,
            "executed_count": executed_count,
            "created": created,
            "modified": modified,
            "deleted": deleted,
        },
    )

    print(f"\nWRITE ACTIONS PARSED: {parsed_count}")
    print(f"WRITE ACTIONS EXECUTED: {executed_count}")
    print(f"FILES CREATED: {created}")
    print(f"FILES MODIFIED: {modified}")
    print(f"FILES DELETED: {deleted}", flush=True)

    claimed_files = re.search(r"FILES CHANGED:\s*\n((?:\s*-\s*[^\n]+\n*)+)", agent_output, re.IGNORECASE)
    if claimed_files:
        items = [line.strip().lstrip("-").strip() for line in claimed_files.group(1).splitlines() if line.strip().lstrip("-").strip()]
        real_items = [i for i in items if i.lower() not in ("none", "(none)", "none.", "n/a")]
        if real_items and executed_count == 0:
            raise RuntimeError(
                f"Agent [{role}] claimed files changed ({real_items}) but WRITE ACTIONS EXECUTED is 0. "
                "Ensure code blocks use ```write:path/to/file syntax."
            )

    return accounting


def parse_reviewer_verdict(reviewer_output: str) -> dict:
    """
    Parse machine-readable Reviewer verdict header:
    VERDICT: APPROVE / CHANGES REQUIRED
    FRONTEND_FIX_REQUIRED: YES / NO
    BACKEND_FIX_REQUIRED: YES / NO
    DEPENDENCY_FIX_REQUIRED: YES / NO
    """
    verdict_match = re.search(r"VERDICT:\s*(APPROVE|CHANGES REQUIRED)", reviewer_output, re.IGNORECASE)
    if not verdict_match:
        raise ValueError(f"Reviewer output does not contain valid 'VERDICT: APPROVE' or 'VERDICT: CHANGES REQUIRED'.\nOutput:\n{reviewer_output}")

    verdict = verdict_match.group(1).upper()

    fe_match = re.search(r"FRONTEND_FIX_REQUIRED:\s*(YES|NO)", reviewer_output, re.IGNORECASE)
    be_match = re.search(r"BACKEND_FIX_REQUIRED:\s*(YES|NO)", reviewer_output, re.IGNORECASE)
    dep_match = re.search(r"DEPENDENCY_FIX_REQUIRED:\s*(YES|NO)", reviewer_output, re.IGNORECASE)

    fe_req = fe_match.group(1).upper() == "YES" if fe_match else False
    be_req = be_match.group(1).upper() == "YES" if be_match else False
    dep_req = dep_match.group(1).upper() == "YES" if dep_match else False

    # If changes required but none explicitly tagged, default to Frontend fix if unspecified
    if verdict == "CHANGES REQUIRED" and not (fe_req or be_req or dep_req):
        fe_req = True

    return {
        "verdict": verdict,
        "frontend_fix_required": fe_req,
        "backend_fix_required": be_req,
        "dependency_fix_required": dep_req,
    }


def get_untracked_files_content() -> str:
    status = run_safe_git_command(["git", "status", "--short"])
    lines = status["stdout"].splitlines()
    untracked = []
    for line in lines:
        if line.startswith("??"):
            raw_path = line[3:].strip()
            # Strip surrounding quotes if Git quoted the path (e.g. spaces/special chars)
            if (raw_path.startswith('"') and raw_path.endswith('"')) or (raw_path.startswith("'") and raw_path.endswith("'")):
                raw_path = raw_path[1:-1]
            untracked.append(raw_path)

    parts = []
    for rel_path in untracked:
        # If it's a directory (e.g. src/app/), read files inside
        target = (get_repo_root() / rel_path).resolve()
        if target.is_dir():
            for subfile in target.rglob("*"):
                if subfile.is_file():
                    sub_rel = str(subfile.relative_to(get_repo_root())).replace("\\", "/")
                    content = read_file(sub_rel)
                    parts.append(f"FILE: {sub_rel}\n```\n{content}\n```")
        elif target.is_file():
            content = read_file(rel_path)
            parts.append(f"FILE: {rel_path}\n```\n{content}\n```")

    return "\n\n".join(parts)


def execute_test_and_git_commands(baseline: Optional[dict] = None):
    manifest = get_active_manifest()
    test_commands = []

    # Dynamically select verification commands from active manifest
    if manifest and manifest.verification:
        if manifest.verification.typecheck_cmd:
            test_commands.append(shlex.split(manifest.verification.typecheck_cmd))
        if manifest.verification.test_cmd:
            test_commands.append(shlex.split(manifest.verification.test_cmd))

    if not test_commands:
        test_commands = [
            ["npm", "run", "ts:check"],
            ["npm", "test"],
        ]

    command_results = []
    for cmd in test_commands:
        cmd_str = " ".join(cmd)
        try:
            res = run_safe_command(cmd)
            res["timed_out"] = False
        except subprocess.TimeoutExpired:
            res = {"command": cmd_str, "returncode": -1, "stdout": "", "stderr": "Command timed out after 300s", "timed_out": True}
        except Exception as e:
            res = {"command": cmd_str, "returncode": -1, "stdout": "", "stderr": str(e), "timed_out": False}
        command_results.append(res)


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

    # Extract git diff details if available
    diff_stat_res = next((r for r in git_results if r.get("command") == "git diff --stat"), None)
    name_only_res = next((r for r in git_results if r.get("command") == "git diff --name-only"), None)
    diff_stat = diff_stat_res.get("stdout", "") if diff_stat_res else ""
    changed_files = [f.strip() for f in name_only_res.get("stdout", "").splitlines() if f.strip()] if name_only_res else []

    status_res = next((r for r in git_results if r.get("command") == "git status --short"), None)
    untracked_files = []
    if status_res and status_res.get("stdout"):
        for line in status_res["stdout"].splitlines():
            if line.startswith("??"):
                untracked_files.append(line[3:].strip().strip("\"'"))

    # Compute task-scoped git attribution if baseline is available
    attribution = None
    if baseline is not None:
        try:
            attribution = compute_run_git_attribution(baseline)
        except Exception as e:
            print(f"[WARN] Failed to compute git attribution: {e}", file=sys.stderr)

    emit_event(
        event="test_result",
        stage="tester",
        payload={"commands": command_results},
    )

    git_payload = {
        "diff_stat": diff_stat,
        "changed_files": changed_files,
        "untracked_files": untracked_files,
        "git_results": git_results,
    }
    if attribution:
        git_payload["attribution"] = {
            "pre_existing": attribution["pre_existing"],
            "run_delta": attribution["run_delta"],
        }

    emit_event(
        event="git_diff_updated",
        stage="tester",
        payload=git_payload,
    )

    return command_results, git_results, attribution


def run_pipeline(
    task: str,
    run_id: Optional[str] = None,
    cancellation_token: Optional[CancellationToken] = None,
    retry_of: Optional[str] = None,
    label: Optional[str] = None,
) -> str:
    logger = EventLogger(run_id=run_id)
    set_current_logger(logger)
    pipeline_start_time = time.time()
    agent_configs = load_agents()

    def check_cancellation(current_stage: str, cycle_num: Optional[int] = None) -> None:
        """Helper to safely abort at checkpoints if cancellation was requested."""
        if cancellation_token and cancellation_token.is_cancelled():
            reason = cancellation_token.reason or "USER_REQUESTED_STOP"
            emit_event(
                event="cancellation_requested",
                stage=current_stage,
                cycle=cycle_num,
                payload={
                    "requested_by": "operator",
                    "reason": reason,
                    "stage": current_stage,
                    "cycle": cycle_num,
                },
            )
            emit_event(
                event="pipeline_finished",
                stage=current_stage,
                cycle=cycle_num,
                payload={
                    "final_status": "CANCELLED",
                    "reason": reason,
                    "cycles_used": cycle_num or 0,
                    "total_duration_sec": time.time() - pipeline_start_time,
                },
            )
            print(f"\nPIPELINE_CANCELLED ({reason}) at stage: {current_stage}", flush=True)
            raise PipelineCancelledException(reason)

    def safe_run_agent(role: str, user_prompt: str, current_stage: str, cycle_num: Optional[int] = None) -> str:
        """Execute an agent call wrapped in provider error & timeout safety."""
        try:
            return run_agent(role, user_prompt)
        except ProviderTimeoutError as exc:
            emit_event(
                event="stage_failed",
                stage=current_stage,
                cycle=cycle_num,
                payload={
                    "error_type": "PROVIDER_TIMEOUT",
                    "provider": exc.provider,
                    "model": exc.model,
                    "timeout_seconds": exc.timeout_seconds,
                    "error": str(exc),
                },
            )
            emit_event(
                event="pipeline_finished",
                stage=current_stage,
                cycle=cycle_num,
                payload={
                    "final_status": "FAILED",
                    "reason": "PROVIDER_TIMEOUT",
                    "cycles_used": cycle_num or 0,
                    "total_duration_sec": time.time() - pipeline_start_time,
                },
            )
            print(f"\n[ERROR] Provider call timed out in stage {current_stage}: {exc}", flush=True)
            raise
        except ProviderError as exc:
            emit_event(
                event="stage_failed",
                stage=current_stage,
                cycle=cycle_num,
                payload={
                    "error_type": exc.error_type,
                    "provider": exc.provider,
                    "model": exc.model,
                    "error": str(exc),
                },
            )
            emit_event(
                event="pipeline_finished",
                stage=current_stage,
                cycle=cycle_num,
                payload={
                    "final_status": "FAILED",
                    "reason": exc.error_type,
                    "cycles_used": cycle_num or 0,
                    "total_duration_sec": time.time() - pipeline_start_time,
                },
            )
            print(f"\n[ERROR] Provider error in stage {current_stage}: {exc}", flush=True)
            raise

    repo_path_str = ""
    try:
        repo_path_str = str(get_repo_root())
    except Exception:
        pass

    pipeline_started_payload = {
        "task": task,
        "repo_path": repo_path_str,
        "max_review_cycles": MAX_REVIEW_CYCLES,
        "agent_configs": agent_configs,
    }
    if label:
        pipeline_started_payload["label"] = label
    if retry_of:
        pipeline_started_payload["retry_of"] = retry_of

    emit_event(
        event="pipeline_started",
        payload=pipeline_started_payload,
    )

    print("=== TRAYNE FIVE-AGENT PIPELINE ===")

    # Preflight Environment Checks
    t0_stage = time.time()
    emit_event(
        event="stage_started",
        stage="preflight",
        payload={"step": "preflight_and_baseline"},
    )
    print("\n[0/5] PREFLIGHT CHECK STARTED", flush=True)
    try:
        preflight = run_preflight_check()
    except Exception as exc:
        emit_event(
            event="stage_failed",
            stage="preflight",
            payload={"error": str(exc)},
        )
        emit_event(
            event="pipeline_finished",
            payload={
                "final_status": "FAILED",
                "reason": f"Preflight check failed: {exc}",
                "cycles_used": 0,
                "total_duration_sec": time.time() - pipeline_start_time,
            },
        )
        raise

    print(f"[0/5] PREFLIGHT CHECK PASSED (Repo: {preflight['repo_root']})", flush=True)

    # Baseline Checks
    print("\nBASELINE CHECK STARTED", flush=True)
    # Guarantee a clean working tree before baseline checks
    print("Resetting workspace to clean HEAD...", flush=True)
    run_safe_git_command(["git", "reset", "--hard", "HEAD"])
    run_safe_git_command(["git", "clean", "-fd"])

    git_init = run_safe_git_command(["git", "status", "--short"])
    if git_init["returncode"] != 0:
        emit_event(
            event="stage_failed",
            stage="baseline",
            payload={"error": git_init["stderr"]},
        )
        emit_event(
            event="pipeline_finished",
            payload={
                "final_status": "FAILED",
                "reason": f"Git baseline failed: {git_init['stderr']}",
                "cycles_used": 0,
                "total_duration_sec": time.time() - pipeline_start_time,
            },
        )
        raise RuntimeError(f"Git status failed before baseline: {git_init['stderr']}")

    manifest = get_active_manifest()
    project_name = manifest.name if manifest else "Target Workspace"

    # Dynamic baseline typecheck if configured
    if manifest and manifest.verification and manifest.verification.typecheck_cmd:
        ts_cmd = shlex.split(manifest.verification.typecheck_cmd)
        ts_check_base = run_safe_command(ts_cmd)
        emit_event(
            event="test_result",
            stage="baseline",
            payload={"commands": [ts_check_base]},
        )
        if ts_check_base["returncode"] != 0:
            print(f"BASELINE TYPECHECK FAILED ({manifest.verification.typecheck_cmd}):")
            print(ts_check_base["stderr"] or ts_check_base["stdout"])
            emit_event(
                event="stage_failed",
                stage="baseline",
                payload={"error": f"Baseline typecheck failed ({manifest.verification.typecheck_cmd})."},
            )
            emit_event(
                event="pipeline_finished",
                payload={
                    "final_status": "FAILED",
                    "reason": f"Baseline typecheck failed ({manifest.verification.typecheck_cmd}).",
                    "cycles_used": 0,
                    "total_duration_sec": time.time() - pipeline_start_time,
                },
            )
            raise RuntimeError(f"Baseline typecheck failed ({manifest.verification.typecheck_cmd}). Halting before coding.")

    # Dynamic baseline test if configured
    if manifest and manifest.verification and manifest.verification.test_cmd:
        test_cmd = shlex.split(manifest.verification.test_cmd)
        test_base = run_safe_command(test_cmd)
        emit_event(
            event="test_result",
            stage="baseline",
            payload={"commands": [test_base]},
        )
        if test_base["returncode"] != 0:
            print(f"BASELINE TEST FAILED ({manifest.verification.test_cmd}):")
            print(test_base["stderr"] or test_base["stdout"])
            emit_event(
                event="stage_failed",
                stage="baseline",
                payload={"error": f"Baseline test suite failed ({manifest.verification.test_cmd})."},
            )
            emit_event(
                event="pipeline_finished",
                payload={
                    "final_status": "FAILED",
                    "reason": f"Baseline test suite failed ({manifest.verification.test_cmd}).",
                    "cycles_used": 0,
                    "total_duration_sec": time.time() - pipeline_start_time,
                },
            )
            raise RuntimeError(f"Baseline test suite failed ({manifest.verification.test_cmd}). Halting before coding.")


    emit_event(
        event="stage_completed",
        stage="preflight",
        payload={
            "duration_sec": time.time() - t0_stage,
            "status": "ok",
        },
    )
    print("BASELINE CHECK PASSED", flush=True)

    # Check cancellation checkpoint after preflight/baseline
    check_cancellation(current_stage="preflight", cycle_num=0)

    # Capture Read-Only Git Worktree Baseline for Task Attribution
    git_baseline = capture_git_baseline()
    emit_event(
        event="git_baseline_captured",
        stage="preflight",
        payload={
            "tracked_modified": git_baseline.get("tracked_modified", []),
            "tracked_staged": git_baseline.get("tracked_staged", []),
            "tracked_deleted": git_baseline.get("tracked_deleted", []),
            "untracked_files": git_baseline.get("untracked_files", []),
            "diff_stat": git_baseline.get("diff_stat", ""),
        },
    )

    shared_context = get_shared_context()

    # Check cancellation checkpoint before Planner
    check_cancellation(current_stage="planner", cycle_num=0)

    # 1. PLANNER
    emit_event(
        event="stage_started",
        stage="planner",
        payload={
            "role": "planner",
            "provider": agent_configs.get("planner", {}).get("provider"),
            "model": agent_configs.get("planner", {}).get("model"),
        },
    )
    print("\n[1/5] PLANNER STARTED", flush=True)
    planner_prompt = f"""
{shared_context}

TASK:

{task}

Create the implementation specification for this task.

CRITICAL ARCHITECTURAL CONSTRAINTS:
- Respect the actual {project_name} architecture and project type ({manifest.project_type if manifest else 'general'}).
- Inspect the current repository tree carefully.
- Adhere strictly to the project rules and file boundaries defined in the manifest.
- Do NOT invent unsupported infrastructure, backend APIs, or unneeded dependencies.
- If backend work is not needed, explicitly state: "BACKEND TASK: None."
- Clearly specify the exact files to create or modify for Frontend and Backend.

Return the complete contents that should be stored in:

pipeline/spec.md
"""

    t0 = time.time()
    spec = safe_run_agent("planner", planner_prompt, current_stage="planner", cycle_num=0)
    t_planner = time.time() - t0
    write_pipeline_file("spec.md", spec)
    emit_event(
        event="stage_output",
        stage="planner",
        payload={
            "role": "planner",
            "output": spec,
            "duration_sec": t_planner,
        },
    )
    emit_event(
        event="stage_completed",
        stage="planner",
        payload={
            "duration_sec": t_planner,
            "status": "ok",
        },
    )
    print(f"[1/5] PLANNER COMPLETE ({t_planner:.2f}s)", flush=True)
    print("Wrote pipeline/spec.md", flush=True)

    # Check cancellation checkpoint after Planner / before Frontend
    check_cancellation(current_stage="planner", cycle_num=0)

    # 2. INITIAL FRONTEND
    emit_event(
        event="stage_started",
        stage="frontend",
        payload={
            "role": "frontend",
            "cycle": 0,
            "provider": agent_configs.get("frontend", {}).get("provider"),
            "model": agent_configs.get("frontend", {}).get("model"),
        },
    )
    print("\n[2/5] FRONTEND STARTED", flush=True)
    frontend_prompt = f"""
{shared_context}

PLANNER SPEC:

{spec}

You are the Frontend agent implementing the frontend portion of this task for {project_name}.

CRITICAL INSTRUCTIONS FOR FILE WRITES:
1. Follow the Planner spec strictly.
2. Only modify or create frontend files assigned to you within authorized write roots.
3. You MUST use this EXACT code block syntax to write or update files:
```write:relative/path/to/file
<complete file contents here>
```
4. If deleting a file:
```delete:relative/path/to/file
```
5. Do NOT modify protected files (.git, .env, etc.).
6. Keep changes minimal, clean, and compliant with project conventions.
7. If no frontend files are needed, output no write blocks.

When finished, provide your standard FRONTEND CHANGES summary at the end of your response.
"""

    t0 = time.time()
    frontend_result = safe_run_agent("frontend", frontend_prompt, current_stage="frontend", cycle_num=0)
    t_frontend = time.time() - t0
    emit_event(
        event="stage_output",
        stage="frontend",
        payload={
            "role": "frontend",
            "cycle": 0,
            "output": frontend_result,
            "duration_sec": t_frontend,
        },
    )
    frontend_accounting = parse_and_apply_agent_file_operations(frontend_result, role="frontend")
    emit_event(
        event="stage_completed",
        stage="frontend",
        payload={
            "duration_sec": t_frontend,
            "status": "ok",
        },
    )
    print(f"[2/5] FRONTEND COMPLETE ({t_frontend:.2f}s)", flush=True)

    # Check cancellation checkpoint after Frontend / before Backend
    check_cancellation(current_stage="frontend", cycle_num=0)

    # 3. INITIAL BACKEND
    emit_event(
        event="stage_started",
        stage="backend",
        payload={
            "role": "backend",
            "cycle": 0,
            "provider": agent_configs.get("backend", {}).get("provider"),
            "model": agent_configs.get("backend", {}).get("model"),
        },
    )
    print("\n[3/5] BACKEND STARTED", flush=True)
    backend_prompt = f"""
{shared_context}

PLANNER SPEC:

{spec}

You are the Backend agent implementing the backend portion of this task for {project_name}.

CRITICAL INSTRUCTIONS FOR FILE WRITES:
1. Follow the Planner spec strictly.
2. If the spec states "BACKEND TASK: None" or no backend work is required, do NOT write any files. State: "BACKEND TASK: None."
3. You MUST use this EXACT code block syntax to write or update files:
```write:relative/path/to/file
<complete file contents here>
```
4. If deleting a file:
```delete:relative/path/to/file
```
5. Do NOT modify protected files (.git, .env, etc.).
6. Keep changes minimal, clean, and compliant with project conventions.

When finished, provide your standard BACKEND CHANGES summary at the end of your response.
"""

    t0 = time.time()
    backend_result = safe_run_agent("backend", backend_prompt, current_stage="backend", cycle_num=0)
    t_backend = time.time() - t0
    emit_event(
        event="stage_output",
        stage="backend",
        payload={
            "role": "backend",
            "cycle": 0,
            "output": backend_result,
            "duration_sec": t_backend,
        },
    )
    backend_accounting = parse_and_apply_agent_file_operations(backend_result, role="backend")
    emit_event(
        event="stage_completed",
        stage="backend",
        payload={
            "duration_sec": t_backend,
            "status": "ok",
        },
    )
    print(f"[3/5] BACKEND COMPLETE ({t_backend:.2f}s)", flush=True)

    changes = f"""
## FRONTEND CHANGES

{frontend_result}


## BACKEND CHANGES

{backend_result}
""".strip()
    write_pipeline_file("changes.md", changes)

    # Check cancellation checkpoint after Initial Coding / before Tester
    check_cancellation(current_stage="backend", cycle_num=0)

    # --------------------------------------------------
    # BOUNDED REVIEW & REPAIR LOOP (MAX 3 CYCLES)
    # --------------------------------------------------
    last_reviewer_output = ""
    last_tester_output = ""

    for cycle in range(1, MAX_REVIEW_CYCLES + 1):
        print(f"\n=== REVIEW CYCLE {cycle}/{MAX_REVIEW_CYCLES} ===")

        # Check cancellation before Tester in cycle
        check_cancellation(current_stage="tester", cycle_num=cycle)

        # 4. TESTER
        emit_event(
            event="stage_started",
            stage="tester",
            cycle=cycle,
            payload={
                "role": "tester",
                "cycle": cycle,
                "provider": agent_configs.get("tester", {}).get("provider"),
                "model": agent_configs.get("tester", {}).get("model"),
            },
        )
        print("\nTESTER STARTED", flush=True)
        command_results, git_results, attribution = execute_test_and_git_commands(baseline=git_baseline)
        command_outputs_formatted = "\n\n".join(format_command_result(r) for r in command_results)
        git_outputs_formatted = "\n\n".join(format_git_result(r) for r in git_results)
        attribution_formatted = format_git_attribution_context(attribution) if attribution else ""
        untracked_contents = attribution.get("current_untracked_contents", get_untracked_files_content()) if attribution else get_untracked_files_content()
        current_tree = repo_tree()

        tester_prompt = f"""
CURRENT REPOSITORY TREE AFTER IMPLEMENTATION:
{current_tree}

PLANNER SPEC:
{spec}

CHANGES (pipeline/changes.md):
{changes}

COMMAND EXECUTION RESULTS:
{command_outputs_formatted}

GIT WORKTREE & TASK ATTRIBUTION:
{attribution_formatted}

GIT INSPECTION RAW RESULTS:
{git_outputs_formatted}

UNTRACKED IMPLEMENTATION FILE CONTENTS:
{untracked_contents}

IMPORTANT INSTRUCTIONS FOR TESTER:
- This is a REAL IMPLEMENTATION test for {project_name}.
- Files have been written to disk by Frontend and/or Backend.
- You do NOT have arbitrary shell access; the above commands were executed in a controlled sandbox by the orchestrator.
- Do NOT fabricate PASS.
- Clearly distinguish between code failures and environment/dependency failures.
- Compare actual implementation files against the Planner acceptance criteria.
- NOTE ON PRE-EXISTING WORKTREE CHANGES:
  * Inspect the "GIT WORKTREE & TASK ATTRIBUTION" section above.
  * Pre-existing changes existed BEFORE this task began.
  * DO NOT mark this task as FAIL simply because pre-existing changes exist in the repository.
  * Focus your verification and scope checking on the "CURRENT RUN DELTA" files introduced for THIS task.

Provide your evaluation using this exact structure:

STATUS: PASS / FAIL / UNVERIFIABLE
FINDINGS:
...
BLOCKERS:
...
"""

        t0 = time.time()
        tester_result = safe_run_agent("tester", tester_prompt, current_stage="tester", cycle_num=cycle)
        t_tester = time.time() - t0
        last_tester_output = tester_result
        emit_event(
            event="stage_output",
            stage="tester",
            cycle=cycle,
            payload={
                "role": "tester",
                "cycle": cycle,
                "output": tester_result,
                "duration_sec": t_tester,
            },
        )
        emit_event(
            event="stage_completed",
            stage="tester",
            cycle=cycle,
            payload={
                "duration_sec": t_tester,
                "status": "ok",
            },
        )
        print(f"TESTER COMPLETE ({t_tester:.2f}s)", flush=True)
        print("\n=== TESTER REPORT ===")
        print(tester_result)

        # Check cancellation after Tester / before Reviewer
        check_cancellation(current_stage="reviewer", cycle_num=cycle)

        # 5. REVIEWER
        emit_event(
            event="stage_started",
            stage="reviewer",
            cycle=cycle,
            payload={
                "role": "reviewer",
                "cycle": cycle,
                "provider": agent_configs.get("reviewer", {}).get("provider"),
                "model": agent_configs.get("reviewer", {}).get("model"),
            },
        )
        print("\nREVIEWER STARTED", flush=True)

        reviewer_prompt = f"""
CURRENT REPOSITORY TREE AFTER IMPLEMENTATION:
{current_tree}

PLANNER SPEC:
{spec}

CHANGES (pipeline/changes.md):
{changes}

TESTER REPORT:
{tester_result}

GIT WORKTREE & TASK ATTRIBUTION:
{attribution_formatted}

GIT INSPECTION RAW RESULTS:
{git_outputs_formatted}

UNTRACKED IMPLEMENTATION FILE CONTENTS:
{untracked_contents}

IMPORTANT INSTRUCTIONS FOR REVIEWER:
- Review the actual implementation changes made by Frontend/Backend for {project_name}.
- IMPORTANT ATTRIBUTION RULES:
  * Inspect the "GIT WORKTREE & TASK ATTRIBUTION" section carefully.
  * Evaluate scope and acceptance criteria strictly against the "CURRENT RUN DELTA" (files created, modified, or deleted during THIS pipeline run).
  * Do NOT request reversion of unrelated pre-existing worktree changes merely because they exist in the repository.
  * Do flag any file changes in the "CURRENT RUN DELTA" that violate task scope or manifest rules.
  * Do consider pre-existing changes only if they directly break, invalidate, or conflict with the current task implementation.
- Output your machine-readable verdict at the VERY TOP:
VERDICT: APPROVE
or
VERDICT: CHANGES REQUIRED

If CHANGES REQUIRED, also provide:
FRONTEND_FIX_REQUIRED: YES/NO
BACKEND_FIX_REQUIRED: YES/NO
DEPENDENCY_FIX_REQUIRED: YES/NO

Followed by TASK, ISSUES, and REASON.
"""

        t0 = time.time()
        reviewer_result = safe_run_agent("reviewer", reviewer_prompt, current_stage="reviewer", cycle_num=cycle)
        t_reviewer = time.time() - t0
        last_reviewer_output = reviewer_result
        emit_event(
            event="stage_output",
            stage="reviewer",
            cycle=cycle,
            payload={
                "role": "reviewer",
                "cycle": cycle,
                "output": reviewer_result,
                "duration_sec": t_reviewer,
            },
        )
        emit_event(
            event="stage_completed",
            stage="reviewer",
            cycle=cycle,
            payload={
                "duration_sec": t_reviewer,
                "status": "ok",
            },
        )
        print(f"REVIEWER COMPLETE ({t_reviewer:.2f}s)", flush=True)
        print("\n=== REVIEWER REPORT ===")
        print(reviewer_result)

        verdict_data = parse_reviewer_verdict(reviewer_result)
        verdict = verdict_data["verdict"]
        print(f"\nVERDICT: {verdict}")

        emit_event(
            event="review_verdict",
            stage="reviewer",
            cycle=cycle,
            payload={
                "cycle": cycle,
                "verdict": verdict,
                "frontend_fix_required": verdict_data["frontend_fix_required"],
                "backend_fix_required": verdict_data["backend_fix_required"],
                "dependency_fix_required": verdict_data["dependency_fix_required"],
            },
        )

        if verdict == "APPROVE":
            emit_event(
                event="human_approval_required",
                stage="reviewer",
                cycle=cycle,
                payload={
                    "cycle": cycle,
                    "reviewer_verdict": "APPROVE",
                    "reason": "Reviewer approved implementation changes. Human operator approval required.",
                },
            )
            emit_event(
                event="pipeline_finished",
                payload={
                    "final_status": "AWAITING_HUMAN_APPROVAL",
                    "reason": "Reviewer approved implementation changes. Awaiting operator decision.",
                    "cycles_used": cycle,
                    "total_duration_sec": time.time() - pipeline_start_time,
                },
            )
            print("\nPIPELINE_AWAITING_HUMAN_APPROVAL", flush=True)
            clear_salvaged_work()
            return logger.run_id

        if cycle == MAX_REVIEW_CYCLES:
            # Salvage unapproved code before clean rollback
            print("Preserving unapproved work into pipeline/salvage/latest...", flush=True)
            try:
                salvage_unapproved_work(logger.run_id)
            except Exception as e:
                print(f"Warning: failed to salvage work: {e}", flush=True)
            print("Auto-rolling back unapproved changes...", flush=True)
            run_safe_git_command(["git", "reset", "--hard", "HEAD"])
            run_safe_git_command(["git", "clean", "-fd"])
            emit_event(
                event="pipeline_finished",
                payload={
                    "final_status": "BLOCKED",
                    "reason": "MAX_REVIEW_CYCLES_EXCEEDED",
                    "cycles_used": cycle,
                    "total_duration_sec": time.time() - pipeline_start_time,
                },
            )
            print("\n=== REVIEW CYCLE 3/3 ===")
            print("VERDICT: BLOCKED")
            print("REASON: MAX_REVIEW_CYCLES_EXCEEDED")
            print("\nREVIEW_LOOP_EXHAUSTED", flush=True)
            return logger.run_id

        # Check for dependency-only blocker
        if verdict_data["dependency_fix_required"] and not (verdict_data["frontend_fix_required"] or verdict_data["backend_fix_required"]):
            emit_event(
                event="pipeline_finished",
                payload={
                    "final_status": "DEPENDENCY_ACTION_REQUIRED",
                    "reason": "Reviewer requested dependency/environment fixes without code repairs.",
                    "cycles_used": cycle,
                    "total_duration_sec": time.time() - pipeline_start_time,
                },
            )
            print("\nDEPENDENCY_ACTION_REQUIRED", flush=True)
            print("Reviewer requested dependency/environment fixes. Halting coding repair loop.")
            return logger.run_id

        # Check cancellation before entering repair execution
        check_cancellation(current_stage="repair", cycle_num=cycle)

        # Execute Repairs
        next_cycle = cycle + 1
        target_agents = []
        if verdict_data["frontend_fix_required"]:
            target_agents.append("frontend")
        if verdict_data["backend_fix_required"]:
            target_agents.append("backend")

        emit_event(
            event="retry_started",
            stage="repair",
            cycle=cycle,
            payload={
                "from_cycle": cycle,
                "to_cycle": next_cycle,
                "target_agents": target_agents,
            },
        )
        print(f"\n=== REPAIR CYCLE {next_cycle}/{MAX_REVIEW_CYCLES} ===")

        if verdict_data["frontend_fix_required"]:
            emit_event(
                event="stage_started",
                stage="frontend_repair",
                cycle=next_cycle,
                payload={
                    "role": "frontend",
                    "cycle": next_cycle,
                    "provider": agent_configs.get("frontend", {}).get("provider"),
                    "model": agent_configs.get("frontend", {}).get("model"),
                },
            )
            print("\nFRONTEND REPAIR STARTED", flush=True)
            fe_repair_prompt = f"""
{shared_context}

PLANNER SPEC:
{spec}

CURRENT IMPLEMENTATION CHANGES:
{changes}

TESTER REPORT:
{tester_result}

REVIEWER FEEDBACK (CHANGES REQUIRED):
{reviewer_result}

UNTRACKED IMPLEMENTATION FILE CONTENTS:
{untracked_contents}

You are the Frontend agent repairing issues identified in review for {project_name}.
INSTRUCTIONS:
1. Modify ONLY what is necessary to address the reviewer feedback.
2. Use the canonical write syntax:
```write:relative/path/to/file
<complete file contents here>
```
3. Do NOT merely describe fixes in prose without write blocks.
4. Keep changes clean, minimal, and compliant with project conventions.
"""

            t0 = time.time()
            fe_repair_res = safe_run_agent("frontend", fe_repair_prompt, current_stage="frontend_repair", cycle_num=next_cycle)
            t_fe_rep = time.time() - t0
            emit_event(
                event="stage_output",
                stage="frontend_repair",
                cycle=next_cycle,
                payload={
                    "role": "frontend",
                    "cycle": next_cycle,
                    "output": fe_repair_res,
                    "duration_sec": t_fe_rep,
                },
            )
            parse_and_apply_agent_file_operations(fe_repair_res, role="frontend")
            emit_event(
                event="stage_completed",
                stage="frontend_repair",
                cycle=next_cycle,
                payload={
                    "duration_sec": t_fe_rep,
                    "status": "ok",
                },
            )
            print(f"FRONTEND REPAIR COMPLETE ({t_fe_rep:.2f}s)", flush=True)
            changes += f"\n\n## FRONTEND REPAIR (Cycle {next_cycle})\n\n{fe_repair_res}"

            # Check cancellation after Frontend Repair
            check_cancellation(current_stage="frontend_repair", cycle_num=next_cycle)

        if verdict_data["backend_fix_required"]:
            emit_event(
                event="stage_started",
                stage="backend_repair",
                cycle=next_cycle,
                payload={
                    "role": "backend",
                    "cycle": next_cycle,
                    "provider": agent_configs.get("backend", {}).get("provider"),
                    "model": agent_configs.get("backend", {}).get("model"),
                },
            )
            print("\nBACKEND REPAIR STARTED", flush=True)
            be_repair_prompt = f"""
{shared_context}

PLANNER SPEC:
{spec}

CURRENT IMPLEMENTATION CHANGES:
{changes}

TESTER REPORT:
{tester_result}

REVIEWER FEEDBACK (CHANGES REQUIRED):
{reviewer_result}

You are the Backend agent repairing issues identified in review for {project_name}.
INSTRUCTIONS:
1. Modify ONLY what is necessary to address the reviewer feedback.
2. Use the canonical write syntax:
```write:relative/path/to/file
<complete file contents here>
```
3. Do NOT merely describe fixes in prose without write blocks.
4. Keep changes clean, minimal, and compliant with project conventions.
"""

            t0 = time.time()
            be_repair_res = safe_run_agent("backend", be_repair_prompt, current_stage="backend_repair", cycle_num=next_cycle)
            t_be_rep = time.time() - t0
            emit_event(
                event="stage_output",
                stage="backend_repair",
                cycle=next_cycle,
                payload={
                    "role": "backend",
                    "cycle": next_cycle,
                    "output": be_repair_res,
                    "duration_sec": t_be_rep,
                },
            )
            parse_and_apply_agent_file_operations(be_repair_res, role="backend")
            emit_event(
                event="stage_completed",
                stage="backend_repair",
                cycle=next_cycle,
                payload={
                    "duration_sec": t_be_rep,
                    "status": "ok",
                },
            )
            print(f"BACKEND REPAIR COMPLETE ({t_be_rep:.2f}s)", flush=True)
            changes += f"\n\n## BACKEND REPAIR (Cycle {next_cycle})\n\n{be_repair_res}"

            # Check cancellation after Backend Repair
            check_cancellation(current_stage="backend_repair", cycle_num=next_cycle)

        write_pipeline_file("changes.md", changes)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit('Usage: python orchestrator/pipeline.py "task description"')
    task_text = " ".join(sys.argv[1:])
    run_pipeline(task_text)
