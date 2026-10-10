import sys
from typing import Any, Dict, List, Optional


def reduce_run_state(events: List[Dict[str, Any]], is_active: bool = False) -> Dict[str, Any]:
    """
    Deterministic reducer that folds an event stream into a comprehensive run state.
    Handles complete, active, and interrupted/stale runs gracefully.
    """
    if not events:
        return {
            "run_id": None,
            "task": None,
            "status": "empty",
            "current_cycle": 0,
            "max_review_cycles": 3,
            "started_at": None,
            "finished_at": None,
            "total_duration_sec": None,
            "reason": None,
            "stages": {
                "preflight": {"status": "waiting", "started_at": None, "completed_at": None, "duration_sec": None, "error": None},
                "planner": {"status": "waiting", "started_at": None, "completed_at": None, "duration_sec": None, "provider": None, "model": None, "output": None},
                "frontend": {"status": "waiting", "attempts": []},
                "backend": {"status": "waiting", "attempts": []},
                "tester": {"status": "waiting", "attempts": []},
                "reviewer": {"status": "waiting", "attempts": []},
            },
            "files_changed": {
                "created": [],
                "modified": [],
                "deleted": [],
                "history": [],
            },
            "tests": [],
            "git": {},
            "review": {},
            "retries": [],
        }

    # Extract initial info from pipeline_started
    start_event = next((e for e in events if e.get("event") == "pipeline_started"), None)
    run_id = start_event.get("run_id") if start_event else events[0].get("run_id")
    task = start_event.get("payload", {}).get("task") if start_event else None
    label = start_event.get("payload", {}).get("label") if start_event else None
    retry_of = start_event.get("payload", {}).get("retry_of") if start_event else None
    max_review_cycles = start_event.get("payload", {}).get("max_review_cycles", 3) if start_event else 3
    started_at = start_event.get("timestamp") if start_event else events[0].get("timestamp")

    finish_event = next((e for e in events if e.get("event") == "pipeline_finished"), None)
    human_decision_event = next((e for e in reversed(events) if e.get("event") == "human_decision"), None)

    finished_at = finish_event.get("timestamp") if finish_event else None
    if human_decision_event:
        decision = human_decision_event.get("payload", {}).get("decision", "").upper()
        if decision == "APPROVE":
            final_status = "approved"
        elif decision == "REJECT":
            final_status = "rejected"
        else:
            final_status = decision.lower()
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
    else:
        final_status = "running" if is_active else "interrupted"

    reason = finish_event.get("payload", {}).get("reason") if finish_event else None
    if human_decision_event and human_decision_event.get("payload", {}).get("reason"):
        reason = human_decision_event.get("payload", {}).get("reason")
    elif not finish_event and not is_active:
        reason = "PROCESS_INTERRUPTED_BEFORE_COMPLETION"
    total_duration_sec = finish_event.get("payload", {}).get("total_duration_sec") if finish_event else None

    # Base stage structures
    stages: Dict[str, Any] = {
        "preflight": {"status": "waiting", "started_at": None, "completed_at": None, "duration_sec": None, "error": None},
        "planner": {"status": "waiting", "started_at": None, "completed_at": None, "duration_sec": None, "provider": None, "model": None, "output": None},
        "frontend": {"status": "waiting", "attempts": []},
        "backend": {"status": "waiting", "attempts": []},
        "tester": {"status": "waiting", "attempts": []},
        "reviewer": {"status": "waiting", "attempts": []},
    }

    files_created: List[str] = []
    files_modified: List[str] = []
    files_deleted: List[str] = []
    files_history: List[Dict[str, Any]] = []
    active_file_operations: List[Dict[str, Any]] = []

    tests_history: List[Dict[str, Any]] = []
    git_state: Dict[str, Any] = {}
    review_state: Dict[str, Any] = {}
    retries_history: List[Dict[str, Any]] = []

    current_cycle = 0

    for ev in events:
        event_name = ev.get("event")
        stage_name = ev.get("stage")
        cycle = ev.get("cycle")
        payload = ev.get("payload", {})
        ts = ev.get("timestamp")

        if cycle is not None and isinstance(cycle, int):
            if cycle > current_cycle:
                current_cycle = cycle

        # Stage started
        if event_name == "stage_started":
            if stage_name in ("preflight", "baseline"):
                stages["preflight"]["status"] = "running"
                if not stages["preflight"]["started_at"]:
                    stages["preflight"]["started_at"] = ts

            elif stage_name == "planner":
                stages["planner"]["status"] = "running"
                stages["planner"]["started_at"] = ts
                stages["planner"]["provider"] = payload.get("provider")
                stages["planner"]["model"] = payload.get("model")

            elif stage_name in ("frontend", "frontend_repair"):
                stages["frontend"]["status"] = "running"
                attempt = {
                    "type": "initial" if stage_name == "frontend" else "repair",
                    "cycle": cycle or 0,
                    "status": "running",
                    "started_at": ts,
                    "completed_at": None,
                    "duration_sec": None,
                    "provider": payload.get("provider"),
                    "model": payload.get("model"),
                    "output": None,
                    "files": None,
                }
                stages["frontend"]["attempts"].append(attempt)

            elif stage_name in ("backend", "backend_repair"):
                stages["backend"]["status"] = "running"
                attempt = {
                    "type": "initial" if stage_name == "backend" else "repair",
                    "cycle": cycle or 0,
                    "status": "running",
                    "started_at": ts,
                    "completed_at": None,
                    "duration_sec": None,
                    "provider": payload.get("provider"),
                    "model": payload.get("model"),
                    "output": None,
                    "files": None,
                }
                stages["backend"]["attempts"].append(attempt)

            elif stage_name == "tester":
                stages["tester"]["status"] = "running"
                attempt = {
                    "cycle": cycle or 1,
                    "status": "running",
                    "started_at": ts,
                    "completed_at": None,
                    "duration_sec": None,
                    "provider": payload.get("provider"),
                    "model": payload.get("model"),
                    "output": None,
                }
                stages["tester"]["attempts"].append(attempt)

            elif stage_name == "reviewer":
                stages["reviewer"]["status"] = "running"
                attempt = {
                    "cycle": cycle or 1,
                    "status": "running",
                    "started_at": ts,
                    "completed_at": None,
                    "duration_sec": None,
                    "provider": payload.get("provider"),
                    "model": payload.get("model"),
                    "output": None,
                }
                stages["reviewer"]["attempts"].append(attempt)

        # Stage output
        elif event_name == "stage_output":
            if stage_name == "planner":
                stages["planner"]["output"] = payload.get("output")
                stages["planner"]["duration_sec"] = payload.get("duration_sec")

            elif stage_name in ("frontend", "frontend_repair"):
                if stages["frontend"]["attempts"]:
                    last_att = stages["frontend"]["attempts"][-1]
                    last_att["output"] = payload.get("output")
                    last_att["duration_sec"] = payload.get("duration_sec")

            elif stage_name in ("backend", "backend_repair"):
                if stages["backend"]["attempts"]:
                    last_att = stages["backend"]["attempts"][-1]
                    last_att["output"] = payload.get("output")
                    last_att["duration_sec"] = payload.get("duration_sec")

            elif stage_name == "tester":
                if stages["tester"]["attempts"]:
                    last_att = stages["tester"]["attempts"][-1]
                    last_att["output"] = payload.get("output")
                    last_att["duration_sec"] = payload.get("duration_sec")

            elif stage_name == "reviewer":
                if stages["reviewer"]["attempts"]:
                    last_att = stages["reviewer"]["attempts"][-1]
                    last_att["output"] = payload.get("output")
                    last_att["duration_sec"] = payload.get("duration_sec")

        # Files changed
        elif event_name == "files_changed":
            role = payload.get("role")
            created = payload.get("created", [])
            modified = payload.get("modified", [])
            deleted = payload.get("deleted", [])

            for f in created:
                if f not in files_created:
                    files_created.append(f)
            for f in modified:
                if f not in files_modified:
                    files_modified.append(f)
            for f in deleted:
                if f not in files_deleted:
                    files_deleted.append(f)

            files_history.append({
                "timestamp": ts,
                "role": role,
                "cycle": cycle,
                "parsed_count": payload.get("parsed_count", 0),
                "executed_count": payload.get("executed_count", 0),
                "created": created,
                "modified": modified,
                "deleted": deleted,
            })

            # Associate with active attempt if applicable
            target_stage = "frontend" if role == "frontend" else "backend" if role == "backend" else None
            if target_stage and stages[target_stage]["attempts"]:
                stages[target_stage]["attempts"][-1]["files"] = {
                    "created": created,
                    "modified": modified,
                    "deleted": deleted,
                }

        # File operation started
        elif event_name == "file_operation_started":
            active_file_operations.append({
                "path": payload.get("path"),
                "op": payload.get("op", "write"),
                "stage": stage_name or payload.get("role", "dev"),
                "status": "in_progress",
                "timestamp": ts,
            })

        # File operation completed
        elif event_name == "file_operation_completed":
            target_path = payload.get("path")
            matched = next((op for op in reversed(active_file_operations) if op["path"] == target_path and op["status"] == "in_progress"), None)
            if matched:
                matched["status"] = "verified"
                matched["bytes"] = payload.get("bytes", 0)
                matched["completed_at"] = ts
            else:
                active_file_operations.append({
                    "path": target_path,
                    "op": payload.get("op", "write"),
                    "stage": stage_name or payload.get("role", "dev"),
                    "status": "verified",
                    "bytes": payload.get("bytes", 0),
                    "timestamp": ts,
                })

        # Test results
        elif event_name == "test_result":
            tests_history.append({
                "timestamp": ts,
                "stage": stage_name,
                "cycle": cycle,
                "commands": payload.get("commands", []),
            })

        # Git diff updated
        elif event_name == "git_diff_updated":
            git_state = {
                "timestamp": ts,
                "diff_stat": payload.get("diff_stat", ""),
                "changed_files": payload.get("changed_files", []),
                "untracked_files": payload.get("untracked_files", []),
                "git_results": payload.get("git_results", []),
                "attribution": payload.get("attribution", None),
            }

        # Review verdict
        elif event_name == "review_verdict":
            review_state = {
                "timestamp": ts,
                "cycle": payload.get("cycle", cycle),
                "verdict": payload.get("verdict"),
                "frontend_fix_required": payload.get("frontend_fix_required", False),
                "backend_fix_required": payload.get("backend_fix_required", False),
                "dependency_fix_required": payload.get("dependency_fix_required", False),
            }

        # Human approval required
        elif event_name == "human_approval_required":
            stages["reviewer"]["status"] = "complete"

        # Human decision
        elif event_name == "human_decision":
            review_state["human_decision"] = {
                "timestamp": ts,
                "decision": payload.get("decision"),
                "reason": payload.get("reason"),
                "source": payload.get("source", "operator"),
            }

        # Retry started
        elif event_name == "retry_started":
            retries_history.append({
                "timestamp": ts,
                "from_cycle": payload.get("from_cycle"),
                "to_cycle": payload.get("to_cycle"),
                "target_agents": payload.get("target_agents", []),
            })

        # Stage completed
        elif event_name == "stage_completed":
            if stage_name in ("preflight", "baseline"):
                stages["preflight"]["status"] = "complete"
                stages["preflight"]["completed_at"] = ts
                stages["preflight"]["duration_sec"] = payload.get("duration_sec")

            elif stage_name == "planner":
                stages["planner"]["status"] = "complete"
                stages["planner"]["completed_at"] = ts
                stages["planner"]["duration_sec"] = payload.get("duration_sec", stages["planner"]["duration_sec"])

            elif stage_name in ("frontend", "frontend_repair"):
                stages["frontend"]["status"] = "complete"
                if stages["frontend"]["attempts"]:
                    last_att = stages["frontend"]["attempts"][-1]
                    last_att["status"] = "complete"
                    last_att["completed_at"] = ts
                    if payload.get("duration_sec"):
                        last_att["duration_sec"] = payload.get("duration_sec")

            elif stage_name in ("backend", "backend_repair"):
                stages["backend"]["status"] = "complete"
                if stages["backend"]["attempts"]:
                    last_att = stages["backend"]["attempts"][-1]
                    last_att["status"] = "complete"
                    last_att["completed_at"] = ts
                    if payload.get("duration_sec"):
                        last_att["duration_sec"] = payload.get("duration_sec")

            elif stage_name == "tester":
                stages["tester"]["status"] = "complete"
                if stages["tester"]["attempts"]:
                    last_att = stages["tester"]["attempts"][-1]
                    last_att["status"] = "complete"
                    last_att["completed_at"] = ts
                    if payload.get("duration_sec"):
                        last_att["duration_sec"] = payload.get("duration_sec")

            elif stage_name == "reviewer":
                stages["reviewer"]["status"] = "complete"
                if stages["reviewer"]["attempts"]:
                    last_att = stages["reviewer"]["attempts"][-1]
                    last_att["status"] = "complete"
                    last_att["completed_at"] = ts
                    if payload.get("duration_sec"):
                        last_att["duration_sec"] = payload.get("duration_sec")

        # Stage failed
        elif event_name == "stage_failed":
            if stage_name in stages:
                stages[stage_name]["status"] = "failed"
                stages[stage_name]["error"] = payload.get("error")

    # Map terminal stage status based on final_status if pipeline finished
    if final_status == "blocked":
        stages["reviewer"]["status"] = "blocked"

    return {
        "run_id": run_id,
        "label": label,
        "task": task,
        "retry_of": retry_of,
        "status": final_status.lower() if final_status else "running",
        "current_cycle": current_cycle,
        "max_review_cycles": max_review_cycles,
        "started_at": started_at,
        "finished_at": finished_at,
        "total_duration_sec": total_duration_sec,
        "reason": reason,
        "stages": stages,
        "files_changed": {
            "created": files_created,
            "modified": files_modified,
            "deleted": files_deleted,
            "history": files_history,
            "operations": active_file_operations,
        },
        "tests": tests_history,
        "git": git_state,
        "review": review_state,
        "retries": retries_history,
    }
