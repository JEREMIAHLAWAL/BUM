import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from orchestrator.repo_tools import get_repo_root

# Whitelist of allowed Expo/React Native packages that the orchestrator permits installing via expo install
ALLOWED_EXPO_PACKAGES = {
    "expo-router",
    "react-native-safe-area-context",
    "react-native-screens",
    "expo-linking",
    "expo-constants",
    "expo-status-bar",
    "expo-sqlite",
    "lucide-react-native",
    "react-native-svg",
}

# Regex to validate safe npm/expo package names
PACKAGE_NAME_REGEX = re.compile(r"^(?:@[a-z0-9-*~][a-z0-9-*._~]*/)?[a-z0-9-~][a-z0-9-._~]*$")


class DependencyActionError(Exception):
    """Raised when a dependency action request is invalid or forbidden."""
    pass


def validate_package_name(pkg: str) -> str:
    pkg = pkg.strip()
    if not pkg:
        raise DependencyActionError("Package name cannot be empty.")

    # Prevent shell injection characters or paths
    if any(c in pkg for c in [";", "&", "|", "`", "$", "(", ")", "<", ">", "\\", "\n", "\r", " "]):
        raise DependencyActionError(f"Package name contains illegal shell characters: {pkg}")

    if "/" in pkg and not pkg.startswith("@"):
        raise DependencyActionError(f"Illegal package path format: {pkg}")

    if not PACKAGE_NAME_REGEX.match(pkg):
        raise DependencyActionError(f"Invalid package name format: {pkg}")

    if pkg not in ALLOWED_EXPO_PACKAGES:
        raise DependencyActionError(
            f"Package '{pkg}' is not in the orchestrator's approved dependency allowlist: {sorted(ALLOWED_EXPO_PACKAGES)}"
        )

    return pkg


def build_dependency_command(action: str, packages: Optional[list[str]] = None) -> list[str]:
    """
    Construct safe, exact command lists for subprocess.run(shell=False).
    """
    action = action.strip().upper()

    if action == "NPM_CI":
        return ["npm", "ci"]

    elif action == "EXPO_INSTALL":
        if not packages:
            raise DependencyActionError("EXPO_INSTALL requires a non-empty list of packages.")

        validated_pkgs = [validate_package_name(p) for p in packages]
        return ["npx", "expo", "install"] + validated_pkgs

    else:
        raise DependencyActionError(
            f"Unsupported dependency action: '{action}'. Only 'NPM_CI' and 'EXPO_INSTALL' are allowed."
        )


def parse_dependency_request(reviewer_or_agent_text: str) -> dict:
    """
    Parse machine-readable DEPENDENCY_ACTION block:
    DEPENDENCY_ACTION: EXPO_INSTALL
    DEPENDENCY_PACKAGES:
    expo-router
    react-native-safe-area-context
    or
    DEPENDENCY_ACTION: NPM_CI
    """
    action_match = re.search(r"DEPENDENCY_ACTION:\s*([A-Z_]+)", reviewer_or_agent_text)
    if not action_match:
        raise DependencyActionError("No DEPENDENCY_ACTION specified in the request.")

    action = action_match.group(1).strip()

    packages = []
    if action == "EXPO_INSTALL":
        pkg_block = re.search(r"DEPENDENCY_PACKAGES:\s*\n((?:[ \t]*[^\n]+\n*)+)", reviewer_or_agent_text)
        if not pkg_block:
            raise DependencyActionError("EXPO_INSTALL requested but DEPENDENCY_PACKAGES block is missing.")

        lines = pkg_block.group(1).splitlines()
        for line in lines:
            line_str = line.strip().lstrip("-").strip()
            # Stop if hitting another header
            if not line_str or line_str.isupper() and ":" in line_str:
                break
            packages.append(line_str)

        if not packages:
            raise DependencyActionError("EXPO_INSTALL requested with empty package list.")

    return {
        "action": action,
        "packages": packages,
    }


def execute_controlled_dependency_action(action: str, packages: Optional[list[str]] = None, dry_run: bool = False) -> dict:
    """
    Execute an allowed dependency command with strict safety boundaries.
    """
    cmd = build_dependency_command(action, packages)
    repo = get_repo_root()

    print(f"[AUDIT DEPENDENCY] Executing: {' '.join(cmd)} (dry_run={dry_run})", flush=True)

    if dry_run:
        return {
            "command": " ".join(cmd),
            "returncode": 0,
            "stdout": "[DRY RUN] Command validated successfully.",
            "stderr": "",
            "timed_out": False,
        }

    executable = shutil.which(cmd[0])
    if not executable:
        raise FileNotFoundError(f"Executable not found on PATH: {cmd[0]}")

    exec_command = [executable] + cmd[1:]

    try:
        result = subprocess.run(
            exec_command,
            cwd=repo,
            capture_output=True,
            text=True,
            shell=False,
            timeout=300,
        )
        return {
            "command": " ".join(cmd),
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "command": " ".join(cmd),
            "returncode": -1,
            "stdout": e.stdout or "",
            "stderr": "Command timed out after 300s",
            "timed_out": True,
        }
