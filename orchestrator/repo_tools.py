from pathlib import Path
import os
import re
from typing import Optional

from dotenv import load_dotenv

from orchestrator.manifest import load_manifest, find_manifest, BumManifest


load_dotenv()

AGENTS_ROOT = Path(__file__).resolve().parent.parent

# The orchestrator and the Trayne repo are siblings inside the synced workspace, so
# the repo location is derivable from this file. Absolute paths cannot be committed
# or synced here: the workspace mounts at a different point on each dev machine.
WORKSPACE_ROOT = AGENTS_ROOT.parent
DERIVED_REPO_PATH = WORKSPACE_ROOT / "CLAUDE" / "trayne"

_ACTIVE_PROJECT_PATH: Optional[Path] = None
_RUN_WORKTREE_OVERRIDE: Optional[Path] = None


def set_active_project_path(path: Optional[Path]) -> None:
    """Dynamically set the active project root during runtime."""
    global _ACTIVE_PROJECT_PATH
    _ACTIVE_PROJECT_PATH = path.resolve() if path else None


def get_active_project_path() -> Optional[Path]:
    """Retrieve the dynamically active project path if set."""
    return _ACTIVE_PROJECT_PATH


def set_run_worktree_override(path: Optional[Path]) -> None:
    """Point repo resolution at an isolated per-run git worktree instead of the
    real checkout. Highest precedence in resolve_repo_root(): while a run's
    worktree is active, every read/write/git/command helper in this process
    transparently operates on the throwaway worktree, so a destructive or
    buggy pipeline run can never touch the real checkout's uncommitted work.
    Pass None to clear and fall back to the real checkout again."""
    global _RUN_WORKTREE_OVERRIDE
    _RUN_WORKTREE_OVERRIDE = path.resolve() if path else None


def get_run_worktree_override() -> Optional[Path]:
    return _RUN_WORKTREE_OVERRIDE


def list_available_projects() -> list[dict]:
    """
    Discover all workspace repositories and return metadata for project switcher.
    Inspects each directory for a bum.config.json workspace manifest.
    """
    projects = []
    current_root, source = resolve_repo_root()

    # 1. Primary Trayne Mobile App (CLAUDE/trayne)
    derived = DERIVED_REPO_PATH.resolve()
    trayne_manifest = load_manifest(derived) if derived.is_dir() else None
    projects.append({
        "id": "trayne",
        "name": trayne_manifest.name if trayne_manifest else "TRAYNE (Mobile App)",
        "path": str(derived),
        "exists": derived.is_dir(),
        "is_active": (current_root == derived),
        "type": trayne_manifest.project_type if trayne_manifest else "expo_react_native",
        "has_manifest": find_manifest(derived) is not None if derived.is_dir() else False,
    })

    # 2. BUM / Trayne Agents Orchestrator (BUM)
    agents_dir = AGENTS_ROOT.resolve()
    agents_manifest = load_manifest(agents_dir) if agents_dir.is_dir() else None
    projects.append({
        "id": "bum-orchestrator",
        "name": agents_manifest.name if agents_manifest else "BUM (Orchestrator)",
        "path": str(agents_dir),
        "exists": agents_dir.is_dir(),
        "is_active": (current_root == agents_dir),
        "type": agents_manifest.project_type if agents_manifest else "python_orchestrator",
        "has_manifest": find_manifest(agents_dir) is not None if agents_dir.is_dir() else False,
    })

    # 3. Discover any other subdirectories under WORKSPACE_ROOT
    if WORKSPACE_ROOT.is_dir():
        for item in sorted(WORKSPACE_ROOT.iterdir()):
            if item.is_dir() and not item.name.startswith((".", "__")):
                if item.resolve() not in (derived, agents_dir):
                    is_active = (current_root == item.resolve())
                    manifest = load_manifest(item.resolve())
                    has_manifest = find_manifest(item.resolve()) is not None
                    projects.append({
                        "id": item.name.lower().replace(" ", "-"),
                        "name": manifest.name if has_manifest else item.name,
                        "path": str(item.resolve()),
                        "exists": True,
                        "is_active": is_active,
                        "type": manifest.project_type if has_manifest else "repo",
                        "has_manifest": has_manifest,
                    })

    return projects


