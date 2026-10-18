"""BUM-05 offline-only fail-closed audit. No smoke/server/live probes.
Reviewed real processes are confined to exact per-test scratch fixtures.
--allow-dirty-diagnostic never establishes committed-head acceptance.
"""
import argparse
import contextlib
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[3]
RUNNER = Path(__file__).resolve()

def digest(data):
    return hashlib.sha256(data).hexdigest()

def provenance():
    def git(*args):
        return subprocess.run(["git", "--no-optional-locks", *args], cwd=ROOT, capture_output=True, check=True).stdout
    paths = sorted(set(p for base in (ROOT / "orchestrator", RUNNER.parent) for p in base.rglob("*.py")) | {ROOT / "config/agents.yaml"})
    tracked = set(git("ls-files").decode().splitlines())
    head_tracked = set(git('ls-tree', '-r', '--name-only', 'HEAD').decode().splitlines())
    paths = sorted(set(paths) | {ROOT / rel for rel in tracked | head_tracked if rel.endswith(".py")})
    hashes = {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) if p.is_file() else None for p in paths}
    changed = []
    for p in paths:
        rel = p.relative_to(ROOT).as_posix()
        if not p.is_file() or rel not in head_tracked or git("show", "HEAD:" + rel).splitlines() != p.read_bytes().splitlines():
            changed.append(rel)
    diff = git("diff", "HEAD", "--", "orchestrator", str(RUNNER.parent.relative_to(ROOT)), "config/agents.yaml")
    return dict(head=git("rev-parse", "HEAD").decode().strip(), status=git("status", "--porcelain=v1", "--untracked-files=all").decode(),
                diff_sha256=digest(diff), diff=diff.decode(errors="replace"), runner_sha256=digest(RUNNER.read_bytes()),
                file_sha256=hashes, dirty_executable_inputs=changed,
                coordinator_commands="read-only git rev-parse/status/diff/ls-files/show; outside test audit")

class OfflineAudit:
    def __init__(self, scratch, root):
        self.scratch, self.root = scratch.resolve(), root.resolve()
        self.denied, self.allowed, self.active = [], [], True
        self.trusted = {Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()}
    def refuse(self, event, path=None):
        self.denied.append(dict(event=event, path=str(path) if path else None,
                                test=getattr(getattr(self, 'processes', None), 'current', None)))
        raise PermissionError("OFFLINE audit denied: " + event + " " + str(path))
    def path(self, value):
        if not isinstance(value, (str, bytes, os.PathLike)): return None
        value = os.fsdecode(value)
        if value.startswith('\\\\?\\'):
            value = value[4:]
            if value.startswith('UNC\\'): value = '\\\\' + value[4:]
        return Path(value).resolve()
    def mutation(self, value, event):
        path = self.path(value)
        if path is None or not path.is_relative_to(self.scratch): self.refuse(event, path)
    def __call__(self, event, args):
        if not self.active: return
        processes = getattr(self, "processes", None)
        if event == "tempfile.mkdtemp" and processes and processes.current:
            processes.register(args[0])
        if event == "subprocess.Popen" and processes and processes.allow_event(args):
            return
        if event.startswith("socket.") and event != "socket.__new__":
            caller = sys._getframe(1)
            addr = args[1] if len(args)>1 else None
            if (sys.platform == "win32" and caller.f_globals.get("__name__") == "socket"
                and caller.f_code.co_name == "_fallback_socketpair"
                and Path(caller.f_code.co_filename).resolve() == Path(os.__file__).resolve().parent / "socket.py"
                and any(caller.f_locals.get(k) is args[0] for k in ("csock", "ssock", "lsock"))
                and event in ("socket.bind", "socket.connect") and isinstance(addr, tuple) and addr[0] in ("127.0.0.1", "::1")):
                self.allowed.append(dict(event=event, purpose="exact Windows stdlib socketpair")); return
            self.refuse(event)
        if event.startswith(("subprocess.", "os.exec", "os.spawn", "os.posix_spawn")) or event in ("os.system", "os.startfile", "os.startfile/2", "pty.spawn"):
            self.refuse(event)
        if event == "open":
            value, mode, flags = args
            path = self.path(value)
            if path is None:
                caller = sys._getframe(1)
                if caller.f_code.co_name == 'child_policy' and Path(caller.f_code.co_filename).resolve() == RUNNER.parent / 'child_audit.py':
                    caller = caller.f_back
                if (isinstance(value, int) and caller.f_code.co_name == '_write_atomic'
                    and caller.f_code.co_filename == '<frozen importlib._bootstrap_external>'
                    and self.path(caller.f_locals.get('path')) is not None
                    and self.path(caller.f_locals.get('path')).is_relative_to(self.scratch)):
                    return
                if (processes and isinstance(value, int) and caller.f_globals.get("__name__") == "subprocess"
                    and Path(caller.f_code.co_filename).resolve() == Path(subprocess.__file__).resolve()):
                    return
                self.refuse("open_file_descriptor")
            fixture_dummy_write = (processes and path.name == ".env" and mode == "w"
                                   and any(path.is_relative_to(r) for r in processes.roots))
            if not fixture_dummy_write and any(n.lower() == ".env" or n.lower().startswith(".env.") or n.lower() in (".ssh", ".aws", ".azure", "credentials", "credentials.json", "id_rsa", "id_ed25519", "token.json") for n in path.parts):
                self.refuse("credential_file", path)
            # inspect/linecache may probe synthetic code filenames. Permit only
            # nonexistent pseudo-files: this cannot expose any file contents.
            pseudo = path.name == "<unknown>" or (path.name.startswith("__editable__.") and path.name.endswith(".__path_hook__"))
            writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            if pseudo and not writing and not path.exists():
                return
            if writing: self.mutation(value, event)
            elif not (path.is_relative_to(self.scratch) or (path.is_relative_to(self.root) and path.suffix in (".py", ".pyc")) or path == self.root / "config/agents.yaml" or any(path.is_relative_to(b) and not path.is_relative_to(self.root) for b in self.trusted)):
                self.refuse("outside_fixture_read", path)
        elif event in ("os.mkdir", "os.rmdir", "os.remove", "os.chmod", "os.utime", "os.truncate"): self.mutation(args[0],event)
        elif event in ("os.rename", "os.link", "os.symlink"):
            self.mutation(args[0],event); self.mutation(args[1],event)
        elif event == "shutil.rmtree":
            self.mutation(args[0], event)
            if len(args) > 1 and args[1] is not None:
                self.refuse("relative_directory_descriptor")
        elif event.startswith("shutil."):
            for value in args[:2]: self.mutation(value,event)

