"""Independent HTTP readback of the real, read-only BUM console instance."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

import psutil

ROOT = Path(__file__).resolve().parents[3]
SCRATCH = Path('C:/Users/2880441/AppData/Local/hermes/cache/scratch').resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--port', type=int, default=8900)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(SCRATCH):
        parser.error('Output must be in coordinator scratch')
    result = {'ok': False, 'checks': {}, 'responses': {}, 'failure': None,
              'implementation_started': False}
    try:
        probe = json.loads(args.probe_report.read_text(encoding='utf-8'))
        if not probe.get('planner_probe_ok') or probe.get('head') != args.expected_head:
            raise RuntimeError('Planner probe failed or wrong tested HEAD')
        pid = probe['pid']
        run_id = probe['run_id']
        process = psutil.Process(pid)
        result['pid'] = pid
        result['expected_head'] = args.expected_head
        result['probe_sha256'] = hashlib.sha256(args.probe_report.read_bytes()).hexdigest()
        result['process'] = {'executable': process.exe(), 'cwd': process.cwd()}
        if Path(process.cwd()).resolve() != ROOT:
            raise RuntimeError('Wrong process working directory')
        if not any(c.status == 'LISTEN' and c.laddr.ip == '127.0.0.1' and c.laddr.port == args.port
                   for c in process.net_connections(kind='tcp')):
            raise RuntimeError('Expected PID does not own loopback listening socket')
        def request(path, method='GET'):
            req = urllib.request.Request(f'http://127.0.0.1:{args.port}' + path, method=method)
            try:
                response = urllib.request.urlopen(req, timeout=10)
            except urllib.error.HTTPError as exc:
                with exc:
                    return exc.code, exc.read().decode('utf-8'), dict(exc.headers)
            with response:
                headers = dict(response.headers)
                if response.headers.get('x-bum05-pid') != str(pid) or response.headers.get('x-bum05-session') != probe['session_identity']:
                    raise RuntimeError('HTTP session/process identity mismatch')
                return response.status, response.read().decode('utf-8'), headers
        for name, path in [('health', '/api/health'), ('version', '/api/version'),
                           ('projects', '/api/projects'), ('status', '/api/pipeline/status'),
                           ('artifact', '/api/runs/' + run_id)]:
            status, body, headers = request(path)
            if status != 200:
                raise RuntimeError('Required endpoint failed: ' + name)
            result['responses'][name] = {'status': status, 'body': json.loads(body)}
        version = result['responses']['version']['body']
        result['checks']['exact_loaded_version'] = (version['boot_commit'] == args.expected_head
            and version['current_commit_on_disk'] == args.expected_head and not version['is_stale'])
        active = result['responses']['projects']['body']['active_path']
        result['checks']['active_project'] = Path(active).resolve() == ROOT.parent / 'FinderShip'
        result['checks']['idle'] = not result['responses']['status']['body']['running']
        artifact = result['responses']['artifact']['body']['artifact_context']
        result['checks']['artifact_context'] = artifact == probe['artifact_context']
        result['checks']['artifact_location'] = Path(artifact['artifact_dir']).resolve() == ROOT / '.bum/runs' / run_id / 'pipeline'
        spec_file = Path(artifact['artifact_dir']) / 'spec.md'
        result['checks']['planner_output'] = hashlib.sha256(spec_file.read_bytes()).hexdigest() == probe['planner_output_sha256']
        result['checks']['runtime_versions'] = probe['runtime_versions'] == {'node': 'v24.22.0', 'pnpm': '10.9.0', 'pnpm_exec_node': 'v24.22.0'}
        result['checks']['five_roles'] = set(probe['loaded_roles']) == {'planner', 'frontend', 'backend', 'tester', 'reviewer'}
        result['checks']['planner_validation'] = probe['planner_validation']['valid'] and bool(probe['planner_contract']['file_boundaries'])
        result['checks']['role_config_preserved'] = hashlib.sha256((ROOT / 'config/agents.yaml').read_bytes()).hexdigest() == probe['config_sha256']
        result['checks']['role_instructions_preserved'] = all(hashlib.sha256((ROOT / probe['loaded_roles'][role]['instructions']).read_bytes()).hexdigest() == digest
                                                            for role, digest in probe['instruction_hashes'].items())
        blocked = {}
        for method, path in [('POST', '/api/pipeline/run'), ('POST', '/api/projects/select'),
                             ('DELETE', '/api/runs/purge'), ('GET', '/api/prompts/preview?file=.env')]:
            code, body, headers = request(path, method)
            blocked[method + ' ' + path] = code == 403
        result['mutation_denials'] = blocked
        result['checks']['read_only_boundary'] = all(blocked.values())
        code, body, _ = request('/api/pipeline/status')
        result['checks']['still_idle_after_denials'] = code == 200 and not json.loads(body)['running']
        result['ok'] = all(result['checks'].values())
    except BaseException as exc:
        result['failure'] = {'class': type(exc).__name__, 'message': str(exc)}
    finally:
        output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'ok': result['ok'], 'checks': result['checks'], 'failure': result['failure'], 'output': str(output)}, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
