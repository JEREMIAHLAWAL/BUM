import json
import os.path
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
    # Each heading carries its effective authority. Popping siblings restores
    # the parent, never the previous nested owner's/reference section.
    headings = []
    fence = None
    lines = spec_text.splitlines()
    skip_underline = False
    for index, line in enumerate(lines):
        if skip_underline:
            skip_underline = False
            continue
        # Indented code and blockquotes are examples, even inside a grant.
        if re.match(r"^(?: {4}| {0,3}\t| {0,3}>)", line):
            continue
        stripped = line.strip()
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence is not None:
            if (marker and marker.group(1)[0] == fence[0]
                    and len(marker.group(1)) >= len(fence) and not marker.group(2).strip()):
                fence = None
            continue
        if marker:
            fence = marker.group(1)
            continue

        markdown = re.match(r"^ {0,3}(#{1,6})(?:\s+(.*?)|\s*)$", line)
        underline = (re.fullmatch(r" {0,3}(=+|-+)\s*", lines[index + 1])
                     if index + 1 < len(lines) and stripped else None)
        # Do not reinterpret list entries as setext heading text.
        setext = underline and not re.match(r"^(?:[-+*]\s|>|`|~)", stripped)
        label = stripped.rstrip(":").strip()
        bold = re.fullmatch(r"\*\*(.+?)\*\*", label)
        if bold:
            label = bold.group(1).rstrip(":").strip()
        plain = re.fullmatch(r"(?:\d+[a-z]?(?:\.\d+)*\.?\s+)?[A-Za-z][A-Za-z0-9 /(),—–-]*", label)
        conventional = plain and (stripped.endswith(":") or bold or label.isupper())
        if markdown or setext or conventional:
            if markdown:
                title = re.sub(r"\s+#+\s*$", "", markdown.group(2) or "")
                level = len(markdown.group(1))
            elif setext:
                title = stripped
                level = 1 if underline.group(1)[0] == "=" else 2
                skip_underline = True
            else:
                title, level = label, 7
            title = title.rstrip(":").strip().strip("* ").rstrip(":").strip()
            title = re.sub(r"^\d+[a-z]?(?:\.\d+)*\.?\s+", "", title, flags=re.IGNORECASE)
            owner = re.match(
                r"^(?:(?:Frontend|Backend|Tester|Coordinator|Planner|Integrator)\b"
                r"|(?:Create|Modify)\s*\((?:Frontend|Backend|Tester|Coordinator|Planner|Integrator)\b)",
                title, re.IGNORECASE,
            )
            if (not markdown and not setext and owner
                    and any(rank == 7 and kind for rank, kind in headings)):
                level = 8  # Conventional role labels nest under plain authority labels.
            while headings and headings[-1][0] >= level:
                headings.pop()
            parent = headings[-1][1] if headings else None
            if parent == "reference_files":
                section = parent  # No nested label can upgrade a read-only section.
            elif re.fullmatch(
                r"(?:FILES?(?:\s+TO\s+(?:CREATE(?:\s+OR\s+MODIFY)?|MODIFY|CHANGE))?"
                r"|FILE\s+(?:MODIFICATION\s+)?BOUNDARIES)(?:\s+\(exact paths\))?",
                title, re.IGNORECASE,
            ):
                section = "file_boundaries"
            elif re.fullmatch(
                r"(?:NEEDS\s+CONTEXT|REFERENCE(?:-ONLY)?\s+FILES)"
                r"(?:\s+\(READ FOR CONTEXT — DO NOT CREATE OR MODIFY\))?",
                title, re.IGNORECASE,
            ):
                section = "reference_files"
            elif parent == "file_boundaries" and owner:
                section = parent
            else:
                section = None
            headings.append((level, section))
            continue
        if headings and headings[-1][1]:
            yield headings[-1][1], line


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
        # Match whole tokens before validating them. Searching for filename
        # substrings would turn [id]/page.tsx or **/page.tsx into /page.tsx.
        # A quote is not a token separator: retain the entire chunk so an
        # unmatched delimiter or an attached suffix cannot manufacture a grant.
        for match in re.finditer(r"(?:`[^`]*`|'[^']*'|\"[^\"]*\"|[^\s,;<>])+", line):
            path = match.group(0)
            if len(path) >= 2 and path[0] in "`'\"" and path[-1] == path[0]:
                path = path[1:-1]
            if (re.fullmatch(r"[A-Za-z0-9_./()\[\]-]+\.[A-Za-z0-9]+", path)
                    and path not in paths_by_section[section]):
                paths_by_section[section].append(path)

    # Only validated, whole literal paths reach identity comparison. Lexical
    # normpath catches dot segments/repeated separators; normcase additionally
    # catches Windows case aliases. Neither performs filesystem/repo lookups.
    # This identity is ONLY a conflict veto, never a normalized permission grant:
    # retain the Planner's exact spelling in both stored lists and diagnostics.
    def identity(path):
        return os.path.normcase(os.path.normpath(path))

    reference_identities = {identity(path) for path in reference_files}
    conflicting_identities = {identity(path) for path in file_boundaries} & reference_identities
    conflicts = sorted({path for path in file_boundaries + reference_files
                        if identity(path) in conflicting_identities})
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
