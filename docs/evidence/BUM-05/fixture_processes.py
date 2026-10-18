"""Reviewed BUM-05 fixture process boundary (not a general command runner).

Only trusted pinned Git runs natively. Python payloads run through child_audit
under -I -S; cmd mklink is replaced with the stdlib Windows junction API.
The test inventory reviewed is test_worktree_bootstrap.py, test_tester_writes.py,
command_tools.py and worktree_tools.py. No class-name permission shortcuts.
"""
import ast
import configparser
import contextlib
import hashlib
import inspect
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch

HERE = Path(__file__).resolve().parent

class FixtureProcesses:
    def __init__(self, audit):
        self.audit = audit
        self.git = Path(shutil.which('git')).resolve()
        self.python = Path(sys.executable).resolve()
        self.hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.git, self.python)}
        self.records, self.roots, self.children = [], [], []
        self.current = None
        self.permit = None
        self.report_root = Path(tempfile.mkdtemp(prefix='bum05-child-reports-', dir=audit.scratch))
        self.empty = self.report_root / 'empty'
        self.empty.mkdir()
        self.real_popen = subprocess.Popen
        self.real_run = subprocess.run
        # Hash exactly the reviewed literal lock payload, not arbitrary -c text.
        tree = ast.parse((audit.root / 'orchestrator/test_worktree_bootstrap.py').read_text(encoding='utf-8'))
        self.lock_script = next(n.value.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                                and any(isinstance(t, ast.Name) and t.id == 'script' for t in n.targets)
                                and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))
        self.audit.processes = self

    def begin(self, test_id):
        self.current, self.roots = test_id, []

    def register(self, path):
        path = Path(path).resolve()
        if not self.current or not path.is_relative_to(self.audit.scratch) or path == self.audit.scratch:
            self.audit.refuse('fixture_registration', path)
        self.roots.append(path)

    def owned(self, path):
        path = Path(path).resolve()
        if not any(path.is_relative_to(root) for root in self.roots):
            self.audit.refuse('process_outside_test_fixture', path)
        return path

    def environment(self, root, supplied):
        if supplied is not None:
            self.audit.refuse('unexpected_process_environment')
        # Construct from a positive list; never inherit GIT_*, credentials,
        # PYTHONPATH, module preloaders, proxies, or user shell configuration.
        env = {k: os.environ[k] for k in ('SystemRoot', 'WINDIR', 'SYSTEMDRIVE') if k in os.environ}
        env.update(TEMP=str(root), TMP=str(root), TMPDIR=str(root), HOME=str(root), USERPROFILE=str(root),
                   PATH=str(self.git.parent), LANG='C', LC_ALL='C',
                   GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_TERMINAL_PROMPT='0', GIT_ASKPASS='', SSH_ASKPASS='', GIT_SSH_COMMAND='false',
                   GIT_PROTOCOL_FROM_USER='0', GIT_ALLOW_PROTOCOL='', GIT_NO_REPLACE_OBJECTS='1',
                   GIT_ATTR_NOSYSTEM='1', GIT_PAGER='', GIT_EDITOR='false', GIT_SEQUENCE_EDITOR='false',
                   GIT_EXEC_PATH=str(self.git.parent), PYTHON_DOTENV_DISABLED='1', PYTHONDONTWRITEBYTECODE='1')
        return env

    def validate_git_fixture(self, cwd, initializing=False):
        # A gitfile/commondir/alternate may redirect a seemingly safe cwd into
        # a different repository. Never trust Git's upward discovery or config
        # includes, even within an otherwise registered TemporaryDirectory.
        owner = next(root for root in self.roots if cwd.is_relative_to(root))
        metadata = cwd / '.git'
        if not initializing and not metadata.exists():
            self.audit.refuse('git_missing_owned_metadata', cwd)
        if not metadata.resolve().is_relative_to(owner):
            self.audit.refuse('git_metadata_escape', metadata)
        if metadata.is_file():
            raw = metadata.read_text(encoding='utf-8').strip()
            if not raw.startswith('gitdir: '): self.audit.refuse('git_invalid_gitfile', metadata)
            metadata = (cwd / raw[8:]).resolve()
        if metadata.exists():
            if not metadata.resolve().is_relative_to(owner):
                self.audit.refuse('git_metadata_escape', metadata)
            common = metadata / 'commondir'
            if common.exists() and not (metadata / common.read_text(encoding='utf-8').strip()).resolve().is_relative_to(owner):
                self.audit.refuse('git_commondir_escape', common)
        for root in self.roots:
            for candidate in root.rglob('*'):
                if candidate.name.lower() in ('alternates', 'http-alternates', '.gitmodules', 'git', 'git.exe', 'git.com', 'git.cmd', 'git.bat'):
                    self.audit.refuse('git_external_fixture_metadata', candidate)
                if not candidate.resolve().is_relative_to(root):
                    self.audit.refuse('git_fixture_path_escape', candidate)

    def git_args(self, args, cwd):
        fixed = [
            ['init', '-b', 'main'], ['config', 'user.email', 'tests@example.invalid'],
            ['config', 'user.name', 'Bootstrap Tests'], ['add', '.'],
            *[['add', p] for p in ('bum.config.json', 'package.json', 'pnpm-workspace.yaml')],
            *[['commit', '-m', message] for message in ('fixture', 'tracked config fixture', 'invalid test pin',
                                                       'missing lockfile fixture', 'escaping glob fixture')],
            ['rm', 'pnpm-lock.yaml'], ['rev-parse', '--abbrev-ref', 'HEAD'],
            ['worktree', 'list', '--porcelain'], ['worktree', 'list', '--porcelain', '-z'],
            ['rev-parse', '--verify', 'bum-run/run_bootstrap'],
            ['rev-parse', '--verify', '--quiet', 'bum-run/run_bootstrap'],
            ['branch', '--list', 'bum-run/run_bootstrap'], ['branch', '-D', 'bum-run/run_bootstrap']]
        valid = args in fixed
        if len(args) == 6 and args[:3] == ['worktree', 'add', '-b'] and args[3] in ('bum-run/run_bootstrap', 'other-fixture') and args[5] == 'HEAD':
            target = self.owned(args[4])
            valid = any(cwd.is_relative_to(r) and target.is_relative_to(r) for r in self.roots)
        if len(args) == 4 and args[:3] == ['worktree', 'remove', '--force']:
            target = self.owned(args[3])
            valid = any(cwd.is_relative_to(r) and target.is_relative_to(r) for r in self.roots)
        if not valid:
            self.audit.refuse('unreviewed_git_argv', repr(args))
        self.validate_git_fixture(cwd, initializing=args[:1] == ['init'])
        if args == ['add', '.']:
            for candidate in cwd.rglob('*'):
                name = candidate.name.lower()
                if name == '.env' or name.startswith('.env.') or name in ('.ssh', '.aws', '.azure', 'credentials', 'credentials.json', 'id_rsa', 'id_ed25519', 'token.json'):
                    self.audit.refuse('git_credential_staging', candidate)
        # No includes, aliases, filters, helpers, hooks or redirects from local
        # config. These fixtures only generate core settings and user identity.
        for root in self.roots:
            for config in root.glob('**/.git/config'):
                parser = configparser.ConfigParser(strict=True)
                parser.read_string(config.read_text(encoding='utf-8'))
                permitted = {'core': {'repositoryformatversion', 'filemode', 'bare', 'logallrefupdates', 'symlinks', 'ignorecase', 'longpaths'},
                             'user': {'name', 'email'}}
                if any(s not in permitted or set(parser[s]) - permitted[s] for s in parser.sections()):
                    self.audit.refuse('unsafe_git_fixture_config', config)
            if list(root.glob('**/.gitattributes')):
                self.audit.refuse('git_fixture_attributes')
        options = {'core.hooksPath': str(self.empty), 'core.fsmonitor': 'false', 'core.untrackedCache': 'false',
                   'core.attributesFile': os.devnull, 'core.pager': '', 'core.editor': 'false',
                   'commit.gpgSign': 'false', 'tag.gpgSign': 'false', 'gc.auto': '0',
                   'maintenance.auto': 'false', 'protocol.allow': 'never', 'protocol.file.allow': 'never',
                   'credential.helper': '', 'diff.external': '', 'core.quotePath': 'false'}
        if args[:1] == ['init']:
            args = [*args, '--template=' + str(self.empty)]
        return [str(self.git), *[v for k, value in options.items() for v in ('-c', k + '=' + value)], *args]

    def prepare(self, argv, kwargs):
        if not isinstance(argv, (list, tuple)) or not argv or not all(isinstance(v, (str, os.PathLike)) for v in argv):
            self.audit.refuse('non_list_process_argv')
        argv = list(map(os.fspath, argv))
        if kwargs.get('shell', False) or kwargs.get('executable') or kwargs.get('preexec_fn') or kwargs.get('startupinfo') or kwargs.get('creationflags', 0):
            self.audit.refuse('unsafe_process_options')
        lock_payload = len(argv) == 5 and argv[1:3] == ['-u', '-c'] and argv[3] == self.lock_script
        if lock_payload and not kwargs.get('cwd'):
            path = self.owned(argv[-1])
            kwargs['cwd'] = next(r for r in self.roots if path.is_relative_to(r))
        root = self.owned(kwargs.get('cwd') or Path.cwd())
        env = self.environment(root, kwargs.get('env'))
        tool = Path(argv[0])
        is_git = argv[0] == 'git' or tool.resolve() == self.git
        is_python = tool.resolve() == self.python
        report = None
        if is_git:
            actual = self.git_args(argv[1:], root)
            executable = self.git
            trace_dir = root / '.git' / 'bum05-process-audit'
            trace_dir.mkdir(parents=True, exist_ok=True)
            trace = trace_dir / ('process-%d.jsonl' % len(self.records))
            env['GIT_TRACE2_EVENT'] = str(trace)
            env['GIT_TRACE2_EVENT_NESTING'] = '20'
        elif is_python:
            payload = argv[1:]
            allowed = [ ['-m', 'compileall', '-q', 'tests'], ['-m', 'compileall', '-q', '-f', 'tests'],
                        ['-m', 'unittest', 'discover', '-s', 'tests'], ['-m', 'unittest', 'discover', '-s', 'tests', '-v'] ]
            mode = 'module'
            if payload not in allowed:
                if len(payload) != 4 or payload[:2] != ['-u', '-c'] or payload[2] != self.lock_script:
                    self.audit.refuse('unreviewed_python_argv', repr(payload))
                self.owned(payload[-1])
                if not Path(payload[-1]).resolve().is_relative_to(root):
                    self.audit.refuse('lock_outside_child_cwd')
                mode, payload = 'lock', [str(Path(payload[-1]).resolve())]
            report = self.report_root / ('child-%d.json' % len(self.records))
            actual = [str(self.python), '-I', '-S', '-B', '-u', str(HERE / 'child_audit.py'),
                      str(root), str(report), mode, *payload]
            executable = self.python
        else:
            self.audit.refuse('unreviewed_process_tool', argv[0])
        record = dict(test=self.current, executable=str(executable), sha256=self.hashes[str(executable)],
                      argv=argv, actual_argv=actual, cwd=str(root),
                      environment_policy='positive-list-v1:no-inherited-GIT/PYTHON/credentials;isolated-home;no-protocols/config/hooks/filters',
                      environment=env, timeout_seconds=30, child_report=str(report) if report else None,
                      git_trace=str(trace) if is_git else None)
        self.records.append(record)
        kwargs.update(cwd=str(root), env=env, shell=False, executable=str(executable))
        self.permit = (str(executable), subprocess.list2cmdline(actual), str(root), env)
        return actual, kwargs, report

    def completed(self, record):
        if record.get('git_trace') and 'git_descendants' not in record:
            try:
                raw = Path(record['git_trace']).read_bytes()
                events = [json.loads(line) for line in raw.decode('utf-8').splitlines()]
            except (OSError, ValueError):
                self.audit.refuse('invalid_or_missing_git_process_trace', record['git_trace'])
            record['git_descendants'] = [e for e in events if e.get('event') == 'child_start']
            record['git_trace_sha256'] = hashlib.sha256(raw).hexdigest()
            if not events or not any(e.get('event') == 'exit' for e in events):
                self.audit.refuse('incomplete_git_process_trace', record['git_trace'])
            expected = [ ['git', 'branch', branch, 'HEAD'] for branch in ('bum-run/run_bootstrap', 'other-fixture') ]
            expected.append(['git', 'reset', '--hard', '--no-recurse-submodules'])
            for event in record['git_descendants']:
                if event.get('use_shell') is not False or event.get('argv') not in expected:
                    self.audit.refuse('unexpected_git_descendant', repr(event))
            owner = next(r for r in self.roots if Path(record['cwd']).is_relative_to(r))
            for event in events:
                if event.get('event') == 'def_repo' and event.get('worktree') and not Path(event['worktree']).resolve().is_relative_to(owner):
                    self.audit.refuse('git_descendant_repository_escape', event['worktree'])

    def allow_event(self, args):
        expected, self.permit = self.permit, None
        return expected is not None and tuple(args) == expected

    def junction(self, argv, kwargs):
        if len(argv) != 6 or argv[:4] not in (['cmd', '/c', 'mklink', '/J'], ['cmd.exe', '/c', 'mklink', '/J']):
            self.audit.refuse('unreviewed_junction_command', repr(argv))
        if kwargs.get('shell') or kwargs.get('env') is not None:
            self.audit.refuse('unsafe_junction_options')
        source, target = self.owned(argv[4]), self.owned(argv[5])
        import _winapi
        _winapi.CreateJunction(str(target), str(source))
        self.records.append(dict(test=self.current, executable='_winapi.CreateJunction',
                                 sha256=self.hashes[str(self.python)], argv=argv, cwd=None,
                                 environment_policy='no-process:Windows-API;both-paths-exact-test-owned', timeout_seconds=0))
        return subprocess.CompletedProcess(argv, 0, '', '')

    @contextlib.contextmanager
    def install(self):
        policy = self
        class AuditedPopen(self.real_popen):
            def __init__(self, argv, *args, **kwargs):
                if args:
                    policy.audit.refuse('positional_process_options')
                actual, kwargs, report = policy.prepare(argv, kwargs)
                self._bum_record = policy.records[-1]
                try:
                    super().__init__(actual, **kwargs)
                finally:
                    policy.permit = None
                self._bum_timer = threading.Timer(30, self._bounded_kill)
                self._bum_timer.daemon = True
                self._bum_timer.start()
                policy.children.append(self)
            def _bounded_kill(self):
                if self.poll() is None:
                    policy.audit.denied.append(dict(event='fixture_process_timeout', path=str(self.pid)))
                    self.kill()
            def wait(self, timeout=None):
                result = super().wait(timeout=min(timeout, 30) if timeout is not None else 30)
                if hasattr(self, '_bum_timer'): self._bum_timer.cancel()
                policy.completed(self._bum_record)
                return result
        def run(argv, *args, **kwargs):
            if isinstance(argv, list) and argv and argv[0] in ('cmd', 'cmd.exe'):
                return policy.junction(argv, kwargs)
            kwargs['timeout'] = min(kwargs.get('timeout', 30), 30)
            return policy.real_run(argv, *args, **kwargs)
        with patch.object(subprocess, 'Popen', AuditedPopen), patch.object(subprocess, 'run', run):
            yield self
        for child in self.children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
                self.audit.refuse('fixture_child_leaked')

    def check_reports(self):
        reports = []
        for record in self.records:
            if record.get('child_report'):
                path = Path(record['child_report'])
                try:
                    report = json.loads(path.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    self.audit.denied.append(dict(event='missing_child_audit_report', path=str(path)))
                    continue
                reports.append(report)
                if report['denied_attempts']:
                    self.audit.denied.extend(report['denied_attempts'])
        return reports
