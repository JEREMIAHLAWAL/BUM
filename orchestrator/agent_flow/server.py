import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

AGENTS_ROOT = Path(__file__).resolve().parent.parent.parent
if str(AGENTS_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENTS_ROOT))

from orchestrator.agent_flow.repository import (
    get_run_events,
    list_runs,
    validate_run_id,
    get_run_dir,
    append_event_to_run,
    purge_all_runs,
    delete_single_run,
)
from orchestrator.agent_flow.reducer import reduce_run_state
from orchestrator.agent_flow.executor import execution_manager
from orchestrator.repo_tools import (
    get_repo_root,
    list_available_projects,
    set_active_project_path,
    resolve_repo_root,
    WORKSPACE_ROOT,
)
from orchestrator.worktree_tools import merge_run_worktree, discard_run_worktree

import subprocess
import time as _time

_AGENTS_ROOT = AGENTS_ROOT  # alias for readability below
_SERVER_BOOT_TIME = _time.time()


def _git_commit_hash(repo_dir: Path) -> Optional[str]:
    """Best-effort current commit hash for a directory. Returns None if not
    a git repo or git is unavailable — callers must handle that gracefully."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            shell=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:
        pass
    return None


def _git_commit_message(repo_dir: Path, commit_hash: Optional[str]) -> Optional[str]:
    if not commit_hash:
        return None
    try:
        proc = subprocess.run(
            ["git", "log", "-1", "--format=%s", commit_hash],
            cwd=repo_dir,
            shell=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:
        pass
    return None


# Captured once at process import time — this is "what code is actually
# loaded and running right now", independent of whatever Syncthing has since
# written to disk. Python does not hot-reload already-imported modules, so
# a .py edit synced in after this point will NOT be live until the service
# (bum-agent-flow / uvicorn process) is restarted.
_BOOT_COMMIT_HASH = _git_commit_hash(_AGENTS_ROOT)
_BOOT_COMMIT_MESSAGE = _git_commit_message(_AGENTS_ROOT, _BOOT_COMMIT_HASH)


def get_version_info() -> Dict[str, Any]:
    """Compare the commit hash this process booted with against whatever is
    currently on disk. A mismatch means Syncthing has synced newer BUM
    orchestrator code than what's actually loaded in memory — the
    bum-agent-flow service needs a restart before any fix in that newer
    commit takes effect. This directly targets the recurring 'shipped a fix,
    forgot to restart the Pi service, burned a run on stale code' failure
    mode logged in MASTER_TODO.md."""
    current_hash = _git_commit_hash(_AGENTS_ROOT)
    is_stale = bool(
        _BOOT_COMMIT_HASH and current_hash and _BOOT_COMMIT_HASH != current_hash
    )
    return {
        "boot_commit": _BOOT_COMMIT_HASH,
        "boot_commit_message": _BOOT_COMMIT_MESSAGE,
        "current_commit_on_disk": current_hash,
        "current_commit_message": _git_commit_message(_AGENTS_ROOT, current_hash) if is_stale else _BOOT_COMMIT_MESSAGE,
        "is_stale": is_stale,
        "server_boot_time": _SERVER_BOOT_TIME,
        "warning": (
            "Newer BUM orchestrator code is on disk than what this running service "
            "loaded at boot. Restart the bum-agent-flow service before relying on "
            "any fix from the newer commit(s) — Python does not hot-reload."
        ) if is_stale else None,
    }

app = FastAPI(
    title="BUM Multi-Agent SWE Orchestrator API",
    description="Local backend providing run summaries, derived pipeline states, live event streams, and pipeline run controls.",
    version="1.0.0",
)

# Enable CORS for local, LAN, and Tailscale clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


class RunTaskRequest(BaseModel):
    task: str = Field(..., description="The task description prompt to run in the pipeline")
    label: Optional[str] = Field(None, description="Optional custom name / label for the run")


class RejectRunRequest(BaseModel):
    reason: Optional[str] = Field(None, description="Optional explanation for rejecting the run")


class SelectProjectRequest(BaseModel):
    path: str = Field(..., description="Absolute path or valid ID of the target workspace repository")


@app.get("/api/projects")
async def get_projects():
    """List available workspace repositories and the current active target."""
    projects = list_available_projects()
    active_root, source = resolve_repo_root()
    return {
        "projects": projects,
        "active_path": str(active_root),
        "source": source,
        "version": get_version_info(),
    }


@app.post("/api/projects/select")
async def select_project(req: SelectProjectRequest):
    """Switch active target workspace directory dynamically."""
    active_status = execution_manager.get_status()
    if active_status.get("running"):
        raise HTTPException(
            status_code=409,
            detail="Cannot switch project workspace while a pipeline is running.",
        )

    clean_path = req.path.strip()
    target_path = Path(clean_path).expanduser().resolve()
    if not target_path.exists() or not target_path.is_dir():
        # Try matching by ID from available projects
        available = list_available_projects()
        matched = next((p for p in available if p["id"] == clean_path), None)
        if matched and Path(matched["path"]).is_dir():
            target_path = Path(matched["path"])
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Target path '{clean_path}' does not exist or is not a directory.",
            )

    set_active_project_path(target_path)
    return {
        "status": "ok",
        "active_path": str(target_path),
        "projects": list_available_projects(),
    }


@app.get("/api/pipeline/status")
async def get_pipeline_status():
    """Return whether a pipeline is currently executing."""
    return execution_manager.get_status()


@app.post("/api/runs", status_code=202)
@app.post("/api/pipeline/run", status_code=202)
async def start_run(req: RunTaskRequest):
    """
    Launch a new pipeline run with the provided task description.
    Executes asynchronously in the background. Returns 409 Conflict if a pipeline is already running.
    """
    clean_task = req.task.strip()
    if not clean_task:
        raise HTTPException(
            status_code=400,
            detail="Task description cannot be empty or whitespace.",
        )
    clean_label = req.label.strip() if req.label and req.label.strip() else None

    try:
        result = execution_manager.start_pipeline(task=clean_task, label=clean_label)
        return result
    except RuntimeError as exc:
        status = execution_manager.get_status()
        return JSONResponse(
            status_code=409,
            content={
                "error": "pipeline_already_running",
                "message": str(exc),
                "run_id": status.get("run_id"),
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/pipeline/stop")
@app.post("/api/runs/{run_id}/stop")
async def stop_pipeline(run_id: Optional[str] = None):
    """
    Request cancellation of the active pipeline execution.
    Cooperative: signals active worker thread to stop at the next safe boundary.
    """
    try:
        res = execution_manager.request_stop(run_id=run_id)
        return res
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/runs/{run_id}/resume", status_code=202)
async def resume_run_endpoint(run_id: str):
    """Refuse unsafe legacy recovery; use a new isolated full-pipeline retry instead."""
    if not validate_run_id(run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id format")

    try:
        run_dir = get_run_dir(run_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    # Legacy recovery reads shared artifacts and cannot reconstruct a retained
    # isolated worktree or manifest verification context. Fail closed for all
    # historical runs rather than selecting an unrelated project's checkout.
    raise HTTPException(
        status_code=409,
        detail=("Legacy /resume is disabled: it cannot safely restore run-scoped artifacts, "
                "the isolated worktree and manifest verification context. "
                f"Use POST /api/runs/{run_id}/retry for a new isolated full pipeline run "
                "with parent lineage only; previous artifacts will not be imported."),
    )


@app.post("/api/runs/{run_id}/retry", status_code=202)
async def retry_run(run_id: str):
    """
    Launch a completely new pipeline run for the task of the specified historical run,
    establishing parent lineage (retry_of).
    Eligibility: FAILED, BLOCKED, CANCELLED, INTERRUPTED/STALE.
    """
    if not validate_run_id(run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id format")

    try:
        run_dir = get_run_dir(run_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Source run '{run_id}' not found")

    events = get_run_events(run_id)
    active_status = execution_manager.get_status()
    is_active = bool(active_status.get("running") and active_status.get("run_id") == run_id)
    state = reduce_run_state(events, is_active=is_active)

    original_task = state.get("task")
    if not original_task or not original_task.strip():
        raise HTTPException(
            status_code=400,
            detail=f"Source run '{run_id}' has no valid task recorded to retry.",
        )

    current_status = (state.get("status") or "").lower()
    if is_active or current_status == "running":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry run '{run_id}': pipeline is currently running.",
        )

    if current_status == "approved":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry run '{run_id}': run is already approved.",
        )

    eligible_statuses = ("failed", "blocked", "cancelled", "interrupted", "stale", "empty", "rejected")
    if current_status not in eligible_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Run '{run_id}' with status '{current_status}' is not eligible for retry.",
        )

    try:
        result = execution_manager.start_pipeline(
            task=original_task.strip(),
            retry_of=run_id,
        )
        return result
    except RuntimeError as exc:
        status = execution_manager.get_status()
        return JSONResponse(
            status_code=409,
            content={
                "error": "pipeline_already_running",
                "message": str(exc),
                "run_id": status.get("run_id"),
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/runs/{run_id}/approve")
async def approve_run(run_id: str):
    """
    Operator approves a pipeline run that is in AWAITING_HUMAN_APPROVAL state.
    Transitions the run to APPROVED by appending a human_decision event.
    """
    if not validate_run_id(run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id format")

    try:
        run_dir = get_run_dir(run_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    events = get_run_events(run_id)
    active_status = execution_manager.get_status()
    is_active = bool(active_status.get("running") and active_status.get("run_id") == run_id)
    state = reduce_run_state(events, is_active=is_active)

    current_status = (state.get("status") or "").lower()
    if is_active or current_status != "awaiting_human_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve run '{run_id}': run status is '{current_status}', must be 'awaiting_human_approval'.",
        )

    # Append human_decision event
    event_record = append_event_to_run(
        run_id=run_id,
        event="human_decision",
        payload={
            "decision": "APPROVE",
            "reason": None,
            "source": "operator",
        },
    )

    # Merge the run's isolated worktree branch into the real checkout now
    # that a human has approved it. This is the ONLY path by which a
    # pipeline run's changes reach the real checkout (see worktree_tools.py).
    try:
        real_repo_root, _source = resolve_repo_root()
        merge_result = merge_run_worktree(run_id, real_repo_root)
    except Exception as exc:
        merge_result = {"success": False, "error": str(exc)}

    if not merge_result.get("success"):
        # Approval is recorded, but surface the merge failure distinctly so
        # the operator knows the real checkout was NOT updated and the
        # worktree/branch were preserved for manual recovery.
        raise HTTPException(
            status_code=500,
            detail=(
                f"Run '{run_id}' was approved but merging into the real checkout failed: "
                f"{merge_result.get('error')}"
            ),
        )

    return {
        "accepted": True,
        "run_id": run_id,
        "status": "approved",
        "event": event_record,
        "merge": merge_result,
    }


@app.post("/api/runs/{run_id}/reject")
async def reject_run(run_id: str, req: Optional[RejectRunRequest] = None):
    """
    Operator rejects a pipeline run that is in AWAITING_HUMAN_APPROVAL state.
    Transitions the run to REJECTED by appending a human_decision event.
    """
    if not validate_run_id(run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id format")

    try:
        run_dir = get_run_dir(run_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    events = get_run_events(run_id)
    active_status = execution_manager.get_status()
    is_active = bool(active_status.get("running") and active_status.get("run_id") == run_id)
    state = reduce_run_state(events, is_active=is_active)

    current_status = (state.get("status") or "").lower()
    if is_active or current_status != "awaiting_human_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject run '{run_id}': run status is '{current_status}', must be 'awaiting_human_approval'.",
        )

    clean_reason = req.reason.strip() if (req and req.reason and req.reason.strip()) else None

    # Append human_decision event
    event_record = append_event_to_run(
        run_id=run_id,
        event="human_decision",
        payload={
            "decision": "REJECT",
            "reason": clean_reason,
            "source": "operator",
        },
    )

    # The run's isolated worktree never touched the real checkout — discard
    # it (and its throwaway branch) now that it's been explicitly rejected.
    try:
        real_repo_root, _source = resolve_repo_root()
        discard_result = discard_run_worktree(run_id, real_repo_root)
    except Exception as exc:
        discard_result = {"error": str(exc)}

    return {
        "accepted": True,
        "run_id": run_id,
        "status": "rejected",
        "reason": clean_reason,
        "event": event_record,
        "worktree_cleanup": discard_result,
    }



@app.get("/api/health")
async def health():
    """Basic health check endpoint. Includes deployed-code version info so a
    stale-vs-live code mismatch is visible without a separate call."""
    return {
        "status": "ok",
        "service": "trayne-agent-flow",
        "version": get_version_info(),
    }


@app.get("/api/version")
async def version():
    """Dedicated endpoint for the Web UI header's code-version banner.
    Reports the git commit this running process actually booted with vs.
    whatever commit is currently on disk (post-Syncthing-sync). See
    get_version_info() for why this matters — the service does not
    hot-reload .py changes."""
    return get_version_info()


@app.get("/api/runs")
async def get_runs():
    """List all available pipeline runs with summarized status."""
    active_status = execution_manager.get_status()
    active_run_id = active_status.get("run_id") if active_status.get("running") else None
    runs = list_runs(active_run_id=active_run_id)
    return {"runs": runs, "total": len(runs)}


@app.delete("/api/runs/purge")
async def purge_runs_endpoint():
    """Purge all inactive pipeline runs from disk."""
    active_status = execution_manager.get_status()
    active_run_id = active_status.get("run_id") if active_status.get("running") else None
    purged_count = purge_all_runs(active_run_id=active_run_id)
    return {"purged_count": purged_count, "status": "ok"}


@app.delete("/api/runs/{run_id}")
async def delete_run_endpoint(run_id: str):
    """Delete a single inactive pipeline run from disk."""
    active_status = execution_manager.get_status()
    active_run_id = active_status.get("run_id") if active_status.get("running") else None
    try:
        deleted = delete_single_run(run_id, active_run_id=active_run_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
        return {"run_id": run_id, "status": "deleted"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/runs/{run_id}")
async def get_run_details(run_id: str):
    """Return the derived pipeline & stage state for a specific run."""
    if not validate_run_id(run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id format")

    try:
        run_dir = get_run_dir(run_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    events = get_run_events(run_id)
    active_status = execution_manager.get_status()
    is_active = bool(active_status.get("running") and active_status.get("run_id") == run_id)
    state = reduce_run_state(events, is_active=is_active)
    try:
        state["artifact_context"] = json.loads((run_dir / "artifact_context.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state["artifact_context"] = None  # Historical runs may predate scoped artifacts.
    return state


@app.get("/api/runs/{run_id}/events")
async def get_run_events_endpoint(run_id: str):
    """Return the raw chronological JSONL events for a specific run."""
    if not validate_run_id(run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id format")

    try:
        run_dir = get_run_dir(run_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    events = get_run_events(run_id)
    return {"run_id": run_id, "events": events, "count": len(events)}


@app.get("/api/runs/{run_id}/stream")
async def stream_run_events(run_id: str, request: Request):
    """
    Server-Sent Events (SSE) endpoint to stream new events as they are written to disk.
    Polls the local events.jsonl file with a lightweight interval and yields new records.
    """
    if not validate_run_id(run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id format")

    try:
        run_dir = get_run_dir(run_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    events_file = run_dir / "events.jsonl"

    async def event_generator():
        last_line_read = 0
        is_finished = False

        while True:
            # Check client disconnection
            if await request.is_disconnected():
                break

            if events_file.exists():
                try:
                    with open(events_file, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        if len(lines) > last_line_read:
                            new_lines = lines[last_line_read:]
                            for line in new_lines:
                                clean = line.strip()
                                if clean:
                                    try:
                                        record = json.loads(clean)
                                        yield f"data: {json.dumps(record, ensure_ascii=False)}\n\n"
                                        if record.get("event") in ("pipeline_finished", "human_decision"):
                                            is_finished = True
                                    except json.JSONDecodeError:
                                        pass
                            last_line_read = len(lines)
                except Exception:
                    pass

            if is_finished:
                # Send terminal close marker event
                yield "event: close\ndata: [DONE]\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/prompts/preview")
async def preview_prompt_file(file: str):
    """
    Safely load a referenced prompt markdown file under the active repository, agents, or workspace root.
    """
    clean_file = file.strip().lstrip("@file:").strip()
    if not clean_file:
        raise HTTPException(status_code=400, detail="File path parameter cannot be empty")

    repo_root = get_repo_root()
    agents_root = AGENTS_ROOT
    workspace_root = WORKSPACE_ROOT

    # Attempt resolution relative to agents_root, repo_root, then workspace_root
    candidate_paths = [
        agents_root / clean_file,
        repo_root / clean_file,
        workspace_root / clean_file,
    ]

    target_path = None
    for p in candidate_paths:
        try:
            resolved = p.resolve()
            # Security guard: ensure resolved path is within agents_root, repo_root, or workspace_root
            if resolved.is_file() and (
                resolved.is_relative_to(agents_root.resolve())
                or resolved.is_relative_to(repo_root.resolve())
                or resolved.is_relative_to(workspace_root.resolve())
            ):
                target_path = resolved
                break
        except Exception:
            continue

    if not target_path or not target_path.exists():
        raise HTTPException(status_code=404, detail=f"Prompt file '{clean_file}' not found or inaccessible")

    try:
        content = target_path.read_text(encoding="utf-8")
        return {
            "file": clean_file,
            "resolved_path": str(target_path),
            "content": content,
            "size": len(content),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read prompt file: {exc}")


UI_DIST_DIR = AGENTS_ROOT / "agent-flow-ui" / "dist"
if UI_DIST_DIR.exists() and (UI_DIST_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=str(UI_DIST_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        file_candidate = UI_DIST_DIR / full_path
        if file_candidate.is_file():
            return FileResponse(file_candidate)
        return FileResponse(UI_DIST_DIR / "index.html")


def start_server(host: str = "0.0.0.0", port: int = 8900):
    """Start local uvicorn server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