def get_active_manifest() -> BumManifest:
    """Load and return the manifest for the active project repository."""
    repo = get_repo_root()
    return load_manifest(repo)



def resolve_repo_root() -> tuple[Path, str]:
    """
    Resolve the repository root and report where the value came from.

    Precedence:
      0. Active run worktree override (_RUN_WORKTREE_OVERRIDE) — an isolated
         git worktree for the currently executing pipeline run, if one exists.
      1. Dynamic runtime selection (_ACTIVE_PROJECT_PATH)
      2. TRAYNE_REPO_PATH (environment or .env) — escape hatch for an alternate checkout.
      3. The path derived from this file's location inside the workspace.
    """
    if _RUN_WORKTREE_OVERRIDE is not None:
        return _RUN_WORKTREE_OVERRIDE, "run_worktree"

    if _ACTIVE_PROJECT_PATH is not None:
        return _ACTIVE_PROJECT_PATH, "dynamic_selection"

    configured_path = os.getenv("TRAYNE_REPO_PATH")

    if configured_path and configured_path.strip():
        clean_path = configured_path.strip().strip("\"'").replace("\t", "\\t")
        return Path(clean_path).expanduser().resolve(), "TRAYNE_REPO_PATH"

    return DERIVED_REPO_PATH.resolve(), "derived"


def get_repo_root() -> Path:
    """
    Locate and validate the Trayne repository root. See resolve_repo_root for precedence.
    """
    repo, source = resolve_repo_root()

    if source == "TRAYNE_REPO_PATH":
        remedy = (
            "Please verify that TRAYNE_REPO_PATH points to a valid directory, "
            "or unset it to fall back to the workspace-relative default "
            f"({DERIVED_REPO_PATH})."
        )
    else:
        remedy = (
            f"Expected the Trayne repo at the workspace-relative default, derived from "
            f"{AGENTS_ROOT}. Either restore it there, or set TRAYNE_REPO_PATH to an "
            "alternate checkout."
        )

    if not repo.exists():
        raise FileNotFoundError(
            f"Trayne repo path does not exist: {repo} (source: {source})\n{remedy}"
        )

    if not repo.is_dir():
        raise NotADirectoryError(
            f"Trayne repo path is not a directory: {repo} (source: {source})\n{remedy}"
        )

    return repo


def run_preflight_check(required_executables: Optional[list[str]] = None) -> dict:
    """
    Verify the Trayne repository configuration and required tools before running the pipeline.
    """
    import shutil

    if required_executables is None:
        required_executables = ["git", "npm", "npx"]

    repo = get_repo_root()

    missing_tools = [exe for exe in required_executables if not shutil.which(exe)]
    if missing_tools:
        raise EnvironmentError(
            f"Preflight check failed: Required executable(s) missing from PATH: {', '.join(missing_tools)}.\n"
            "Please ensure these tools are installed and accessible in your system PATH."
        )

    return {
        "repo_root": str(repo),
        "verified_executables": required_executables,
        "status": "ready",
    }


FORBIDDEN_WRITE_PREFIXES = (
    ".git",
    ".env",
    "node_modules",
    "package.json",
    "package-lock.json",
    "tsconfig.json",
    "jest.config.js",
    "src/domain",
    "src/db",
)


def safe_path(relative_path: str) -> Path:
    repo = get_repo_root()
    target = (repo / relative_path).resolve()

    try:
        target.relative_to(repo)
    except ValueError:
        raise PermissionError(
            f"Attempted access outside Trayne repo: {relative_path}"
        )

    return target


def read_file(relative_path: str) -> str:
    path = safe_path(relative_path)

    if not path.exists():
        raise FileNotFoundError(f"File does not exist: {relative_path}")

    if not path.is_file():
        raise IsADirectoryError(f"Not a file: {relative_path}")

    return path.read_text(encoding="utf-8")


