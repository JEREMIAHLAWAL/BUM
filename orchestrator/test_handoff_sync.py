"""
Guards the two HANDOFF.md copies against silent drift.

`Collaboration/HANDOFF.md` is the canonical protocol document that Hermes and Claude read.
`Trayne-Agents/pipeline/HANDOFF.md` is the copy loaded into agent context at run time
(orchestrator/run.py, planner/run_planner.py, declared in pipeline/CONTRACTS.md).

Two copies of the same protocol will diverge, and the failure is silent: the pipeline
keeps running against a stale handoff. This test makes that divergence loud.

Runnable without pytest:  python3 orchestrator/test_handoff_sync.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

WORKSPACE_ROOT = PROJECT_ROOT.parent

CANONICAL_HANDOFF = WORKSPACE_ROOT / "Collaboration" / "HANDOFF.md"
PIPELINE_HANDOFF = PROJECT_ROOT / "pipeline" / "HANDOFF.md"


def _normalise(text: str) -> str:
    """Compare content, not line endings — the two machines commit different ones."""
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def test_both_handoff_copies_exist() -> None:
    assert CANONICAL_HANDOFF.is_file(), f"Missing canonical handoff: {CANONICAL_HANDOFF}"
    assert PIPELINE_HANDOFF.is_file(), (
        f"Missing pipeline handoff: {PIPELINE_HANDOFF}\n"
        "The pipeline loads this file into agent context; it is not optional."
    )


def test_pipeline_handoff_matches_canonical() -> None:
    canonical = _normalise(CANONICAL_HANDOFF.read_text(encoding="utf-8"))
    pipeline = _normalise(PIPELINE_HANDOFF.read_text(encoding="utf-8"))

    if canonical == pipeline:
        return

    canonical_lines = canonical.splitlines()
    pipeline_lines = pipeline.splitlines()
    first_diff = next(
        (
            i
            for i, (a, b) in enumerate(zip(canonical_lines, pipeline_lines), start=1)
            if a != b
        ),
        min(len(canonical_lines), len(pipeline_lines)) + 1,
    )

    raise AssertionError(
        "HANDOFF.md copies have drifted.\n"
        f"  canonical: {CANONICAL_HANDOFF} ({len(canonical_lines)} lines)\n"
        f"  pipeline:  {PIPELINE_HANDOFF} ({len(pipeline_lines)} lines)\n"
        f"  first difference at line {first_diff}\n"
        "Treat Collaboration/HANDOFF.md as the source of truth and re-copy it into "
        "Trayne-Agents/pipeline/."
    )


def test_handoff_contains_no_absolute_paths() -> None:
    """The handoff is read on both machines; an absolute path in it is stale on one."""
    forbidden = ("/Users/", "C:/", "C:\\")
    for path in (CANONICAL_HANDOFF, PIPELINE_HANDOFF):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, (
                f"{path} contains an absolute path fragment {token!r}. "
                "Use workspace-relative paths (see Collaboration/SPEC.md §1)."
            )


def run_handoff_sync_tests() -> None:
    print("=== TESTING HANDOFF PROTOCOL SYNC ===")

    checks = (
        test_both_handoff_copies_exist,
        test_pipeline_handoff_matches_canonical,
        test_handoff_contains_no_absolute_paths,
    )

    for index, check in enumerate(checks, start=1):
        print(f"\n{index}. {check.__name__}...")
        check()
        print("   OK")

    print("\nHANDOFF_SYNC_OK")


if __name__ == "__main__":
    run_handoff_sync_tests()
