import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from orchestrator.manifest import BumManifest
from orchestrator.repo_tools import get_repo_root, get_active_manifest


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

    # 2. File boundaries
    file_boundaries: List[str] = []
    # Match bulleted file lists or FILES TO CREATE / MODIFY
    files_section = re.search(r"(?:FILES?(?:\s+TO\s+(?:CREATE|MODIFY|CHANGE))?|FILE\s+BOUNDARIES)[\s\S]*?(?=\n\n[A-Z0-9_\- ]+:|\Z)", spec_text, re.IGNORECASE)
    if files_section:
        for line in files_section.group(0).splitlines():
            # Match paths like `src/app/index.tsx` or - src/app/index.tsx
            # or `src/app/(app)/_layout.tsx` (Expo Router / Next.js route-group
            # folders use parens, e.g. `(app)`, `(auth)` — the char class must
            # include '()' or the match truncates to just "_layout.tsx" with
            # no slash, silently dropping the path from file_boundaries).
            match = re.findall(r"[`']?([a-zA-Z0-9_./\-()]+\.[a-zA-Z0-9]+)[`']?", line)
            for m in match:
                if "/" in m or "\\" in m:
                    clean_path = m.replace("\\", "/").strip("./")
                    if clean_path not in file_boundaries:
                        file_boundaries.append(clean_path)

    # 2b. Reference-only files (NEEDS CONTEXT): read-only files the Planner
    # flags as required reading before implementation but that are NOT in
    # file_boundaries (not being created/modified). Frontend/Backend have no
    # read tool, so without this extraction these paths are dead prompt text
    # and agents guess at import names/shapes (e.g. hallucinating a `theme`
    # export that doesn't exist). Anchored to an actual markdown heading
    # line so it can't false-match an inline mention of the phrase elsewhere
    # in the spec (e.g. inside a NEGATIVE CONSTRAINTS bullet).
    reference_files: List[str] = []
    needs_context_section = re.search(
        r"^#{1,6}\s*\d*\.?\s*NEEDS\s+CONTEXT.*$([\s\S]*?)(?=^#{1,6}\s|\Z)",
        spec_text,
        re.IGNORECASE | re.MULTILINE,
    )
    if needs_context_section:
        for line in needs_context_section.group(1).splitlines():
            # Same parens fix as file_boundaries above — route-group paths
            # like `(app)/_layout.tsx` must not be truncated.
            match = re.findall(r"[`']?([a-zA-Z0-9_./\-()]+\.[a-zA-Z0-9]+)[`']?", line)
            for m in match:
                if "/" in m or "\\" in m:
                    clean_path = m.replace("\\", "/").strip("./")
                    if clean_path not in reference_files and clean_path not in file_boundaries:
                        reference_files.append(clean_path)

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
