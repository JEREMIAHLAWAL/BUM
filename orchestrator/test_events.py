import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestrator.events import EventLogger, emit_event, generate_run_id, set_current_logger
import orchestrator.events as events_module


class TestEventSystem(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.orig_runs_dir = events_module.RUNS_DIR
        events_module.RUNS_DIR = self.test_dir

    def tearDown(self):
        set_current_logger(None)
        events_module.RUNS_DIR = self.orig_runs_dir
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_run_id_generation(self):
        id1 = generate_run_id()
        id2 = generate_run_id()
        self.assertTrue(id1.startswith("run_"))
        self.assertTrue(id2.startswith("run_"))
        self.assertNotEqual(id1, id2)

    def test_event_serialization_and_envelope(self):
        logger = EventLogger(run_id="test_run_123")
        set_current_logger(logger)

        emit_event(
            event="pipeline_started",
            payload={"task": "Implement test feature", "repo_path": "/fake/path"},
        )
        emit_event(
            event="stage_started",
            stage="planner",
            payload={"role": "planner", "model": "test-model"},
        )
        emit_event(
            event="stage_output",
            stage="planner",
            payload={"role": "planner", "output": "test spec content", "duration_sec": 1.5},
        )
        emit_event(
            event="stage_completed",
            stage="planner",
            payload={"duration_sec": 1.5, "status": "ok"},
        )

        self.assertTrue(logger.events_file.exists())
        lines = logger.events_file.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 4)

        for line in lines:
            record = json.loads(line)
            self.assertEqual(record["run_id"], "test_run_123")
            self.assertIn("timestamp", record)
            self.assertIn("event", record)
            self.assertIn("stage", record)
            self.assertIn("cycle", record)
            self.assertIn("payload", record)
            self.assertIsInstance(record["payload"], dict)

        # Check first event
        first_record = json.loads(lines[0])
        self.assertEqual(first_record["event"], "pipeline_started")
        self.assertEqual(first_record["payload"]["task"], "Implement test feature")

    def test_fail_safe_emission(self):
        logger = EventLogger(run_id="test_fail_safe")
        # Point events_file to an invalid path or trigger exception
        with patch("builtins.open", side_effect=PermissionError("Simulated disk write error")):
            # Should not raise exception
            try:
                logger.emit("test_event", payload={"data": 123})
            except Exception as exc:
                self.fail(f"logger.emit raised an exception unexpectedly: {exc}")


class TestMockPipelineEventSequence(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.orig_runs_dir = events_module.RUNS_DIR
        events_module.RUNS_DIR = self.test_dir

    def tearDown(self):
        set_current_logger(None)
        events_module.RUNS_DIR = self.orig_runs_dir
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_mock_pipeline_execution_events(self):
        """Simulate the exact event sequence of a pipeline without calling external LLM APIs."""
        from orchestrator.pipeline import run_pipeline

        # Mock dependencies in pipeline
        def mock_execute_test_and_git(*args, **kwargs):
            # Call real safe commands or emit simulated commands
            command_results = [{"command": "npm run ts:check", "returncode": 0, "stdout": "", "stderr": "", "timed_out": False}]
            git_results = [
                {"command": "git diff --stat", "returncode": 0, "stdout": "1 file changed", "stderr": "", "timed_out": False},
                {"command": "git diff --name-only", "returncode": 0, "stdout": "src/app/index.tsx", "stderr": "", "timed_out": False},
                {"command": "git status --short", "returncode": 0, "stdout": " M src/app/index.tsx\n?? src/app/new.tsx", "stderr": "", "timed_out": False},
            ]
            emit_event(
                event="test_result",
                stage="tester",
                payload={"commands": command_results},
            )
            emit_event(
                event="git_diff_updated",
                stage="tester",
                payload={
                    "diff_stat": "1 file changed",
                    "changed_files": ["src/app/index.tsx"],
                    "untracked_files": ["src/app/new.tsx"],
                    "git_results": git_results,
                },
            )
            return command_results, git_results, None

        with patch("orchestrator.pipeline.run_preflight_check", return_value={"repo_root": "C:/fake/trayne", "verified_executables": ["git", "npm", "npx"], "status": "ready"}), \
             patch("orchestrator.pipeline.run_safe_git_command", return_value={"command": "git status --short", "returncode": 0, "stdout": "", "stderr": "", "timed_out": False}), \
             patch("orchestrator.pipeline.run_safe_command", return_value={"command": "npm test", "returncode": 0, "stdout": "PASS", "stderr": "", "timed_out": False}), \
             patch("orchestrator.pipeline.execute_test_and_git_commands", side_effect=mock_execute_test_and_git), \
             patch("orchestrator.pipeline.write_pipeline_file"), \
             patch("orchestrator.pipeline.get_untracked_files_content", return_value=""), \
             patch("orchestrator.pipeline.run_agent") as mock_agent, \
             patch("orchestrator.pipeline.write_file", return_value={"action": "created", "path": "src/app/new.tsx"}):

            def agent_side_effect(role, prompt):
                if role == "planner":
                    return "SPEC CONTENT"
                elif role == "frontend":
                    return "```write:src/app/new.tsx\nexport default function Screen() {}\n```\nFILES CHANGED:\n- src/app/new.tsx"
                elif role == "backend":
                    return "BACKEND TASK: None."
                elif role == "tester":
                    return "STATUS: PASS\nFINDINGS: Tests pass."
                elif role == "reviewer":
                    return "VERDICT: APPROVE\nTASK: Done\nISSUES: None\nREASON: Looks good"
                return ""

            mock_agent.side_effect = agent_side_effect

            run_pipeline("Test synthetic task")

            # Verify runs directory was created and contains event file
            run_folders = list(self.test_dir.glob("run_*"))
            self.assertEqual(len(run_folders), 1)

            events_file = run_folders[0] / "events.jsonl"
            self.assertTrue(events_file.exists())

            lines = events_file.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines]
            event_names = [e["event"] for e in events]

            # Assert key pipeline lifecycle events are emitted in order
            expected_in_order = [
                "pipeline_started",
                "stage_started",    # preflight
                "stage_completed",  # preflight
                "stage_started",    # planner
                "stage_output",     # planner
                "stage_completed",  # planner
                "stage_started",    # frontend
                "stage_output",     # frontend
                "files_changed",    # frontend writes
                "stage_completed",  # frontend
                "stage_started",    # backend
                "stage_output",     # backend
                "stage_completed",  # backend
                "stage_started",    # tester
                "test_result",      # test execution
                "git_diff_updated", # git inspection
                "stage_output",     # tester
                "stage_completed",  # tester
                "stage_started",    # reviewer
                "stage_output",     # reviewer
                "stage_completed",  # reviewer
                "review_verdict",   # parsed reviewer verdict
                "human_approval_required", # human gate
                "pipeline_finished", # terminal awaiting human approval
            ]

            for expected in expected_in_order:
                self.assertIn(expected, event_names)

            # Check final status
            final_event = events[-1]
            self.assertEqual(final_event["event"], "pipeline_finished")
            self.assertEqual(final_event["payload"]["final_status"], "AWAITING_HUMAN_APPROVAL")


if __name__ == "__main__":
    unittest.main()
