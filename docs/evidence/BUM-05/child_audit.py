"""Isolated trusted entrypoint; installs audit before workload imports/runpy."""
import atexit
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_offline import OfflineAudit


def main():
    root, report, mode, *payload = sys.argv[1:]
    root, report = Path(root).resolve(), Path(report).resolve()
    if Path.cwd().resolve() != root:
        raise SystemExit('child cwd mismatch')
    audit = OfflineAudit(root, HERE)
    native_lock = None
    if mode == 'lock':
        import _winapi
        target = Path(payload[0]).resolve()
        if not target.is_relative_to(root):
            raise SystemExit('lock target escaped fixture')
        native_lock = (_winapi.CreateFile, _winapi.CloseHandle, str(target))
    original = audit.__call__
    native_permit = mode == 'lock'
    def child_policy(event, args):
        nonlocal native_permit
        if event == '_winapi.CreateFile' and native_permit and args[0] == native_lock[2] and args[1:4] == (0x80000000, 3, 3):
            native_permit = False
            return
        if event == 'import' and len(args) > 1 and args[1]:
            path = Path(args[1]).resolve()
            if path.suffix.lower() in ('.pyd', '.dll') and not any(path.is_relative_to(p) for p in audit.trusted):
                audit.refuse('child_untrusted_native_extension', path)
        if event.startswith(('ctypes.', '_winapi.', 'winreg.')) or (event == 'import' and args[0] in ('ctypes', '_ctypes', '_winapi', 'winreg')):
            audit.refuse('child_native_escape:' + event, args[0] if args else event)
        original(event, args)
    def finish():
        audit.active = False
        report.write_text(json.dumps(dict(denied_attempts=audit.denied, cwd=str(root), mode=mode,
                                         payload=payload, audit_before_workload=True)), encoding='utf-8')
        if audit.denied:
            os._exit(97)  # A caught denial must not be reported as a green child.
    atexit.register(finish)
    sys.addaudithook(child_policy)
    sys.path[:] = [str(root), *[p for p in sys.path if p and p != str(HERE) and Path(p).resolve() != root]]
    if mode == 'lock':
        create, close, target = native_lock
        handle = create(target, 0x80000000, 3, 0, 3, 0, 0)
        try:
            print('locked', flush=True)
            sys.stdin.readline()
            import time
            time.sleep(0.05)
        finally:
            close(handle)
    elif mode == 'module':
        import runpy
        if payload[:1] != ['-m'] or payload[1] not in ('compileall', 'unittest'):
            audit.refuse('child_unreviewed_module')
        sys.argv = payload[1:]
        runpy.run_module(payload[1], run_name='__main__', alter_sys=True)
    else:
        audit.refuse('child_unreviewed_mode')

if __name__ == '__main__':
    main()
