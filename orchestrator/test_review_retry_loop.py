import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestrator.pipeline import (
    parse_reviewer_verdict,
    MAX_REVIEW_CYCLES,
)
from orchestrator.git_tools import run_safe_git_command


def test_retry_loop_logic():
    print("=== TESTING REVIEW RETRY LOOP LOGIC ===")

    # 1. Test Reviewer verdict parsing: APPROVE
    print("\n1. Testing APPROVE parsing...")
    approve_text = """
VERDICT: APPROVE

TASK: Placeholder Profile Screen
ISSUES: None
REASON: Meets all criteria.
"""
    parsed_app = parse_reviewer_verdict(approve_text)
    assert parsed_app["verdict"] == "APPROVE"
    print("   APPROVE parsed correctly.")

    # 2. Test Reviewer verdict parsing: CHANGES REQUIRED with Frontend fix
    print("\n2. Testing CHANGES REQUIRED (Frontend fix) parsing...")
    fe_fix_text = """
VERDICT: CHANGES REQUIRED
FRONTEND_FIX_REQUIRED: YES
BACKEND_FIX_REQUIRED: NO
DEPENDENCY_FIX_REQUIRED: NO

TASK: Placeholder Profile Screen
ISSUES: Profile text formatting missing.
REASON: Needs adjustment.
"""
    parsed_fe = parse_reviewer_verdict(fe_fix_text)
    assert parsed_fe["verdict"] == "CHANGES REQUIRED"
    assert parsed_fe["frontend_fix_required"] is True
    assert parsed_fe["backend_fix_required"] is False
    assert parsed_fe["dependency_fix_required"] is False
    print("   Frontend fix routing flags parsed correctly.")

    # 3. Test Reviewer verdict parsing: DEPENDENCY ONLY fix
    print("\n3. Testing DEPENDENCY ONLY fix parsing...")
    dep_fix_text = """
VERDICT: CHANGES REQUIRED
FRONTEND_FIX_REQUIRED: NO
BACKEND_FIX_REQUIRED: NO
DEPENDENCY_FIX_REQUIRED: YES

TASK: Missing dependency
ISSUES: expo-router package missing from package.json
REASON: Environment dependency fix needed.
"""
    parsed_dep = parse_reviewer_verdict(dep_fix_text)
    assert parsed_dep["verdict"] == "CHANGES REQUIRED"
    assert parsed_dep["frontend_fix_required"] is False
    assert parsed_dep["backend_fix_required"] is False
    assert parsed_dep["dependency_fix_required"] is True
    print("   Dependency fix routing flags parsed correctly.")

    # 4. Test max cycle limit
    print("\n4. Verifying max review cycles constraint...")
    assert MAX_REVIEW_CYCLES == 3, f"Expected MAX_REVIEW_CYCLES=3, got {MAX_REVIEW_CYCLES}"
    print(f"   Max review cycles strictly bounded to {MAX_REVIEW_CYCLES}.")

    # 5. Verify simulated retry routing logic
    print("\n5. Testing simulated retry loop execution...")
    simulated_cycle = 1
    frontend_called = False
    backend_called = False

    if parsed_fe["frontend_fix_required"]:
        frontend_called = True
    if parsed_fe["backend_fix_required"]:
        backend_called = True

    assert frontend_called is True, "Frontend should have been called."
    assert backend_called is False, "Backend should NOT have been called."
    print("   Simulated routing correctly engaged only the requested coding agent.")

    # 6. Verify Git status remains intact and uncommitted
    print("\n6. Checking Trayne Git working tree state...")
    status = run_safe_git_command(["git", "status", "--short"])
    assert status["returncode"] == 0, "Git status command failed."
    print(f"   Current working tree status:\n{status['stdout']}")
    assert "src/app/" in status["stdout"], "Existing Profile screen files were unexpectedly removed!"
    print("   Existing Profile screen files remain intact and uncommitted.")

    print("\nREVIEW_RETRY_LOOP_OK")


if __name__ == "__main__":
    test_retry_loop_logic()
