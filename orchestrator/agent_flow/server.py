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
)

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
    """
    Resume an existing run from Tester/Reviewer evaluation after manual or automated intervention,
    skipping re-planning and re-coding.
    """
    if not validate_run_id(run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id format")

    try:
        run_dir = get_run_dir(run_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    active_status = execution_manager.get_status()
    if active_status.get("running"):
        return JSONResponse(
            status_code=409,
            content={
                "error": "pipeline_already_running",
                "message": f"Pipeline already running with run_id: {active_status.get('run_id')}",
                "run_id": active_status.get("run_id"),
            },
        )

    from orchestrator.resume_test_review import run_test_and_review
    def _runner(task_text, r_id, token):
        append_event_to_run(
            run_id=r_id,
            event="stage_resumed",
            stage="tester",
            payload={"resumed_from": run_id, "mode": "test_and_review"},
        )
        run_test_and_review()

    res = execution_manager.start_pipeline(
        task=f"Resume evaluation for {run_id}",
        pipeline_func=_runner,
        retry_of=run_id,
    )
    return res


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

    return {
        "accepted": True,
        "run_id": run_id,
        "status": "approved",
        "event": event_record,
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

    return {
        "accepted": True,
        "run_id": run_id,
        "status": "rejected",
        "reason": clean_reason,
        "event": event_record,
    }



@app.get("/api/health")
async def health():
    """Basic health check endpoint."""
    return {
        "status": "ok",
        "service": "trayne-agent-flow",
    }


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
    Safely load a referenced prompt markdown file under the active repository or pipeline root.
    """
    clean_file = file.strip().lstrip("@file:").strip()
    if not clean_file:
        raise HTTPException(status_code=400, detail="File path parameter cannot be empty")

    repo_root = get_repo_root()
    agents_root = AGENTS_ROOT

    # Attempt resolution relative to agents_root, then repo_root
    candidate_paths = [
        agents_root / clean_file,
        repo_root / clean_file,
    ]

    target_path = None
    for p in candidate_paths:
        try:
            resolved = p.resolve()
            # Security guard: ensure resolved path is within agents_root or repo_root
            if resolved.is_file() and (
                resolved.is_relative_to(agents_root.resolve()) or resolved.is_relative_to(repo_root.resolve())
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
