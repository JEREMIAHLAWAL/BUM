"""Offline safety contracts for legacy, manually invoked capability scripts.

Do not import the real provider stack here: its initialization can load local
credentials. Dependency sentinels let us exercise the real script imports while
making every provider, repository, command and write operation fail closed.
"""
import ast
import builtins
from contextlib import ExitStack, redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


SCRIPT_DIR = Path(__file__).resolve().parent
LEGACY_SCRIPTS = (
    "test_backend_context", "test_frontend_context", "test_reviewer_context",
    "test_reviewer_git", "test_tester_context", "test_tester_execution",
    "test_dependency_tools", "test_parser_protocol", "test_planner_perf",
    "test_review_retry_loop", "test_write_capability", "test_write_protocol",
)
DEPENDENCY_EXPORTS = {
    "run": ("run_agent",),
    "providers": ("call_provider", "call_openrouter", "call_anthropic"),
    "repo_tools": ("repo_tree", "read_file", "write_file", "delete_file",
                   "file_exists", "get_repo_root"),
    "command_tools": ("run_safe_command",),
    "git_tools": ("run_safe_git_command", "get_repo_root"),
    "pipeline": ("parse_and_apply_agent_file_operations", "parse_reviewer_verdict"),
    "dependency_tools": ("build_dependency_command", "validate_package_name",
                         "parse_dependency_request", "execute_controlled_dependency_action"),
}


def load_script(name):
    spec = importlib.util.spec_from_file_location(
        "_legacy_import_safety_" + name, SCRIPT_DIR / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LegacyImportSafetyTests(unittest.TestCase):
    def test_legacy_imports_have_no_provider_command_git_or_file_side_effects(self):
        for name in LEGACY_SCRIPTS:
            with self.subTest(script=name):
                forbidden = Mock(side_effect=AssertionError("Import-time side effect"))
                dependencies = {}
                for short_name, exports in DEPENDENCY_EXPORTS.items():
                    module = ModuleType("orchestrator." + short_name)
                    for export in exports:
                        setattr(module, export, forbidden)
                    dependencies[module.__name__] = module
                dependencies["orchestrator.pipeline"].MalformedWriteError = type(
                    "MalformedWriteError", (Exception,), {})
                dependencies["orchestrator.pipeline"].MAX_REVIEW_CYCLES = 3
                dependencies["orchestrator.dependency_tools"].DependencyActionError = type(
                    "DependencyActionError", (Exception,), {})
                dependencies["orchestrator.dependency_tools"].ALLOWED_EXPO_PACKAGES = set()
                output = io.StringIO()
                with ExitStack() as stack:
                    stack.enter_context(patch.dict(sys.modules, dependencies))
                    stack.enter_context(patch.object(sys, "dont_write_bytecode", True))
                    stack.enter_context(patch.object(sys, "path", list(sys.path)))
                    for target, attribute in (
                        (builtins, "open"), (io, "open"),
                        (subprocess, "run"), (subprocess, "Popen"),
                        (os, "system"), (os, "mkdir"), (os, "remove"),
                        (os, "unlink"), (os, "rename"), (os, "replace"),
                        (Path, "read_text"), (Path, "read_bytes"),
                        (Path, "write_text"), (Path, "write_bytes"),
                        (Path, "mkdir"), (Path, "unlink"), (Path, "touch"),
                    ):
                        stack.enter_context(patch.object(target, attribute, forbidden))
                    stack.enter_context(redirect_stdout(output))
                    load_script(name)
                forbidden.assert_not_called()
                self.assertEqual(output.getvalue(), "", "Import must not run a smoke test")

    def test_legacy_scripts_have_explicit_manual_entrypoints(self):
        for name in LEGACY_SCRIPTS:
            with self.subTest(script=name):
                tree = ast.parse((SCRIPT_DIR / (name + ".py")).read_text(encoding="utf-8"))
                guards = [node for node in tree.body if isinstance(node, ast.If)
                          and ast.dump(node.test) == ast.dump(ast.parse(
                              "__name__ == '__main__'", mode="eval").body)]
                self.assertEqual(len(guards), 1)
                self.assertTrue(any(isinstance(node, ast.FunctionDef) and node.name == "main"
                                    for node in tree.body))
                self.assertEqual(ast.unparse(guards[0].body[0]), "main()")

    def test_reviewer_git_policy_probe_never_reaches_repository_or_subprocess(self):
        # Load the real allowlist implementation with repository resolution disabled.
        # Never execute any git command, not even against a temporary checkout.
        forbidden = Mock(side_effect=AssertionError("Must not reach repository or git"))
        repo = ModuleType("orchestrator.repo_tools")
        repo.get_repo_root = forbidden
        run = ModuleType("orchestrator.run")
        run.run_agent = forbidden
        spec = importlib.util.spec_from_file_location(
            "_legacy_git_policy", SCRIPT_DIR / "git_tools.py")
        git = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"orchestrator.repo_tools": repo,
                                      "orchestrator.run": run}), \
             patch.object(sys, "dont_write_bytecode", True), \
             patch.object(subprocess, "run", forbidden):
            spec.loader.exec_module(git)
            with patch.dict(sys.modules, {"orchestrator.git_tools": git}):
                script = load_script("test_reviewer_git")
                with redirect_stdout(io.StringIO()):
                    script.verify_forbidden_git_command()
                # If a future edit allows the probe, fail closed before resolving
                # any default checkout (the manual test must remain harmless).
                with patch.object(git, "ALLOWED_GIT_COMMANDS",
                                  git.ALLOWED_GIT_COMMANDS | {("git", "push", "--dry-run")}):
                    with self.assertRaisesRegex(AssertionError, "repository resolution"):
                        script.verify_forbidden_git_command()
        forbidden.assert_not_called()


if __name__ == "__main__":
    unittest.main()
