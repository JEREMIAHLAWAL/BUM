import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from orchestrator.manifest import BumManifest
from orchestrator.repo_tools import get_repo_root, get_active_manifest


def _ownership_section_lines(spec_text: str):
    """Yield ownership lines only from exact, heading-delimited sections.

    Nested role headings belong to FILE BOUNDARIES; unrelated headings (even
    deeper ones) end the grant. Inline mentions and fenced examples are not
    authority. Keep this separate from the signature/token extractors.
    """
    section = None
    section_level = 0
    fence = None
    for line in spec_text.splitlines():
        stripped = line.strip()
        marker = re.match(r"^(`{3,}|~{3,})", stripped)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is not None:
            continue

        markdown = re.match(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        label = stripped.removeprefix("**").removesuffix("**").strip()
        plain = re.fullmatch(r"[A-Za-z][A-Za-z0-9 /(),—–-]*:", label)
        if markdown or plain:
            title = markdown.group(2) if markdown else label
            level = len(markdown.group(1)) if markdown else 7
            title = title.strip("* ").rstrip(":").strip()
            title = re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", title)
            if re.fullmatch(
                r"(?:FILES?(?:\s+TO\s+(?:CREATE(?:\s+OR\s+MODIFY)?|MODIFY|CHANGE))?"
                r"|FILE\s+(?:MODIFICATION\s+)?BOUNDARIES)(?:\s+\(exact paths\))?",
                title, re.IGNORECASE,
            ):
                section, section_level = "file_boundaries", level
            elif re.fullmatch(r"NEEDS\s+CONTEXT|REFERENCE(?:-ONLY)?\s+FILES", title, re.IGNORECASE):
                section, section_level = "reference_files", level
            elif (section == "file_boundaries" and level > section_level and re.match(
                r"^(?:(?:Frontend|Backend|Tester|Coordinator|Planner|Integrator)\b"
                r"|(?:Create|Modify)\s*\((?:Frontend|Backend|Tester|Coordinator|Planner|Integrator)\b)",
                title, re.IGNORECASE,
            )):
                pass  # A nested owner subdivision, not a new authority section.
            else:
                section = None
            continue
        if section:
            yield section, line


def extract_contract_from_spec(spec_text: str, manifest: Optional[BumManifest] = None) -> Dict[str, Any]:
    """
    Extract structured spec contract boundaries from the Planner's spec.md and active manifest.
    
    Extracts:
    - exported_signatures: list of explicit function/type/interface declarations
    - permitted_tokens: allowed theme tokens / design variables
    - negative_constraints: forbidden imports and anti-patterns
    - file_boundaries: exact files allowed to be created or modified
    """
    if manifest is None:
        try:
            manifest = get_active_manifest()
        except Exception:
            manifest = None

    # 1. Negative constraints (from manifest + spec)
    negative_constraints: List[str] = []
    if manifest and manifest.rules:
        if manifest.rules.forbidden_imports:
            negative_constraints.extend([f"forbidden_import: {imp}" for imp in manifest.rules.forbidden_imports])
        if manifest.rules.forbidden_tokens:
            negative_constraints.extend([f"forbidden_token: {tok}" for tok in manifest.rules.forbidden_tokens])

    # Extract negative constraints or forbidden sections from spec
    forbidden_match = re.search(r"(?:FORBIDDEN|NEGATIVE CONSTRAINTS?|DO NOT USE)[\s\S]*?(?=\n\n[A-Z0-9_\- ]+:|\Z)", spec_text, re.IGNORECASE)
    if forbidden_match:
        for line in forbidden_match.group(0).splitlines():
            clean_l = line.strip().lstrip("-* ").strip()
            if clean_l and not re.match(r"^(?:FORBIDDEN|NEGATIVE CONSTRAINTS?|DO NOT USE)", clean_l, re.IGNORECASE):
                if clean_l not in negative_constraints:
                    negative_constraints.append(clean_l)

    # 2. Writable and reference-only paths use the same heading boundaries.
    # Keep route-group parentheses and root-level filenames intact.
    file_boundaries: List[str] = []
    reference_files: List[str] = []
    paths_by_section = {"file_boundaries": file_boundaries, "reference_files": reference_files}
    for section, line in _ownership_section_lines(spec_text):
        for path in re.findall(r"[`']?([a-zA-Z0-9_./\-()]+\.[a-zA-Z0-9]+)[`']?", line):
            if path not in paths_by_section[section]:
                paths_by_section[section].append(path)

    conflicts = sorted(set(file_boundaries).intersection(reference_files))
    if conflicts:
        raise ValueError("Conflicting writable/reference Planner ownership: " + ", ".join(conflicts))

    # 3. Exported signatures
    exported_signatures: List[str] = []
    sig_section = re.search(r"(?:SIGNATURES?|INTERFACES?|EXPORTS?|TYPE\s+DEFINITIONS?)[\s\S]*?(?=\n\n[A-Z0-9_\- ]+:|\Z)", spec_text, re.IGNORECASE)
    if sig_section:
        for line in sig_section.group(0).splitlines():
            clean_l = line.strip().lstrip("-* ").strip()
            if clean_l and not re.match(r"^(?:SIGNATURES?|INTERFACES?|EXPORTS?|TYPE\s+DEFINITIONS?)", clean_l, re.IGNORECASE):
                if clean_l not in exported_signatures:
                    exported_signatures.append(clean_l)

    # 4. Permitted tokens / Theme rules
    permitted_tokens: List[str] = []
    if manifest and manifest.rules and manifest.rules.required_packages:
        permitted_tokens.extend([f"package: {p}" for p in manifest.rules.required_packages])

    token_section = re.search(r"(?:DESIGN\s+TOKENS?|THEME(?:\s+TOKENS?)?|PERMITTED\s+TOKENS?)[\s\S]*?(?=\n\n[A-Z0-9_\- ]+:|\Z)", spec_text, re.IGNORECASE)
    if token_section:
        for line in token_section.group(0).splitlines():
            clean_l = line.strip().lstrip("-* ").strip()
            if clean_l and not re.match(r"^(?:DESIGN\s+TOKENS?|THEME|PERMITTED\s+TOKENS?)", clean_l, re.IGNORECASE):
                if clean_l not in permitted_tokens:
                    permitted_tokens.append(clean_l)

    return {
        "file_boundaries": file_boundaries,
        "reference_files": reference_files,
        "negative_constraints": negative_constraints,
        "exported_signatures": exported_signatures,
        "permitted_tokens": permitted_tokens,
    }


def format_contract_markdown(contract: Dict[str, Any]) -> str:
    """Format contract dict into a strict markdown contract document."""
    lines = [
        "# SPECIFICATION CONTRACT (IMMUTABLE BOUNDARY)",
        "",
        "## 1. FILE MODIFICATION BOUNDARIES",
    ]
    if contract.get("file_boundaries"):
        for f in contract["file_boundaries"]:
            lines.append(f"- `{f}`")
    else:
        lines.append("- (Defined by Planner Spec)")

    lines.extend([
        "",
        "## 1b. REFERENCE-ONLY FILES (READ FOR CONTEXT — DO NOT CREATE OR MODIFY)",
    ])
    if contract.get("reference_files"):
        for f in contract["reference_files"]:
            lines.append(f"- `{f}`")
    else:
        lines.append("- None specified")

    lines.extend([
        "",
        "## 2. NEGATIVE CONSTRAINTS (FORBIDDEN)",
    ])
    if contract.get("negative_constraints"):
        for c in contract["negative_constraints"]:
            lines.append(f"- {c}")
    else:
        lines.append("- None specified")

    lines.extend([
        "",
        "## 3. EXPORTED SIGNATURES & CONTRACTS",
    ])
    if contract.get("exported_signatures"):
        for s in contract["exported_signatures"]:
            lines.append(f"- {s}")
    else:
        lines.append("- None specified")

    lines.extend([
        "",
        "## 4. PERMITTED DESIGN TOKENS & PACKAGES",
    ])
    if contract.get("permitted_tokens"):
        for t in contract["permitted_tokens"]:
            lines.append(f"- {t}")
    else:
        lines.append("- None specified")

    return "\n".join(lines) + "\n"


def write_spec_contract(spec_text: str, manifest: Optional[BumManifest] = None, pipeline_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Extract, format, and persist the specification contract to disk.
    Persists:
    - pipeline/contract.md
    - .bum/contract.json (under repo root)
    """
    contract_data = extract_contract_from_spec(spec_text, manifest=manifest)
    contract_md = format_contract_markdown(contract_data)

    # 1. Write to pipeline directory
    if pipeline_dir is None:
        agent_project_root = Path(__file__).resolve().parent.parent
        pipeline_dir = agent_project_root / "pipeline"

    pipeline_dir.mkdir(parents=True, exist_ok=True)
    (pipeline_dir / "contract.md").write_text(contract_md, encoding="utf-8")

    # 2. Write to repo .bum directory
    try:
        repo_root = get_repo_root()
        bum_dir = repo_root / ".bum"
        bum_dir.mkdir(parents=True, exist_ok=True)
        (bum_dir / "contract.json").write_text(json.dumps(contract_data, indent=2), encoding="utf-8")
    except Exception:
        pass

    return {
        "contract": contract_data,
        "markdown": contract_md,
    }
