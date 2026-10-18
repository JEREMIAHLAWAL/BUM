"""BUM-02 offline regressions. Never load credentials or invoke real tools."""
import asyncio
import io
import json
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# Both providers and repo_tools load dotenv at import; server probes Git at import.
with patch("dotenv.load_dotenv", return_value=False), patch("subprocess.run"):
    from orchestrator import pipeline, repo_tools, resume_test_review
    from orchestrator.agent_flow import server, executor


class OfflineFixture(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        scratch = Path.home() / "AppData/Local/hermes/cache/scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(dir=scratch)))
        self.repo = self.root / "selected"
        self.repo.mkdir()
        self.legacy = self.root / "pipeline"
        self.legacy.mkdir()
        self.manifest = SimpleNamespace(name="Fixture", project_type="python", rules=SimpleNamespace(
            test_write_roots=[], forbidden_imports=[], required_packages=[], forbidden_tokens=[],
            allowed_write_roots=[], prohibited_files=[]), verification=None)
        self.stack.enter_context(patch.object(pipeline, "AGENT_PROJECT_ROOT", self.root))
        self.stack.enter_context(patch.object(pipeline, "PIPELINE_DIR", self.legacy))
        for name in ("AGENTS_ROOT", "WORKSPACE_ROOT"):
            self.stack.enter_context(patch.object(repo_tools, name, self.root))
        for module in (pipeline, repo_tools, server):
            self.stack.enter_context(patch.object(module, "get_repo_root", return_value=self.repo))
        for module in (pipeline, server):
            self.stack.enter_context(patch.object(module, "resolve_repo_root", return_value=(self.repo, "fixture")))
        for module in (pipeline, repo_tools):
            self.stack.enter_context(patch.object(module, "get_active_manifest", return_value=self.manifest))
        self.stack.enter_context(patch.object(pipeline, "repo_tree", return_value="fixture tree"))
        self.stack.enter_context(patch.object(pipeline, "extract_type_skeletons", return_value=""))
        self.stack.enter_context(patch.object(pipeline, "create_run_worktree", return_value={
            "success": True, "worktree_path": str(self.repo)}))
        self.override = self.stack.enter_context(patch.object(pipeline, "set_run_worktree_override"))
        self.discard = self.stack.enter_context(patch.object(pipeline, "discard_run_worktree"))
        self.effects = []
        for module in (pipeline, resume_test_review):
            for name in ("run_agent", "run_safe_command", "run_safe_git_command"):
                mock = self.stack.enter_context(patch.object(module, name, side_effect=AssertionError("Unexpected real boundary: " + name)))
                self.effects.append(mock)
        self.stack.enter_context(patch("orchestrator.providers.call_provider", side_effect=AssertionError("Provider forbidden")))
        self.stack.enter_context(patch("subprocess.run", side_effect=AssertionError("Subprocess forbidden")))
        self.stack.enter_context(patch.object(pipeline, "emit_event"))


class ArtifactRegressionTests(OfflineFixture):
    def test_malformed_legacy_provenance_fails_closed(self):
        (self.legacy / "HANDOFF.md").write_text("FOREIGN HANDOFF")
        salvage = self.legacy / "salvage/latest"
        salvage.mkdir(parents=True)
        (salvage / "code.py").write_text("FOREIGN SALVAGE")
        for raw in ("[]", '"not metadata"', "null", "{bad json", "{}"):
            with self.subTest(raw=raw):
                (self.legacy / "artifact_context.json").write_text(raw)
                (salvage / "meta.json").write_text(raw)
                self.assertNotIn("FOREIGN", pipeline.get_shared_context())
                self.assertEqual(pipeline.get_salvaged_context(), "")

    def test_scoped_handoff_requires_matching_project_and_artifact_path(self):
        def impl(*args, **kwargs):
            directory = pipeline.get_pipeline_dir()
            pipeline.write_pipeline_file("HANDOFF.md", "SCOPED HANDOFF")
            marker = directory.parent / "artifact_context.json"
            good = json.loads(marker.read_text())
            salvage = directory / "salvage/latest"
            salvage.mkdir(parents=True)
            (salvage / "code.py").write_text("SCOPED SALVAGE")
            (salvage / "meta.json").write_text(json.dumps({"project_repo_path": str(self.repo)}))
            self.assertIn("SCOPED HANDOFF", pipeline.get_shared_context())
            self.assertIn("SCOPED SALVAGE", pipeline.get_salvaged_context())
            for mutation in ({"project_repo_path": str(self.root / "foreign")},
                             {"artifact_dir": str(self.root / "foreign/pipeline")},
                             {"run_id": "run_foreign"}):
                with self.subTest(mutation=mutation):
                    marker.write_text(json.dumps({**good, **mutation}))
                    self.assertNotIn("SCOPED HANDOFF", pipeline.get_shared_context())
                    self.assertEqual(pipeline.get_salvaged_context(), "")
            marker.unlink()
            self.assertNotIn("SCOPED HANDOFF", pipeline.get_shared_context())
            self.assertEqual(pipeline.get_salvaged_context(), "")
        with patch.object(pipeline, "_run_pipeline_impl", side_effect=impl):
            pipeline.run_pipeline("task", run_id="run_scope_marker")

    def test_two_projects_and_retry_never_import_previous_artifacts(self):
        paths = []
        def impl(*args, **kwargs):
            directory = pipeline.get_pipeline_dir()
            self.assertNotIn("PREVIOUS", pipeline.get_shared_context())
            paths.append(directory)
            pipeline.write_pipeline_file("HANDOFF.md", "PREVIOUS HANDOFF")
            salvage = directory / "salvage/latest"
            salvage.mkdir(parents=True)
            (salvage / "code.py").write_text("PREVIOUS SALVAGE")
            (salvage / "meta.json").write_text(json.dumps({
                "project_repo_path": str(self.repo), "run_id": kwargs["run_id"]}))
        with patch.object(pipeline, "_run_pipeline_impl", side_effect=impl):
            pipeline.run_pipeline("first", run_id="run_first")
            other = self.root / "foreign"
            other.mkdir()
            with patch.object(pipeline, "resolve_repo_root", return_value=(other, "fixture")):
                pipeline.run_pipeline("second", run_id="run_second", retry_of="run_first")
        self.assertNotEqual(paths[0], paths[1])
        self.assertEqual((paths[0] / "HANDOFF.md").read_text(), "PREVIOUS HANDOFF")
        self.assertEqual(list(self.legacy.iterdir()), [])

    def test_context_restored_after_impl_and_setup_failure(self):
        outer = self.root / "outer"
        artifact_token = pipeline._artifact_directory.set(outer)
        project_token = pipeline._artifact_project.set(self.repo)
        self.addCleanup(pipeline._artifact_directory.reset, artifact_token)
        self.addCleanup(pipeline._artifact_project.reset, project_token)
        def impl(*args, **kwargs):
            self.assertNotEqual(pipeline.get_pipeline_dir(), outer)
            pipeline.write_pipeline_file("spec.md", "scoped")
            raise RuntimeError("fixture implementation failure")
        with patch.object(pipeline, "_run_pipeline_impl", side_effect=impl):
            with self.assertRaisesRegex(RuntimeError, "implementation failure"):
                pipeline.run_pipeline("task", run_id="run_failure")
        self.assertEqual(pipeline.get_pipeline_dir(), outer)
        self.assertEqual(pipeline._artifact_project.get(), self.repo)
        self.override.assert_called_with(None)
        self.discard.assert_called_once_with("run_failure", self.repo.resolve())
        with patch.object(Path, "write_text", side_effect=OSError("fixture metadata failure")):
            with self.assertRaisesRegex(OSError, "metadata failure"):
                pipeline.run_pipeline("task", run_id="run_setup_failure")
        self.assertEqual(pipeline.get_pipeline_dir(), outer)
        self.assertEqual(pipeline._artifact_project.get(), self.repo)
        self.override.assert_called_with(None)
        self.assertEqual(self.discard.call_count, 2)

    def test_duplicate_and_invalid_run_ids_do_not_overwrite_artifacts(self):
        with patch.object(pipeline, "_run_pipeline_impl", return_value="ok") as impl:
            pipeline.run_pipeline("task", run_id="run_unique")
            marker = self.root / ".bum/runs/run_unique/artifact_context.json"
            before = marker.read_bytes()
            with self.assertRaises(FileExistsError):
                pipeline.run_pipeline("task", run_id="run_unique")
            self.assertEqual(marker.read_bytes(), before)
            impl.assert_called_once()
            for invalid in ("../escape", "run/path", "run\\path", "run:ads"):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    pipeline.run_pipeline("task", run_id=invalid)


class ResumeRegressionTests(OfflineFixture):
    run_id = "run_20261018_000000_abcdef"

    def prepare_retry(self, source_project=None):
        self.run_dir = self.root / self.run_id
        self.run_dir.mkdir()
        self.stack.enter_context(patch.object(server, "get_run_dir", return_value=self.run_dir))
        self.stack.enter_context(patch.object(server, "get_run_events", return_value=[{
            "event": "pipeline_started", "run_id": self.run_id,
            "payload": {"task": "task @file:brief.md", "project_repo_path": str(source_project or self.repo), "isolated": True}},
            {"event": "pipeline_finished", "run_id": self.run_id, "payload": {"final_status": "FAILED"}}]))
        self.stack.enter_context(patch.object(server.execution_manager, "get_status", return_value={"running": False}))
        return self.stack.enter_context(patch.object(server.execution_manager, "start_pipeline", return_value={"accepted": True}))

    def test_retry_rejects_foreign_project_before_worker(self):
        start = self.prepare_retry(self.root / "foreign")
        with self.assertRaises(server.HTTPException) as raised:
            asyncio.run(server.retry_run(self.run_id))
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("project", raised.exception.detail.lower())
        start.assert_not_called()

    def test_retry_rejects_missing_project_provenance_before_worker(self):
        start = self.prepare_retry()
        events = [{"event": "pipeline_started", "run_id": self.run_id, "payload": {"task": "historical task"}},
                  {"event": "pipeline_finished", "run_id": self.run_id, "payload": {"final_status": "FAILED"}}]
        with patch.object(server, "get_run_events", return_value=events):
            with self.assertRaises(server.HTTPException) as raised:
                asyncio.run(server.retry_run(self.run_id))
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("new", raised.exception.detail.lower())
        start.assert_not_called()

    def test_same_project_retry_is_new_full_pipeline_with_lineage_only(self):
        start = self.prepare_retry()
        result = asyncio.run(server.retry_run(self.run_id))
        self.assertTrue(result["accepted"])
        start.assert_called_once_with(task="task @file:brief.md", retry_of=self.run_id)

    def test_legacy_resume_and_manual_resume_have_no_effects(self):
        start = self.prepare_retry()
        with self.assertRaises(server.HTTPException) as raised:
            asyncio.run(server.resume_run_endpoint(self.run_id))
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn(f"/api/runs/{self.run_id}/retry", raised.exception.detail)
        with patch.object(resume_test_review, "read_pipeline_file") as read, \
                patch.object(resume_test_review, "repo_tree") as tree:
            with self.assertRaisesRegex(RuntimeError, "retry"):
                resume_test_review.run_test_and_review()
        start.assert_not_called()
        read.assert_not_called()
        tree.assert_not_called()
        for effect in self.effects:
            effect.assert_not_called()

    def test_execution_manager_default_uses_public_isolated_wrapper(self):
        manager = executor.PipelineExecutionManager()
        with patch.object(pipeline, "run_pipeline", return_value="ok") as run, \
                patch.object(executor, "generate_run_id", return_value="run_manager"):
            result = manager.start_pipeline("  task  ", retry_of=self.run_id)
            manager._thread.join(timeout=2)
        self.assertFalse(manager._thread.is_alive())
        self.assertFalse(manager.get_status()["running"])
        self.assertEqual(result["run_id"], "run_manager")
        self.assertEqual(run.call_args.args, ("task",))
        self.assertEqual(run.call_args.kwargs["run_id"], "run_manager")
        self.assertEqual(run.call_args.kwargs["retry_of"], self.run_id)


class SourceRegressionTests(OfflineFixture):
    def test_all_five_roles_planner_retry_and_both_repairs_share_frozen_real_source(self):
        brief = self.repo / "brief.md"
        original = "CANONICAL ORIGINAL SOURCE: immutable ownership and acceptance"
        brief.write_text(original)
        calls = []
        planners = 0
        reviews = 0
        def agent(role, prompt):
            nonlocal planners, reviews
            calls.append((role, prompt))
            if role == "planner":
                planners += 1
                return "<tool_call>bad planner</tool_call>" if planners == 1 else "# Valid fixture spec"
            if role == "frontend":
                brief.write_text("MUTATED SOURCE MUST NEVER REPLACE ORIGINAL")
            if role == "reviewer":
                reviews += 1
                if reviews == 1:
                    return ("VERDICT: CHANGES REQUIRED\nFRONTEND_FIX_REQUIRED: YES\n"
                            "BACKEND_FIX_REQUIRED: YES\nDEPENDENCY_FIX_REQUIRED: NO")
                return "VERDICT: APPROVE\nREASON: Fixture only."
            return "No file operations."
        returns = {
            "EventLogger": SimpleNamespace(run_id="run_source"), "set_current_logger": None,
            "load_agents": {}, "run_preflight_check": {"repo_root": str(self.repo)},
            "capture_git_baseline": {}, "get_file_boundary_contents": "",
            "write_spec_contract": {"contract": {"file_boundaries": []}, "markdown": "fixture contract"},
            "parse_and_apply_agent_file_operations": {},
            "execute_test_and_git_commands": ([], [], {}), "get_untracked_files_content": "",
            "write_verification_evidence": {"summary": {"has_failures": False}},
            "create_micro_commit": {"created": False}, "clear_salvaged_work": None,
        }
        for name, result in returns.items():
            self.stack.enter_context(patch.object(pipeline, name, return_value=result))
        with patch.object(pipeline, "run_agent", side_effect=agent), \
                patch.object(pipeline, "run_safe_git_command", return_value={"returncode": 0, "stdout": "", "stderr": ""}), \
                patch.object(pipeline, "resolve_task_file_references", wraps=repo_tools.resolve_task_file_references) as resolve, \
                redirect_stdout(io.StringIO()):
            pipeline.run_pipeline("Implement @file:brief.md", run_id="run_source")
        resolve.assert_called_once_with("Implement @file:brief.md")
        self.assertEqual([role for role, _ in calls], ["planner", "planner", "frontend", "backend", "tester", "reviewer",
                                                        "frontend", "backend", "tester", "reviewer"])
        prefixes = []
        for role, prompt in calls:
            with self.subTest(role=role):
                self.assertIn(original, prompt)
                self.assertNotIn("MUTATED SOURCE", prompt)
                prefixes.append(prompt.split("=== END IMMUTABLE TASK SOURCE ===")[0])
        self.assertEqual(len(set(prefixes)), 1)
        directory = self.root / ".bum/runs/run_source/pipeline"
        self.assertIn(original, (directory / "resolved_task.md").read_text())
        started = next(c.kwargs["payload"] for c in pipeline.emit_event.call_args_list if c.kwargs.get("event") == "pipeline_started")
        self.assertEqual(started["artifact_dir"], str(directory.resolve()))
        self.assertEqual(started["project_repo_path"], str(self.repo.resolve()))
        self.assertTrue(started["isolated"])


if __name__ == "__main__":
    unittest.main()
