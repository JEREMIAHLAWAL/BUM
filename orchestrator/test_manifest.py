"""
Unit tests for the BUM Workspace Manifest Engine (orchestrator/manifest.py).

Tests parsing, validation errors, smart fallbacks, and repo tools integration.
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

from orchestrator.manifest import (
    BumManifest,
    ManifestRules,
    ManifestVerification,
    ManifestContext,
    find_manifest,
    load_manifest,
    generate_default_manifest,
)
from orchestrator.repo_tools import (
    list_available_projects,
    get_active_manifest,
    get_repo_root,
)


class TestBumManifest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="bum_manifest_test_"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parse_valid_manifest(self):
        manifest_data = {
            "name": "Custom Repo",
            "project_type": "fastapi",
            "version": "1.2.0",
            "description": "Python backend API",
            "rules": {
                "forbidden_imports": ["flask"],
                "required_packages": ["pydantic"],
                "forbidden_tokens": ["TODO_LEGACY"],
                "allowed_write_roots": ["app/", "tests/"],
                "prohibited_files": [".env"]
            },
            "verification": {
                "typecheck_cmd": "mypy .",
                "test_cmd": "pytest",
                "lint_cmd": "flake8"
            },
            "context": {
                "type_skeleton_paths": ["app/models.py"],
                "domain_paths": ["app/domain/"]
            }
        }
        manifest_file = self.temp_dir / "bum.config.json"
        manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

        manifest = load_manifest(manifest_file)
        self.assertEqual(manifest.name, "Custom Repo")
        self.assertEqual(manifest.project_type, "fastapi")
        self.assertEqual(manifest.version, "1.2.0")
        self.assertIn("flask", manifest.rules.forbidden_imports)
        self.assertEqual(manifest.verification.typecheck_cmd, "mypy .")
        self.assertEqual(manifest.verification.test_cmd, "pytest")
        self.assertEqual(manifest.context.type_skeleton_paths, ["app/models.py"])

    def test_find_manifest_locations(self):
        # 1. bum.config.json in root
        config_root = self.temp_dir / "bum.config.json"
        config_root.write_text('{"name": "Root Config"}', encoding="utf-8")
        found = find_manifest(self.temp_dir)
        self.assertEqual(found, config_root.resolve())

        # 2. .bum/config.json
        config_root.unlink()
        bum_subdir = self.temp_dir / ".bum"
        bum_subdir.mkdir(parents=True, exist_ok=True)
        config_sub = bum_subdir / "config.json"
        config_sub.write_text('{"name": "Sub Config"}', encoding="utf-8")
        found = find_manifest(self.temp_dir)
        self.assertEqual(found, config_sub.resolve())

    def test_fallback_on_missing_manifest(self):
        # Directory without any manifest file
        empty_dir = self.temp_dir / "empty_project"
        empty_dir.mkdir()
        manifest = load_manifest(empty_dir)

        self.assertIsInstance(manifest, BumManifest)
        self.assertEqual(manifest.name, "empty_project")
        self.assertEqual(manifest.project_type, "general")

    def test_fallback_on_corrupted_json(self):
        corrupt_file = self.temp_dir / "bum.config.json"
        corrupt_file.write_text("{ unclosed json: ...", encoding="utf-8")

        manifest = load_manifest(self.temp_dir)
        self.assertIsInstance(manifest, BumManifest)
        self.assertTrue("Fallback manifest" in (manifest.description or ""))

    def test_auto_generate_manifest_for_node(self):
        pkg_json = self.temp_dir / "package.json"
        pkg_json.write_text(json.dumps({
            "name": "my-node-app",
            "scripts": {
                "ts:check": "tsc --noEmit",
                "test": "jest"
            },
            "dependencies": {
                "react": "18.0.0"
            }
        }), encoding="utf-8")

        manifest = generate_default_manifest(self.temp_dir)
        self.assertEqual(manifest.project_type, "node")
        self.assertEqual(manifest.verification.typecheck_cmd, "npm run ts:check")
        self.assertEqual(manifest.verification.test_cmd, "npm test")

    def test_auto_generate_manifest_for_expo(self):
        pkg_json = self.temp_dir / "package.json"
        pkg_json.write_text(json.dumps({
            "name": "my-expo-app",
            "dependencies": {
                "expo": "50.0.0"
            }
        }), encoding="utf-8")

        manifest = generate_default_manifest(self.temp_dir)
        self.assertEqual(manifest.project_type, "react-native-expo")

    def test_auto_generate_manifest_for_python(self):
        req_file = self.temp_dir / "requirements.txt"
        req_file.write_text("fastapi\npydantic\n", encoding="utf-8")

        manifest = generate_default_manifest(self.temp_dir)
        self.assertEqual(manifest.project_type, "python")
        self.assertEqual(manifest.verification.typecheck_cmd, "mypy .")
        self.assertEqual(manifest.verification.test_cmd, "pytest")

    def test_load_trayne_reference_manifest(self):
        repo_root = get_repo_root()
        trayne_manifest_path = repo_root / "bum.config.json"
        if trayne_manifest_path.is_file():
            manifest = load_manifest(trayne_manifest_path)
            self.assertEqual(manifest.project_type, "react-native-expo")
            self.assertIn("@expo/vector-icons", manifest.rules.forbidden_imports)
            self.assertIn("date-fns", manifest.rules.forbidden_imports)
            self.assertIn("lucide-react-native", manifest.rules.required_packages)
            self.assertEqual(manifest.verification.typecheck_cmd, "npm run ts:check")
            self.assertEqual(manifest.verification.test_cmd, "npm test")

    def test_projects_discovery_includes_manifest_data(self):
        projects = list_available_projects()
        self.assertTrue(len(projects) >= 2)
        trayne_proj = next((p for p in projects if p["id"] == "trayne"), None)
        self.assertIsNotNone(trayne_proj)
        self.assertIn("has_manifest", trayne_proj)


if __name__ == "__main__":
    unittest.main()
