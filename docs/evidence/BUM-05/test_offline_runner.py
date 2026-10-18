"""Runner contracts. Execute directly; no application imports or live probes."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bum05_runner", HERE / "run_offline.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
SCRATCH = Path.home() / "AppData/Local/hermes/cache/scratch"


class RunnerContracts(unittest.TestCase):
    def test_policy_rejects_caught_denials(self):
        audit = runner.OfflineAudit(SCRATCH.resolve(), HERE.parents[2])
        for event, args in (("subprocess.Popen", ("git",)),
                            ("socket.connect", (None, ("127.0.0.1", 80))),
                            ("open", (str(HERE.parents[2] / "pipeline/spec.md"), "r", 0)),
                            ("open", (str(SCRATCH / ".env"), "r", 0)),
                            ("open", (str(HERE / "outside.txt"), "w", os.O_WRONLY))):
            with self.subTest(event=event), self.assertRaises(PermissionError):
                audit(event, args)
        self.assertEqual(len(audit.denied), 5)

    def invoke(self, *flags):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="bum05-contract-") as temp:
            output = Path(temp) / "report.json"
            result = subprocess.run([sys.executable, "-B", str(HERE / "run_offline.py"),
                                     "--output", str(output), *flags],
                                    capture_output=True, text=True, timeout=120)
            self.assertTrue(output.exists(), result.stderr)
            return result, json.loads(output.read_text(encoding="utf-8"))

    def test_setup_failure_retains_gate_and_never_loads_full_suite(self):
        result, report = self.invoke("--allow-dirty-diagnostic", "--probe-setup-failure")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["groups"][0]["tests_run"], 3)
        self.assertTrue(report["groups"][0]["ok"])
        self.assertEqual(report["groups"][1]["tests_run"], 0)
        self.assertIn("deliberate setup failure", report["groups"][1]["setup_error"])
        self.assertEqual(report["full_modules_loaded"], [])
        self.assertFalse(report["acceptance"])

    def test_exact_head_refuses_dirty_tree(self):
        # Synthetic provenance keeps this contract valid after committing.
        before = {"dirty_executable_inputs": ["synthetic/modified.py"]}
        with self.assertRaisesRegex(RuntimeError, "dirty"):
            runner.enforce_exact_head(before, False)
        runner.enforce_exact_head(before, True)
        runner.enforce_exact_head({"dirty_executable_inputs": []}, False)

    def test_deleted_head_helpers_and_entrypoints_are_dirty(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(dir=SCRATCH, prefix='bum05-missing-inputs-') as temp:
            root = Path(temp)
            script = root / 'docs/evidence/BUM-05/run_offline.py'
            script.parent.mkdir(parents=True)
            script.write_text('pass\n', encoding='utf-8')
            (root / 'config').mkdir()
            (root / 'config/agents.yaml').write_text('agents: {}\n', encoding='utf-8')
            inventory = b'config/agents.yaml\ndocs/evidence/BUM-05/run_offline.py\norchestrator/deleted_helper.py\nrun_server.py\n'
            (root / 'staged_added.py').write_text('pass\n', encoding='utf-8')
            index_inventory = b'config/agents.yaml\ndocs/evidence/BUM-05/run_offline.py\nstaged_added.py\n'
            def fake_git(argv, **kwargs):
                command = argv[2:]
                if command[0] == 'ls-files':
                    data = index_inventory
                elif command[0] == 'ls-tree':
                    data = inventory
                elif command[0] == 'show':
                    data = (root / command[1].removeprefix('HEAD:')).read_bytes()
                elif command[0] == 'rev-parse':
                    data = b'a' * 40
                else:
                    data = b''
                return subprocess.CompletedProcess(argv, 0, data, b'')
            with patch.object(runner, 'ROOT', root), patch.object(runner, 'RUNNER', script), \
                    patch.object(runner.subprocess, 'run', side_effect=fake_git):
                before = runner.provenance()
            for path in ['orchestrator/deleted_helper.py', 'run_server.py']:
                with self.subTest(path=path):
                    self.assertIn(path, before['dirty_executable_inputs'])
                    self.assertIsNone(before['file_sha256'][path])
            self.assertIn('staged_added.py', before['dirty_executable_inputs'])
            self.assertIsNotNone(before['file_sha256']['staged_added.py'])
            with self.assertRaisesRegex(RuntimeError, 'dirty'):
                runner.enforce_exact_head(before, False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