def flatten(suite):
    for test in suite:
        if isinstance(test,unittest.TestSuite): yield from flatten(test)
        else: yield test

def group(report, name, setup, modules):
    log = io.StringIO(); start = time.perf_counter()
    record = dict(name=name, tests_run=0, ok=False, setup_error=None)
    report["groups"].append(record)
    try:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log), contextlib.ExitStack() as stack:
            setup(stack)
            suite = unittest.TestSuite()
            for module in modules:
                loaded = importlib.import_module(module)
                if name == "full_offline_suite": report["full_modules_loaded"].append(module)
                suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(loaded))
            record["collected_test_ids"] = [t.id() for t in flatten(suite)]
            expected = len(record['collected_test_ids']) if name == 'full_offline_suite' else 3
            if expected < 1 or len(record['collected_test_ids']) != expected or len(set(record['collected_test_ids'])) != expected:
                raise RuntimeError('Suite inventory mismatch: expected %d unique tests' % expected)
            record['expected_tests'] = expected
            if name == "full_offline_suite":
                stack.enter_context(report["_processes"].install())
            ts = time.perf_counter()
            processes = report.get("_processes")
            class FixtureResult(unittest.TextTestResult):
                def startTest(self, test):
                    if processes: processes.begin(test.id())
                    super().startTest(test)
            result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=FixtureResult).run(suite)
            record.update(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
                          ok=result.wasSuccessful() and not result.skipped and result.testsRun == expected, unittest_seconds=time.perf_counter()-ts,
                          failure_details=[dict(test=str(t),traceback=tb) for t,tb in result.failures+result.errors])
    except BaseException:
        record["setup_error"] = traceback.format_exc(); log.write(record["setup_error"])
    record.update(elapsed_seconds=time.perf_counter()-start, log=log.getvalue())
    print(log.getvalue(),end="")
    return record["ok"]

