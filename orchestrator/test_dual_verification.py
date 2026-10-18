"""
Dual Verification & Benchmark Test Suite for BUM.

Verifies that BUM dynamically switches between and correctly configures
distinct repository architectures without code changes or server restarts:
1. Reference Repository: CLAUDE/trayne (React Native / Expo with bum.config.json)
2. Greenfield Python / FastAPI workspace (auto-detected / manifest)
3. Greenfield Node / TypeScript workspace (auto-detected / manifest)
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestrator.manifest import load_manifest, generate_default_manifest, BumManifest
from orchestrator.command_tools import get_allowed_commands
from orchestrator.harness_tools import extract_type_skeletons
from orchestrator.repo_tools import (
    set_active_project_path,
    get_repo_root,
    get_active_manifest,
    list_available_projects,
    check_write_allowed,
    safe_path,
)
from orchestrator.pipeline import get_shared_context


class TestDualVerification(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp(prefix="bum_dual_verify_"))
        # Reference architecture is explicit scratch data, never the live trayne checkout.
        from unittest.mock import patch
        mobile = self.temp_root / "mobile"
        mobile.mkdir()
        (mobile / "bum.config.json").write_text(json.dumps({
            "name": "TRAYNE", "project_type": "react-native-expo",
            "rules": {"forbidden_imports": ["@expo/vector-icons", "date-fns"],
                      "required_packages": ["lucide-react-native"]},
            "verification": {"typecheck_cmd": "npm run ts:check", "test_cmd": "npm test"}
        }), encoding="utf-8")
        for target, value in (("orchestrator.repo_tools.DERIVED_REPO_PATH", mobile),
                              ("orchestrator.repo_tools._ACTIVE_PROJECT_PATH", None),
                              ("orchestrator.repo_tools._RUN_WORKTREE_OVERRIDE", None)):
            mock = patch(target, value)
            mock.start()
            self.addCleanup(mock.stop)

    def tearDown(self):
        set_active_project_path(None)
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_trayne_reference_repo_resolution(self):
        """Verify BUM resolves CLAUDE/trayne manifest and enforce mobile constraints."""
        set_active_project_path(None)
        manifest = get_active_manifest()
        
        # Verify trayne manifest properties
        self.assertEqual(manifest.project_type, "react-native-expo")
        self.assertIn("@expo/vector-icons", manifest.rules.forbidden_imports)
        self.assertIn("date-fns", manifest.rules.forbidden_imports)
        self.assertIn("lucide-react-native", manifest.rules.required_packages)
        self.assertEqual(manifest.verification.typecheck_cmd, "npm run ts:check")
        self.assertEqual(manifest.verification.test_cmd, "npm test")
        
        # Shared context should reflect mobile guardrails
        ctx = get_shared_context()
        self.assertIn("FORBIDDEN IMPORTS (Do NOT import): @expo/vector-icons, date-fns", ctx)
        self.assertIn("REQUIRED / PREFERRED PACKAGES: lucide-react-native", ctx)

    def test_greenfield_fastapi_repo_resolution(self):
        """Verify BUM dynamically switches to a Python/FastAPI repo and adjusts context."""
        fastapi_dir = self.temp_root / "fastapi_app"
        fastapi_dir.mkdir(parents=True, exist_ok=True)
        
        # Create manifest
        manifest_data = {
            "name": "FastAPI Microservice",
            "project_type": "fastapi",
            "version": "1.0.0",
            "rules": {
                "forbidden_imports": ["flask", "django"],
                "required_packages": ["pydantic", "fastapi"],
                "allowed_write_roots": ["app/", "tests/"],
                "prohibited_files": [".env", "config/secrets.json"]
            },
            "verification": {
                "typecheck_cmd": "mypy app/",
                "test_cmd": "pytest -v",
                "lint_cmd": "ruff check"
            },
            "context": {
                "type_skeleton_paths": ["app/schemas.py"]
            }
        }
        (fastapi_dir / "bum.config.json").write_text(json.dumps(manifest_data), encoding="utf-8")
        
        app_dir = fastapi_dir / "app"
        app_dir.mkdir(parents=True, exist_ok=True)
        (app_dir / "schemas.py").write_text("class ItemSchema(BaseModel):\n    id: int\n    name: str\n", encoding="utf-8")
        
        # Switch active workspace dynamically
        set_active_project_path(fastapi_dir)
        
        # 1. Active manifest check
        active_manifest = get_active_manifest()
        self.assertEqual(active_manifest.name, "FastAPI Microservice")
        self.assertEqual(active_manifest.project_type, "fastapi")
        
        # 2. Dynamic command allowance
        allowed_cmds = get_allowed_commands()
        self.assertIn(("mypy", "app/"), allowed_cmds)
        self.assertIn(("pytest", "-v"), allowed_cmds)
        self.assertIn(("ruff", "check"), allowed_cmds)
        
        # 3. Dynamic shared context
        ctx = get_shared_context()
        self.assertIn("FASTAPI MICROSERVICE", ctx)
        self.assertIn("FORBIDDEN IMPORTS (Do NOT import): flask, django", ctx)
        self.assertIn("AUTHORIZED WRITE ROOTS: app/, tests/", ctx)
        
        # 4. Type skeleton extraction
        skeletons = extract_type_skeletons(fastapi_dir)
        self.assertIn("class ItemSchema", skeletons)
        
        # 5. Boundary guards
        self.assertTrue(check_write_allowed(safe_path("app/api.py"), "app/api.py"))
        with self.assertRaises(PermissionError):
            check_write_allowed(safe_path("config/secrets.json"), "config/secrets.json")

    def test_greenfield_node_repo_auto_detection(self):
        """Verify BUM auto-detects a Node repo without a pre-existing manifest file."""
        node_dir = self.temp_root / "express_app"
        node_dir.mkdir(parents=True, exist_ok=True)
        
        (node_dir / "package.json").write_text(json.dumps({
            "name": "express-backend",
            "scripts": {
                "ts:check": "tsc --noEmit",
                "test": "mocha"
            },
            "dependencies": {
                "express": "^4.18.2"
            }
        }), encoding="utf-8")
        
        # Switch active workspace dynamically
        set_active_project_path(node_dir)
        
        # 1. Fallback auto-detection
        active_manifest = get_active_manifest()
        self.assertEqual(active_manifest.project_type, "node")
        self.assertEqual(active_manifest.verification.typecheck_cmd, "npm run ts:check")
        self.assertEqual(active_manifest.verification.test_cmd, "npm test")
        
        # 2. Commands allowed automatically
        allowed_cmds = get_allowed_commands()
        self.assertIn(("npm", "run", "ts:check"), allowed_cmds)
        self.assertIn(("npm", "test"), allowed_cmds)

    def test_dynamic_switching_back_and_forth(self):
        """Verify switching between repos in the same process seamlessly alternates state."""
        # Switch to custom repo
        custom_dir = self.temp_root / "custom_app"
        custom_dir.mkdir(parents=True, exist_ok=True)
        (custom_dir / "bum.config.json").write_text(json.dumps({
            "name": "Custom Microservice",
            "project_type": "rust",
            "verification": {"test_cmd": "cargo test"}
        }), encoding="utf-8")
        
        set_active_project_path(custom_dir)
        self.assertEqual(get_active_manifest().project_type, "rust")
        self.assertIn(("cargo", "test"), get_allowed_commands())
        
        # Switch back to trayne reference
        set_active_project_path(None)
        self.assertEqual(get_active_manifest().project_type, "react-native-expo")
        self.assertIn(("npm", "run", "ts:check"), get_allowed_commands())


if __name__ == "__main__":
    unittest.main()
