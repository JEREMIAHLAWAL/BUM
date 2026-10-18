"""Launch the unchanged console with a bounded, read-only Planner readiness probe.

Not an implementation entrypoint. No pipeline worker is started. Requires explicit
operator permission for one BUM-local dotenv load and one configured Planner call.
The standard provider client retains its own bounded retry policy (max_retries=2).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import re

ROOT = Path(__file__).resolve().parents[3]
FINDER = ROOT.parent / 'FinderShip'
ROLES = ('planner', 'frontend', 'backend', 'tester', 'reviewer')


class ReadOnlyConsole:
    """External method/path guard; the existing app and five roles are unchanged."""
    def __init__(self, app, identity, run_id):
        self.app = app
        self.identity = identity
        self.paths = {'/', '/api/health', '/api/version', '/api/projects',
                      '/api/pipeline/status', '/api/runs/' + run_id}

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            return await self.app(scope, receive, send)
        allowed = (scope['type'] == 'http' and scope.get('method') == 'GET'
                   and (scope.get('path') in self.paths or scope.get('path', '').startswith('/assets/')))
        if not allowed:
            if scope['type'] == 'websocket':
                await send({'type': 'websocket.close', 'code': 1008})
                return
            await send({'type': 'http.response.start', 'status': 403,
                        'headers': [(b'content-type', b'application/json')]})
            await send({'type': 'http.response.body', 'body': b'{"detail":"BUM-05 read-only readiness session"}'})
            return
        async def identified(message):
            if message['type'] == 'http.response.start':
                message = dict(message)
                message['headers'] = list(message.get('headers', [])) + [
                    (b'x-bum05-pid', str(os.getpid()).encode()),
                    (b'x-bum05-session', self.identity.encode())]
            await send(message)
        await self.app(scope, receive, identified)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-bum-dotenv-and-planner', action='store_true')
    parser.add_argument('--port', type=int, default=8900)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--preservation-baseline', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.expected_head):
        parser.error('Expected HEAD must be the exact 40-character tested SHA')
    scratch = Path('C:/Users/2880441/AppData/Local/hermes/cache/scratch').resolve()
    output = args.output.resolve()
    if not output.is_relative_to(scratch):
        parser.error('Evidence output must be in coordinator scratch')
    if not args.allow_bum_dotenv_and_planner:
        parser.error('Explicit dotenv and Planner authorization is required')
    os.environ.update(TEMP=str(scratch), TMP=str(scratch), TMPDIR=str(scratch),
                      PYTHON_DOTENV_DISABLED='1')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT))
    report = {'timestamp_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'pid': os.getpid(), 'invocation': sys.argv, 'bum_root': str(ROOT),
              'implementation_started': False, 'ready': False,
              'provider_call_limit': 'one run_agent invocation; standard client max_retries=2',
              'dotenv_scope': 'explicit BUM/.env only, once; Hermes stores never accessed'}
    def persist():
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    try:
        report['head'] = git('rev-parse', 'HEAD')
        if report['head'] != args.expected_head:
            raise RuntimeError('Disk HEAD differs from expected tested SHA')
        report['expected_head'] = args.expected_head
        report['status'] = git('status', '--porcelain=v1')
        code_status = git('status', '--porcelain=v1', '--', 'orchestrator', 'config',
                          'planner', 'frontend', 'backend', 'tester', 'reviewer',
                          'run_server.py', 'docs/evidence/BUM-05/serve_readiness.py')
        if code_status:
            raise RuntimeError('Uncommitted loaded-console source or readiness runner')
        report['runner_sha256'] = digest(Path(__file__))
        runtime = scratch / 'fs011-runtime/node-v24.22.0-win-x64'
        os.environ['PATH'] = str(runtime / 'node_modules/.bin') + os.pathsep + str(runtime) + os.pathsep + os.environ.get('PATH', '')
        report['runtime_versions'] = {}
        for name, argv in [('node', ['node', '--version']), ('pnpm', ['pnpm', '--version']),
                           ('pnpm_exec_node', ['pnpm', 'exec', 'node', '--version'])]:
            command = subprocess.run(argv, cwd=FINDER, capture_output=True, text=True, check=True, timeout=20)
            report['runtime_versions'][name] = command.stdout.strip()
        if report['runtime_versions'] != {'node': 'v24.22.0', 'pnpm': '10.9.0', 'pnpm_exec_node': 'v24.22.0'}:
            raise RuntimeError('Loaded console runtime differs from verified preparation runtime')
        baseline = json.loads(args.preservation_baseline.read_text(encoding='utf-8'))
        report['baseline_sha256'] = digest(args.preservation_baseline)
        if digest(ROOT / 'config/agents.yaml') != baseline['role_config']:
            raise RuntimeError('Five-role configuration differs from approved baseline')
        if any(digest(ROOT / p) != h for p, h in baseline['instructions'].items()):
            raise RuntimeError('Role instructions differ from preservation baseline')
        if digest(FINDER / 'bum.config.json') != baseline['files']['bum.config.json']:
            raise RuntimeError('FinderShip manifest differs from preservation baseline')
        # User-authorized BUM-local loading only. All later module-level calls
        # remain disabled, preventing upward dotenv discovery or repeat loads.
        import dotenv
        os.environ['PYTHON_DOTENV_DISABLED'] = '0'
        try:
            dotenv.load_dotenv(dotenv_path=ROOT / '.env', override=False)
        finally:
            os.environ['PYTHON_DOTENV_DISABLED'] = '1'
        from orchestrator import repo_tools
        repo_tools.set_active_project_path(FINDER)
        from orchestrator.agent_flow import server
        from orchestrator.agent_flow.executor import execution_manager
        from orchestrator.run import load_agents, run_agent
        from orchestrator import pipeline
        from orchestrator.contract_tools import extract_contract_from_spec
        agents = load_agents()
        if set(agents) != set(ROLES):
            raise RuntimeError('Five-role identity mismatch')
        report['loaded_roles'] = agents
        report['config_sha256'] = digest(ROOT / 'config/agents.yaml')
        report['instruction_hashes'] = {role: digest(ROOT / agents[role]['instructions']) for role in ROLES}
        report['module_files'] = {'server': server.__file__, 'pipeline': pipeline.__file__}
        report['loaded_version'] = server.get_version_info()
        loaded = report['loaded_version']
        if (loaded['boot_commit'] != args.expected_head or loaded['current_commit_on_disk'] != args.expected_head
                or loaded['is_stale'] or not loaded['boot_commit']):
            raise RuntimeError('Loaded revision is missing, stale or mismatched')
        if Path(server.__file__).resolve() != ROOT / 'orchestrator/agent_flow/server.py' or Path(pipeline.__file__).resolve() != ROOT / 'orchestrator/pipeline.py':
            raise RuntimeError('Console imported outside expected checkout')
        report['active_project'] = {'path': str(repo_tools.get_repo_root()),
                                    'manifest': repo_tools.get_active_manifest().model_dump()}
        if Path(report['active_project']['path']).resolve() != FINDER.resolve():
            raise RuntimeError('Active project mismatch')
        from orchestrator.manifest import BumManifest
        expected_manifest = BumManifest.model_validate_json((FINDER / 'bum.config.json').read_text(encoding='utf-8')).model_dump()
        if report['active_project']['manifest'] != expected_manifest:
            raise RuntimeError('Loaded manifest fallback or mismatch')
        report['execution_status_before'] = execution_manager.get_status()
        if report['execution_status_before']['running']:
            raise RuntimeError('Unexpected active implementation worker')
        report['credential_presence'] = {name: bool(os.getenv(name)) for name in ('OPENROUTER_API_KEY', 'ANTHROPIC_API_KEY')}
        if not all(report['credential_presence'].values()):
            raise RuntimeError('Required five-role provider credentials not loaded')
        run_id = 'run_bum05_readiness_' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '_' + uuid.uuid4().hex[:6]
        run_dir = ROOT / '.bum/runs' / run_id
        artifact = run_dir / 'pipeline'
        artifact.mkdir(parents=True, exist_ok=False)
        metadata = {'schema_version': 1, 'run_id': run_id, 'artifact_dir': str(artifact.resolve()),
                    'project_repo_path': str(FINDER.resolve()), 'retry_of': None,
                    'isolated': True, 'mode': 'read-only-planner-probe-no-worktree-no-implementation'}
        (run_dir / 'artifact_context.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        report['run_id'] = run_id
        report['artifact_context'] = metadata
        prompt_path = FINDER / 'pipeline/FS-011_PLANNER_READINESS.md'
        prompt = ('BUM-05 READ-ONLY READINESS PROBE ONLY. Do not implement or execute any task. '
                  'Return a bounded planning specification in your normal contract format. '
                  'All file boundaries below are proposed future ownership only; nothing is authorized to be written. '
                  'No tools, commands, provider/model substitutions, or application code. '
                  'Explicitly preserve FinderShip sources and five roles. This does NOT start FS-011.\n\n'
                  + prompt_path.read_text(encoding='utf-8'))
        report['source_prompt'] = {'path': str(prompt_path), 'sha256': digest(prompt_path),
                                   'submitted_sha256': hashlib.sha256(prompt.encode()).hexdigest()}
        def verify_preserved_roles():
            if load_agents() != agents or digest(ROOT / 'config/agents.yaml') != baseline['role_config']:
                raise RuntimeError('Five-role identity drift')
            if any(digest(ROOT / p) != h for p, h in baseline['instructions'].items()):
                raise RuntimeError('Role instruction drift')
        directory_token = pipeline._artifact_directory.set(artifact.resolve())
        project_token = pipeline._artifact_project.set(FINDER.resolve())
        try:
            report['artifact_resolver_matches'] = pipeline.get_pipeline_dir() == artifact.resolve()
            verify_preserved_roles()
            response = run_agent('planner', prompt, timeout=90.0)
            verify_preserved_roles()
            validation = pipeline.validate_planner_spec(response)
            contract = extract_contract_from_spec(response, manifest=repo_tools.get_active_manifest())
            report['planner_validation'] = validation
            report['planner_contract'] = contract
            pipeline.write_pipeline_file('spec.md', response)
            report['planner_output_sha256'] = digest(artifact / 'spec.md')
            if not validation['valid'] or not report['artifact_resolver_matches']:
                raise RuntimeError('Read-only Planner or scoped artifact validation failed')
            if not contract or not contract.get('file_boundaries'):
                raise RuntimeError('Planner supplied no usable file boundaries')
        finally:
            pipeline._artifact_project.reset(project_token)
            pipeline._artifact_directory.reset(directory_token)
        report['context_restored'] = (pipeline._artifact_directory.get() is None and pipeline._artifact_project.get() is None)
        report['execution_status_after'] = execution_manager.get_status()
        if git('rev-parse', 'HEAD') != report['head'] or report['execution_status_after']['running']:
            raise RuntimeError('Loaded HEAD drift or unexpected worker')
        verify_preserved_roles()
        if git('status', '--porcelain=v1', '--', 'orchestrator', 'config', 'planner', 'frontend', 'backend', 'tester', 'reviewer', 'run_server.py', 'docs/evidence/BUM-05/serve_readiness.py'):
            raise RuntimeError('Loaded source became dirty during probe')
        report['planner_probe_ok'] = bool(report['context_restored'])
        # This file alone is not loaded-console readiness: the coordinator must
        # independently read the real HTTP endpoints after successful binding.
        report['console_readiness'] = 'AWAITING_INDEPENDENT_HTTP_READBACK'
        report['ready'] = False
        report['session_identity'] = uuid.uuid4().hex
        persist()
        import uvicorn
        # External read-only guard, not a modified/replacement app or pipeline.
        uvicorn.run(ReadOnlyConsole(server.app, report['session_identity'], run_id),
                    host='127.0.0.1', port=args.port, log_level='warning')
        report['console_readiness'] = 'SERVER_STOPPED'
        persist()
        return 0
    except BaseException as exc:
        # Never serialize provider exceptions/raw SDK payloads or environment values.
        report['failure'] = {'class': type(exc).__name__,
                             'error_type': getattr(exc, 'error_type', 'READINESS_FAILED')}
        report['ready'] = False
        persist()
        print('BUM-05 loaded-console readiness failed; see redacted evidence.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
