"""Run only BUM-02 offline gates with fail-closed side-effect auditing.

Invoke from the BUM repository root. No console, provider or external process is
started. Fixture writes are restricted to Hermes scratch. Not broad discovery.
"""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import time
import unittest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="JSON result under Hermes scratch")
    args = parser.parse_args()
    scratch = (Path.home() / "AppData/Local/hermes/cache/scratch").resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    output = args.output.resolve()
    if not output.is_relative_to(scratch):
        parser.error("--output must be under Hermes scratch")
    os.environ.update(TMPDIR=str(scratch), TEMP=str(scratch), TMP=str(scratch), PYTHON_DOTENV_DISABLED="1")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    denied = []
    local_socketpairs = []

    def check_path(path, event):
        if isinstance(path, (str, bytes, os.PathLike)):
            candidate = Path(os.fsdecode(path)).resolve()
            if not candidate.is_relative_to(scratch):
                denied.append({"event": event, "path": str(candidate)})
                raise AssertionError("Filesystem mutation outside scratch: " + str(candidate))

    def audit(event, values):
        if event == "socket.connect":
            # Windows asyncio's self-pipe uses stdlib's loopback socketpair
            # fallback. Permit only its exact caller/socket, not general HTTP
            # or loopback connections made by application/provider code.
            caller = sys._getframe(1)
            address = values[1]
            if (caller.f_globals.get("__name__") == "socket"
                    and caller.f_code.co_name == "_fallback_socketpair"
                    and caller.f_locals.get("csock") is values[0]
                    and isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1")):
                local_socketpairs.append({"event": event, "purpose": "stdlib socketpair self-pipe"})
                return
        if event in ("subprocess.Popen", "os.system", "os.posix_spawn", "os.spawn", "socket.connect", "socket.connect_ex", "socket.sendto"):
            denied.append({"event": event})
            raise AssertionError("External process/network forbidden: " + event)
        if event == "open":
            path, mode, flags = values
            if isinstance(path, (str, bytes, os.PathLike)):
                name = Path(os.fsdecode(path)).name.lower()
                if name == ".env" or name.startswith(".env."):
                    denied.append({"event": event, "credential_file": True})
                    raise AssertionError("Credential-file read forbidden")
                if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
                    check_path(path, event)
        elif event in ("os.mkdir", "os.rmdir", "os.remove", "os.chmod", "os.utime", "os.truncate"):
            check_path(values[0], event)
        elif event in ("os.rename", "os.link", "os.symlink"):
            check_path(values[0], event)
            check_path(values[1], event)
        elif event.startswith("shutil."):
            for value in values[:2]:
                check_path(value, event)

    sys.addaudithook(audit)
    groups = [
        ("import_safety", ["orchestrator.test_legacy_import_safety"]),
        ("bum02_scoped", ["orchestrator.test_bum02_artifacts",
                          "orchestrator.test_artifact_scope_and_batch.ArtifactScopeTests",
                          "orchestrator.test_artifact_scope_and_batch.CanonicalSourceStageTests"]),
    ]
    report = {"python": sys.version, "scratch": str(scratch), "groups": [], "denied_attempts": denied,
              "allowed_stdlib_socketpairs": local_socketpairs}
    for name, tests in groups:
        log = io.StringIO()
        started = time.perf_counter()
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            suite = unittest.defaultTestLoader.loadTestsFromNames(tests)
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        record = {"name": name, "tests": tests, "tests_run": result.testsRun,
                  "failures": len(result.failures), "errors": len(result.errors),
                  "skipped": len(result.skipped), "ok": result.wasSuccessful(),
                  "elapsed_seconds": round(time.perf_counter() - started, 3), "log": log.getvalue()}
        report["groups"].append(record)
        print(record["log"], end="")
        if not result.wasSuccessful():
            break
    report["ok"] = len(report["groups"]) == len(groups) and all(group["ok"] for group in report["groups"]) and not denied
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("AUDIT:", json.dumps({"ok": report["ok"], "denied_attempts": denied, "output": str(output)}))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
