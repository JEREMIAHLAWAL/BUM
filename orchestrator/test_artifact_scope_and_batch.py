"""Offline end-to-end guards for artifact isolation and Tester batch preflight."""
import asyncio
import io
import json
import os
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest.mock import patch

# Prevent credential reads and the server's import-time Git probe.
with patch("dotenv.load_dotenv", return_value=False), patch("subprocess.run"):
    from orchestrator import pipeline, repo_tools
    from orchestrator import test_tester_writes as fixtures
    from orchestrator.agent_flow import server


class BatchPreflightTests(unittest.TestCase):
    def setUp(self):
        with patch.object(tempfile, "tempdir", str(Path.home() / "AppData/Local/hermes/cache/scratch")):
            fixtures.TesterWriteTests.setUp(self)

    def apply_batch(self, operations, contract=None):
        output = "\n".join(f"```{op}:{path}\n{content}```" for op, path, content in operations)
        c = contract if contract is not None else {
            "file_boundaries": list(dict.fromkeys(path for _, path, _ in operations))}
        return pipeline.parse_and_apply_agent_file_operations(output, "tester", contract=c)

    def test_predictable_invalid_later_operation_never_writes_earlier_file(self):
        self.manifest = fixtures.manifest_for(["tests"])
        (self.root / "tests/directory").mkdir(parents=True)
        (self.root / "tests/parent").write_text("parent unchanged")
        for op, path, content in [("delete", "tests/missing.py", ""),
                                  ("delete", "tests/directory", ""),
                                  ("write", "tests/directory", "bad"),
                                  ("write", "tests/parent/child.py", "bad")]:
            with self.subTest(op=op, path=path):
                with self.assertRaises((OSError, PermissionError)):
                    self.apply_batch([("write", "tests/first.py", "must not exist\n"), (op, path, content)])
                self.assertFalse((self.root / "tests/first.py").exists())
        self.assertEqual((self.root / "tests/parent").read_text(), "parent unchanged")

    def test_simulated_new_parent_file_conflict_blocks_whole_batch(self):
        self.manifest = fixtures.manifest_for(["tests"])
        with self.assertRaises((OSError, PermissionError)):
            self.apply_batch([("write", "tests/parent", "file"), ("write", "tests/parent/child.py", "bad")])
        self.assertFalse((self.root / "tests").exists())

    def test_sequential_write_delete_and_delete_write_are_valid(self):
        self.manifest = fixtures.manifest_for(["tests"])
        result = self.apply_batch([("write", "tests/transient.py", "pass\n"),
                                   ("delete", "tests/transient.py", "")])
        self.assertEqual(result["executed_count"], 2)
        self.assertFalse((self.root / "tests/transient.py").exists())
        (self.root / "tests/existing.py").write_text("old")
        self.apply_batch([("delete", "tests/existing.py", ""), ("write", "tests/existing.py", "new")])
        self.assertEqual((self.root / "tests/existing.py").read_text(), "new")

    def test_double_delete_is_blocked_before_any_writes(self):
        self.manifest = fixtures.manifest_for(["tests"])
        (self.root / "tests").mkdir()
        (self.root / "tests/existing.py").write_text("unchanged")
        with self.assertRaises(FileNotFoundError):
            self.apply_batch([("write", "tests/first.py", "bad"), ("delete", "tests/existing.py", ""),
                              ("delete", "tests/existing.py", "")])
        self.assertFalse((self.root / "tests/first.py").exists())
        self.assertEqual((self.root / "tests/existing.py").read_text(), "unchanged")

    def test_contract_and_manifest_guards_block_batch_before_first_mutation(self):
        self.manifest = fixtures.manifest_for(["tests"])
        # Outside manifest root
        with self.assertRaises(PermissionError):
            self.apply_batch([("write", "tests/valid.py", "valid"), ("write", "src/auth.py", "bad")])
        self.assertFalse((self.root / "tests/valid.py").exists())

        # Reference file in contract
        with self.assertRaises(PermissionError):
            self.apply_batch([("write", "tests/valid.py", "valid"), ("write", "tests/ref.py", "bad")],
                             contract={"file_boundaries": ["tests/valid.py", "tests/ref.py"],
                                       "reference_files": ["tests/ref.py"]})
        self.assertFalse((self.root / "tests/valid.py").exists())

    def test_delete_file_then_write_child_directory_in_same_batch(self):
        self.manifest = fixtures.manifest_for(["tests"])
        (self.root / "tests").mkdir()
        (self.root / "tests/parent").write_text("old file")
        result = self.apply_batch([("delete", "tests/parent", ""),
                                   ("write", "tests/parent/child.py", "child content\n")])
        self.assertEqual(result["executed_count"], 2)
        self.assertTrue((self.root / "tests/parent/child.py").is_file())
        self.assertEqual((self.root / "tests/parent/child.py").read_text(), "child content\n")

    def test_write_child_then_delete_parent_directory_blocked_before_writes(self):
        self.manifest = fixtures.manifest_for(["tests"])
        with self.assertRaises(IsADirectoryError):
            self.apply_batch([("write", "tests/dir/child.py", "content\n"),
                              ("delete", "tests/dir", "")])
        self.assertFalse((self.root / "tests").exists())

    def test_unpredictable_io_error_propagates_without_claiming_atomic_rollback(self):
        self.manifest = fixtures.manifest_for(["tests"])
        real_write = pipeline.write_file
        def write(path, content, role):
            if path == "tests/second.py":
                raise OSError("fixture unexpected disk failure")
            return real_write(path, content, role=role)
        with patch.object(pipeline, "write_file", side_effect=write):
            with self.assertRaisesRegex(OSError, "unexpected disk failure"):
                self.apply_batch([("write", "tests/first.py", "first\n"),
                                  ("write", "tests/second.py", "second\n")])
        self.assertEqual((self.root / "tests/first.py").read_text(), "first\n")
        self.assertFalse((self.root / "tests/second.py").exists())


class ArtifactScopeTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        scratch = Path.home() / "AppData/Local/hermes/cache/scratch"
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(dir=scratch)))
        self.legacy = self.root / "pipeline"
        self.legacy.mkdir()
        (self.legacy / "HANDOFF.md").write_text("UNRELATED EXPO HANDOFF")
        salvage = self.legacy / "salvage/latest"
        salvage.mkdir(parents=True)
        (salvage / "code.py").write_text("UNRELATED SALVAGE")
        (salvage / "meta.json").write_text(json.dumps({"project_repo_path": str(self.root / "OtherProject")}))
        self.repo = self.root / "FinderShip"
        self.repo.mkdir()
        self.stack.enter_context(patch.object(pipeline, "AGENT_PROJECT_ROOT", self.root))
        self.stack.enter_context(patch.object(pipeline, "PIPELINE_DIR", self.legacy))
        self.stack.enter_context(patch.object(pipeline, "resolve_repo_root", return_value=(self.repo, "fixture")))
        self.stack.enter_context(patch.object(pipeline, "get_repo_root", return_value=self.repo))
        self.stack.enter_context(patch.object(pipeline, "get_active_manifest", return_value=fixtures.manifest_for()))
        self.stack.enter_context(patch.object(pipeline, "repo_tree", return_value="FinderShip source tree"))
        self.stack.enter_context(patch.object(pipeline, "extract_type_skeletons", return_value=""))
        self.stack.enter_context(patch.object(pipeline, "create_run_worktree", return_value={
            "success": True, "worktree_path": str(self.repo)}))
        self.stack.enter_context(patch.object(pipeline, "set_run_worktree_override"))
        self.stack.enter_context(patch.object(pipeline, "discard_run_worktree"))

    def test_real_helpers_use_scope_before_impl_and_restore_on_exception(self):
        observed = []
        def impl(*args, **kwargs):
            context = pipeline.get_shared_context()
            observed.append(context)
            self.assertNotIn("UNRELATED", context)
            pipeline.write_pipeline_file("spec.md", "SCOPED SPEC")
            self.assertEqual(pipeline.read_pipeline_file("spec.md"), "SCOPED SPEC")
            raise RuntimeError("fixture interrupted")
        with patch.object(pipeline, "_run_pipeline_impl", side_effect=impl):
            with self.assertRaisesRegex(RuntimeError, "fixture interrupted"):
                pipeline.run_pipeline("task", run_id="run_scope_fixture", retry_of="run_other_project")
        artifact_dir = self.root / ".bum/runs/run_scope_fixture/pipeline"
        self.assertEqual((artifact_dir / "spec.md").read_text(), "SCOPED SPEC")
        metadata = json.loads((artifact_dir.parent / "artifact_context.json").read_text())
        self.assertEqual(metadata["artifact_dir"], str(artifact_dir.resolve()))
        self.assertEqual(metadata["project_repo_path"], str(self.repo.resolve()))
        self.assertEqual(metadata["retry_of"], "run_other_project")
        self.assertEqual(pipeline.read_pipeline_file("HANDOFF.md"), "UNRELATED EXPO HANDOFF")
        self.assertFalse((self.legacy / "spec.md").exists())
        self.assertEqual(len(observed), 1)

    def test_unprovenanced_or_other_project_shared_salvage_never_autoloads(self):
        self.assertEqual(pipeline.get_salvaged_context(), "")
        self.assertNotIn("UNRELATED", pipeline.get_shared_context())
        (self.legacy / "salvage/latest/meta.json").unlink()
        self.assertEqual(pipeline.get_salvaged_context(), "")

    def test_legacy_resume_http_refuses_before_starting_worker(self):
        from fastapi import HTTPException
        from orchestrator.agent_flow import server
        run_dir = self.root / "run_20261018_000000_abcdef"
        run_dir.mkdir()
        with patch.object(server, "get_run_dir", return_value=run_dir), \
                patch.object(server.execution_manager, "get_status", return_value={"running": False}), \
                patch.object(server.execution_manager, "start_pipeline") as start:
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(server.resume_run_endpoint(run_dir.name))
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("retry", str(raised.exception.detail).lower())
        start.assert_not_called()

    def test_manual_legacy_resume_refuses_before_reading_or_running_commands(self):
        from orchestrator import resume_test_review
        with patch.object(resume_test_review, "read_pipeline_file") as read, \
                patch.object(resume_test_review, "run_safe_command") as command, \
                patch.object(resume_test_review, "run_agent", return_value="OFFLINE ONLY"), \
                patch.object(resume_test_review, "repo_tree", return_value="fixture"), \
                patch.object(resume_test_review, "run_safe_git_command", return_value={
                    "command": "git status", "returncode": 0, "stdout": "", "stderr": "", "timed_out": False}), \
                patch.object(resume_test_review, "get_untracked_files_content", return_value=""):
            with self.assertRaisesRegex(RuntimeError, "(?i)retry"):
                resume_test_review.run_test_and_review()
        read.assert_not_called()
        command.assert_not_called()

    def test_run_details_exposes_exact_persisted_artifact_context(self):
        from orchestrator.agent_flow import server
        run_id = "run_20261018_000000_abcdef"
        run_dir = self.root / run_id
        run_dir.mkdir()
        metadata = {"schema_version": 1, "run_id": run_id,
                    "artifact_dir": str(run_dir / "pipeline"),
                    "project_repo_path": str(self.repo), "retry_of": None, "isolated": True}
        (run_dir / "artifact_context.json").write_text(json.dumps(metadata))
        with patch.object(server, "get_run_dir", return_value=run_dir), \
                patch.object(server, "get_run_events", return_value=[]), \
                patch.object(server.execution_manager, "get_status", return_value={}):
            details = asyncio.run(server.get_run_details(run_id))
        self.assertEqual(details["artifact_context"], metadata)


