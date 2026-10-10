import re
import shlex
from pathlib import Path
from typing import Dict, List, Optional
from orchestrator.command_tools import run_safe_command
from orchestrator.manifest import load_manifest, BumManifest


ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text: str) -> str:
    """Strip ANSI escape codes from terminal output."""
    if not text:
        return ""
    return ANSI_ESCAPE_RE.sub("", text)


def extract_type_skeletons(repo_root: Path, max_chars: int = 4000, manifest: Optional[BumManifest] = None) -> str:
    """
    Scan type declaration files in the repo and extract
    high-signal type definitions, interfaces, and enums without function bodies.
    Uses manifest context configuration when available.
    """
    if not repo_root or not repo_root.exists():
        return ""

    if manifest is None:
        try:
            manifest = load_manifest(repo_root)
        except Exception:
            manifest = None

    type_files = []

    # 1. Use explicit type skeleton paths from manifest if configured
    if manifest and manifest.context and manifest.context.type_skeleton_paths:
        for rel_pattern in manifest.context.type_skeleton_paths:
            match_path = (repo_root / rel_pattern).resolve()
            if match_path.is_file():
                if match_path not in type_files:
                    type_files.append(match_path)
            else:
                for match in repo_root.glob(rel_pattern):
                    if match.is_file() and match not in type_files:
                        type_files.append(match)

    # 2. Fall back to standard candidate patterns if no specific paths found
    if not type_files:
        candidate_patterns = [
            "src/**/types.ts",
            "src/**/types/*.ts",
            "src/domain/**/*.ts",
            "src/theme/**/*.ts",
            "**/*types*.py",
            "**/*models*.py",
        ]
        for pattern in candidate_patterns:
            for match in repo_root.glob(pattern):
                if match.is_file() and not match.name.endswith((".test.ts", ".spec.ts", "_test.py")):
                    # Skip common ignore directories
                    posix_str = match.as_posix()
                    if any(ign in posix_str for ign in ["node_modules", ".git", ".venv", "__pycache__", "dist", "build"]):
                        continue
                    if match not in type_files:
                        type_files.append(match)

    skeletons = []
    total_chars = 0

    type_block_pattern = re.compile(
        r"((?:export\s+)?(?:type|interface|enum)\s+[A-Za-z0-9_]+(?:\s*<[^>]+>)?\s*(?:=\s*[^;]+;|(?:\s*extends\s+[^{]+)?\s*\{[^}]*\}))|"
        r"(class\s+[A-Za-z0-9_]+(?:\([^)]*\))?:(?:\s*\n(?:\s{4,}.*\n?)+))",
        re.MULTILINE,
    )

    for file_path in sorted(type_files):
        try:
            rel_path = file_path.relative_to(repo_root).as_posix()
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            continue

        matches = type_block_pattern.findall(content)
        if not matches:
            continue

        clean_blocks = []
        for match_item in matches:
            if isinstance(match_item, tuple):
                block = next((m for m in match_item if m), "")
            else:
                block = match_item
            block_stripped = block.strip()
            if block_stripped:
                clean_blocks.append(block_stripped)

        if clean_blocks:
            file_header = f"// File: {rel_path}"
            file_summary = file_header + "\n" + "\n\n".join(clean_blocks)
            if total_chars + len(file_summary) > max_chars:
                remaining = max_chars - total_chars
                if remaining > 100:
                    skeletons.append(file_summary[:remaining] + "\n// ... [truncated for context budget]")
                break
            skeletons.append(file_summary)
            total_chars += len(file_summary)

    if not skeletons:
        return ""

    return "=== TYPE SKELETONS & REPO CONTRACTS ===\n" + "\n\n".join(skeletons) + "\n=== END TYPE SKELETONS ==="


def sanitize_test_output(raw_output: str, max_lines: int = 60) -> str:
    """
    Extract high-signal failure and assertion blocks from test runners (Vitest/Jest/Pytest).
    Removes verbose runtime banners, ANSI colors, and noisy module stack traces.
    """
    if not raw_output:
        return ""

    clean_text = strip_ansi(raw_output)
    lines = clean_text.splitlines()

    filtered_lines: List[str] = []
    capture = False
    failure_keywords = ["FAIL", "FAILED", "Error:", "Expected:", "Received:", "AssertionError", "✕", "●", "at "]

    for line in lines:
        stripped = line.strip()
        # Always keep failure markers, errors, and assertion diffs
        if any(keyword in line for keyword in failure_keywords):
            filtered_lines.append(line)
            capture = True
        elif capture and (stripped.startswith("+") or stripped.startswith("-") or stripped.startswith("-->") or "..." in stripped):
            filtered_lines.append(line)
        elif capture and not stripped:
            filtered_lines.append(line)
        elif "Tests:" in line or "Test Suites:" in line or "passed" in line or "failed" in line:
            filtered_lines.append(line)

    if not filtered_lines:
        filtered_lines = lines[-max_lines:]

    if len(filtered_lines) > max_lines:
        filtered_lines = filtered_lines[:max_lines] + ["... [test output truncated for brevity]"]

    return "\n".join(filtered_lines).strip()


def run_typecheck_gate(repo_root: Path, manifest: Optional[BumManifest] = None) -> Dict[str, any]:
    """
    Execute compiler/typecheck verification using manifest command or default discovery.
    Returns a structured dictionary with success status and sanitized error lines.
    """
    if not repo_root or not repo_root.exists():
        return {"success": False, "error": "Invalid repo root", "output": ""}

    if manifest is None:
        try:
            manifest = load_manifest(repo_root)
        except Exception:
            manifest = None

    # 1. Manifest configured typecheck command
    if manifest and manifest.verification and manifest.verification.typecheck_cmd:
        cmd_parts = shlex.split(manifest.verification.typecheck_cmd)
        res = run_safe_command(cmd_parts, cwd=str(repo_root), timeout=60)
        clean_out = strip_ansi(res.get("stdout", "") + "\n" + res.get("stderr", "")).strip()
        return {
            "success": res.get("returncode") == 0,
            "gate": manifest.verification.typecheck_cmd,
            "returncode": res.get("returncode", -1),
            "output": clean_out,
        }

    # 2. Check for tsconfig.json (TypeScript fallback)
    if (repo_root / "tsconfig.json").exists():
        res = run_safe_command(["npm", "run", "ts:check"], cwd=str(repo_root), timeout=60)
        clean_out = strip_ansi(res.get("stdout", "") + "\n" + res.get("stderr", "")).strip()
        return {
            "success": res.get("returncode") == 0,
            "gate": "typescript",
            "returncode": res.get("returncode", -1),
            "output": clean_out,
        }

    return {"success": True, "gate": "none", "output": "No typechecker configured"}
