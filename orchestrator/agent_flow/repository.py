import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

AGENTS_ROOT = Path(__file__).resolve().parent.parent.parent
BUM_STATE_DIR = AGENTS_ROOT / ".bum"
RUNS_DIR = BUM_STATE_DIR / "runs"

VALID_RUN_ID_REGEX = re.compile(r"^run_[a-zA-Z0-9_\-]+$")


def validate_run_id(run_id: str) -> bool:
    """Validate that run_id matches the expected safe pattern to prevent path traversal."""
    if not run_id or not isinstance(run_id, str):
        return False
    return bool(VALID_RUN_ID_REGEX.match(run_id))


def get_run_dir(run_id: str) -> Path:
    """
    Safely resolve the directory for a specific run_id.
    Raises ValueError on invalid format or path traversal attempt.
    """
    if not validate_run_id(run_id):
        raise ValueError(f"Invalid run_id format: '{run_id}'")

    target_dir = (RUNS_DIR / run_id).resolve()
    runs_root = RUNS_DIR.resolve()

    try:
        target_dir.relative_to(runs_root)
    except ValueError:
        raise PermissionError(f"Path traversal blocked for run_id: '{run_id}'")

    return target_dir


def append_event_to_run(
    run_id: str,
    event: str,
    stage: Optional[str] = None,
    cycle: Optional[int] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Append an event to a specific historical run's events.jsonl.
    Used for out-of-band events such as human_decision.
    """
    if not validate_run_id(run_id):
        raise ValueError(f"Invalid run_id format: '{run_id}'")

    run_dir = get_run_dir(run_id)
    if not run_dir.exists():
        raise FileNotFoundError(f"Run directory for '{run_id}' does not exist.")

    events_file = run_dir / "events.jsonl"
    record = {
        "run_id": run_id,
        "timestamp": time.time(),
        "event": event,
        "stage": stage,
        "cycle": cycle,
        "payload": payload or {},
    }

    with open(events_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record


def get_run_events(run_id: str) -> List[Dict[str, Any]]:
    """
    Read and parse all JSONL records for a given run_id in chronological order.
    Safely handles incomplete/trailing lines and returns valid parsed events.
    """
    run_dir = get_run_dir(run_id)
    events_file = run_dir / "events.jsonl"

    if not events_file.exists():
        return []

    events = []
    try:
        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                clean_line = line.strip()
                if not clean_line:
                    continue
                try:
                    record = json.loads(clean_line)
                    events.append(record)
                except json.JSONDecodeError:
                    # Trailing incomplete line or malformed record during active write
                    continue
    except Exception as exc:
        print(f"[WARN] Error reading events for run '{run_id}': {exc}", file=sys.stderr)
        return []

    return events


def purge_all_runs(active_run_id: Optional[str] = None) -> int:
    """
    Remove all completed / non-active run directories from pipeline/runs/.
    Preserves any currently executing run. Returns count of purged directories.
    """
    if not RUNS_DIR.exists():
        return 0

    import shutil
    purged_count = 0
    for item in list(RUNS_DIR.iterdir()):
        if item.is_dir() and item.name.startswith("run_"):
            if active_run_id and item.name == active_run_id:
                continue
            try:
                shutil.rmtree(item)
                purged_count += 1
            except Exception as exc:
                print(f"[WARN] Failed to delete run folder '{item.name}': {exc}", file=sys.stderr)

    return purged_count


def delete_single_run(run_id: str, active_run_id: Optional[str] = None) -> bool:
    """
    Safely delete a single non-active run directory.
    """
    if not validate_run_id(run_id):
        raise ValueError(f"Invalid run_id format: '{run_id}'")
    if active_run_id and run_id == active_run_id:
        raise ValueError(f"Cannot delete active run: '{run_id}'")

    import shutil
    run_dir = get_run_dir(run_id)
    if run_dir.exists():
        shutil.rmtree(run_dir)
        return True
    return False
def list_runs(active_run_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    List all available runs in pipeline/runs/ sorted by start timestamp descending.
    Extracts summary metadata directly from events.jsonl.
    If a run has no pipeline_finished and is NOT the active_run_id, it is classified as 'interrupted'.
    """
    if not RUNS_DIR.exists():
        return []

    runs = []
    for item in RUNS_DIR.iterdir():
        if item.is_dir() and item.name.startswith("run_"):
            run_id = item.name
            events = get_run_events(run_id)
            if not events:
                # Run folder exists without events yet
                runs.append({
                    "run_id": run_id,
                    "started_at": None,
                    "finished_at": None,
                    "task": None,
                    "final_status": "empty",
                    "cycles_used": 0,
                    "total_duration_sec": None,
                    "is_running": False,
                    "events_count": 0,
                })
                continue

            # Find start event, finish event, human decision event
            start_event = next((e for e in events if e.get("event") == "pipeline_started"), events[0])
            finish_event = next((e for e in events if e.get("event") == "pipeline_finished"), None)
            human_decision_event = next((e for e in reversed(events) if e.get("event") == "human_decision"), None)

            started_at = start_event.get("timestamp")
            finished_at = finish_event.get("timestamp") if finish_event else None

            task = start_event.get("payload", {}).get("task")
            label = start_event.get("payload", {}).get("label")
            retry_of = start_event.get("payload", {}).get("retry_of")

            if human_decision_event:
                decision = human_decision_event.get("payload", {}).get("decision", "").upper()
                if decision == "APPROVE":
                    final_status = "approved"
                elif decision == "REJECT":
                    final_status = "rejected"
                else:
                    final_status = decision.lower()
                is_running = False
                finished_at = human_decision_event.get("timestamp") or finished_at
            elif finish_event:
                raw_status = str(finish_event.get("payload", {}).get("final_status") or "").lower()
                if raw_status in ("awaiting_human_approval", "approve", "approved_awaiting_operator"):
                    final_status = "awaiting_human_approval"
                elif raw_status in ("blocked", "max_review_cycles_exceeded"):
                    final_status = "blocked"
                elif raw_status in ("cancelled", "canceled"):
                    final_status = "cancelled"
                elif raw_status in ("failed", "failure"):
                    final_status = "failed"
                elif raw_status in ("dependency_action_required", "dependency_required"):
                    final_status = "blocked"
                elif raw_status:
                    final_status = raw_status
                else:
                    final_status = "interrupted"
                is_running = False
            else:
                if active_run_id and run_id == active_run_id:
                    final_status = "running"
                    is_running = True
                else:
                    final_status = "interrupted"
                    is_running = False

            cycles_used = finish_event.get("payload", {}).get("cycles_used", 0) if finish_event else 0
            total_duration_sec = finish_event.get("payload", {}).get("total_duration_sec") if finish_event else None

            run_summary_entry = {
                "run_id": run_id,
                "label": label,
                "started_at": started_at,
                "finished_at": finished_at,
                "task": task,
                "final_status": final_status or "interrupted",
                "cycles_used": cycles_used,
                "total_duration_sec": total_duration_sec,
                "is_running": is_running,
                "events_count": len(events),
            }
            if retry_of:
                run_summary_entry["retry_of"] = retry_of

            runs.append(run_summary_entry)

    # Sort newest first (by started_at descending, fallback to folder name)
    runs.sort(key=lambda r: (r["started_at"] or 0, r["run_id"]), reverse=True)
    return runs
