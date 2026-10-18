"""BUM-01 real bounded bootstrap/cleanup verification; no agent invocation."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

BUM = Path('C:/Users/2880441/Documents/AGENTS/JL/BUM')
REPO = BUM.parent / 'FinderShip'
SCRATCH = Path('C:/Users/2880441/AppData/Local/hermes/cache/scratch')
RUNTIME = SCRATCH / 'fs011-runtime/node-v24.22.0-win-x64'
os.environ['TEMP'] = os.environ['TMP'] = os.environ['TMPDIR'] = str(SCRATCH)
os.environ['PATH'] = str(RUNTIME / 'node_modules/.bin') + os.pathsep + str(RUNTIME) + os.pathsep + os.environ['PATH']
sys.path.insert(0, str(BUM))
from orchestrator.worktree_tools import create_run_worktree, discard_run_worktree, branch_name


def git(*args):
    return subprocess.run(['git', *args], cwd=REPO, capture_output=True, text=True, check=True).stdout


def canonical():
    return {'head': git('rev-parse', 'HEAD').strip(), 'status': git('status', '--porcelain=v1'),
            'node_modules_inode': (REPO / 'node_modules').stat().st_ino}


run_id = 'run_bum01_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:6]
report = {'run_id': run_id, 'bum_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=BUM, text=True).strip(),
          'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'canonical_before': canonical(), 'commands': []}
report_path = SCRATCH / (run_id + '.json')
log_path = SCRATCH / (run_id + '.log')
result = create_run_worktree(run_id, REPO)
report['create'] = {k: str(v) if isinstance(v, Path) else v for k, v in result.items()}
print('CREATE', json.dumps(report['create']), flush=True)
try:
    if not result.get('success'):
        raise RuntimeError('Fresh isolated bootstrap failed')
    root = result['worktree_path']
    report['dependency_isolation'] = {str(p.relative_to(root)): {'exists': p.is_dir(), 'junction': p.is_junction(), 'symlink': p.is_symlink()}
                                      for p in (root / 'node_modules', root / 'apps/web/node_modules', root / 'packages/shared/node_modules')}
    assert all(v['exists'] and not v['junction'] and not v['symlink'] for v in report['dependency_isolation'].values())
    with log_path.open('w', encoding='utf-8') as log:
        for command in (['node', '--version'], ['pnpm', '--version'], ['pnpm', 'exec', 'node', '--version'], ['pnpm', 'run', 'typecheck'], ['pnpm', 'run', 'lint']):
            completed = subprocess.run([shutil.which(command[0]), *command[1:]], cwd=root, capture_output=True, text=True, timeout=180)
            text = completed.stdout + completed.stderr
            report['commands'].append({'argv': command, 'exit_code': completed.returncode, 'output': text})
            log.write('$ ' + ' '.join(command) + '\n' + text + '\n')
            log.flush()
            print('COMMAND', command, 'EXIT', completed.returncode, text[-1500:], flush=True)
            if completed.returncode:
                raise RuntimeError('Verification command failed')
finally:
    report['cleanup'] = discard_run_worktree(run_id, REPO)
    root = Path(report['create'].get('worktree_path') or BUM / '.bum/worktrees' / run_id)
    report['post_cleanup'] = {'directory_absent': not root.exists(),
                              'registration_absent': str(root).replace('\\', '/') not in git('worktree', 'list', '--porcelain'),
                              'branch_absent': not git('branch', '--list', branch_name(run_id)).strip()}
    report['canonical_after'] = canonical()
    report['canonical_preserved'] = report['canonical_before'] == report['canonical_after']
    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('REPORT', report_path, flush=True)
    print('CLEANUP', json.dumps(report['cleanup']), flush=True)
    print('POST_CLEANUP', report['post_cleanup'], 'CANONICAL_PRESERVED', report['canonical_preserved'], flush=True)
assert report['canonical_preserved']
assert all(report['post_cleanup'].values()), 'Cleanup verification failed; branch/registration retained where needed'
