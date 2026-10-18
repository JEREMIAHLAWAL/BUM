import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))






def test_parser_protocol():
    from orchestrator.pipeline import parse_and_apply_agent_file_operations, MalformedWriteError
    from orchestrator.repo_tools import read_file, file_exists, delete_file
    from orchestrator.git_tools import run_safe_git_command

    print("=== TESTING WRITE PROTOCOL & PARSER HARDENING ===\n")

    test_file = "agent_parser_test.tmp"

    # ----------------------------------------------------
    # Case 1: Valid write format
    # ----------------------------------------------------
    print("1. Testing valid write format...")
    valid_input = f"""
Some preamble text from agent...

```write:{test_file}
hello
```

## FRONTEND CHANGES
FILES CHANGED:
- {test_file}
SUMMARY:
- Created test file.
"""
    accounting = parse_and_apply_agent_file_operations(valid_input, role="frontend")
    assert accounting["parsed_count"] == 1, f"Expected 1 parsed, got {accounting['parsed_count']}"
    assert accounting["executed_count"] == 1, f"Expected 1 executed, got {accounting['executed_count']}"
    assert file_exists(test_file), "File does not exist on disk."
    content = read_file(test_file)
    assert content.strip() == "hello", f"Expected 'hello', got {content}"
    print("   Valid write parsed and executed successfully.")

    # Clean up test file
    delete_file(test_file, role="orchestrator")
    assert not file_exists(test_file)
    print("   Cleaned up test file.")

    # ----------------------------------------------------
    # Case 2: Malformed old format
    # ----------------------------------------------------
    print("\n2. Testing malformed old format (```write without path)...")
    malformed_input = f"""
```write
{test_file}
hello
```

## FRONTEND CHANGES
FILES CHANGED:
- {test_file}
"""
    try:
        parse_and_apply_agent_file_operations(malformed_input, role="frontend")
        raise AssertionError("Security/Protocol failure: Malformed write did not raise MalformedWriteError!")
    except MalformedWriteError as e:
        print(f"   Correctly caught malformed write error: {e}")

    # ----------------------------------------------------
    # Case 3: Forbidden path
    # ----------------------------------------------------
    print("\n3. Testing forbidden path write via parser...")
    forbidden_input = """
```write:.git/test
hello
```
"""
    try:
        parse_and_apply_agent_file_operations(forbidden_input, role="backend")
        raise AssertionError("Security failure: .git write was not blocked by repo_tools!")
    except PermissionError as e:
        print(f"   Correctly blocked forbidden path write: {e}")

    # ----------------------------------------------------
    # Case 4: Claimed changes with 0 writes executed
    # ----------------------------------------------------
    print("\n4. Testing claimed changes with 0 executed writes...")
    claimed_zero_writes = """
I decided not to use code blocks.

## FRONTEND CHANGES
FILES CHANGED:
- src/app/profile.tsx
SUMMARY:
- Said I changed it but emitted no write blocks.
"""
    try:
        parse_and_apply_agent_file_operations(claimed_zero_writes, role="frontend")
        raise AssertionError("Protocol failure: Claimed changes with 0 writes did not raise RuntimeError!")
    except RuntimeError as e:
        print(f"   Correctly caught discrepancy error: {e}")

    # ----------------------------------------------------
    # 5. Verify Git status is clean
    # ----------------------------------------------------
    print("\n5. Checking Git working tree cleanliness...")
    git_status = run_safe_git_command(["git", "status", "--short"])
    assert git_status["returncode"] == 0, f"Git status failed with return code {git_status['returncode']}"
    assert git_status["stdout"].strip() == "", f"Git working tree is not clean:\n{git_status['stdout']}"
    print("   Git working tree is completely clean.")

    print("\nWRITE_PROTOCOL_OK")


def main():
    test_parser_protocol()


if __name__ == "__main__":
    main()
