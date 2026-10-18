"""No-provider verifier contract against the actual project's endpoint body."""
import ast
import asyncio
from email.message import Message
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('bum05_verify', HERE / 'verify_loaded.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class LoadedVerifierContracts(unittest.TestCase):
    def test_real_project_schema_and_fail_closed_wrong_project(self):
        source = (verifier.ROOT / 'orchestrator/agent_flow/server.py').read_text(encoding='utf-8')
        function = next(n for n in ast.parse(source).body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'get_projects')
        function.decorator_list = []
        for wrong in (False, True):
            with self.subTest(wrong_project=wrong), tempfile.TemporaryDirectory(dir=verifier.SCRATCH, prefix='bum05-http-contract-') as folder:
                base = Path(folder)
                root = base / 'BUM'
                artifact = root / '.bum/runs/run_probe/pipeline'
                artifact.mkdir(parents=True)
                (artifact / 'spec.md').write_text('fixture specification', encoding='utf-8')
                (root / 'config').mkdir()
                (root / 'config/agents.yaml').write_text('fixture configuration', encoding='utf-8')
                digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
                roles = {}
                instructions = {}
                for role in ['planner', 'frontend', 'backend', 'tester', 'reviewer']:
                    path = root / role / 'instructions.md'
                    path.parent.mkdir()
                    path.write_text('fixture instructions', encoding='utf-8')
                    roles[role] = {'instructions': role + '/instructions.md'}
                    instructions[role] = digest(path)
                head = 'a' * 40
                version = {'boot_commit': head, 'current_commit_on_disk': head, 'is_stale': False}
                metadata = {'artifact_dir': str(artifact), 'run_id': 'run_probe'}
                report = {'planner_probe_ok': True, 'head': head, 'pid': 123, 'run_id': 'run_probe',
                          'session_identity': 'fixture-session', 'artifact_context': metadata,
                          'planner_output_sha256': digest(artifact / 'spec.md'), 'loaded_roles': roles,
                          'planner_validation': {'valid': True}, 'planner_contract': {'file_boundaries': ['future.ts']},
                          'runtime_versions': {'node': 'v24.22.0', 'pnpm': '10.9.0', 'pnpm_exec_node': 'v24.22.0'},
                          'config_sha256': digest(root / 'config/agents.yaml'), 'instruction_hashes': instructions}
                probe = base / 'probe.json'
                probe.write_text(json.dumps(report), encoding='utf-8')
                namespace = {'list_available_projects': lambda: [],
                             'resolve_repo_root': lambda: (base / ('WrongProject' if wrong else 'FinderShip'), 'dynamic_selection'),
                             'get_version_info': lambda: version}
                exec(compile(ast.Module(body=[function], type_ignores=[]), '<actual-get-projects-handler>', 'exec'), namespace)
                project_response = asyncio.run(namespace['get_projects']())
                self.assertIn('active_path', project_response)
                bodies = {'/api/health': {'status': 'ok'}, '/api/version': version,
                          '/api/projects': project_response, '/api/pipeline/status': {'running': False},
                          '/api/runs/run_probe': {'artifact_context': metadata}}
                class Response:
                    status = 200
                    def __init__(self, body):
                        self.body = body
                        self.headers = Message()
                        self.headers['x-bum05-pid'] = '123'
                        self.headers['x-bum05-session'] = 'fixture-session'
                    def __enter__(self): return self
                    def __exit__(self, *args): return False
                    def read(self): return json.dumps(self.body).encode()
                def urlopen(request, **kwargs):
                    path = request.full_url.removeprefix('http://127.0.0.1:8900')
                    if request.method != 'GET' or path.startswith('/api/prompts/'):
                        raise urllib.error.HTTPError(request.full_url, 403, 'read-only fixture', Message(), io.BytesIO(b'{}'))
                    return Response(bodies[path])
                process = SimpleNamespace(exe=lambda: sys.executable, cwd=lambda: str(root), net_connections=lambda **k: [
                    SimpleNamespace(status='LISTEN', laddr=SimpleNamespace(ip='127.0.0.1', port=8900))])
                output = base / 'verified.json'
                with patch.object(verifier, 'ROOT', root), patch.object(verifier.psutil, 'Process', return_value=process), \
                        patch.object(verifier.urllib.request, 'urlopen', side_effect=urlopen), \
                        patch.object(sys, 'argv', ['verify_loaded.py', '--probe-report', str(probe), '--output', str(output), '--expected-head', head]):
                    self.assertEqual(verifier.main(), 1 if wrong else 0)
                observed = json.loads(output.read_text(encoding='utf-8'))
                self.assertEqual(observed['checks']['active_project'], not wrong)
                self.assertEqual(observed['ok'], not wrong)


if __name__ == '__main__':
    unittest.main(verbosity=2)