class CanonicalSourceStageTests(unittest.TestCase):
    def setUp(self):
        with patch.object(tempfile, "tempdir", str(Path.home() / "AppData/Local/hermes/cache/scratch")):
            fixtures.TesterWriteTests.setUp(self)
        for name in ("AGENTS_ROOT", "WORKSPACE_ROOT"):
            self.stack.enter_context(patch.object(repo_tools, name, self.root))
        self.stack.enter_context(patch("subprocess.run", side_effect=AssertionError("Source tests cannot run subprocesses")))
        # Source propagation is under test, not execution of fixture checks.
        self.stack.enter_context(patch("orchestrator.command_tools.run_safe_command", return_value={
            "command": "fixture command", "returncode": 0, "stdout": "OFFLINE FIXTURE",
            "stderr": "", "timed_out": False}))

    command_fixture = fixtures.TesterWriteTests.command_fixture

    pipeline_fixture = fixtures.TesterWriteTests.pipeline_fixture
    run_offline_pipeline = fixtures.TesterWriteTests.run_offline_pipeline

    def test_every_actual_stage_receives_once_resolved_immutable_brief(self):
        calls, _ = self.pipeline_fixture()
        brief = "CANONICAL RESOLVED BRIEF: no unrelated project and no source edits"
        with patch.object(pipeline, "resolve_task_file_references", return_value=brief) as resolve:
            self.run_offline_pipeline()
        self.assertEqual(resolve.call_count, 1)
        self.assertEqual(set(role for role, _ in calls), {"planner", "frontend", "backend", "tester", "reviewer"})
        for role, prompt in calls:
            with self.subTest(role=role):
                self.assertIn(brief, prompt)
                self.assertIn("IMMUTABLE TASK SOURCE", prompt)
        self.assertEqual((self.root / "pipeline/resolved_task.md").read_text(), brief)
        started = [c.kwargs["payload"] for c in pipeline.emit_event.call_args_list
                   if c.kwargs.get("event") == "pipeline_started"]
        self.assertEqual(started[0]["artifact_dir"], str((self.root / "pipeline").resolve()))

    def test_actual_file_reference_content_is_frozen_for_all_stages(self):
        from orchestrator.repo_tools import resolve_task_file_references
        calls, _ = self.pipeline_fixture()
        brief = self.root / "canonical_fixture_brief.md"
        source = "CANONICAL EXACT SOURCE: immutable acceptance and ownership instructions"
        brief.write_text(source)
        original_agent = pipeline.run_agent.side_effect
        def agent(role, prompt):
            if role == "frontend":
                brief.write_text("LATER ON DISK CHANGE MUST NOT REPLACE THE SOURCE SNAPSHOT")
            return original_agent(role, prompt)
        with patch.object(pipeline, "resolve_task_file_references", wraps=resolve_task_file_references) as resolve, \
                patch.object(pipeline, "run_agent", side_effect=agent), redirect_stdout(io.StringIO()):
            pipeline._run_pipeline_impl("Implement @file:canonical_fixture_brief.md", run_id="offline-tester")
        self.assertEqual(resolve.call_count, 1)
        for role, prompt in calls:
            with self.subTest(role=role):
                self.assertIn(source, prompt)
                self.assertNotIn("LATER ON DISK CHANGE", prompt)
        saved_source = (self.root / "pipeline/resolved_task.md").read_text()
        self.assertIn(source, saved_source)
        self.assertIn("--- REFERENCED FILE: canonical_fixture_brief.md ---", saved_source)


if __name__ == "__main__":
    unittest.main()
