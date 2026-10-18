import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))





def run_write_capability_test():
    from orchestrator.repo_tools import (
         write_file,
         read_file,
         delete_file,
         file_exists,
         get_repo_root,
    )
    from orchestrator.git_tools import run_safe_git_command

    print("=== TESTING CONTROLLED REPOSITORY WRITE ACCESS ===")

    test_filename = "agent_write_test.tmp"
    test_content = "controlled write access capability test"

    # 1. Test safe write (file creation)
    print("\n1. Testing safe write (creation)...")
    res_create = write_file(test_filename, test_content, role="frontend")
    assert res_create["action"] == "created", f"Expected created, got {res_create['action']}"
    assert file_exists(test_filename), "Test file was not created on disk."
    content_read = read_file(test_filename)
    assert content_read == test_content, f"Content mismatch: expected {test_content}, got {content_read}"
    print("   Safe creation verified.")

    # 2. Test safe write (modification)
    print("\n2. Testing safe write (modification)...")
    updated_content = "updated controlled content"
    res_mod = write_file(test_filename, updated_content, role="backend")
    assert res_mod["action"] == "modified", f"Expected modified, got {res_mod['action']}"
    assert read_file(test_filename) == updated_content, "Content modification failed."
    print("   Safe modification verified.")

    # 3. Clean up temporary test file
    print("\n3. Cleaning up temporary test file...")
    delete_file(test_filename, role="orchestrator")
    assert not file_exists(test_filename), "Test file was not deleted."
    print("   Temporary file removed.")

    # 4. Test forbidden write (.git/)
    print("\n4. Testing forbidden write to .git/ ...")
    try:
        write_file(".git/agent_test", "malicious payload", role="frontend")
        raise AssertionError("Security failure: .git/ write was not blocked!")
    except PermissionError as e:
        print(f"   Correctly blocked .git write: {e}")

    # 5. Test forbidden write (.env)
    print("\n5. Testing forbidden write to .env ...")
    try:
        write_file(".env", "FAKE_KEY=123", role="backend")
        raise AssertionError("Security failure: .env write was not blocked!")
    except PermissionError as e:
        print(f"   Correctly blocked .env write: {e}")

    # 6. Test forbidden write (node_modules/)
    print("\n6. Testing forbidden write to node_modules/ ...")
    try:
        write_file("node_modules/fake_package/index.js", "console.log()", role="frontend")
        raise AssertionError("Security failure: node_modules write was not blocked!")
    except PermissionError as e:
        print(f"   Correctly blocked node_modules write: {e}")

    # 7. Test forbidden traversal outside repo
    print("\n7. Testing forbidden path traversal (outside repo) ...")
    try:
        write_file("../forbidden_file.txt", "outside repo", role="backend")
        raise AssertionError("Security failure: Path traversal was not blocked!")
    except PermissionError as e:
        print(f"   Correctly blocked path traversal: {e}")

    # 8. Check Git status
    print("\n8. Checking Git working tree cleanliness...")
    git_status = run_safe_git_command(["git", "status", "--short"])
    assert git_status["returncode"] == 0, f"Git status failed with return code {git_status['returncode']}"
    assert git_status["stdout"].strip() == "", f"Git working tree is not clean:\n{git_status['stdout']}"
    print("   Git working tree is completely clean.")

    print("\nCONTROLLED_WRITE_ACCESS_OK")


def main():
    run_write_capability_test()


if __name__ == "__main__":
    main()
