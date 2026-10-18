import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from orchestrator.cancellation import CancellationToken, PipelineCancelledException
from orchestrator.pipeline import run_pipeline
from orchestrator.events import EventLogger, set_current_logger


class TestCancellationSystem(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.fake_root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cancellation_token_lifecycle(self):
        token = CancellationToken(run_id="run_test_cancel_1")
        self.assertFalse(token.is_cancelled())
        self.assertIsNone(token.reason)

        # First request returns True
        self.assertTrue(token.request_cancel(reason="USER_REQUESTED_STOP"))
        self.assertTrue(token.is_cancelled())
        self.assertEqual(token.reason, "USER_REQUESTED_STOP")

        # Second request returns False (idempotent)
        self.assertFalse(token.request_cancel(reason="ANOTHER_REASON"))
        self.assertEqual(token.reason, "USER_REQUESTED_STOP")

    def test_pipeline_exits_at_checkpoint_when_cancelled(self):
        token = CancellationToken(run_id="run_test_cancel_2")
        events_emitted = []

        class MockLogger:
            def __init__(self):
                self.run_id = "run_test_cancel_2"
            def emit(self, event, stage=None, cycle=None, payload=None):
                events_emitted.append({"event": event, "stage": stage, "cycle": cycle, "payload": payload or {}})

        logger = MockLogger()

        # This is a pipeline-body checkpoint test, not a worktree lifecycle test.
        from orchestrator.pipeline import _run_pipeline_impl as run_pipeline
        with patch("orchestrator.pipeline.PIPELINE_DIR", self.fake_root / "pipeline"), \
             patch("orchestrator.pipeline.AGENT_PROJECT_ROOT", self.fake_root), \
             patch("orchestrator.pipeline.EventLogger", return_value=logger), \
             patch("orchestrator.pipeline.run_preflight_check", return_value={"repo_root": "C:/fake", "verified_executables": ["git"], "status": "ready"}), \
             patch("orchestrator.pipeline.run_safe_git_command", return_value={"returncode": 0, "stdout": "", "stderr": ""}), \
             patch("orchestrator.pipeline.run_safe_command", return_value={"returncode": 0, "stdout": "", "stderr": ""}), \
             patch("orchestrator.pipeline.capture_git_baseline", return_value={}), \
             patch("orchestrator.pipeline.get_shared_context", return_value="context"):

            # Request cancel before planner runs
            token.request_cancel(reason="USER_REQUESTED_STOP")

            with self.assertRaises(PipelineCancelledException):
                run_pipeline("Test cancellation task", run_id="run_test_cancel_2", cancellation_token=token)

            # Check that cancellation_requested and pipeline_finished(CANCELLED) were emitted
            finish_ev = next((e for e in events_emitted if e["event"] == "pipeline_finished"), None)
            self.assertIsNotNone(finish_ev)
            self.assertEqual(finish_ev["payload"]["final_status"], "CANCELLED")
            self.assertEqual(finish_ev["payload"]["reason"], "USER_REQUESTED_STOP")


if __name__ == "__main__":
    unittest.main()
