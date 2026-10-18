"""Revalidate a genuine read-only Planner capture and serve the real console.

No dotenv load or provider call occurs in this entrypoint. A previous failed
harness result is retained as failed; this is a separately identified replay of
its hash-pinned actual provider artifact, not a new live-call claim. It cannot
establish an executable implementation contract or authorize builders.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from serve_readiness import ROOT, FINDER, ROLES, ReadOnlyConsole, digest, git
SCRATCH = Path('C:/Users/2880441/AppData/Local/hermes/cache/scratch').resolve()


def read_capture(path, expected_sha256):
    path = path.resolve()
    if not path.is_relative_to(SCRATCH) or not re.fullmatch('[0-9a-f]{64}', expected_sha256):
        raise RuntimeError('Capture path or SHA format invalid')
    if digest(path) != expected_sha256:
        raise RuntimeError('Capture report hash mismatch')
    capture = json.loads(path.read_text(encoding='utf-8'))
    if not re.fullmatch('[0-9a-f]{40}', capture['head']):
        raise RuntimeError('Capture HEAD invalid')
    if capture['planner_validation'] != {'valid': True, 'reason': ''}:
        raise RuntimeError('Original Planner text validation failed')
    if capture['planner_contract']['file_boundaries']:
        raise RuntimeError('Capture is not the zero-authority read-only probe')
    run_id = capture['run_id']
    if not re.fullmatch('run_bum05_readiness_[A-Za-z0-9_]+', run_id):
        raise RuntimeError('Wrong capture run type')
    artifact = (ROOT / '.bum/runs' / run_id / 'pipeline').resolve()
    metadata = capture['artifact_context']
    if (Path(metadata['artifact_dir']).resolve() != artifact
            or Path(metadata['project_repo_path']).resolve() != FINDER.resolve()
            or metadata['mode'] != 'read-only-planner-probe-no-worktree-no-implementation'):
        raise RuntimeError('Capture artifact scope mismatch')
    if json.loads((artifact.parent / 'artifact_context.json').read_text(encoding='utf-8')) != metadata:
        raise RuntimeError('Physical capture metadata mismatch')
    if digest(artifact / 'spec.md') != capture['planner_output_sha256']:
        raise RuntimeError('Actual captured Planner output hash mismatch')
    prompt = FINDER / 'pipeline/FS-011_PLANNER_READINESS.md'
    if digest(prompt) != capture['source_prompt']['sha256']:
        raise RuntimeError('Capture source prompt changed')
    # The call implementation, instructions, identities and production parser
    # must be the same as when the genuine provider artifact was obtained.
    diff = subprocess.run(['git', 'diff', '--exit-code', capture['head'], 'HEAD', '--',
                           'orchestrator', 'config', 'planner', 'frontend', 'backend',
                           'tester', 'reviewer', 'run_server.py'], cwd=ROOT,
                          capture_output=True, text=True, check=False)
    if diff.returncode:
        raise RuntimeError('Production console differs from genuine call revision')
    return capture, artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--capture-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--preservation-baseline', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8900)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(SCRATCH) or not re.fullmatch('[0-9a-f]{40}', args.expected_head):
        parser.error('Scratch output and exact expected HEAD required')
    os.environ.update(PYTHON_DOTENV_DISABLED='1', TEMP=str(SCRATCH), TMP=str(SCRATCH), TMPDIR=str(SCRATCH))
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT))
    report = {'pid': os.getpid(), 'head': args.expected_head, 'ready': False,
              'implementation_started': False, 'provider_calls_this_process': 0,
              'dotenv_loads_this_process': 0, 'readiness_mode': 'CAPTURE_REVALIDATION_READ_ONLY',
              'timestamp_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'runner_sha256': digest(Path(__file__))}
    def persist():
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    try:
        if git('rev-parse', 'HEAD') != args.expected_head or git('status', '--porcelain=v1'):
            raise RuntimeError('Expected completely clean committed HEAD required')
        capture, artifact = read_capture(args.capture, args.capture_sha256)
        baseline = json.loads(args.preservation_baseline.read_text(encoding='utf-8'))
        report['capture'] = {'path': str(args.capture.resolve()), 'sha256': args.capture_sha256,
                             'genuine_call_head': capture['head'], 'genuine_call_pid': capture['pid'],
                             'original_harness_failure': capture.get('failure'),
                             'not_a_new_provider_call': True}
        if digest(ROOT / 'config/agents.yaml') != baseline['role_config'] or capture['config_sha256'] != baseline['role_config']:
            raise RuntimeError('Role config differs from approved genuine call')
        if any(digest(ROOT / p) != h for p, h in baseline['instructions'].items()):
            raise RuntimeError('Instructions differ from preservation baseline')
        from orchestrator import repo_tools, pipeline
        from orchestrator.run import load_agents
        from orchestrator.contract_tools import extract_contract_from_spec
        from orchestrator.agent_flow import server
        from orchestrator.agent_flow.executor import execution_manager
        repo_tools.set_active_project_path(FINDER)
        agents = load_agents()
        if set(agents) != set(ROLES) or agents != capture['loaded_roles']:
            raise RuntimeError('Loaded five roles differ from genuine call')
        report['loaded_roles'] = agents
        report['config_sha256'] = digest(ROOT / 'config/agents.yaml')
        report['instruction_hashes'] = {role: digest(ROOT / agents[role]['instructions']) for role in ROLES}
        if report['instruction_hashes'] != capture['instruction_hashes']:
            raise RuntimeError('Instructions differ from actual call')
        report['loaded_version'] = server.get_version_info()
        version = report['loaded_version']
        if (version['boot_commit'] != args.expected_head or version['current_commit_on_disk'] != args.expected_head
                or version['is_stale'] or Path(server.__file__).resolve() != ROOT / 'orchestrator/agent_flow/server.py'):
            raise RuntimeError('Loaded console revision/module mismatch')
        manifest_bytes = (FINDER / 'bum.config.json').read_bytes()
        if digest(FINDER / 'bum.config.json') != baseline['files']['bum.config.json']:
            raise RuntimeError('Approved manifest changed')
        from orchestrator.manifest import BumManifest
        loaded_manifest = repo_tools.get_active_manifest().model_dump()
        if loaded_manifest != BumManifest.model_validate_json(manifest_bytes).model_dump() or repo_tools.get_repo_root() != FINDER.resolve():
            raise RuntimeError('Active project or manifest mismatch')
        report['active_project'] = {'path': str(repo_tools.get_repo_root()), 'manifest': loaded_manifest}
        # Version commands were genuinely executed by the original process;
        # repeat the same explicitly resolved commands for this loaded instance.
        runtime = SCRATCH / 'fs011-runtime/node-v24.22.0-win-x64'
        os.environ['PATH'] = str(runtime / 'node_modules/.bin') + os.pathsep + str(runtime) + os.pathsep + os.environ.get('PATH', '')
        import shutil
        tools = {name: shutil.which(name) for name in ('node', 'pnpm')}
        if any(not value or not Path(value).resolve().is_relative_to(runtime) for value in tools.values()):
            raise RuntimeError('Runtime executable escaped approved directory')
        report['runtime_versions'] = {}
        for name, argv in [('node', [tools['node'], '--version']), ('pnpm', [tools['pnpm'], '--version']), ('pnpm_exec_node', [tools['pnpm'], 'exec', 'node', '--version'])]:
            report['runtime_versions'][name] = subprocess.run(argv, cwd=FINDER, capture_output=True, text=True, check=True, timeout=20).stdout.strip()
        if report['runtime_versions'] != {'node': 'v24.22.0', 'pnpm': '10.9.0', 'pnpm_exec_node': 'v24.22.0'}:
            raise RuntimeError('Loaded process runtime mismatch')
        text = (artifact / 'spec.md').read_text(encoding='utf-8')
        report['planner_validation'] = pipeline.validate_planner_spec(text)
        report['planner_contract'] = extract_contract_from_spec(text, manifest=repo_tools.get_active_manifest())
        if not report['planner_validation']['valid'] or report['planner_contract']['file_boundaries']:
            raise RuntimeError('Captured probe no longer validates as zero-authority read-only text')
        report['zero_write_authority'] = True
        report['run_id'] = capture['run_id']
        report['artifact_context'] = capture['artifact_context']
        report['planner_output_sha256'] = digest(artifact / 'spec.md')
        a = pipeline._artifact_directory.set(artifact)
        p = pipeline._artifact_project.set(FINDER.resolve())
        try:
            report['artifact_resolver_matches'] = pipeline.get_pipeline_dir() == artifact
        finally:
            pipeline._artifact_project.reset(p)
            pipeline._artifact_directory.reset(a)
        report['context_restored'] = pipeline._artifact_directory.get() is None and pipeline._artifact_project.get() is None
        if not report['artifact_resolver_matches'] or not report['context_restored'] or execution_manager.get_status()['running']:
            raise RuntimeError('Scope or execution-manager readiness failed')
        if digest(ROOT / 'config/agents.yaml') != report['config_sha256'] or any(digest(ROOT / agents[r]['instructions']) != h for r, h in report['instruction_hashes'].items()):
            raise RuntimeError('Roles changed during revalidation')
        if git('rev-parse', 'HEAD') != args.expected_head or git('status', '--porcelain=v1'):
            raise RuntimeError('Source changed during revalidation')
        report['planner_probe_ok'] = True
        report['session_identity'] = uuid.uuid4().hex
        report['console_readiness'] = 'AWAITING_INDEPENDENT_HTTP_READBACK'
        persist()
        import uvicorn
        uvicorn.run(ReadOnlyConsole(server.app, report['session_identity'], report['run_id']), host='127.0.0.1', port=args.port, log_level='warning')
        report['console_readiness'] = 'SERVER_STOPPED'
        persist()
        return 0
    except BaseException as exc:
        report['failure'] = {'class': type(exc).__name__, 'error_type': getattr(exc, 'error_type', 'READINESS_FAILED')}
        persist()
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
