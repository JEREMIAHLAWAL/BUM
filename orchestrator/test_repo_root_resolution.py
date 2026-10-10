"""
Guards the Trayne repo path against per-machine rot.

The workspace is synced between a Mac and a Windows box, which mount it at different
absolute paths. Any hardcoded absolute path in the synced tree is therefore stale on at
least one machine. These tests assert the repo root resolves with no configuration at
all, so a fresh checkout on either machine works without hand-editing .env.

Runnable without pytest:  python3 orchestrator/test_repo_root_resolution.py
"""

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestrator.repo_tools import (
    AGENTS_ROOT,
    DERIVED_REPO_PATH,
    get_repo_root,
    resolve_repo_root,
)

ENV_VAR = "TRAYNE_REPO_PATH"


@contextmanager
def repo_path_env(value: Optional[str]) -> Iterator[None]:
    """Set (or clear) TRAYNE_REPO_PATH for the duration of the block, then restore it."""
    previous = os.environ.get(ENV_VAR)
    if value is None:
        os.environ.pop(ENV_VAR, None)
    else:
        os.environ[ENV_VAR] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(ENV_VAR, None)
        else:
            os.environ[ENV_VAR] = previous


def test_resolves_without_configuration() -> None:
    """The primary guarantee: zero config on a fresh machine."""
    with repo_path_env(None):
        repo, source = resolve_repo_root()
        assert source == "derived", f"Expected derived source, got {source}"
        assert repo == DERIVED_REPO_PATH.resolve(), f"Unexpected derived path: {repo}"
        assert get_repo_root() == repo, "get_repo_root disagreed with resolve_repo_root"


def test_derived_path_is_anchored_to_this_file() -> None:
    """
    The derived path must be a function of the orchestrator's own location, not of any
    machine-specific prefix. If someone reintroduces a hardcoded root, this fails.
    """
    assert DERIVED_REPO_PATH == AGENTS_ROOT.parent / "CLAUDE" / "trayne", (
        f"Derived path is no longer anchored to AGENTS_ROOT: {DERIVED_REPO_PATH}"
    )
    assert AGENTS_ROOT == Path(__file__).resolve().parent.parent, (
        "AGENTS_ROOT does not match the orchestrator package location"
    )


def test_derived_target_exists_in_this_workspace() -> None:
    """Catches the repo being moved or renamed without updating the derivation."""
    with repo_path_env(None):
        repo = get_repo_root()
        assert repo.is_dir(), f"Derived repo root is not a directory: {repo}"
        assert (repo / "package.json").is_file(), (
            f"Derived repo root does not look like the Trayne app: {repo}"
        )


def test_env_var_overrides_derived_path(tmp_dir: Optional[Path] = None) -> None:
    """The escape hatch still works for an alternate checkout."""
    override = tmp_dir or AGENTS_ROOT
    with repo_path_env(str(override)):
        repo, source = resolve_repo_root()
        assert source == ENV_VAR, f"Expected env source, got {source}"
        assert repo == override.resolve(), f"Override not honoured: {repo}"
        assert get_repo_root() == override.resolve()


def test_blank_env_var_falls_back_to_derived() -> None:
    """An empty or whitespace value is a non-answer, not a fatal error."""
    for blank in ("", "   ", "\n"):
        with repo_path_env(blank):
            _, source = resolve_repo_root()
            assert source == "derived", f"Blank value {blank!r} did not fall back"


def test_quoted_env_var_is_unwrapped() -> None:
    """.env values are frequently pasted with surrounding quotes."""
    with repo_path_env(f'"{AGENTS_ROOT}"'):
        repo, source = resolve_repo_root()
        assert source == ENV_VAR
        assert repo == AGENTS_ROOT.resolve(), f"Quotes not stripped: {repo}"


def test_missing_override_raises_with_fallback_hint() -> None:
    """A stale override must name the derived default so the fix is obvious."""
    missing = AGENTS_ROOT / "definitely-not-a-real-directory"
    with repo_path_env(str(missing)):
        try:
            get_repo_root()
        except FileNotFoundError as exc:
            message = str(exc)
            assert ENV_VAR in message, "Error does not name the offending variable"
            assert str(DERIVED_REPO_PATH) in message, (
                "Error does not point at the workspace-relative default"
            )
        else:
            raise AssertionError("Expected FileNotFoundError for a missing override")


def test_file_override_raises_not_a_directory() -> None:
    with repo_path_env(str(Path(__file__).resolve())):
        try:
            get_repo_root()
        except NotADirectoryError:
            pass
        else:
            raise AssertionError("Expected NotADirectoryError for a file override")


def run_repo_root_resolution_tests() -> None:
    print("=== TESTING TRAYNE REPO ROOT RESOLUTION ===")

    checks = (
        test_resolves_without_configuration,
        test_derived_path_is_anchored_to_this_file,
        test_derived_target_exists_in_this_workspace,
        test_env_var_overrides_derived_path,
        test_blank_env_var_falls_back_to_derived,
        test_quoted_env_var_is_unwrapped,
        test_missing_override_raises_with_fallback_hint,
        test_file_override_raises_not_a_directory,
    )

    for index, check in enumerate(checks, start=1):
        print(f"\n{index}. {check.__name__}...")
        check()
        print("   OK")

    with repo_path_env(None):
        print(f"\nResolved repo root (no config): {get_repo_root()}")

    print("\nREPO_ROOT_RESOLUTION_OK")


if __name__ == "__main__":
    run_repo_root_resolution_tests()
