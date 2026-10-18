"""Bounded audited regression for the scratch-only API prompt fixture."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bum05_runner", HERE / "run_offline.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def main():
    scratch = Path.home() / "AppData/Local/hermes/cache/scratch"
    os.environ.update(TEMP=str(scratch), TMP=str(scratch), TMPDIR=str(scratch), PYTHON_DOTENV_DISABLED="1")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(runner.ROOT))
    audit = runner.OfflineAudit(scratch, runner.ROOT)
    sys.addaudithook(audit)
    log = io.StringIO()
    result = None
    try:
        def boot(argv, **kwargs):
            if Path(kwargs.get("cwd", "")).resolve() == runner.ROOT and argv in (
                    ["git", "rev-parse", "HEAD"], ["git", "log", "-1", "--format=%s", "offline-fixture"]):
                return subprocess.CompletedProcess(argv, 0, "offline-fixture", "")
            audit.refuse("unexpected_import_subprocess")
        with patch("subprocess.run", side_effect=boot), patch("dotenv.load_dotenv", return_value=False):
            suite = unittest.defaultTestLoader.loadTestsFromName(
                "orchestrator.test_agent_flow_backend.TestAgentFlowBackend.test_prompt_preview_endpoint_and_security")
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    finally:
        audit.active = False
        report = dict(tests_run=result.testsRun if result else 0, ok=bool(result and result.wasSuccessful() and not result.skipped and not audit.denied),
                      denied_attempts=audit.denied, allowed_stdlib_socketpairs=audit.allowed, log=log.getvalue(), acceptance=False)
        output = scratch / "bum05-prompt-fixture-regression.json"
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
