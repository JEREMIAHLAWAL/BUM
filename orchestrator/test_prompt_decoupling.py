"""
Unit tests for Pipeline Decoupling and Manifest Context Injection.

Tests that:
1. Manifest rules & token guards are injected into shared context.
2. Custom verification commands from bum.config.json are allowed by command_tools.
3. Type-skeleton extraction adheres to manifest context paths.
4. Repository boundaries and write permissions adhere to manifest rules.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestrator.manifest import BumManifest, ManifestRules, ManifestVerification, ManifestContext
from orchestrator.command_tools import get_allowed_commands, run_safe_command
from orchestrator.harness_tools import extract_type_skeletons, run_typecheck_gate
from orchestrator.repo_tools import (
    set_active_project_path,
    get_repo_root,
    check_write_allowed,
    safe_path,
)
from orchestrator.pipeline import get_shared_context


class TestPromptDecoupling(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="bum_decoupling_test_"))
        # Scaffold a mock repository with a custom manifest
        self.manifest_data = {
            "name": "Acme API",
            "project_type": "fastapi",
            "version": "2.0.0",
            "rules": {
                "forbidden_imports": ["flask", "django"],
                "required_packages": ["pydantic", "fastapi"],
                "forbidden_tokens": ["TODO_DEPRECATED"],
                "allowed_write_roots": ["app/", "tests/"],
                "prohibited_files": ["config.py", ".env"]
            },
            "verification": {
                "typecheck_cmd": "mypy .",
                "test_cmd": "pytest",
                "lint_cmd": "flake8"
            },
            "context": {
                "type_skeleton_paths": ["app/schemas.py"]
            }
        }
        (self.temp_dir / "bum.config.json").write_text(json.dumps(self.manifest_data), encoding="utf-8")
        
        # Create app directory and skeleton file
        app_dir = self.temp_dir / "app"
        app_dir.mkdir(parents=True, exist_ok=True)
        (app_dir / "schemas.py").write_text(
            """
            export type UserID = string;
            export interface UserModel {
                id: UserID;
                name: string;
            }
            """,
            encoding="utf-8"
        )
        set_active_project_path(self.temp_dir)

    def tearDown(self):
        set_active_project_path(None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_allowed_commands_includes_manifest_verification(self):
        allowed = get_allowed_commands()
        self.assertIn(("mypy", "."), allowed)
        self.assertIn(("pytest",), allowed)
        self.assertIn(("flake8",), allowed)

    def test_shared_context_injects_manifest_rules(self):
        ctx = get_shared_context()
        self.assertIn("ACME API", ctx)
        self.assertIn("FORBIDDEN IMPORTS (Do NOT import): flask, django", ctx)
        self.assertIn("REQUIRED / PREFERRED PACKAGES: pydantic, fastapi", ctx)
        self.assertIn("FORBIDDEN TOKENS / PATTERNS: TODO_DEPRECATED", ctx)
        self.assertIn("AUTHORIZED WRITE ROOTS: app/, tests/", ctx)
        self.assertIn("PROTECTED FILES (Never modify): config.py, .env", ctx)

    def test_extract_type_skeletons_from_manifest_paths(self):
        skeletons = extract_type_skeletons(self.temp_dir)
        self.assertIn("interface UserModel", skeletons)
        self.assertIn("type UserID", skeletons)

    def test_write_allowed_enforces_manifest_boundaries(self):
        # 1. Allowed path in app/
        allowed_target = safe_path("app/routes.py")
        check_write_allowed(allowed_target, "app/routes.py")

        # 2. Prohibited file
        prohibited_target = safe_path("config.py")
        with self.assertRaises(PermissionError):
            check_write_allowed(prohibited_target, "config.py")

        # 3. Path outside allowed write roots (e.g. scripts/build.sh)
        outside_target = safe_path("scripts/build.sh")
        with self.assertRaises(PermissionError):
            check_write_allowed(outside_target, "scripts/build.sh")

        # 4. Protected system file (.env)
        env_target = safe_path(".env")
        with self.assertRaises(PermissionError):
            check_write_allowed(env_target, ".env")


if __name__ == "__main__":
    unittest.main()