def check_write_allowed(target: Path, relative_path: str) -> bool:
    repo = get_repo_root()
    rel = target.relative_to(repo)
    posix_rel = rel.as_posix()

    if not rel.parts:
        raise PermissionError("Cannot write to repository root directly.")

    # 1. Global unbypassable protection (.git, .env)
    for prefix in (".git", ".env"):
        if (
            posix_rel == prefix
            or posix_rel.startswith(f"{prefix}/")
            or rel.parts[0] == prefix
            or rel.name.startswith(".env")
        ):
            raise PermissionError(
                f"Write access forbidden for protected system path: {relative_path}"
            )

    # 2. Check active manifest rules if defined
    manifest = get_active_manifest()
    if manifest and manifest.rules:
        # Check prohibited files
        if manifest.rules.prohibited_files:
            for proh in manifest.rules.prohibited_files:
                clean_proh = proh.strip().lstrip("/")
                if posix_rel == clean_proh or posix_rel.startswith(f"{clean_proh}/"):
                    raise PermissionError(
                        f"Write access forbidden by manifest rule for path: {relative_path}"
                    )

        # Check allowed write roots if explicitly configured
        if manifest.rules.allowed_write_roots:
            allowed = False
            for root in manifest.rules.allowed_write_roots:
                clean_root = root.strip().strip("/")
                if posix_rel == clean_root or posix_rel.startswith(f"{clean_root}/"):
                    allowed = True
                    break
            # Root files (like temporary test files in root) or allowed dirs
            if not allowed and len(rel.parts) > 1:
                raise PermissionError(
                    f"Write access outside allowed manifest roots ({manifest.rules.allowed_write_roots}): {relative_path}"
                )

    # 3. Default fallback protection when no custom manifest rules exist
    if not (manifest and (manifest.rules.prohibited_files or manifest.rules.allowed_write_roots)):
        for prefix in FORBIDDEN_WRITE_PREFIXES:
            if (
                posix_rel == prefix
                or posix_rel.startswith(f"{prefix}/")
                or rel.parts[0] == prefix
            ):
                raise PermissionError(
                    f"Write access forbidden for protected path: {relative_path}"
                )

    return True



def write_file(relative_path: str, content: str, role: str = "orchestrator") -> dict:
    """
    Safely write or update a file inside the Trayne repository.
    Enforces repository boundaries, forbidden path restrictions, and audits write actions.
    """
    path = safe_path(relative_path)
    check_write_allowed(path, relative_path)

    created = not path.exists()

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    action = "created" if created else "modified"
    print(f"[AUDIT WRITE] Role: {role} | Action: {action} | File: {relative_path}", flush=True)

    return {
        "role": role,
        "path": relative_path,
        "action": action,
        "success": True,
    }


def delete_file(relative_path: str, role: str = "orchestrator") -> dict:
    """
    Safely delete a file inside the Trayne repository.
    Enforces repository boundaries and forbidden path restrictions.
    """
    path = safe_path(relative_path)
    check_write_allowed(path, relative_path)

    if not path.exists():
        raise FileNotFoundError(f"Cannot delete nonexistent file: {relative_path}")

    if path.is_dir():
        raise IsADirectoryError(f"Cannot delete directory using delete_file: {relative_path}")

    path.unlink()
    print(f"[AUDIT DELETE] Role: {role} | File: {relative_path}", flush=True)

    return {
        "role": role,
        "path": relative_path,
        "action": "deleted",
        "success": True,
    }


def file_exists(relative_path: str) -> bool:
    return safe_path(relative_path).exists()


def list_directory(relative_path: str = ".") -> list[str]:
    path = safe_path(relative_path)

    if not path.exists():
        return []

    if not path.is_dir():
        raise NotADirectoryError(f"Not a directory: {relative_path}")

    return sorted(item.name for item in path.iterdir())


FILE_REF_PATTERN = re.compile(r'@file:([^\s]+)')


def resolve_file_reference(ref_path: str) -> Optional[Path]:
    """Resolve a bare @file: reference against agents root, active repo root,
    and workspace root (same precedence as the UI prompt-preview endpoint)."""
    clean = ref_path.strip()
    if not clean:
        return None

    agents_root = AGENTS_ROOT.resolve()
    workspace_root = WORKSPACE_ROOT.resolve()
    try:
        repo_root = get_repo_root().resolve()
    except Exception:
        repo_root = None

    candidates = [agents_root / clean, workspace_root / clean]
    if repo_root:
        candidates.insert(1, repo_root / clean)

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            if resolved.is_file() and (
                resolved.is_relative_to(agents_root)
                or (repo_root and resolved.is_relative_to(repo_root))
                or resolved.is_relative_to(workspace_root)
            ):
                return resolved
        except Exception:
            continue
    return None