def enforce_exact_head(before, allow_dirty_diagnostic):
    if before["dirty_executable_inputs"] and not allow_dirty_diagnostic:
        raise RuntimeError("Exact-head mode refuses dirty executable code/test/runner inputs")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--allow-dirty-diagnostic",action="store_true")
    parser.add_argument("--probe-setup-failure",action="store_true")
    args = parser.parse_args()
    scratch = (Path.home()/"AppData/Local/hermes/cache/scratch").resolve()
    output = args.output.resolve()
    if not output.is_relative_to(scratch): parser.error("--output must be beneath coordinator Hermes scratch")
    scratch.mkdir(parents=True,exist_ok=True)
    os.environ.update(TEMP=str(scratch),TMP=str(scratch),TMPDIR=str(scratch),PYTHON_DOTENV_DISABLED="1")
    sys.dont_write_bytecode=True; sys.path.insert(0,str(ROOT))
    report = dict(python=sys.version,scratch=str(scratch),groups=[],provenance={},full_modules_loaded=[],ok=False,acceptance=False,
                  console_readiness="NOT_EVALUATED_OFFLINE_ONLY",fatal_error=None,mode="dirty_diagnostic_not_acceptance" if args.allow_dirty_diagnostic else "exact_head")
    audit=None
    try:
        report["provenance"]["before"]=provenance()
        enforce_exact_head(report["provenance"]["before"], args.allow_dirty_diagnostic)
        audit=OfflineAudit(scratch,ROOT)
        processes=FixtureProcesses(audit)
        report["_processes"]=processes
        sys.addaudithook(audit)
        if group(report,"import_safety",lambda stack: None,["orchestrator.test_legacy_import_safety"]) and not audit.denied:
            def isolate(stack):
                if args.probe_setup_failure: raise RuntimeError("deliberate setup failure before full suite loading")
                stack.enter_context(patch("dotenv.load_dotenv",return_value=False))
                fixture=scratch/("bum05-project-"+str(os.getpid())); fixture.mkdir(exist_ok=False)
                # Make the reference-manifest contract non-vacuous: its conditional
                # assertions must run against explicit scratch data, not a missing file.
                (fixture / 'bum.config.json').write_text(json.dumps({
                    'name': 'TRAYNE offline fixture', 'project_type': 'react-native-expo',
                    'rules': {'forbidden_imports': ['@expo/vector-icons', 'date-fns'],
                              'required_packages': ['lucide-react-native']},
                    'verification': {'typecheck_cmd': 'npm run ts:check', 'test_cmd': 'npm test'}
                }), encoding='utf-8')
                repo=importlib.import_module("orchestrator.repo_tools")
                for key,value in (("_ACTIVE_PROJECT_PATH",fixture),("_RUN_WORKTREE_OVERRIDE",None),("DERIVED_REPO_PATH",fixture),("AGENTS_ROOT",fixture),("WORKSPACE_ROOT",fixture)):
                    stack.enter_context(patch.object(repo,key,value))
                def boot_probe(argv,**kwargs):
                    if Path(kwargs.get("cwd","")).resolve()==ROOT and argv in (["git","rev-parse","HEAD"],["git","log","-1","--format=%s","offline-fixture"]):
                        report.setdefault("mocked_import_probes",[]).append(argv)
                        return subprocess.CompletedProcess(argv,0,"offline-fixture\n","")
                    audit.refuse("unexpected_import_subprocess")
                with patch("subprocess.run",side_effect=boot_probe): importlib.import_module("orchestrator.agent_flow.server")
                pipeline=importlib.import_module("orchestrator.pipeline")
                stack.enter_context(patch.object(pipeline,"PIPELINE_DIR",fixture / "pipeline"))
            modules=["orchestrator."+p.stem for p in sorted((ROOT/"orchestrator").glob("test_*.py"))]
            report["requested_full_modules"]=modules
            group(report,"full_offline_suite",isolate,modules)
    except BaseException: report["fatal_error"]=traceback.format_exc()
    finally:
        processes = report.pop("_processes", None)
        if processes:
            report["child_audit_reports"] = processes.check_reports()
            report["allowed_processes"] = processes.records
        if audit: audit.active=False
        try:
            report["provenance"]["after"]=provenance()
            report["provenance"]["unchanged"]=report["provenance"].get("before")==report["provenance"]["after"]
        except BaseException: report["provenance"]["after_error"]=traceback.format_exc()
        report["denied_attempts"]=audit.denied if audit else []
        report["allowed_stdlib_socketpairs"]=audit.allowed if audit else []
        report["ok"]=not report["fatal_error"] and len(report["groups"])==2 and all(g["ok"] for g in report["groups"]) and not report["denied_attempts"] and report["provenance"].get("unchanged",False)
        report["acceptance"]=report["ok"] and not args.allow_dirty_diagnostic and not args.probe_setup_failure
        output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(dict(ok=report["ok"],acceptance=report["acceptance"],output=str(output))))
    return 0 if report["ok"] else 1

sys.path.insert(0, str(RUNNER.parent))
from fixture_processes import FixtureProcesses

if __name__=="__main__": raise SystemExit(main())
