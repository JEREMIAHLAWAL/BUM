import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from orchestrator.repo_tools import get_repo_root


def write_verification_evidence(
    command_results: List[Dict[str, Any]],
    stage: str = "tester",
    cycle: int = 1,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Write verification results to disk under .evidence/:
    - .evidence/<stage>_verification.json
    - .evidence/<stage>_output.log
    """
    if repo_root is None:
        try:
            repo_root = get_repo_root()
        except Exception:
            repo_root = Path.cwd()

    evidence_dir = repo_root / ".evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "stage": stage,
        "cycle": cycle,
        "all_passed": True,
        "has_failures": False,
        "commands": [],
        "errors": [],
    }

    log_lines = [
        f"=== BUM VERIFICATION EVIDENCE (Stage: {stage}, Cycle: {cycle}) ===",
        "",
    ]

    for cmd_res in command_results:
        cmd_str = cmd_res.get("command", "")
        rc = cmd_res.get("returncode", 0)
        stdout = cmd_res.get("stdout", "")
        stderr = cmd_res.get("stderr", "")
        timed_out = cmd_res.get("timed_out", False)

        passed = (rc == 0 and not timed_out)
        if not passed:
            summary["all_passed"] = False
            summary["has_failures"] = True

        cmd_entry = {
            "command": cmd_str,
            "returncode": rc,
            "timed_out": timed_out,
            "passed": passed,
            "stdout_len": len(stdout),
            "stderr_len": len(stderr),
        }

        # Extract explicit error lines if failed
        if not passed:
            err_details = []
            for line in (stderr + "\n" + stdout).splitlines():
                clean_l = line.strip()
                if clean_l and any(err_kw in clean_l.lower() for err_kw in ["error", "fail", "cannot find", "not recognized", "exception"]):
                    err_details.append(clean_l)
            cmd_entry["error_highlights"] = err_details[:10]
            summary["errors"].extend(err_details[:10])

        summary["commands"].append(cmd_entry)

        log_lines.extend([
            f"COMMAND: {cmd_str}",
            f"RETURN CODE: {rc}",
            f"TIMED OUT: {timed_out}",
            "--- STDOUT ---",
            stdout.strip(),
            "--- STDERR ---",
            stderr.strip(),
            "=" * 50,
            "",
        ])

    json_path = evidence_dir / f"{stage}_verification.json"
    log_path = evidence_dir / f"{stage}_output.log"

    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log_path.write_text("\n".join(log_lines), encoding="utf-8")

    return {
        "summary": summary,
        "json_path": str(json_path),
        "log_path": str(log_path),
    }


def parse_evidence_on_disk(stage: str = "tester", repo_root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Read and parse the latest verification evidence file from .evidence/."""
    if repo_root is None:
        try:
            repo_root = get_repo_root()
        except Exception:
            repo_root = Path.cwd()

    json_path = repo_root / ".evidence" / f"{stage}_verification.json"
    if not json_path.exists():
        return None

    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return None
