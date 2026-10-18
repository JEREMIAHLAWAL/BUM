"""Real-process policy contracts; all fixtures owned by this test."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_offline as runner

class FixtureSandboxContracts(unittest.TestCase):
    def test_reviewed_git_init_and_rejections(self):
        scratch = Path.home() / 'AppData/Local/hermes/cache/scratch'
        with tempfile.TemporaryDirectory(dir=scratch) as temp:
            root = Path(temp)
            audit = runner.OfflineAudit(scratch, runner.ROOT)
            policy = runner.FixtureProcesses(audit)
            policy.begin('synthetic.fixture')
            policy.register(root)
            sys.addaudithook(audit)
            self.addCleanup(setattr, audit, 'active', False)
            with policy.install():
                result = subprocess.run(['git', 'init', '-b', 'main'], cwd=root,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                for argv, kwargs in (
                    (['git', 'init', '-b', 'main'], {'cwd': HERE}),
                    (['git', 'add', str(HERE)], {'cwd': root}),
                    (['git', '-c', 'alias.pwn=!echo unsafe', 'pwn'], {'cwd': root}),
                    (['git', 'status'], {'cwd': root, 'env': {'GIT_DIR': str(HERE)}}),
                    (['git', 'fetch', 'https://example.invalid'], {'cwd': root}),
                    (['git', 'init', '-b', 'main'], {'cwd': root, 'shell': True}),
                    (['git', 'worktree', 'add', '-b', 'bum-run/run_bootstrap', str(HERE), 'HEAD'], {'cwd': root}),
                ):
                    with self.subTest(argv=argv), self.assertRaises(PermissionError):
                        subprocess.run(argv, capture_output=True, **kwargs)
            self.assertEqual(len(policy.records), 1)
            self.assertIn('sha256', policy.records[0])
            self.assertIn('environment_policy', policy.records[0])
            trace = root / '.git/unexpected-descendant.jsonl'
            trace.write_text('{"event":"child_start","use_shell":false,"argv":["cmd.exe","/c","unexpected"]}\n{"event":"exit"}\n', encoding='utf-8')
            with self.assertRaises(PermissionError):
                policy.completed({'git_trace': str(trace), 'cwd': str(root)})
            audit.active = False
            import json
            (scratch / 'bum05-git-policy-negatives.json').write_text(json.dumps({
                'allowed_processes': policy.records, 'denied_attempts': audit.denied,
                'acceptance': False, 'expected_denials': 8,
            }, indent=2), encoding='utf-8')
            self.assertEqual(len(audit.denied), 8)

    def test_reviewed_lock_child_uses_scratch_only_native_api(self):
        scratch = Path.home() / 'AppData/Local/hermes/cache/scratch'
        with tempfile.TemporaryDirectory(dir=scratch) as temp:
            root = Path(temp)
            target = root / 'locked.txt'
            target.write_text('fixture', encoding='utf-8')
            audit = runner.OfflineAudit(scratch, runner.ROOT)
            policy = runner.FixtureProcesses(audit)
            policy.begin(self.id())
            policy.register(root)
            sys.addaudithook(audit)
            try:
                with policy.install():
                    child = subprocess.Popen([sys.executable, '-u', '-c', policy.lock_script, str(target)],
                                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    output, error = child.communicate('\n', timeout=5)
                    self.assertEqual(child.returncode, 0, error)
                    self.assertEqual(output.strip(), 'locked')
                self.assertFalse(policy.check_reports()[0]['denied_attempts'])
                self.assertFalse(audit.denied)
            finally:
                audit.active = False

    def test_python_children_audit_before_workload_and_fail_on_caught_denial(self):
        scratch = Path.home() / 'AppData/Local/hermes/cache/scratch'
        with tempfile.TemporaryDirectory(dir=scratch) as temp:
            root = Path(temp)
            (root / 'tests').mkdir()
            test = root / 'tests/test_fixture.py'
            test.write_text('import unittest\nclass Fixture(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n', encoding='utf-8')
            audit = runner.OfflineAudit(scratch, runner.ROOT)
            policy = runner.FixtureProcesses(audit)
            policy.begin(self.id())
            policy.register(root)
            sys.addaudithook(audit)
            try:
                with policy.install():
                    for argv in ([sys.executable, '-m', 'compileall', '-q', 'tests'],
                                 [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests']):
                        result = subprocess.run(argv, cwd=root, capture_output=True, text=True)
                        self.assertEqual(result.returncode, 0, result.stderr)
                    probes = {
                        'network': "__import__('socket').getaddrinfo('localhost', 80)",
                        'outside_write': "Path(%r).write_text('forbidden')" % str(Path(temp).parent / 'bum05-child-MUST-NOT-EXIST.txt'),
                        'credential': "Path('.env').read_text()",
                        'descendant': "__import__('subprocess').run([__import__('sys').executable, '-c', 'pass'])",
                    }
                    for name, expression in probes.items():
                        test.write_text('from pathlib import Path\nimport unittest\nclass Fixture(unittest.TestCase):\n def test_denied(self):\n  with self.assertRaises(PermissionError):\n   ' + expression + '\n', encoding='utf-8')
                        result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests'], cwd=root,
                                                capture_output=True, text=True)
                        self.assertEqual(result.returncode, 97, (name, result.stdout, result.stderr))
                reports = policy.check_reports()
                self.assertEqual(len(reports), 6)
                self.assertEqual(sum(bool(r['denied_attempts']) for r in reports), 4)
                self.assertTrue(all(r['audit_before_workload'] for r in reports))
                import json
                (scratch / 'bum05-child-policy-negatives.json').write_text(json.dumps({
                    'allowed_processes': policy.records, 'child_reports': reports,
                    'denied_attempts': audit.denied, 'acceptance': False,
                    'probes': list(probes),
                }, indent=2), encoding='utf-8')
            finally:
                audit.active = False

if __name__ == '__main__':
    unittest.main(verbosity=2)
