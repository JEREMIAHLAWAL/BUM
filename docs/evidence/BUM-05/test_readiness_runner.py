"""No-provider tests of readiness entrypoint authorization and provenance guards."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('bum05_serve', HERE / 'serve_readiness.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
SCRATCH = Path('C:/Users/2880441/AppData/Local/hermes/cache/scratch')
REQUIRED = ['--expected-head', 'a' * 40, '--preservation-baseline', str(SCRATCH / 'unused-baseline.json')]


class ReadinessGuardTests(unittest.TestCase):
    def test_explicit_authorization_required_before_git_or_dotenv(self):
        with patch.object(sys, 'argv', ['serve_readiness.py', '--output', str(SCRATCH / 'unused.json'), *REQUIRED]), \
                patch.object(runner, 'git') as git:
            with self.assertRaises(SystemExit) as caught:
                runner.main()
            self.assertEqual(caught.exception.code, 2)
            git.assert_not_called()

    def test_evidence_outside_scratch_refused(self):
        with patch.object(sys, 'argv', ['serve_readiness.py', '--output', str(HERE / 'forbidden.json'),
                                       '--allow-bum-dotenv-and-planner', *REQUIRED]), patch.object(runner, 'git') as git:
            with self.assertRaises(SystemExit) as caught:
                runner.main()
            self.assertEqual(caught.exception.code, 2)
            git.assert_not_called()

    def test_dirty_loaded_source_fails_before_dotenv_or_providers(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH, prefix='bum05-readiness-guard-') as folder:
            output = Path(folder) / 'failed.json'
            argv = ['serve_readiness.py', '--output', str(output), '--allow-bum-dotenv-and-planner', *REQUIRED]
            with patch.object(sys, 'argv', argv), \
                    patch.object(runner, 'git', side_effect=['a' * 40, ' M orchestrator/pipeline.py',
                                                             ' M orchestrator/pipeline.py']), \
                    patch('dotenv.load_dotenv') as dotenv:
                self.assertEqual(runner.main(), 1)
                dotenv.assert_not_called()
            report = json.loads(output.read_text(encoding='utf-8'))
            self.assertFalse(report['ready'])
            self.assertFalse(report['implementation_started'])
            self.assertEqual(report['failure']['class'], 'RuntimeError')
            self.assertNotIn('loaded_roles', report)

    def test_runtime_uses_resolved_windows_command_before_dotenv(self):
        runtime = SCRATCH / 'fs011-runtime/node-v24.22.0-win-x64'
        tools = {'node': str(runtime / 'node.exe'), 'pnpm': str(runtime / 'node_modules/.bin/pnpm.cmd')}
        calls = []
        def command(argv, **kwargs):
            calls.append(argv)
            version = '10.9.0' if argv == [tools['pnpm'], '--version'] else 'v24.22.0'
            return runner.subprocess.CompletedProcess(argv, 0, version + '\n', '')
        with tempfile.TemporaryDirectory(dir=SCRATCH, prefix='bum05-runtime-contract-') as folder:
            output = Path(folder) / 'failed.json'
            argv = ['serve_readiness.py', '--output', str(output), '--allow-bum-dotenv-and-planner',
                    '--expected-head', 'a' * 40, '--preservation-baseline', str(Path(folder) / 'missing.json')]
            with patch.object(sys, 'argv', argv), patch.object(runner, 'git', side_effect=['a' * 40, '', '']), \
                    patch.object(runner.shutil, 'which', side_effect=lambda name: tools[name]), \
                    patch.object(runner.subprocess, 'run', side_effect=command), \
                    patch('dotenv.load_dotenv') as dotenv:
                self.assertEqual(runner.main(), 1)
                dotenv.assert_not_called()
            self.assertEqual(calls, [[tools['node'], '--version'], [tools['pnpm'], '--version'],
                                     [tools['pnpm'], 'exec', 'node', '--version']])
            report = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(report['runtime_executables'], tools)
            self.assertEqual(report['runtime_versions'], {'node': 'v24.22.0', 'pnpm': '10.9.0', 'pnpm_exec_node': 'v24.22.0'})
            self.assertFalse(report['ready'])


class ReadOnlyBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_mutations_and_sensitive_gets_never_reach_app(self):
        calls = []
        async def app(scope, receive, send):
            calls.append(scope)
        wrapped = runner.ReadOnlyConsole(app, 'session-test', 'run_probe')
        for method, path in [('POST', '/api/pipeline/run'), ('POST', '/api/projects/select'),
                             ('DELETE', '/api/runs/purge'), ('GET', '/api/prompts/preview'),
                             ('GET', '/api/runs/other_run')]:
            with self.subTest(method=method, path=path):
                messages = []
                async def send(value):
                    messages.append(value)
                await wrapped({'type': 'http', 'method': method, 'path': path}, None, send)
                self.assertEqual(messages[0]['status'], 403)
        self.assertEqual(calls, [])

    async def test_actual_app_read_response_has_process_identity(self):
        calls = []
        messages = []
        async def app(scope, receive, send):
            calls.append(scope['path'])
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'{}'})
        async def send(value):
            messages.append(value)
        await runner.ReadOnlyConsole(app, 'session-test', 'run_probe')(
            {'type': 'http', 'method': 'GET', 'path': '/api/version'}, None, send)
        self.assertEqual(calls, ['/api/version'])
        headers = dict(messages[0]['headers'])
        self.assertEqual(headers[b'x-bum05-session'], b'session-test')
        self.assertEqual(headers[b'x-bum05-pid'], str(runner.os.getpid()).encode())


if __name__ == '__main__':
    unittest.main(verbosity=2)
