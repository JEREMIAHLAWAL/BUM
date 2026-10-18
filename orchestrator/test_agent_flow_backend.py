import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import patch
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import orchestrator.agent_flow.repository as repo_module
import orchestrator.events as events_module
from orchestrator.agent_flow.repository import (
    get_run_dir,
    get_run_events,
    list_runs,
    validate_run_id,
)
from orchestrator.agent_flow.reducer import reduce_run_state
from orchestrator.agent_flow.executor import execution_manager
from orchestrator.agent_flow.server import app
from orchestrator.repo_tools import resolve_repo_root


class TestAgentFlowBackend(unittest.TestCase):
    def setUp(self):
        scratch = Path.home() / "AppData/Local/hermes/cache/scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        self.test_dir = Path(tempfile.mkdtemp(dir=scratch, prefix="bum05-api-"))
        self.project_dir = self.test_dir / "project"
        self.project_dir.mkdir()
        # Historical-run provenance must never resolve a user's selected/default repo.
        self.project_patch = patch("orchestrator.repo_tools._ACTIVE_PROJECT_PATH", self.project_dir)
        self.project_patch.start()
        self.addCleanup(self.project_patch.stop)
        self.override_patch = patch("orchestrator.repo_tools._RUN_WORKTREE_OVERRIDE", None)
        self.override_patch.start()
        self.addCleanup(self.override_patch.stop)
        self.orig_repo_runs_dir = repo_module.RUNS_DIR
        self.orig_events_runs_dir = events_module.RUNS_DIR
        repo_module.RUNS_DIR = self.test_dir
        events_module.RUNS_DIR = self.test_dir
        self.client = TestClient(app)
        # API fixtures use deterministic version metadata; never inspect the checkout.
        version = patch("orchestrator.agent_flow.server.get_version_info", return_value={
            "boot_commit": "offline-fixture", "current_commit_on_disk": "offline-fixture", "is_stale": False})
        version.start()
        self.addCleanup(version.stop)
        # Ensure execution manager is clean
        with execution_manager._lock:
            execution_manager._running = False
            execution_manager._current_run_id = None
            execution_manager._current_task = None
            execution_manager._token = None
            execution_manager._thread = None

    def tearDown(self):
        repo_module.RUNS_DIR = self.orig_repo_runs_dir
        events_module.RUNS_DIR = self.orig_events_runs_dir
        with execution_manager._lock:
            execution_manager._running = False
            execution_manager._current_run_id = None
            execution_manager._current_task = None
            execution_manager._token = None
            execution_manager._thread = None
        # Give worker threads a moment to release file handles on Windows
        time.sleep(0.05)
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_sample_run(self, run_id: str, events: list[dict]):
        run_folder = self.test_dir / run_id
        run_folder.mkdir(parents=True, exist_ok=True)
        events_file = run_folder / "events.jsonl"
        with open(events_file, "w", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

    def test_health_endpoint(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "trayne-agent-flow")

    def test_run_id_validation_and_traversal_protection(self):
        self.assertTrue(validate_run_id("run_20260825_120000_abc123"))
        self.assertTrue(validate_run_id("run_test-123_456"))
        self.assertFalse(validate_run_id("../../etc/passwd"))
        self.assertFalse(validate_run_id("run_test/../../something"))
        self.assertFalse(validate_run_id("invalid_name"))

        with self.assertRaises(ValueError):
            get_run_dir("../../secret")

        with self.assertRaises(ValueError):
            get_run_dir("run_bad/../../secret")

        # Test traversal rejection via API
        res = self.client.get("/api/runs/bad_run_id")
        self.assertEqual(res.status_code, 400)

    def test_list_runs_and_incomplete_run_handling(self):
        # 1. Completed run
        completed_events = [
            {"run_id": "run_completed_1", "timestamp": 1000.0, "event": "pipeline_started", "payload": {"task": "Task A"}},
            {"run_id": "run_completed_1", "timestamp": 1020.0, "event": "pipeline_finished", "payload": {"final_status": "APPROVE", "cycles_used": 1, "total_duration_sec": 20.0}},
        ]
        self._create_sample_run("run_completed_1", completed_events)

        # 2. Running/Incomplete run (no pipeline_finished)
        running_events = [
            {"run_id": "run_running_2", "timestamp": 2000.0, "event": "pipeline_started", "payload": {"task": "Task B"}},
            {"run_id": "run_running_2", "timestamp": 2005.0, "event": "stage_started", "stage": "planner"},
        ]
        self._create_sample_run("run_running_2", running_events)

        # Case A: When run_running_2 is the actively running pipeline
        runs_active = list_runs(active_run_id="run_running_2")
        self.assertEqual(len(runs_active), 2)
        self.assertEqual(runs_active[0]["run_id"], "run_running_2")
        self.assertTrue(runs_active[0]["is_running"])
        self.assertEqual(runs_active[0]["final_status"], "running")

        # Case B: After backend restart / when NO active worker owns run_running_2 -> classified as interrupted/stale
        runs_idle = list_runs(active_run_id=None)
        self.assertEqual(runs_idle[0]["run_id"], "run_running_2")
        self.assertFalse(runs_idle[0]["is_running"])
        self.assertEqual(runs_idle[0]["final_status"], "interrupted")

        self.assertEqual(runs_idle[1]["run_id"], "run_completed_1")
        self.assertFalse(runs_idle[1]["is_running"])
        self.assertEqual(runs_idle[1]["final_status"], "awaiting_human_approval")

        # API check
        api_res = self.client.get("/api/runs")
        self.assertEqual(api_res.status_code, 200)
        api_data = api_res.json()
        self.assertEqual(api_data["total"], 2)

    def test_malformed_jsonl_handling(self):
        run_folder = self.test_dir / "run_corrupt_1"
        run_folder.mkdir(parents=True, exist_ok=True)
        events_file = run_folder / "events.jsonl"
        with open(events_file, "w", encoding="utf-8") as f:
            f.write('{"run_id": "run_corrupt_1", "timestamp": 100.0, "event": "pipeline_started"}\n')
            f.write('{"corrupted incomplete json line...\n')  # Corrupted line
            f.write('{"run_id": "run_corrupt_1", "timestamp": 105.0, "event": "stage_started", "stage": "planner"}\n')

        events = get_run_events("run_corrupt_1")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["event"], "pipeline_started")
        self.assertEqual(events[1]["event"], "stage_started")

    def test_state_reduction_complete_lifecycle(self):
        events = [
            {"run_id": "run_full_cycle", "timestamp": 100.0, "event": "pipeline_started", "payload": {"task": "Build workout widget", "max_review_cycles": 3}},
            {"run_id": "run_full_cycle", "timestamp": 101.0, "event": "stage_started", "stage": "preflight"},
            {"run_id": "run_full_cycle", "timestamp": 102.0, "event": "stage_completed", "stage": "preflight", "payload": {"duration_sec": 1.0}},
            {"run_id": "run_full_cycle", "timestamp": 103.0, "event": "stage_started", "stage": "planner", "payload": {"provider": "openrouter", "model": "gemini"}},
            {"run_id": "run_full_cycle", "timestamp": 106.0, "event": "stage_output", "stage": "planner", "payload": {"output": "# Spec", "duration_sec": 3.0}},
            {"run_id": "run_full_cycle", "timestamp": 106.0, "event": "stage_completed", "stage": "planner"},
            # Initial Frontend & Backend (Cycle 0)
            {"run_id": "run_full_cycle", "timestamp": 107.0, "event": "stage_started", "stage": "frontend", "cycle": 0, "payload": {"provider": "openrouter", "model": "qwen"}},
            {"run_id": "run_full_cycle", "timestamp": 110.0, "event": "stage_output", "stage": "frontend", "cycle": 0, "payload": {"output": "fe code", "duration_sec": 3.0}},
            {"run_id": "run_full_cycle", "timestamp": 110.1, "event": "files_changed", "stage": "frontend", "payload": {"role": "frontend", "created": ["src/app/widget.tsx"], "modified": [], "deleted": []}},
            {"run_id": "run_full_cycle", "timestamp": 110.2, "event": "stage_completed", "stage": "frontend"},
            {"run_id": "run_full_cycle", "timestamp": 111.0, "event": "stage_started", "stage": "backend", "cycle": 0, "payload": {"provider": "openrouter", "model": "qwen"}},
            {"run_id": "run_full_cycle", "timestamp": 113.0, "event": "stage_output", "stage": "backend", "cycle": 0, "payload": {"output": "be code", "duration_sec": 2.0}},
            {"run_id": "run_full_cycle", "timestamp": 113.1, "event": "stage_completed", "stage": "backend"},
            # Cycle 1 Tester & Reviewer -> Changes Required
            {"run_id": "run_full_cycle", "timestamp": 114.0, "event": "stage_started", "stage": "tester", "cycle": 1, "payload": {"provider": "openrouter", "model": "deepseek"}},
            {"run_id": "run_full_cycle", "timestamp": 115.0, "event": "test_result", "stage": "tester", "cycle": 1, "payload": {"commands": [{"command": "npm test", "returncode": 1, "stdout": "1 test failed"}]}},
            {"run_id": "run_full_cycle", "timestamp": 115.1, "event": "git_diff_updated", "stage": "tester", "payload": {"diff_stat": "1 file changed", "changed_files": ["src/app/widget.tsx"]}},
            {"run_id": "run_full_cycle", "timestamp": 116.0, "event": "stage_output", "stage": "tester", "cycle": 1, "payload": {"output": "STATUS: FAIL", "duration_sec": 2.0}},
            {"run_id": "run_full_cycle", "timestamp": 116.1, "event": "stage_completed", "stage": "tester", "cycle": 1},
            {"run_id": "run_full_cycle", "timestamp": 117.0, "event": "stage_started", "stage": "reviewer", "cycle": 1, "payload": {"provider": "anthropic", "model": "sonnet"}},
            {"run_id": "run_full_cycle", "timestamp": 120.0, "event": "stage_output", "stage": "reviewer", "cycle": 1, "payload": {"output": "VERDICT: CHANGES REQUIRED", "duration_sec": 3.0}},
            {"run_id": "run_full_cycle", "timestamp": 120.1, "event": "stage_completed", "stage": "reviewer", "cycle": 1},
            {"run_id": "run_full_cycle", "timestamp": 120.2, "event": "review_verdict", "stage": "reviewer", "cycle": 1, "payload": {"cycle": 1, "verdict": "CHANGES REQUIRED", "frontend_fix_required": True, "backend_fix_required": False, "dependency_fix_required": False}},
            # Retry -> Repair (Cycle 2)
            {"run_id": "run_full_cycle", "timestamp": 121.0, "event": "retry_started", "stage": "repair", "cycle": 1, "payload": {"from_cycle": 1, "to_cycle": 2, "target_agents": ["frontend"]}},
            {"run_id": "run_full_cycle", "timestamp": 122.0, "event": "stage_started", "stage": "frontend_repair", "cycle": 2, "payload": {"provider": "openrouter", "model": "qwen"}},
            {"run_id": "run_full_cycle", "timestamp": 125.0, "event": "stage_output", "stage": "frontend_repair", "cycle": 2, "payload": {"output": "fe fixed code", "duration_sec": 3.0}},
            {"run_id": "run_full_cycle", "timestamp": 125.1, "event": "files_changed", "stage": "frontend_repair", "payload": {"role": "frontend", "created": [], "modified": ["src/app/widget.tsx"], "deleted": []}},
            {"run_id": "run_full_cycle", "timestamp": 125.2, "event": "stage_completed", "stage": "frontend_repair", "cycle": 2},
            # Cycle 2 Tester & Reviewer -> Approve
            {"run_id": "run_full_cycle", "timestamp": 126.0, "event": "stage_started", "stage": "tester", "cycle": 2, "payload": {"provider": "openrouter", "model": "deepseek"}},
            {"run_id": "run_full_cycle", "timestamp": 127.0, "event": "test_result", "stage": "tester", "cycle": 2, "payload": {"commands": [{"command": "npm test", "returncode": 0, "stdout": "PASS"}]}},
            {"run_id": "run_full_cycle", "timestamp": 128.0, "event": "stage_output", "stage": "tester", "cycle": 2, "payload": {"output": "STATUS: PASS", "duration_sec": 2.0}},
            {"run_id": "run_full_cycle", "timestamp": 128.1, "event": "stage_completed", "stage": "tester", "cycle": 2},
            {"run_id": "run_full_cycle", "timestamp": 129.0, "event": "stage_started", "stage": "reviewer", "cycle": 2, "payload": {"provider": "anthropic", "model": "sonnet"}},
            {"run_id": "run_full_cycle", "timestamp": 132.0, "event": "stage_output", "stage": "reviewer", "cycle": 2, "payload": {"output": "VERDICT: APPROVE", "duration_sec": 3.0}},
            {"run_id": "run_full_cycle", "timestamp": 132.1, "event": "stage_completed", "stage": "reviewer", "cycle": 2},
            {"run_id": "run_full_cycle", "timestamp": 132.2, "event": "review_verdict", "stage": "reviewer", "cycle": 2, "payload": {"cycle": 2, "verdict": "APPROVE", "frontend_fix_required": False, "backend_fix_required": False, "dependency_fix_required": False}},
            {"run_id": "run_full_cycle", "timestamp": 132.3, "event": "pipeline_finished", "payload": {"final_status": "APPROVE", "reason": "Approved", "cycles_used": 2, "total_duration_sec": 32.3}},
        ]

        state = reduce_run_state(events)

        # Assert state fields
        self.assertEqual(state["run_id"], "run_full_cycle")
        self.assertEqual(state["task"], "Build workout widget")
        self.assertEqual(state["status"], "awaiting_human_approval")
        self.assertEqual(state["current_cycle"], 2)
        self.assertEqual(state["stages"]["planner"]["status"], "complete")
        self.assertEqual(state["stages"]["planner"]["output"], "# Spec")

        # Frontend attempts preserved
        self.assertEqual(len(state["stages"]["frontend"]["attempts"]), 2)
        self.assertEqual(state["stages"]["frontend"]["attempts"][0]["type"], "initial")
        self.assertEqual(state["stages"]["frontend"]["attempts"][1]["type"], "repair")
        self.assertEqual(state["stages"]["frontend"]["attempts"][1]["cycle"], 2)

        # Files changed tracking
        self.assertIn("src/app/widget.tsx", state["files_changed"]["created"])
        self.assertIn("src/app/widget.tsx", state["files_changed"]["modified"])

        # Test & Git tracking
        self.assertEqual(len(state["tests"]), 2)
        self.assertEqual(state["git"]["diff_stat"], "1 file changed")

        # Review state
        self.assertEqual(state["review"]["verdict"], "APPROVE")
        self.assertEqual(len(state["retries"]), 1)

    def test_api_endpoints_integration(self):
        events = [
            {"run_id": "run_api_test_1", "timestamp": 100.0, "event": "pipeline_started", "payload": {"task": "Task Test"}},
            {"run_id": "run_api_test_1", "timestamp": 105.0, "event": "pipeline_finished", "payload": {"final_status": "APPROVE", "cycles_used": 1, "total_duration_sec": 5.0}},
        ]
        self._create_sample_run("run_api_test_1", events)

        # Details endpoint
        res = self.client.get("/api/runs/run_api_test_1")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["run_id"], "run_api_test_1")
        self.assertEqual(data["status"], "awaiting_human_approval")

        # Raw events endpoint
        ev_res = self.client.get("/api/runs/run_api_test_1/events")
        self.assertEqual(ev_res.status_code, 200)
        ev_data = ev_res.json()
        self.assertEqual(ev_data["count"], 2)

        # Non-existent run
        not_found_res = self.client.get("/api/runs/run_non_existent")
        self.assertEqual(not_found_res.status_code, 404)


    def test_live_streaming_sse_receives_appended_events(self):
        run_id = "run_stream_test_1"
        run_folder = self.test_dir / run_id
        run_folder.mkdir(parents=True, exist_ok=True)
        events_file = run_folder / "events.jsonl"

        # Write initial event
        initial_ev = {"run_id": run_id, "timestamp": 100.0, "event": "pipeline_started", "payload": {"task": "Stream Test"}}
        with open(events_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(initial_ev) + "\n")

        # Append terminal event
        terminal_ev = {"run_id": run_id, "timestamp": 105.0, "event": "pipeline_finished", "payload": {"final_status": "APPROVE"}}
        with open(events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(terminal_ev) + "\n")

        with self.client.stream("GET", f"/api/runs/{run_id}/stream") as response:
            self.assertEqual(response.status_code, 200)
            lines = [line for line in response.iter_lines() if line]
            # Verify stream yielded data lines
            self.assertTrue(any("pipeline_started" in l for l in lines))
            self.assertTrue(any("pipeline_finished" in l for l in lines))
            self.assertTrue(any("[DONE]" in l for l in lines))

    def test_pipeline_status_endpoint_idle(self):
        res = self.client.get("/api/pipeline/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["running"])
        self.assertIsNone(data["run_id"])
        self.assertIsNone(data["task"])

    def test_pipeline_run_endpoint_validation_and_rejection(self):
        # Empty task
        res1 = self.client.post("/api/runs", json={"task": ""})
        self.assertEqual(res1.status_code, 400)

        res2 = self.client.post("/api/runs", json={"task": "   \n\t  "})
        self.assertEqual(res2.status_code, 400)

        # Missing task
        res3 = self.client.post("/api/runs", json={})
        self.assertEqual(res3.status_code, 422)

    def test_pipeline_run_endpoint_successful_launch_and_concurrency_guard(self):
        import time
        from orchestrator.agent_flow.executor import execution_manager

        executed_tasks = []
        executed_run_ids = []

        def mock_pipeline_func(task: str, run_id: Optional[str] = None, token=None):
            executed_tasks.append(task)
            executed_run_ids.append(run_id)
            time.sleep(0.3)

        with patch.object(execution_manager, "_thread", None):
            # Launch 1st pipeline with custom mock function
            res = execution_manager.start_pipeline("Build Workout UI", pipeline_func=mock_pipeline_func, label="Feature 3")
            self.assertTrue(res["accepted"])
            self.assertEqual(res.get("label"), "Feature 3")
            run_id_1 = res["run_id"]
            self.assertTrue(run_id_1.startswith("run_"))

            # Active status reports running
            status_res = self.client.get("/api/pipeline/status")
            status_data = status_res.json()
            self.assertTrue(status_data["running"])
            self.assertEqual(status_data["run_id"], run_id_1)
            self.assertEqual(status_data["task"], "Build Workout UI")

            # Launch 2nd pipeline via API while active -> 409 Conflict
            conflict_res = self.client.post("/api/runs", json={"task": "Another task"})
            self.assertEqual(conflict_res.status_code, 409)
            conflict_data = conflict_res.json()
            self.assertEqual(conflict_data["error"], "pipeline_already_running")
            self.assertEqual(conflict_data["run_id"], run_id_1)

            # Wait for mock to finish
            time.sleep(0.4)

            # After completion, status resets to idle
            status_res2 = self.client.get("/api/pipeline/status")
            status_data2 = status_res2.json()
            self.assertFalse(status_data2["running"])
            self.assertIsNone(status_data2["run_id"])

            self.assertEqual(executed_tasks, ["Build Workout UI"])
            self.assertEqual(executed_run_ids, [run_id_1])

    def test_pipeline_run_resets_on_exception(self):
        import time
        from orchestrator.agent_flow.executor import execution_manager

        def mock_failing_pipeline(task: str, run_id: Optional[str] = None, token=None):
            raise RuntimeError("Simulated internal worker crash")

        res = execution_manager.start_pipeline("Failing Task", pipeline_func=mock_failing_pipeline)
        self.assertTrue(res["accepted"])
        # Wait for thread to fail and clean up
        time.sleep(0.2)

        status_res = self.client.get("/api/pipeline/status")
        status_data = status_res.json()
        self.assertFalse(status_data["running"])
        self.assertIsNone(status_data["run_id"])

    def test_pipeline_stop_endpoints_and_cancellation_flow(self):
        import time
        from orchestrator.agent_flow.executor import execution_manager
        from orchestrator.cancellation import CancellationToken

        # 1. Stop when idle -> rejected 400
        res_idle = self.client.post("/api/pipeline/stop")
        self.assertEqual(res_idle.status_code, 400)

        # 2. Start mock long-running pipeline
        worker_reached_checkpoint = False
        worker_honored_cancel = False

        def mock_stoppable_pipeline(task: str, run_id: Optional[str] = None, token: Optional[CancellationToken] = None):
            nonlocal worker_reached_checkpoint, worker_honored_cancel
            for _ in range(50):
                if token and token.is_cancelled():
                    worker_honored_cancel = True
                    break
                time.sleep(0.05)
            worker_reached_checkpoint = True

        res_launch = execution_manager.start_pipeline("Stoppable task", pipeline_func=mock_stoppable_pipeline)
        run_id = res_launch["run_id"]

        # Status immediately shows running and cancellation_requested=False
        st1 = self.client.get("/api/pipeline/status").json()
        self.assertTrue(st1["running"])
        self.assertFalse(st1["cancellation_requested"])

        # Stop via mismatched run ID -> 400
        res_bad_stop = self.client.post("/api/runs/run_wrong_123/stop")
        self.assertEqual(res_bad_stop.status_code, 400)

        # Stop via matching run ID
        res_stop = self.client.post(f"/api/runs/{run_id}/stop")
        self.assertEqual(res_stop.status_code, 200)
        self.assertEqual(res_stop.json()["status"], "cancellation_requested")

        # Status immediately shows cancellation_requested=True, running STILL True
        st2 = self.client.get("/api/pipeline/status").json()
        self.assertTrue(st2["running"])
        self.assertTrue(st2["cancellation_requested"])

        # Concurrent run launch still blocked with 409
        res_conflict = self.client.post("/api/runs", json={"task": "Another task"})
        self.assertEqual(res_conflict.status_code, 409)

        # Wait for worker to exit
        time.sleep(0.3)

        self.assertTrue(worker_reached_checkpoint)
        self.assertTrue(worker_honored_cancel)

        # After worker exit, status resets to idle and cancellation_requested=False
        st3 = self.client.get("/api/pipeline/status").json()
        self.assertFalse(st3["running"])
        self.assertIsNone(st3["run_id"])
        self.assertFalse(st3["cancellation_requested"])

    def test_pipeline_retry_endpoint_and_lineage(self):
        import time
        from orchestrator.agent_flow.executor import execution_manager

        active_root, _ = resolve_repo_root()
        # 1. Create a historical failed run and a historical approved run
        failed_events = [
            {"run_id": "run_hist_failed", "timestamp": 100.0, "event": "pipeline_started", "payload": {"task": "Build workout timer", "project_repo_path": str(active_root)}},
            {"run_id": "run_hist_failed", "timestamp": 110.0, "event": "pipeline_finished", "payload": {"final_status": "FAILED", "reason": "PROVIDER_TIMEOUT"}},
        ]
        self._create_sample_run("run_hist_failed", failed_events)

        approved_events = [
            {"run_id": "run_hist_approved", "timestamp": 200.0, "event": "pipeline_started", "payload": {"task": "Approved task", "project_repo_path": str(active_root)}},
            {"run_id": "run_hist_approved", "timestamp": 210.0, "event": "pipeline_finished", "payload": {"final_status": "APPROVE"}},
        ]
        self._create_sample_run("run_hist_approved", approved_events)

        # 2. Retrying approved run -> 400 Bad Request
        res_appr = self.client.post("/api/runs/run_hist_approved/retry")
        self.assertEqual(res_appr.status_code, 400)

        # 3. Retrying non-existent run -> 404
        res_404 = self.client.post("/api/runs/run_non_existent_99/retry")
        self.assertEqual(res_404.status_code, 404)

        # 4. Retrying failed run -> accepted (202), returns new run_id with retry_of lineage
        executed_tasks = []
        executed_run_ids = []

        def mock_retry_pipeline(task: str, run_id: Optional[str] = None, token=None):
            executed_tasks.append(task)
            executed_run_ids.append(run_id)
            time.sleep(0.1)

        def _isolated_start_pipeline(task: str, pipeline_func=None, retry_of=None):
            func_to_use = pipeline_func or mock_retry_pipeline
            return orig_start_pipeline(task=task, pipeline_func=func_to_use, retry_of=retry_of)

        orig_start_pipeline = execution_manager.start_pipeline
        with patch.object(execution_manager, "start_pipeline", side_effect=_isolated_start_pipeline):
            res_retry = self.client.post("/api/runs/run_hist_failed/retry")
            self.assertEqual(res_retry.status_code, 202)
            data = res_retry.json()
            self.assertTrue(data["accepted"])
            self.assertNotEqual(data["run_id"], "run_hist_failed")
            self.assertEqual(data["retry_of"], "run_hist_failed")
            self.assertEqual(data["task"], "Build workout timer")

            # While active, another launch/retry -> 409
            res_conf = self.client.post("/api/runs/run_hist_failed/retry")
            self.assertEqual(res_conf.status_code, 409)

            # Wait for execution to finish
            time.sleep(0.2)

        # Old run remains unchanged
        old_events = repo_module.get_run_events("run_hist_failed")
        self.assertEqual(len(old_events), 2)
        self.assertEqual(old_events[-1]["payload"]["final_status"], "FAILED")


    def test_human_approve_and_reject_flow(self):
        import time
        from orchestrator.agent_flow.executor import execution_manager

        # 1. Create a run that finished with AWAITING_HUMAN_APPROVAL
        awaiting_events = [
            {"run_id": "run_awaiting_1", "timestamp": 100.0, "event": "pipeline_started", "payload": {"task": "Add volume chart"}},
            {"run_id": "run_awaiting_1", "timestamp": 105.0, "event": "stage_started", "stage": "reviewer", "cycle": 1, "payload": {}},
            {"run_id": "run_awaiting_1", "timestamp": 110.0, "event": "review_verdict", "stage": "reviewer", "cycle": 1, "payload": {"verdict": "APPROVE", "frontend_fix_required": False, "backend_fix_required": False, "dependency_fix_required": False}},
            {"run_id": "run_awaiting_1", "timestamp": 111.0, "event": "human_approval_required", "stage": "reviewer", "cycle": 1, "payload": {"reviewer_verdict": "APPROVE"}},
            {"run_id": "run_awaiting_1", "timestamp": 112.0, "event": "pipeline_finished", "payload": {"final_status": "AWAITING_HUMAN_APPROVAL", "reason": "Reviewer approved implementation changes. Awaiting operator decision.", "cycles_used": 1, "total_duration_sec": 12.0}},
        ]
        self._create_sample_run("run_awaiting_1", awaiting_events)

        # 2. Check reducer state for awaiting run
        details_res = self.client.get("/api/runs/run_awaiting_1")
        self.assertEqual(details_res.status_code, 200)
        st = details_res.json()
        self.assertEqual(st["status"], "awaiting_human_approval")
        self.assertEqual(st["review"]["verdict"], "APPROVE")
        self.assertIsNone(st["review"].get("human_decision"))

        # 3. Approve run
        # Approval HTTP/reducer fixture must not merge a real repository.
        with patch("orchestrator.agent_flow.server.merge_run_worktree", return_value={"success": True}):
            appr_res = self.client.post("/api/runs/run_awaiting_1/approve")
        self.assertEqual(appr_res.status_code, 200)
        appr_data = appr_res.json()
        self.assertTrue(appr_data["accepted"])
        self.assertEqual(appr_data["status"], "approved")

        # Check state after approve
        st_after_appr = self.client.get("/api/runs/run_awaiting_1").json()
        self.assertEqual(st_after_appr["status"], "approved")
        self.assertEqual(st_after_appr["review"]["human_decision"]["decision"], "APPROVE")

        # 4. Double decision prevented: Cannot approve or reject already approved run
        double_appr = self.client.post("/api/runs/run_awaiting_1/approve")
        self.assertEqual(double_appr.status_code, 400)
        double_rej = self.client.post("/api/runs/run_awaiting_1/reject", json={"reason": "too late"})
        self.assertEqual(double_rej.status_code, 400)

        # 5. Create another run for reject testing
        active_root, _ = resolve_repo_root()
        awaiting_events_2 = [
            {"run_id": "run_awaiting_2", "timestamp": 200.0, "event": "pipeline_started", "payload": {"task": "Add dark mode toggle", "project_repo_path": str(active_root)}},
            {"run_id": "run_awaiting_2", "timestamp": 205.0, "event": "stage_started", "stage": "reviewer", "cycle": 1, "payload": {}},
            {"run_id": "run_awaiting_2", "timestamp": 210.0, "event": "review_verdict", "stage": "reviewer", "cycle": 1, "payload": {"verdict": "APPROVE"}},
            {"run_id": "run_awaiting_2", "timestamp": 211.0, "event": "human_approval_required", "stage": "reviewer", "cycle": 1, "payload": {}},
            {"run_id": "run_awaiting_2", "timestamp": 212.0, "event": "pipeline_finished", "payload": {"final_status": "AWAITING_HUMAN_APPROVAL", "cycles_used": 1, "total_duration_sec": 12.0}},
        ]
        self._create_sample_run("run_awaiting_2", awaiting_events_2)

        # Reject run with reason
        with patch("orchestrator.agent_flow.server.discard_run_worktree", return_value={"worktree_removed": True, "branch_deleted": True}):
            rej_res = self.client.post("/api/runs/run_awaiting_2/reject", json={"reason": "Design needs more contrast"})
        self.assertEqual(rej_res.status_code, 200)
        rej_data = rej_res.json()
        self.assertTrue(rej_data["accepted"])
        self.assertEqual(rej_data["status"], "rejected")
        self.assertEqual(rej_data["reason"], "Design needs more contrast")

        # Check state after reject
        st_after_rej = self.client.get("/api/runs/run_awaiting_2").json()
        self.assertEqual(st_after_rej["status"], "rejected")
        self.assertEqual(st_after_rej["reason"], "Design needs more contrast")
        self.assertEqual(st_after_rej["review"]["human_decision"]["decision"], "REJECT")
        self.assertEqual(st_after_rej["review"]["human_decision"]["reason"], "Design needs more contrast")

        # Double decision prevented on rejected run
        rej_again = self.client.post("/api/runs/run_awaiting_2/reject")
        self.assertEqual(rej_again.status_code, 400)
        appr_rej = self.client.post("/api/runs/run_awaiting_2/approve")
        self.assertEqual(appr_rej.status_code, 400)

        # 6. Retry on REJECTED run is eligible!
        def mock_reject_retry_pipeline(task: str, run_id: Optional[str] = None, token=None):
            time.sleep(0.05)

        def _isolated_start_pipeline(task: str, pipeline_func=None, retry_of=None):
            func_to_use = pipeline_func or mock_reject_retry_pipeline
            return orig_start_pipeline(task=task, pipeline_func=func_to_use, retry_of=retry_of)

        orig_start_pipeline = execution_manager.start_pipeline
        with patch.object(execution_manager, "start_pipeline", side_effect=_isolated_start_pipeline):
            retry_res = self.client.post("/api/runs/run_awaiting_2/retry")
            self.assertEqual(retry_res.status_code, 202)
            r_data = retry_res.json()
            self.assertTrue(r_data["accepted"])
            self.assertEqual(r_data["retry_of"], "run_awaiting_2")
            self.assertEqual(r_data["task"], "Add dark mode toggle")

            # Source rejected run remains intact
            src_evs = repo_module.get_run_events("run_awaiting_2")
            self.assertEqual(src_evs[-1]["event"], "human_decision")
            self.assertEqual(src_evs[-1]["payload"]["decision"], "REJECT")

            time.sleep(0.1)

    def test_purge_and_delete_single_run_endpoints(self):
        """Test DELETE /api/runs/purge and DELETE /api/runs/{run_id}."""
        # Create 3 inactive runs
        for r_id in ["run_to_purge_1", "run_to_purge_2", "run_to_delete_single"]:
            evs = [
                {"run_id": r_id, "timestamp": 100.0, "event": "pipeline_started", "payload": {"task": "Task"}},
                {"run_id": r_id, "timestamp": 110.0, "event": "pipeline_finished", "payload": {"final_status": "FAILED"}},
            ]
            self._create_sample_run(r_id, evs)

        # 1. Delete single run
        del_res = self.client.delete("/api/runs/run_to_delete_single")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json()["status"], "deleted")
        self.assertFalse((self.test_dir / "run_to_delete_single").exists())

        # 2. Purge remaining
        purge_res = self.client.delete("/api/runs/purge")
        self.assertEqual(purge_res.status_code, 200)
        self.assertEqual(purge_res.json()["purged_count"], 2)
        self.assertFalse((self.test_dir / "run_to_purge_1").exists())
        self.assertFalse((self.test_dir / "run_to_purge_2").exists())

    def test_production_run_directory_never_polluted_by_tests(self):
        """Regression test ensuring test suite execution never pollutes production .bum/runs/."""
        prod_runs_dir = events_module.BUM_STATE_DIR / "runs"
        before_entries = set(p.name for p in prod_runs_dir.iterdir() if p.is_dir()) if prod_runs_dir.exists() else set()

        # Simulate synthetic retry and run operations inside isolated test environment
        active_root, _ = resolve_repo_root()
        sample_events = [
            {"run_id": "run_isolated_test", "timestamp": 100.0, "event": "pipeline_started", "payload": {"task": "Isolated Task", "project_repo_path": str(active_root)}},
            {"run_id": "run_isolated_test", "timestamp": 110.0, "event": "pipeline_finished", "payload": {"final_status": "FAILED"}},
        ]
        self._create_sample_run("run_isolated_test", sample_events)

        def mock_quick_pipeline(task: str, run_id: Optional[str] = None, token=None):
            time.sleep(0.05)

        def _isolated_start_pipeline(task: str, pipeline_func=None, retry_of=None):
            func_to_use = pipeline_func or mock_quick_pipeline
            return orig_start_pipeline(task=task, pipeline_func=func_to_use, retry_of=retry_of)

        orig_start_pipeline = execution_manager.start_pipeline
        with patch.object(execution_manager, "start_pipeline", side_effect=_isolated_start_pipeline):
            res = self.client.post("/api/runs/run_isolated_test/retry")
            self.assertEqual(res.status_code, 202)
            time.sleep(0.15)

        after_entries = set(p.name for p in prod_runs_dir.iterdir() if p.is_dir()) if prod_runs_dir.exists() else set()
        self.assertEqual(before_entries, after_entries, "Production pipeline/runs directory was polluted by test run!")

    def test_prompt_preview_endpoint_and_security(self):
        """Deterministic prompt preview; no real prompt or workspace access."""
        import orchestrator.agent_flow.server as server
        agents = self.test_dir / "agents"
        workspace = self.test_dir / "workspace"
        workspace.mkdir()
        relative = Path("pipeline/prompts/test_dummy_prompt.md")
        prompt = agents / relative
        prompt.parent.mkdir(parents=True)
        prompt.write_text("# Test Prompt", encoding="utf-8")
        ws_prompt = workspace / "pipeline/prompts/workspace_fixture.md"
        ws_prompt.parent.mkdir(parents=True)
        ws_prompt.write_text("Workspace fixture", encoding="utf-8")
        with patch.object(server, "AGENTS_ROOT", agents), patch.object(server, "WORKSPACE_ROOT", workspace):
            for value in (relative.as_posix(), "@file:" + relative.as_posix()):
                response = self.client.get("/api/prompts/preview", params={"file": value})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["content"], "# Test Prompt")
                self.assertEqual(Path(response.json()["resolved_path"]), prompt)
            response = self.client.get("/api/prompts/preview", params={"file": "pipeline/prompts/workspace_fixture.md"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["content"], "Workspace fixture")
            for value in ("pipeline/prompts/does_not_exist.md", "../../../../../../etc/passwd"):
                self.assertEqual(self.client.get("/api/prompts/preview", params={"file": value}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
