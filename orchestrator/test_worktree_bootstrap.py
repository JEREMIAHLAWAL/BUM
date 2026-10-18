"""Bounded bootstrap contracts; subprocesses are mocked, never network installs."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError
from orchestrator.manifest import BumManifest, generate_default_manifest, load_manifest
from orchestrator import worktree_tools as wt


class ManifestBootstrapTests(unittest.TestCase):
    def test_engine_comparators_handle_partial_versions_without_wrong_acceptance(self):
        for requirement in (">=24 <25", "24", "=24", "<=24", ">23", ">=24.2 <25"):
            with self.subTest(requirement=requirement):
                wt._check_node_engine("v24.22.0", requirement)
        for requirement in (">24", ">24.22", "<24", ">=25", "^24", ">=24 || <20"):
            with self.subTest(requirement=requirement), self.assertRaises(ValueError):
                wt._check_node_engine("v24.22.0", requirement)

    def test_pinned_pnpm_scripts_inference_never_enables_install(self):
        with tempfile.TemporaryDirectory(prefix="bum_inference_") as temp:
            root = Path(temp)
            (root / "package.json").write_text(json.dumps({
                "packageManager": "pnpm@10.9.0", "scripts": {"typecheck": "pnpm -r typecheck", "test": "node --test", "lint": "eslint ."}
            }), encoding="utf-8")
            manifest = generate_default_manifest(root)
            self.assertEqual(manifest.verification.typecheck_cmd, "pnpm run typecheck")
            self.assertEqual(manifest.verification.test_cmd, "pnpm test")
            self.assertEqual(manifest.verification.lint_cmd, "pnpm run lint")
            self.assertIsNone(manifest.worktree.bootstrap)

    def test_bootstrap_is_explicit_and_not_an_arbitrary_command(self):
        default = BumManifest(name="legacy")
        self.assertIsNone(default.worktree.bootstrap)
        self.assertEqual(default.rules.test_write_roots, [])
        configured = BumManifest.model_validate({
            "name": "workspace", "worktree": {"bootstrap": "pnpm-frozen"},
            "rules": {"test_write_roots": ["apps/web/tests/"]},
        })
        self.assertEqual(configured.worktree.bootstrap, "pnpm-frozen")
        self.assertEqual(configured.rules.test_write_roots, ["apps/web/tests/"])
        for config in ({"bootstrap": "pnpm install; touch bad"},
                       {"bootstrap": "pnpm-frozen", "command": "echo bad"}):
            with self.subTest(config=config), self.assertRaises(ValidationError):
                BumManifest.model_validate({"name": "workspace", "worktree": config})


class WorktreeBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bum_bootstrap_")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo & literal; $(noop)"
        self.repo.mkdir()
        self.real_run = subprocess.run
        for args in (["init", "-b", "main"], ["config", "user.email", "tests@example.invalid"],
                     ["config", "user.name", "Bootstrap Tests"]):
            self.git(*args)
        self.package = {"name": "fixture", "packageManager": "pnpm@10.9.0",
                        "engines": {"node": ">=24 <25"}, "scripts": {"typecheck": "pnpm -r typecheck"},
                        "devDependencies": {"typescript": "6.0.0"}}
        self.write_package()
        (self.repo / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
        (self.repo / "pnpm-workspace.yaml").write_text("packages:\n  - apps/*\n  - packages/*\n", encoding="utf-8")
        for relative in ("apps/web", "packages/shared"):
            folder = self.repo / relative
            folder.mkdir(parents=True)
            (folder / "package.json").write_text(json.dumps({"name": relative.replace("/", "-"), "devDependencies": {"typescript": "6.0.0"}}), encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "fixture")
        self.config = {"name": "untracked active config", "worktree": {"bootstrap": "pnpm-frozen"},
                       "rules": {"test_write_roots": ["apps/web/tests/"]}}
        self.write_config()
        (self.repo / "node_modules").mkdir()
        (self.repo / "node_modules" / "canonical-marker").write_text("unchanged", encoding="utf-8")
        (self.repo / ".env").write_text("DUMMY_TEST_VALUE=not-a-secret", encoding="utf-8")
        self.calls = []
        self.versions = {"node": "v24.3.0\n", "pnpm": "10.9.0\n"}
        self.install_error = None
        self.root_patch = patch.object(wt, "worktree_root_dir", return_value=self.base / "worktrees")
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.addCleanup(lambda: wt.discard_run_worktree("run_bootstrap", self.repo))

    def git(self, *args):
        return self.real_run(["git", *args], cwd=self.repo, capture_output=True, text=True, check=True)

    def write_package(self):
        (self.repo / "package.json").write_text(json.dumps(self.package), encoding="utf-8")

    def write_config(self):
        (self.repo / "bum.config.json").write_text(json.dumps(self.config), encoding="utf-8")

    def fake_run(self, args, **kwargs):
        if args[0] == "git":
            return self.real_run(args, **kwargs)
        self.calls.append((args, kwargs))
        tool = Path(args[0]).stem
        if args[1:] == ["--version"]:
            return subprocess.CompletedProcess(args, 0, self.versions[tool], "")
        self.assertEqual(args[1:], ["install", "--frozen-lockfile"])
        self.assertEqual(tool, "pnpm")
        self.assertFalse(kwargs["shell"])
        self.assertEqual(kwargs["env"]["npm_config_engine_strict"], "true")
        self.assertEqual(kwargs["env"]["npm_config_ignore_scripts"], "true")
        self.assertEqual(kwargs["env"]["COREPACK_ENABLE_NETWORK"], "0")
        self.assertEqual(kwargs["env"]["npm_config_manage_package_manager_versions"], "false")
        self.assertEqual(kwargs["env"]["pnpm_config_pm_on_fail"], "ignore")
        folder = Path(kwargs["cwd"])
        self.assertTrue(Path(kwargs["env"]["npm_config_store_dir"]).is_relative_to(folder / "node_modules"))
        self.assertEqual(kwargs["env"]["npm_config_global"], "false")
        self.assertFalse((folder / "node_modules").exists(), "must not install through canonical junction")
        for relative in ("node_modules", "apps/web/node_modules", "packages/shared/node_modules"):
            (folder / relative).mkdir(parents=True)
        if self.install_error:
            return subprocess.CompletedProcess(args, 1, "", self.install_error)
        return subprocess.CompletedProcess(args, 0, "installed fixture workspace", "")

    def create(self):
        with patch.object(wt.shutil, "which", side_effect=lambda name: "C:/tools/" + name + ".exe"), \
             patch.object(wt.subprocess, "run", side_effect=self.fake_run):
            return wt.create_run_worktree("run_bootstrap", self.repo)

    @unittest.skipUnless(wt.sys.platform == "win32", "Windows long paths and junctions")
    def test_long_path_fallback_removes_only_run_and_unlinks_junction(self):
        result = self.create()
        self.assertTrue(result["success"], result)
        root = result["worktree_path"]
        deep = root / "node_modules" / ("nested_dependency_" * 8) / ("nested_dependency_" * 8)
        extended = "\\\\?\\" + str(deep)
        Path(extended).mkdir(parents=True)
        (Path(extended) / "fixture.txt").write_text("long path", encoding="utf-8")
        junction = root / "shared_modules"
        self.real_run(["cmd", "/c", "mklink", "/J", str(junction), str(self.repo / "node_modules")],
                      capture_output=True, text=True, check=True)
        sibling = self.base / "worktrees" / "run_unrelated"
        sibling.mkdir()
        (sibling / "marker").write_text("preserve", encoding="utf-8")
        original_git = wt._run_git
        original_rmtree = shutil.rmtree
        def fail_git_remove(args, **kwargs):
            if "remove" in args and root.exists():
                return {"returncode": 1, "stderr": "Filename too long"}
            return original_git(args, **kwargs)
        def require_extended(path, *args, **kwargs):
            if not str(path).startswith("\\\\?\\"):
                if kwargs.get("ignore_errors"):
                    return
                raise OSError("Filename too long")
            return original_rmtree(path, *args, **kwargs)
        try:
            with patch.object(wt, "_run_git", side_effect=fail_git_remove), \
                 patch.object(wt.shutil, "rmtree", side_effect=require_extended):
                cleanup = wt.discard_run_worktree("run_bootstrap", self.repo)
            self.assertTrue(cleanup["worktree_removed"], cleanup)
            self.assertFalse(root.exists())
            self.assertEqual((self.repo / "node_modules" / "canonical-marker").read_text(), "unchanged")
            self.assertEqual((sibling / "marker").read_text(), "preserve")
        finally:
            if root.exists():
                original_rmtree("\\\\?\\" + str(root))

    def test_registration_remove_failure_preserves_branch_even_after_files_removed(self):
        result = self.create()
        self.assertTrue(result["success"], result)
        original_git = wt._run_git
        def fail_remove(args, **kwargs):
            if "remove" in args:
                return {"returncode": 1, "stderr": "fixture unregister failed"}
            return original_git(args, **kwargs)
        with patch.object(wt, "_run_git", side_effect=fail_remove):
            cleanup = wt.discard_run_worktree("run_bootstrap", self.repo)
        self.assertFalse(result["worktree_path"].exists())
        self.assertFalse(cleanup["worktree_removed"], cleanup)
        self.assertFalse(cleanup["branch_deleted"], cleanup)
        self.assertIn("bum-run/run_bootstrap", self.git("worktree", "list", "--porcelain").stdout)

    def test_retry_creation_reports_existing_cleanup_failure(self):
        root = self.base / "worktrees" / "run_bootstrap"
        root.mkdir(parents=True)
        with patch.object(wt.shutil, "rmtree", side_effect=PermissionError("fixture locked")):
            result = self.create()
        self.assertFalse(result["success"], result)
        self.assertIn("cleanup incomplete", result["error"])
        self.assertFalse(result["cleanup"]["worktree_removed"])
        self.assertTrue(root.exists())
        self.assertEqual(self.calls, [])

    def test_add_failure_uses_bounded_cleanup_and_reports_result(self):
        original_git = wt._run_git
        def fail_add(args, **kwargs):
            if args[:2] == ["worktree", "add"]:
                return {"returncode": 1, "stderr": "fixture add failed"}
            return original_git(args, **kwargs)
        with patch.object(wt, "_run_git", side_effect=fail_add):
            result = self.create()
        self.assertFalse(result["success"], result)
        self.assertIn("fixture add failed", result["error"])
        self.assertTrue(result["cleanup"]["worktree_removed"])
        self.assertTrue(result["cleanup"]["branch_deleted"])

    def test_cleanup_failure_keeps_branch_and_registration_with_error(self):
        result = self.create()
        self.assertTrue(result["success"], result)
        with patch.object(wt.shutil, "rmtree", side_effect=PermissionError("fixture locked")):
            cleanup = wt.discard_run_worktree("run_bootstrap", self.repo)
        self.assertFalse(cleanup["worktree_removed"], cleanup)
        self.assertFalse(cleanup["branch_deleted"], cleanup)
        self.assertIn("fixture locked", cleanup["details"]["filesystem_error"])
        self.assertTrue(result["worktree_path"].exists())
        self.assertIn("bum-run/run_bootstrap", self.git("worktree", "list", "--porcelain").stdout)
        self.assertEqual(self.git("rev-parse", "--verify", wt.branch_name("run_bootstrap")).returncode, 0)

    def test_missing_run_is_idempotent_and_does_not_prune_other_registration(self):
        other = self.base / "worktrees" / "run_unrelated"
        self.git("worktree", "add", "-b", "other-fixture", str(other), "HEAD")
        shutil.rmtree(other)
        for _ in range(2):
            cleanup = wt.discard_run_worktree("run_bootstrap", self.repo)
            self.assertTrue(cleanup["worktree_removed"], cleanup)
            self.assertTrue(cleanup["branch_deleted"], cleanup)
            self.assertIn("other-fixture", self.git("worktree", "list", "--porcelain").stdout)
        self.git("worktree", "remove", "--force", str(other))

    def test_registration_read_failure_refuses_filesystem_and_branch_cleanup(self):
        result = self.create()
        self.assertTrue(result["success"], result)
        with patch.object(wt, "_run_git", return_value={"returncode": 1, "stderr": "fixture read failure"}):
            cleanup = wt.discard_run_worktree("run_bootstrap", self.repo)
        self.assertFalse(cleanup["worktree_removed"], cleanup)
        self.assertIn("fixture read failure", cleanup["error"])
        self.assertTrue(result["worktree_path"].exists())

    @unittest.skipUnless(wt.sys.platform == "win32", "Windows junctions")
    def test_cleanup_refuses_redirected_run_root_before_git_or_deletion(self):
        managed = self.base / "worktrees"
        managed.mkdir()
        target = managed / "run_bootstrap"
        self.real_run(["cmd", "/c", "mklink", "/J", str(target), str(self.repo)],
                      capture_output=True, text=True, check=True)
        try:
            with patch.object(wt, "_run_git") as git:
                cleanup = wt.discard_run_worktree("run_bootstrap", self.repo)
            self.assertFalse(cleanup["worktree_removed"], cleanup)
            self.assertIn("junction", cleanup["error"])
            git.assert_not_called()
            self.assertEqual((target / "node_modules" / "canonical-marker").read_text(), "unchanged")
        finally:
            target.rmdir()  # unlink only the fixture junction, never its target

    def test_opt_in_bootstraps_complete_isolated_workspace_and_snapshots_manifest(self):
        result = self.create()
        self.assertTrue(result["success"], result)
        self.assertEqual(len(self.calls), 3)
        worktree = result["worktree_path"]
        for relative in ("node_modules", "apps/web/node_modules", "packages/shared/node_modules"):
            self.assertTrue((worktree / relative).is_dir())
            self.assertFalse((worktree / relative).is_symlink())
        self.assertFalse((worktree / ".env").exists())
        self.assertFalse((worktree / "bum.config.json").exists(), "config snapshot must not become agent-editable canonical docs")
        active = load_manifest(worktree)
        self.assertEqual(active.name, self.config["name"])
        self.assertEqual(active.worktree.bootstrap, "pnpm-frozen")
        self.assertEqual(active.rules.test_write_roots, ["apps/web/tests/"])
        self.assertEqual(json.loads((self.repo / "bum.config.json").read_text()), self.config)
        self.assertEqual((self.repo / "node_modules" / "canonical-marker").read_text(), "unchanged")

    def assert_clean_failure(self, result, message):
        self.assertFalse(result["success"], result)
        self.assertIn(message, result["error"])
        self.assertFalse((self.base / "worktrees" / "run_bootstrap").exists())
        self.assertEqual(self.git("branch", "--list", wt.branch_name("run_bootstrap")).stdout.strip(), "")
        self.assertEqual((self.repo / "node_modules" / "canonical-marker").read_text(), "unchanged")

    def test_wrong_pnpm_pin_fails_before_install_and_cleans_up(self):
        self.versions["pnpm"] = "11.0.0\n"
        self.assert_clean_failure(self.create(), "pnpm version mismatch")
        self.assertEqual(len(self.calls), 2)

    def test_bootstrap_timeout_is_bounded_and_cleans_up(self):
        bootstrap_run = self.fake_run
        def timeout(args, **kwargs):
            if args[1:] == ["install", "--frozen-lockfile"]:
                raise subprocess.TimeoutExpired(args, 300, stderr=b"x" * 20000 + b"timeout-tail")
            return bootstrap_run(args, **kwargs)
        with patch.object(self, "fake_run", side_effect=timeout):
            result = self.create()
        self.assert_clean_failure(result, "timed out after 300s")
        self.assertIn("timeout-tail", result["error"])
        self.assertLess(len(result["error"]), 2600)

    def test_unknown_bootstrap_command_fails_before_any_git_changes(self):
        self.config["worktree"] = {"bootstrap": "pnpm-frozen", "command": "pnpm install --no-frozen-lockfile"}
        self.write_config()
        self.assert_clean_failure(self.create(), "Invalid explicit worktree manifest")
        self.assertEqual(self.calls, [])

    def test_snapshot_overrides_stale_tracked_config_and_corruption_fails_closed(self):
        self.git("add", "bum.config.json")
        self.git("commit", "-m", "tracked config fixture")
        self.config["name"] = "updated uncommitted policy"
        self.write_config()
        result = self.create()
        self.assertTrue(result["success"], result)
        root = result["worktree_path"]
        self.assertNotEqual(json.loads((root / "bum.config.json").read_text())["name"], self.config["name"])
        self.assertEqual(load_manifest(root).name, self.config["name"])
        from orchestrator.manifest import worktree_manifest_snapshot
        worktree_manifest_snapshot(root).write_text("invalid snapshot", encoding="utf-8")
        with self.assertRaises(ValidationError):
            load_manifest(root)

    def test_wrong_node_engine_fails_before_pnpm_and_cleans_up(self):
        self.versions["node"] = "v22.15.0\n"
        self.assert_clean_failure(self.create(), "does not satisfy engines.node")
        self.assertEqual(len(self.calls), 1)

    def test_install_failure_returns_bounded_output_and_cleans_up(self):
        self.install_error = "x" * 20000 + "FROZEN_LOCKFILE_FAILURE"
        result = self.create()
        self.assert_clean_failure(result, "FROZEN_LOCKFILE_FAILURE")
        self.assertLess(len(result["error"]), 2600)

    def test_failed_cleanup_is_reported_not_hidden(self):
        self.versions["node"] = "v22.15.0\n"
        with patch.object(wt, "_teardown_worktree", return_value={"worktree_removed": False, "branch_deleted": False}):
            result = self.create()
        self.assertFalse(result["success"])
        self.assertIn("Cleanup incomplete", result["error"])
        self.assertFalse(result["cleanup"]["worktree_removed"])

    def test_missing_workspace_dependencies_fail_closed(self):
        bootstrap_run = self.fake_run
        def partial(args, **kwargs):
            result = bootstrap_run(args, **kwargs)
            if args[1:] == ["install", "--frozen-lockfile"]:
                shutil.rmtree(Path(kwargs["cwd"]) / "packages/shared/node_modules")
            return result
        with patch.object(self, "fake_run", side_effect=partial):
            self.assert_clean_failure(self.create(), "missing workspace dependencies")

    def test_shared_nested_node_modules_junction_is_rejected_before_install(self):
        bootstrap = wt._bootstrap_pnpm
        def inject(root):
            target = root / "apps/web/node_modules"
            target.mkdir()
            with patch.object(Path, "is_junction", new=lambda p: p == target, create=True):
                bootstrap(root)
        with patch.object(wt, "_bootstrap_pnpm", side_effect=inject):
            self.assert_clean_failure(self.create(), "refuses shared/symlink directory")
        self.assertEqual(self.calls, [])

    def test_dangling_node_modules_link_is_rejected(self):
        root = self.base / "isolated"
        root.mkdir()
        with patch.object(wt.os, "walk", return_value=[(str(root), [], ["node_modules"])]), \
             patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaisesRegex(ValueError, "shared/symlink"):
                wt._isolated_directories(root)

    def test_run_id_cannot_have_shell_metacharacters_or_trailing_newline(self):
        for run_id in ("run_ok\n", "run_ok;echo", "run_$(echo)", "run_../escape", "run_a&b"):
            with self.subTest(run_id=run_id), self.assertRaises(ValueError):
                wt.create_run_worktree(run_id, self.repo)

    def test_invalid_package_manager_cannot_execute_shell_or_fallback(self):
        for pin in ("pnpm@10.9.0; echo injected", "pnpm@latest", "npm@10.9.0", "pnpm@^10.9.0"):
            with self.subTest(pin=pin):
                self.package["packageManager"] = pin
                self.write_package()
                self.git("add", "package.json")
                self.git("commit", "-m", "invalid test pin")
                self.assert_clean_failure(self.create(), "exact packageManager pin")
        self.assertEqual(self.calls, [])

    def test_missing_committed_lockfile_cannot_install(self):
        self.git("rm", "pnpm-lock.yaml")
        self.git("commit", "-m", "missing lockfile fixture")
        self.assert_clean_failure(self.create(), "committed regular pnpm-lock.yaml")
        self.assertEqual(self.calls, [])

    def test_workspace_globs_cannot_escape_isolation(self):
        (self.repo / "pnpm-workspace.yaml").write_text("packages:\n  - ../../canonical/*\n", encoding="utf-8")
        self.git("add", "pnpm-workspace.yaml")
        self.git("commit", "-m", "escaping glob fixture")
        self.assert_clean_failure(self.create(), "globs must stay inside")
        self.assertEqual(self.calls, [])

    def test_legacy_no_bootstrap_never_runs_pnpm(self):
        self.config.pop("worktree")
        self.write_config()
        def legacy_run(args, **kwargs):
            if args[0] == "git":
                return self.real_run(args, **kwargs)
            self.assertEqual(args[:4], ["cmd", "/c", "mklink", "/J"])
            return subprocess.CompletedProcess(args, 0, "", "")
        with patch.object(wt.subprocess, "run", side_effect=legacy_run):
            result = wt.create_run_worktree("run_bootstrap", self.repo)
        self.assertTrue(result["success"], result)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
