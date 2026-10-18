"""Offline regressions for the existing Tester's bounded write/verify phases."""
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator import pipeline


def manifest_for(roots=(), **verification):
    return SimpleNamespace(
        name="Fixture", project_type="python", rules=SimpleNamespace(
            test_write_roots=list(roots), allowed_write_roots=[], prohibited_files=[],
            forbidden_imports=[], required_packages=[], forbidden_tokens=[]),
        verification=SimpleNamespace(**{key: verification.get(key) for key in
            ("typecheck_cmd", "test_cmd", "lint_cmd", "build_cmd")}))


class TesterWriteTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.scratch = Path.home() / "AppData/Local/hermes/cache/scratch" if os.name == "nt" else None
        if self.scratch:
            self.scratch.mkdir(parents=True, exist_ok=True)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(dir=self.scratch)))
        self.manifest = manifest_for()
        for module in ("orchestrator.pipeline", "orchestrator.repo_tools"):
            self.stack.enter_context(patch(module + ".get_repo_root", return_value=self.root))
            self.stack.enter_context(patch(module + ".get_active_manifest", side_effect=lambda: self.manifest))
        self.stack.enter_context(patch("orchestrator.pipeline.emit_event"))

    def test_tester_writes_default_to_denied(self):
        with self.assertRaises(PermissionError):
            pipeline.parse_and_apply_agent_file_operations(
                "```write:tests/test_independent.py\nassert True\n```", "tester")
        self.assertFalse((self.root / "tests/test_independent.py").exists())

    def apply(self, path, content="assert True\n", contract=None, delete=False):
        output = f"```delete:{path}\n```" if delete else f"```write:{path}\n{content}```"
        return pipeline.parse_and_apply_agent_file_operations(
            output, "tester", contract=contract if contract is not None else {
                "file_boundaries": [path], "reference_files": []})

    def test_opted_in_create_update_delete_use_real_guarded_helpers(self):
        self.manifest = manifest_for(["tests/"])
        self.assertEqual(self.apply("tests/test_independent.py")["created"], ["tests/test_independent.py"])
        self.apply("tests/test_independent.py", "assert 1 == 1\n")
        self.assertEqual((self.root / "tests/test_independent.py").read_text(), "assert 1 == 1\n")
        self.assertEqual(self.apply("tests/test_independent.py", delete=True)["deleted"], ["tests/test_independent.py"])
        self.assertFalse((self.root / "tests/test_independent.py").exists())

    def test_no_contract_or_empty_contract_is_not_permission(self):
        self.manifest = manifest_for(["tests"])
        for contract in (None, {}, {"file_boundaries": []}):
            with self.subTest(contract=contract), self.assertRaises(PermissionError):
                pipeline.parse_and_apply_agent_file_operations(
                    "```write:tests/test_independent.py\nassert True\n```", "tester", contract=contract)

    def test_production_outside_root_and_outside_contract_are_denied(self):
        self.manifest = manifest_for(["tests"])
        for path in ("src/auth.py", "tests_extra/test_auth.py", "test_auth.py", "tests/test_other.py"):
            with self.subTest(path=path), self.assertRaises(PermissionError):
                self.apply(path, contract={"file_boundaries": ["tests/test_auth.py", "src/auth.py"]})
        self.assertEqual(list(self.root.iterdir()), [])

    def test_reference_only_is_denied_even_if_also_in_boundaries(self):
        self.manifest = manifest_for(["tests"])
        with self.assertRaises(PermissionError):
            self.apply("tests/test_reference.py", contract={
                "file_boundaries": ["tests/test_reference.py"], "reference_files": ["tests/test_reference.py"]})

    def test_unsafe_paths_and_roots_are_denied(self):
        self.manifest = manifest_for(["tests"])
        paths = ("tests/../src/auth.py", "tests/./test_a.py", "../test_a.py", "/tests/test_a.py",
                 "C:/tests/test_a.py", "C:tests/test_a.py", "tests\\..\\auth.py",
                 "tests/.env", "tests/.env.local", "tests/.git/config", "tests/.GIT/config",
                 "tests/.env/sub/test_a.py", "tests/test_a.py:stream", "tests/test_a.py.")
        for path in paths:
            for delete in (False, True):
                with self.subTest(path=path, delete=delete), self.assertRaises(PermissionError):
                    self.apply(path, delete=delete)
        for root in (".", "", "../tests", "/tests", "C:/tests", "tests/../src"):
            self.manifest = manifest_for([root])
            with self.subTest(root=root), self.assertRaises(PermissionError):
                self.apply("tests/test_a.py")

    def test_batch_is_validated_before_first_write(self):
        self.manifest = manifest_for(["tests"])
        with self.assertRaises(PermissionError):
            pipeline.parse_and_apply_agent_file_operations(
                "```write:tests/test_ok.py\nassert True\n```\n```write:src/auth.py\nunsafe\n```",
                "tester", contract={"file_boundaries": ["tests/test_ok.py", "src/auth.py"]})
        self.assertFalse((self.root / "tests/test_ok.py").exists())

    def test_existing_prohibited_file_and_allowed_root_guards_still_apply(self):
        self.manifest = manifest_for(["tests"])
        self.manifest.rules.prohibited_files = ["tests/test_locked.py"]
        with self.assertRaises(PermissionError):
            self.apply("tests/test_locked.py")
        self.manifest.rules.prohibited_files = []
        self.manifest.rules.allowed_write_roots = ["app"]
        with self.assertRaises(PermissionError):
            self.apply("tests/test_blocked.py")

    def test_link_escape_is_denied_without_writing_outside(self):
        self.manifest = manifest_for(["tests"])
        outside = Path(self.stack.enter_context(tempfile.TemporaryDirectory(dir=self.scratch)))
        (self.root / "tests").mkdir()
        link = self.root / "tests/link"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            if os.name != "nt":
                self.skipTest(f"Symlinks unavailable: {exc}")
            # Junctions need no elevated symlink privilege and exercise real escapes on Windows.
            result = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(link), str(outside)],
                                    capture_output=True, text=True, shell=False)
            if result.returncode:
                self.skipTest(f"Symlinks and junctions unavailable: {result.stderr}")
        for delete in (False, True):
            with self.subTest(delete=delete), self.assertRaises(PermissionError):
                self.apply("tests/link/test_escape.py", delete=delete)
        self.assertFalse((outside / "test_escape.py").exists())

    def test_hardlink_to_production_is_denied(self):
        self.manifest = manifest_for(["tests"])
        (self.root / "tests").mkdir()
        (self.root / "src").mkdir()
        production = self.root / "src/auth.py"
        production.write_text("PRODUCTION_UNCHANGED\n")
        try:
            (self.root / "tests/test_alias.py").hardlink_to(production)
        except OSError as exc:
            self.skipTest(f"Hardlinks unavailable: {exc}")
        with self.assertRaises(PermissionError):
            self.apply("tests/test_alias.py", "PRODUCTION_OVERWRITTEN\n")
        self.assertEqual(production.read_text(), "PRODUCTION_UNCHANGED\n")

    def test_non_tester_parser_behavior_remains_unchanged(self):
        result = pipeline.parse_and_apply_agent_file_operations("```write:app/main.py\npass\n```", "frontend")
        self.assertEqual(result["created"], ["app/main.py"])

    def command_fixture(self):
        self.stack.enter_context(patch("orchestrator.pipeline.run_safe_git_command", return_value={
            "command": "git status --short", "returncode": 0, "stdout": "", "stderr": ""}))
        self.stack.enter_context(patch("orchestrator.pipeline.get_untracked_files_content", return_value=""))
        self.stack.enter_context(patch("orchestrator.pipeline.compute_run_git_attribution", return_value={}))

    def test_verification_runs_all_four_unique_manifest_commands(self):
        self.manifest = manifest_for(typecheck_cmd="npm run ts:check", test_cmd="npm test",
                                     lint_cmd="npm run lint", build_cmd="npm run build")
        self.command_fixture()
        with patch("orchestrator.pipeline.run_safe_command", side_effect=lambda cmd: {
                "command": " ".join(cmd), "returncode": 0, "stdout": "", "stderr": ""}) as run:
            results, _, _ = pipeline.execute_test_and_git_commands()
        self.assertEqual([call.args[0] for call in run.call_args_list], [
            ["npm", "run", "ts:check"], ["npm", "test"], ["npm", "run", "lint"], ["npm", "run", "build"]])
        self.assertEqual(len(results), 4)

    def test_verification_deduplicates_argv_not_just_raw_strings(self):
        self.manifest = manifest_for(typecheck_cmd="npm test", test_cmd="npm   test",
                                     lint_cmd="npm test", build_cmd="npm test")
        self.command_fixture()
        with patch("orchestrator.pipeline.run_safe_command", return_value={
                "command": "npm test", "returncode": 0, "stdout": "", "stderr": ""}) as run:
            results, _, _ = pipeline.execute_test_and_git_commands()
        self.assertEqual(run.call_count, 1)
        self.assertEqual(len(results), 1)

    def test_lint_failure_does_not_skip_build_and_is_in_evidence(self):
        self.manifest = manifest_for(lint_cmd="npm run lint", build_cmd="npm run build")
        self.command_fixture()
        def run(cmd):
            if cmd[-1] == "lint":
                raise PermissionError("not allowed")
            return {"command": " ".join(cmd), "returncode": 0, "stdout": "", "stderr": ""}
        with patch("orchestrator.pipeline.run_safe_command", side_effect=run):
            results, _, _ = pipeline.execute_test_and_git_commands()
        self.assertEqual([r["returncode"] for r in results], [-1, 0])
        from orchestrator.evidence_tools import write_verification_evidence
        evidence = write_verification_evidence(results, repo_root=self.root)
        self.assertTrue(evidence["summary"]["has_failures"])

    def pipeline_fixture(self, *, enabled=True, failing=False, lint_failure=False, build_failure=False, author_response=None):
        from orchestrator.command_tools import run_safe_command
        self.manifest = manifest_for(["tests"] if enabled else [],
            typecheck_cmd="python -m compileall -q tests",
            test_cmd="python -m unittest discover -s tests",
            lint_cmd="python -m unittest discover -s tests -v",
            build_cmd="python -m compileall -q -f tests")
        (self.root / "tests").mkdir()
        (self.root / "pipeline").mkdir()
        (self.root / "tests/test_baseline.py").write_text(
            "import unittest\nclass Baseline(unittest.TestCase):\n    def test_green(self): pass\n")
        spec = ("# Task\n## FILES TO MODIFY\n- tests/test_independent.py\n\n"
                "## ACCEPTANCE CRITERIA\n- Independent assertion succeeds.\n\nBACKEND TASK: None.\n")
        assertion = "self.assertEqual(1, 2)" if failing else "self.assertEqual(1, 1)"
        authored = ("```write:tests/test_independent.py\nimport unittest\n"
                    "class IndependentTest(unittest.TestCase):\n"
                    f"    def test_independent(self):\n        {assertion}\n```\n")
        assessment = ("STATUS: PASS\nFINDINGS: Looks fine.\nBLOCKERS: None.\n"
                      "```write:tests/test_narration.py\nraise AssertionError('do not apply')\n```\n"
                      "```delete:tests/test_independent.py\n```\n")
        calls = []
        def agent(role, prompt):
            calls.append((role, prompt))
            if role == "planner":
                return spec
            if role in ("frontend", "backend"):
                return "No implementation changes needed."
            if role == "tester" and "PHASE: AUTHOR_TESTS" in prompt:
                return authored if author_response is None else author_response
            if role == "tester":
                return assessment
            if role == "reviewer":
                return "VERDICT: APPROVE\nREASON: Looks fine."
            raise AssertionError(f"Unexpected agent {role}")
        commands = []
        def command(cmd):
            commands.append((cmd, (self.root / "tests/test_independent.py").exists()))
            if lint_failure and cmd[-1] == "-v":
                return {"command": " ".join(cmd), "returncode": 9, "stdout": "", "stderr": "lint failed"}
            if build_failure and "-f" in cmd:
                return {"command": " ".join(cmd), "returncode": 7, "stdout": "", "stderr": "build failed"}
            return run_safe_command(cmd)
        self.command_fixture()
        mocks = {
            "EventLogger": SimpleNamespace(run_id="offline-tester"),
            "set_current_logger": None, "load_agents": {},
            "run_preflight_check": {"repo_root": str(self.root)},
            "capture_git_baseline": {}, "get_shared_context": "context",
            "repo_tree": "tests/", "create_micro_commit": {"created": False},
            "clear_salvaged_work": None, "salvage_unapproved_work": None,
        }
        for name, result in mocks.items():
            self.stack.enter_context(patch("orchestrator.pipeline." + name, return_value=result))
        self.stack.enter_context(patch("orchestrator.pipeline.PIPELINE_DIR", self.root / "pipeline"))
        self.stack.enter_context(patch("orchestrator.pipeline.MAX_REVIEW_CYCLES", 1))
        self.stack.enter_context(patch("orchestrator.pipeline.resolve_task_file_references", side_effect=lambda t: t))
        self.stack.enter_context(patch("orchestrator.pipeline.run_agent", side_effect=agent))
        self.stack.enter_context(patch("orchestrator.pipeline.run_safe_command", side_effect=command))
        for module in ("orchestrator.contract_tools", "orchestrator.evidence_tools", "orchestrator.command_tools"):
            self.stack.enter_context(patch(module + ".get_repo_root", return_value=self.root))
        self.stack.enter_context(patch("orchestrator.command_tools.get_active_manifest", side_effect=lambda: self.manifest))
        return calls, commands

    def run_offline_pipeline(self):
        from contextlib import redirect_stdout
        with redirect_stdout(io.StringIO()):
            pipeline._run_pipeline_impl("Independent fixture verification", run_id="offline-tester")
        return json.loads((self.root / ".evidence/tester_verification.json").read_text())

    def final_status(self):
        return [call.kwargs["payload"]["final_status"] for call in pipeline.emit_event.call_args_list
                if call.kwargs.get("event") == "pipeline_finished"][-1]

    def test_existing_tester_authors_then_real_checks_then_same_tester_and_reviewer(self):
        calls, commands = self.pipeline_fixture()
        evidence = self.run_offline_pipeline()
        self.assertEqual([role for role, _ in calls], ["planner", "frontend", "backend", "tester", "tester", "reviewer"])
        self.assertEqual([exists for _, exists in commands], [False, False, True, True, True, True])
        self.assertTrue(evidence["all_passed"])
        self.assertEqual(len(evidence["commands"]), 4)
        self.assertIn("Ran 2 tests", calls[-2][1])
        self.assertIn("tests/test_independent.py", calls[-1][1])
        self.assertFalse((self.root / "tests/test_narration.py").exists())
        self.assertTrue((self.root / "tests/test_independent.py").exists())
        self.assertEqual(self.final_status(), "AWAITING_HUMAN_APPROVAL")

    def test_failing_independent_fixture_cannot_be_approved_by_llm_pass(self):
        calls, _ = self.pipeline_fixture(failing=True)
        evidence = self.run_offline_pipeline()
        self.assertTrue(evidence["has_failures"])
        self.assertIn("FAILED (failures=1)", calls[-2][1])
        self.assertEqual(self.final_status(), "BLOCKED")
        self.assertFalse(any(c.kwargs.get("event") == "human_approval_required"
                             for c in pipeline.emit_event.call_args_list))

    def test_lint_failure_cannot_be_approved_by_llm_pass(self):
        self.pipeline_fixture(lint_failure=True)
        evidence = self.run_offline_pipeline()
        self.assertTrue(evidence["has_failures"])
        self.assertEqual(evidence["commands"][2]["returncode"], 9)
        self.assertTrue(evidence["commands"][3]["passed"])
        self.assertEqual(self.final_status(), "BLOCKED")

    def test_build_failure_cannot_be_approved_by_llm_pass(self):
        self.pipeline_fixture(build_failure=True)
        evidence = self.run_offline_pipeline()
        self.assertTrue(evidence["has_failures"])
        self.assertEqual(evidence["commands"][3]["returncode"], 7)
        self.assertEqual(self.final_status(), "BLOCKED")

    def test_legacy_manifest_has_one_read_only_tester_call(self):
        calls, _ = self.pipeline_fixture(enabled=False)
        self.run_offline_pipeline()
        self.assertEqual([role for role, _ in calls].count("tester"), 1)
        self.assertFalse((self.root / "tests/test_narration.py").exists())
        self.assertFalse((self.root / "tests/test_independent.py").exists())
        self.assertEqual(self.final_status(), "AWAITING_HUMAN_APPROVAL")

    def test_out_of_contract_author_response_aborts_before_post_builder_commands(self):
        _, commands = self.pipeline_fixture(author_response="```write:tests/test_unplanned.py\nassert True\n```")
        with self.assertRaises(PermissionError):
            self.run_offline_pipeline()
        self.assertEqual(len(commands), 2)  # baseline only
        self.assertFalse((self.root / "tests/test_unplanned.py").exists())


if __name__ == "__main__":
    unittest.main()
