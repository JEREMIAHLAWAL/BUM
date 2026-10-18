import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))





def test_dependency_tools():
    from orchestrator.dependency_tools import (
        build_dependency_command,
        validate_package_name,
        parse_dependency_request,
        execute_controlled_dependency_action,
        DependencyActionError,
        ALLOWED_EXPO_PACKAGES,
    )
    from orchestrator.git_tools import run_safe_git_command

    print("=== TESTING CONTROLLED DEPENDENCY ACTIONS ===")

    # 1. Test NPM_CI parsing and command generation
    print("\n1. Testing NPM_CI...")
    req_ci = parse_dependency_request("DEPENDENCY_ACTION: NPM_CI\nREASON: lockfile sync")
    assert req_ci["action"] == "NPM_CI"
    cmd_ci = build_dependency_command(req_ci["action"])
    assert cmd_ci == ["npm", "ci"], f"Expected ['npm', 'ci'], got {cmd_ci}"
    res_ci = execute_controlled_dependency_action("NPM_CI", dry_run=True)
    assert res_ci["returncode"] == 0
    print("   NPM_CI validated and structured correctly.")

    # 2. Test EXPO_INSTALL with valid packages
    print("\n2. Testing EXPO_INSTALL with approved package list...")
    req_expo_text = """
DEPENDENCY_ACTION: EXPO_INSTALL
DEPENDENCY_PACKAGES:
expo-router
react-native-safe-area-context
react-native-screens
expo-linking
expo-constants
expo-status-bar
"""
    req_expo = parse_dependency_request(req_expo_text)
    assert req_expo["action"] == "EXPO_INSTALL"
    assert len(req_expo["packages"]) == 6
    cmd_expo = build_dependency_command(req_expo["action"], req_expo["packages"])
    assert cmd_expo[:3] == ["npx", "expo", "install"]
    assert cmd_expo[3:] == req_expo["packages"]
    res_expo = execute_controlled_dependency_action("EXPO_INSTALL", req_expo["packages"], dry_run=True)
    assert res_expo["returncode"] == 0
    print(f"   EXPO_INSTALL constructed exact command: {' '.join(cmd_expo)}")

    # 3. Test rejection of unapproved/random package install
    print("\n3. Testing rejection of unapproved packages (e.g. random-package)...")
    try:
        build_dependency_command("EXPO_INSTALL", ["random-package"])
        raise AssertionError("Security failure: Unapproved package was not rejected!")
    except DependencyActionError as e:
        print(f"   Correctly rejected unapproved package: {e}")

    # 4. Test rejection of arbitrary npm install
    print("\n4. Testing rejection of arbitrary actions (e.g. NPM_INSTALL)...")
    try:
        build_dependency_command("NPM_INSTALL", ["express"])
        raise AssertionError("Security failure: NPM_INSTALL was not rejected!")
    except DependencyActionError as e:
        print(f"   Correctly rejected arbitrary action: {e}")

    # 5. Test rejection of shell chaining / injection in package names
    print("\n5. Testing rejection of shell chaining/injection...")
    malicious_inputs = [
        "expo-router; rm -rf /",
        "expo-router && ls",
        "expo-router | cat",
        "$(whoami)",
        "`calc.exe`",
        "../traversal",
        "expo-router\nmalicious-pkg",
    ]
    for mal in malicious_inputs:
        try:
            validate_package_name(mal)
            raise AssertionError(f"Security failure: Malicious input '{mal}' was not blocked!")
        except DependencyActionError as e:
            pass
    print("   All shell injection and character chaining attempts blocked.")

    # 6. Verify existing Trayne working tree remains intact & uncommitted
    print("\n6. Checking Trayne Git working tree state...")
    status = run_safe_git_command(["git", "status", "--short"])
    assert status["returncode"] == 0
    print(f"   Current working tree status:\n{status['stdout']}")
    assert "src/app/" in status["stdout"], "Existing Profile screen files were unexpectedly removed!"
    print("   Existing Profile screen files and package changes remain intact and uncommitted.")

    print("\nCONTROLLED_DEPENDENCY_ACTIONS_OK")


def main():
    test_dependency_tools()


if __name__ == "__main__":
    main()
