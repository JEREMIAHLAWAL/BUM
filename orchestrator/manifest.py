"""
BUM Workspace Manifest Engine.

Defines schemas and parsing logic for `bum.config.json` configuration files,
allowing the orchestrator to operate across arbitrary repos, frameworks,
and verification environments dynamically.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ValidationError


class ManifestRules(BaseModel):
    """Rules and negative constraints enforced across planning, dev, and review stages."""
    forbidden_imports: List[str] = Field(
        default_factory=list,
        description="Module / package names prohibited from being imported directly."
    )
    required_packages: List[str] = Field(
        default_factory=list,
        description="Packages that must be preferred or used for specific capabilities."
    )
    forbidden_tokens: List[str] = Field(
        default_factory=list,
        description="Regex patterns or strings prohibited in code artifacts (e.g. legacy token patterns)."
    )
    allowed_write_roots: List[str] = Field(
        default_factory=list,
        description="Directories relative to project root that agents are authorized to modify."
    )
    prohibited_files: List[str] = Field(
        default_factory=list,
        description="Specific file paths that agents must never write or modify."
    )


class ManifestVerification(BaseModel):
    """Dynamic commands executed to verify code health."""
    typecheck_cmd: Optional[str] = Field(
        None,
        description="Shell command to execute typecheck gate (e.g., 'npm run ts:check', 'tsc --noEmit', 'mypy .')."
    )
    test_cmd: Optional[str] = Field(
        None,
        description="Shell command to execute automated unit/integration tests (e.g., 'npm test', 'pytest')."
    )
    lint_cmd: Optional[str] = Field(
        None,
        description="Shell command to run static analysis or linter (e.g., 'npm run lint', 'flake8')."
    )
    build_cmd: Optional[str] = Field(
        None,
        description="Optional command to execute full build verification."
    )


class ManifestContext(BaseModel):
    """File paths and patterns used by the context extraction engine."""
    type_skeleton_paths: List[str] = Field(
        default_factory=list,
        description="Key type/interface files to extract AST skeletons from for agent context."
    )
    domain_paths: List[str] = Field(
        default_factory=list,
        description="Directories containing domain logic, models, or core entities."
    )
    spec_dirs: List[str] = Field(
        default_factory=lambda: ["pipeline/"],
        description="Directories where specs, task prompts, and changes are stored."
    )
    excluded_paths: List[str] = Field(
        default_factory=lambda: ["node_modules/", ".git/", "dist/", "build/", ".venv/", "__pycache__/"],
        description="Paths ignored during context extraction."
    )


class BumManifest(BaseModel):
    """Complete workspace manifest schema for BUM projects."""
    name: str = Field(..., description="Human-readable project name.")
    project_type: str = Field(
        "general",
        description="Framework / language identifier (e.g., 'react-native-expo', 'nextjs', 'fastapi', 'rust', 'general')."
    )
    version: str = Field("1.0.0", description="Configuration version.")
    description: Optional[str] = Field(None, description="Brief description of the workspace project.")
    rules: ManifestRules = Field(default_factory=ManifestRules)
    verification: ManifestVerification = Field(default_factory=ManifestVerification)
    context: ManifestContext = Field(default_factory=ManifestContext)


MANIFEST_FILENAMES = ["bum.config.json", ".bum/config.json", "agent.config.json"]


def find_manifest(start_dir: Path) -> Optional[Path]:
    """
    Search for a BUM manifest file starting at `start_dir`.
    Returns the resolved Path if found, otherwise None.
    """
    if not start_dir.is_dir():
        return None

    for fname in MANIFEST_FILENAMES:
        candidate = start_dir / fname
        if candidate.is_file():
            return candidate.resolve()

    return None


def load_manifest(manifest_path_or_dir: Path) -> BumManifest:
    """
    Load and parse a BumManifest from a file path or directory.
    If a directory is passed, attempts to find a manifest inside it.
    If no manifest is found or parsing fails, returns a default fallback manifest.
    """
    target_file: Optional[Path] = None

    if manifest_path_or_dir.is_file():
        target_file = manifest_path_or_dir
    elif manifest_path_or_dir.is_dir():
        target_file = find_manifest(manifest_path_or_dir)

    if not target_file or not target_file.is_file():
        # Fallback to default generic manifest inferred from directory name
        dir_name = manifest_path_or_dir.name if manifest_path_or_dir.is_dir() else manifest_path_or_dir.parent.name
        return generate_default_manifest(
            root_dir=manifest_path_or_dir if manifest_path_or_dir.is_dir() else manifest_path_or_dir.parent,
            name=dir_name or "workspace"
        )

    try:
        raw_text = target_file.read_text(encoding="utf-8")
        data = json.loads(raw_text)
        return BumManifest.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as e:
        # Return fallback with error indication in description
        dir_name = target_file.parent.name
        fallback = generate_default_manifest(target_file.parent, name=dir_name)
        fallback.description = f"Fallback manifest (failed to parse {target_file.name}: {e})"
        return fallback


def generate_default_manifest(
    root_dir: Path,
    name: Optional[str] = None,
    project_type: Optional[str] = None
) -> BumManifest:
    """
    Generate a smart default manifest for a project by inspecting files in root_dir.
    Useful for 'bum init' or greenfield repos without manual configuration.
    """
    proj_name = name or root_dir.name or "workspace"
    inferred_type = project_type or "general"
    verification = ManifestVerification()
    context = ManifestContext()
    rules = ManifestRules()

    # Heuristic detection based on repository files
    if (root_dir / "package.json").is_file():
        try:
            pkg_raw = (root_dir / "package.json").read_text(encoding="utf-8")
            pkg_data = json.loads(pkg_raw)
            scripts = pkg_data.get("scripts", {})

            if "expo" in pkg_data.get("dependencies", {}):
                inferred_type = "react-native-expo"
            elif "next" in pkg_data.get("dependencies", {}):
                inferred_type = "nextjs"
            else:
                inferred_type = "node"

            if "ts:check" in scripts:
                verification.typecheck_cmd = "npm run ts:check"
            elif (root_dir / "tsconfig.json").is_file():
                verification.typecheck_cmd = "npx tsc --noEmit"

            if "test" in scripts:
                verification.test_cmd = "npm test"
            if "lint" in scripts:
                verification.lint_cmd = "npm run lint"

        except Exception:
            inferred_type = "node"

    elif (root_dir / "pyproject.toml").is_file() or (root_dir / "requirements.txt").is_file():
        inferred_type = "python"
        verification.typecheck_cmd = "mypy ."
        verification.test_cmd = "pytest"

    elif (root_dir / "Cargo.toml").is_file():
        inferred_type = "rust"
        verification.typecheck_cmd = "cargo check"
        verification.test_cmd = "cargo test"

    return BumManifest(
        name=proj_name,
        project_type=inferred_type,
        version="1.0.0",
        description=f"Auto-generated manifest for {proj_name}",
        rules=rules,
        verification=verification,
        context=context,
    )
