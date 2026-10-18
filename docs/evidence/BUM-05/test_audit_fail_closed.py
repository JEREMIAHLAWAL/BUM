"""Real installed-hook negatives. Every side effect must be denied before execution."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bum05_runner", HERE / "run_offline.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def main():
    scratch = Path.home() / "AppData/Local/hermes/cache/scratch"
    audit = runner.OfflineAudit(scratch, runner.ROOT)
    sys.addaudithook(audit)
    probes = {
        "process": lambda: subprocess.run([sys.executable, "-c", "raise SystemExit(99)"]),
        "shell": lambda: os.system("exit 99"),
        "network": lambda: socket.getaddrinfo("localhost", 80),
        "outside_write": lambda: (HERE / "MUST_NOT_EXIST.txt").write_text("forbidden"),
        "pseudo_write": lambda: (HERE / "<unknown>").write_text("forbidden"),
        "shared_artifact_read": lambda: (runner.ROOT / "pipeline/spec.md").read_text(),
        "canonical_context_read": lambda: (runner.ROOT.parent / "Collaboration/HANDOFF.md").read_text(),
        "credential_read": lambda: (scratch / "bum05-nonexistent-credential-probe/.env").read_text(),
    }
    results = {}
    try:
        for name, probe in probes.items():
            count = len(audit.denied)
            try:
                probe()
                results[name] = False
            except PermissionError:
                results[name] = len(audit.denied) == count + 1
    finally:
        audit.active = False
        report = dict(ok=all(results.values()) and len(results) == len(probes), probes=results,
                      denied_attempts=audit.denied, acceptance=False)
        (scratch / "bum05-installed-audit-negatives.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