def resolve_task_file_references(task: str) -> str:
    """Expand @file:<path> references inside a task string into inlined file
    content blocks, so the Planner (no tool access) can see referenced prompt
    files without needing to fetch them itself."""
    matches = list(FILE_REF_PATTERN.finditer(task))
    if not matches:
        return task

    seen = set()
    appended_blocks = []
    for match in matches:
        ref = match.group(1).rstrip(".,;:)")
        if ref in seen:
            continue
        seen.add(ref)

        resolved = resolve_file_reference(ref)
        if resolved:
            try:
                content = resolved.read_text(encoding="utf-8")
                appended_blocks.append(
                    f"\n\n--- REFERENCED FILE: {ref} ---\n{content}\n--- END FILE: {ref} ---"
                )
            except Exception as exc:
                appended_blocks.append(
                    f"\n\n[WARNING: Found '@file:{ref}' but failed to read it: {exc}]"
                )
        else:
            appended_blocks.append(
                f"\n\n[WARNING: Could not resolve '@file:{ref}' under agents root, repo root, "
                "or workspace root. The Planner has no tool access and cannot fetch this file "
                "itself — verify the path.]"
            )

    return task + "".join(appended_blocks)


def get_file_boundary_contents(file_boundaries: list, max_chars: int = 160000, reference_files: Optional[list] = None) -> str:
    """Read current on-disk content of every file named in the spec contract's
    file_boundaries and format it for injection into Frontend/Backend prompts.

    Frontend/Backend have no read tool, so without this they cannot safely
    modify any existing file named in the contract (they must guess its
    content or refuse).

    `reference_files` (optional) are READ-ONLY context files the Planner
    flagged (e.g. a NEEDS CONTEXT section) that are not being created or
    modified — things like `src/theme/colors.ts` whose exact export shape
    Frontend must import correctly but never touch. They are inlined in a
    clearly separate, explicitly read-only block so agents can't confuse
    them with files they're allowed to write.

    Files are read smallest-first so a single large file (e.g. a seed data
    file) cannot starve several small-but-critical files (e.g. a port
    interface) out of the budget. The two lists share one combined char
    budget to keep the prompt bounded."""
    if not file_boundaries and not reference_files:
        return ""

    try:
        repo_root = get_repo_root()
    except Exception:
        return ""

    def _collect(paths: list) -> list:
        collected = []
        for rel_path in paths or []:
            clean_rel = rel_path.strip().strip("`").lstrip("./")
            if not clean_rel:
                continue
            try:
                candidate = (repo_root / clean_rel).resolve()
                candidate.relative_to(repo_root.resolve())
            except Exception:
                continue

            if not candidate.is_file():
                continue

            try:
                size = candidate.stat().st_size
            except Exception:
                size = 0
            collected.append((size, clean_rel, candidate))
        return collected

    candidates = []
    skipped_missing = []

    for rel_path in file_boundaries:
        clean_rel = rel_path.strip().strip("`").lstrip("./")
        if not clean_rel:
            continue
        try:
            candidate = (repo_root / clean_rel).resolve()
            candidate.relative_to(repo_root.resolve())
        except Exception:
            continue

        if not candidate.is_file():
            skipped_missing.append(clean_rel)
            continue

        try:
            size = candidate.stat().st_size
        except Exception:
            size = 0
        candidates.append((size, clean_rel, candidate))

    reference_candidates = _collect(reference_files)

    # Smallest files first so the budget is spent on breadth, not hogged by
    # one large file (e.g. a seed/fixture file) at the expense of several
    # small-but-load-bearing files (e.g. a port interface).
    candidates.sort(key=lambda item: item[0])
    reference_candidates.sort(key=lambda item: item[0])

    blocks = []
    total_chars = 0
    truncated_names = []

    for _size, clean_rel, candidate in candidates:
        try:
            content = candidate.read_text(encoding="utf-8")
        except Exception as exc:
            blocks.append(f"--- EXISTING FILE: {clean_rel} ---\n[Could not read: {exc}]\n--- END FILE: {clean_rel} ---")
            continue

        block = f"--- EXISTING FILE: {clean_rel} ---\n{content}\n--- END FILE: {clean_rel} ---"
        if total_chars + len(block) > max_chars:
            truncated_names.append(clean_rel)
            continue
        blocks.append(block)
        total_chars += len(block)

    reference_blocks = []
    reference_truncated_names = []

    for _size, clean_rel, candidate in reference_candidates:
        try:
            content = candidate.read_text(encoding="utf-8")
        except Exception as exc:
            reference_blocks.append(f"--- REFERENCE FILE (READ-ONLY): {clean_rel} ---\n[Could not read: {exc}]\n--- END FILE: {clean_rel} ---")
            continue

        block = f"--- REFERENCE FILE (READ-ONLY): {clean_rel} ---\n{content}\n--- END FILE: {clean_rel} ---"
        if total_chars + len(block) > max_chars:
            reference_truncated_names.append(clean_rel)
            continue
        reference_blocks.append(block)
        total_chars += len(block)

    if not blocks and not skipped_missing and not reference_blocks and not reference_truncated_names:
        return ""

    header = (
        "=== EXISTING FILE CONTENTS (for files named in the IMMUTABLE SPEC CONTRACT file "
        "boundaries that already exist on disk) ===\n"
        "You have no file-read tool. These are the ACTUAL current contents of the files you "
        "may need to modify. A `write:path` block replaces the ENTIRE file, so when editing an "
        "existing file below, reproduce it in full with only your intended changes applied — "
        "never guess or reconstruct content from memory.\n"
    )
    footer = "=== END EXISTING FILE CONTENTS ===\n"
    body = "\n\n".join(blocks) if blocks else ""

    notes = []
    if skipped_missing:
        notes.append(
            "NOTE: the following contract file_boundaries do not exist on disk yet "
            "(safe to create fresh with a `write:` block): " + ", ".join(skipped_missing)
        )
    if truncated_names:
        notes.append(
            "WARNING: the following files exist but were too large to fit in the context "
            "budget and are NOT shown above — do NOT guess their contents or write to them "
            "blind; report them as NEEDS CONTEXT instead: " + ", ".join(truncated_names)
        )

    notes_block = ("\n" + "\n".join(notes) + "\n") if notes else ""

    reference_section = ""
    if reference_blocks or reference_truncated_names:
        ref_header = (
            "\n\n=== REFERENCE-ONLY FILE CONTENTS (READ-ONLY — do NOT create, modify, or write "
            "to any file in this section; these exist purely so you import the correct real "
            "export names/shapes instead of guessing) ===\n"
        )
        ref_body = "\n\n".join(reference_blocks) if reference_blocks else ""
        ref_notes = ""
        if reference_truncated_names:
            ref_notes = (
                "\nWARNING: the following reference files exist but were too large to fit in "
                "the context budget and are NOT shown above — do NOT guess their exported "
                "names/shapes; report them as NEEDS CONTEXT instead: " + ", ".join(reference_truncated_names) + "\n"
            )
        ref_footer = "=== END REFERENCE-ONLY FILE CONTENTS ===\n"
        reference_section = ref_header + ref_body + ref_notes + ref_footer

    return header + body + notes_block + footer + reference_section


def repo_tree(max_depth: int = 3) -> str:
    repo = get_repo_root()
    lines = []

    ignored = {
        ".git",
        "node_modules",
        ".expo",
        "coverage",
        "dist",
        "build",
    }

    def walk(directory: Path, depth: int):
        if depth > max_depth:
            return

        try:
            items = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return

        for item in items:
            if item.name in ignored:
                continue

            relative = item.relative_to(repo)
            prefix = "  " * depth

            if item.is_dir():
                lines.append(f"{prefix}{relative}/")
                walk(item, depth + 1)
            else:
                lines.append(f"{prefix}{relative}")

    walk(repo, 0)

    return "\n".join(lines)
