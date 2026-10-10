import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestrator.pipeline import (
    parse_and_apply_agent_file_operations,
    MalformedWriteError,
)
from orchestrator.repo_tools import read_file, file_exists, delete_file
from orchestrator.git_tools import run_safe_git_command


def test_write_protocol():
    print("=== TESTING WRITE PROTOCOL PARSER ===")

    test_file = "agent_parser_test.tmp"

    # Case 1: Valid write
    print("\n--- Test Case 1: Valid Write ---")
    valid_payload = f"""
Some text before.
```write:{test_file}
hello
```
Some text after.
"""
    accounting = parse_and_apply_agent_file_operations(valid_payload, role="frontend")
    assert accounting["parsed_count"] == 1, f"Expected 1 parsed, got {accounting['parsed_count']}"
    assert accounting["executed_count"] == 1, f"Expected 1 executed, got {accounting['executed_count']}"
    assert file_exists(test_file), "File was not created on disk."
    assert read_file(test_file).strip() == "hello", f"File content mismatch: {read_file(test_file)}"
    print("--> Valid write passed: 1 parsed, 1 executed, content verified.")

    # Clean up test file
    delete_file(test_file, role="orchestrator")
    assert not file_exists(test_file)

    # Case 2: Malformed old format (```write without colon)
    print("\n--- Test Case 2: Malformed Old Format ---")
    malformed_payload = f"""
```write
{test_file}
hello
```
"""
    try:
        parse_and_apply_agent_file_operations(malformed_payload, role="frontend")
        raise AssertionError("Failed: Malformed write was silently ignored or passed!")
    except MalformedWriteError as e:
        print(f"--> Malformed write caught loudly as expected: {e}")

    # Case 3: Forbidden path
    print("\n--- Test Case 3: Forbidden Path ---")
    forbidden_payload = """
```write:.git/test
hello
```
"""
    try:
        parse_and_apply_agent_file_operations(forbidden_payload, role="frontend")
        raise AssertionError("Failed: Forbidden write was not blocked!")
    except PermissionError as e:
        print(f"--> Forbidden write recognized and blocked with PermissionError as expected: {e}")

    # Final Git Check
    print("\n--- Final Git Status Check ---")
    git_status = run_safe_git_command(["git", "status", "--short"])
    assert git_status["returncode"] == 0, f"Git status failed with returncode {git_status['returncode']}"
    assert git_status["stdout"].strip() == "", f"Git working tree is not clean:\n{git_status['stdout']}"
    print("--> Trayne Git working tree is completely clean.")

    print("\nWRITE_PROTOCOL_OK")


if __name__ == "__main__":
    test_write_protocol()
