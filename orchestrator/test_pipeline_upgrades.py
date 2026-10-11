import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestrator.contract_tools import (
    extract_contract_from_spec,
    format_contract_markdown,
    write_spec_contract,
)
from orchestrator.evidence_tools import (
    write_verification_evidence,
    parse_evidence_on_disk,
)
from orchestrator.micro_commit_tools import (
    create_micro_commit,
    rollback_to_micro_commit,
    get_current_head_sha,
)
from orchestrator.manifest import BumManifest


class TestPipelineUpgrades(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp(prefix="bum_upgrades_test_"))

    def tearDown(self):
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_spec_contract_extraction_and_markdown(self):
        sample_spec = """
# Task Implementation Spec

FILES TO CREATE OR MODIFY:
- `src/components/EmptyState.tsx`
- `src/domain/units.ts`

EXPORTED SIGNATURES:
- `export interface EmptyStateProps { title: string; message: string; }`
- `export function formatKgToLbs(kg: number): number`

NEGATIVE CONSTRAINTS:
- forbidden_import: @expo/vector-icons
- forbidden_import: date-fns
- Do NOT delete existing database helpers

PERMITTED TOKENS:
- `theme.colors.bg`
- `theme.colors.accent`
"""
        manifest_data = {
            "name": "TRAYNE",
            "project_type": "react-native-expo",
            "version": "1.0.0",
            "rules": {
                "forbidden_imports": ["@expo/vector-icons", "date-fns"],
                "required_packages": ["lucide-react-native"],
            }
        }
        manifest = BumManifest(**manifest_data)

        contract_data = extract_contract_from_spec(sample_spec, manifest=manifest)

        # File boundaries
        self.assertIn("src/components/EmptyState.tsx", contract_data["file_boundaries"])
        self.assertIn("src/domain/units.ts", contract_data["file_boundaries"])

        # Signatures
        self.assertTrue(any("EmptyStateProps" in s for s in contract_data["exported_signatures"]))
        self.assertTrue(any("formatKgToLbs" in s for s in contract_data["exported_signatures"]))

        # Negative constraints
        self.assertTrue(any("@expo/vector-icons" in c for c in contract_data["negative_constraints"]))
        self.assertTrue(any("date-fns" in c for c in contract_data["negative_constraints"]))

        # Formatted markdown
        md = format_contract_markdown(contract_data)
        self.assertIn("# SPECIFICATION CONTRACT (IMMUTABLE BOUNDARY)", md)
        self.assertIn("`src/components/EmptyState.tsx`", md)
        self.assertIn("EmptyStateProps", md)

        # Write spec contract to disk
        pipeline_dir = self.temp_root / "pipeline"
        res = write_spec_contract(sample_spec, manifest=manifest, pipeline_dir=pipeline_dir)
        self.assertTrue((pipeline_dir / "contract.md").exists())
        self.assertIn("SPECIFICATION CONTRACT", (pipeline_dir / "contract.md").read_text(encoding="utf-8"))

    def test_file_boundaries_survive_route_group_parens(self):
        """Regression test: Expo Router / Next.js route-group folders like
        `(app)` contain parens in the path. The extraction regex's char
        class must include '()' or a path such as
        `src/app/(app)/_layout.tsx` truncates to just "_layout.tsx" (no
        slash) and gets silently dropped from file_boundaries — which is
        exactly what starved Frontend of the file's on-disk content and
        caused 3 straight Reviewer-rejected blind-rewrite cycles on the
        real feature3_4_rebuild_v3 run (see MASTER_TODO.md)."""
        boundaries_spec = """
FILES TO CREATE OR MODIFY:
- `src/app/(app)/history.tsx`
- `src/app/(app)/_layout.tsx`
"""
        contract_data = extract_contract_from_spec(boundaries_spec, manifest=None)

        self.assertIn(
            "src/app/(app)/history.tsx", contract_data["file_boundaries"]
        )
        self.assertIn(
            "src/app/(app)/_layout.tsx", contract_data["file_boundaries"]
        )
        # The truncated, slash-less fragment must never leak in as a
        # separate (wrong) entry.
        self.assertNotIn("_layout.tsx", contract_data["file_boundaries"])

        # NEEDS CONTEXT uses its own markdown-heading-anchored regex;
        # verify the same parens fix applies to reference_files too.
        reference_spec = """
## 9. NEEDS CONTEXT

- `src/app/(app)/profile.tsx`
"""
        reference_data = extract_contract_from_spec(reference_spec, manifest=None)
        self.assertIn(
            "src/app/(app)/profile.tsx", reference_data["reference_files"]
        )
        self.assertNotIn("profile.tsx", reference_data["reference_files"])

    def test_evidence_on_disk_logging_and_parsing(self):
        cmd_results = [
            {
                "command": "npm run ts:check",
                "returncode": 0,
                "stdout": "TypeScript check passed successfully",
                "stderr": "",
                "timed_out": False,
            },
            {
                "command": "npm test",
                "returncode": 1,
                "stdout": "FAIL src/domain/units.test.ts\nTypeError: Cannot read property of undefined",
                "stderr": "Jest encountered an error",
                "timed_out": False,
            }
        ]

        # Write evidence
        evidence_res = write_verification_evidence(cmd_results, stage="tester", cycle=1, repo_root=self.temp_root)
        self.assertTrue(Path(evidence_res["json_path"]).exists())
        self.assertTrue(Path(evidence_res["log_path"]).exists())

        # Parse evidence back from disk
        parsed = parse_evidence_on_disk(stage="tester", repo_root=self.temp_root)
        self.assertIsNotNone(parsed)
        self.assertFalse(parsed["all_passed"])
        self.assertTrue(parsed["has_failures"])
        self.assertEqual(len(parsed["commands"]), 2)
        self.assertEqual(parsed["commands"][0]["passed"], True)
        self.assertEqual(parsed["commands"][1]["passed"], False)
        self.assertTrue(len(parsed["errors"]) > 0)

    def test_micro_commit_and_rollback_mechanics(self):
        with patch("orchestrator.micro_commit_tools.run_safe_git_command") as mock_git, \
             patch("subprocess.run") as mock_sub:

            # 1. Clean worktree -> no micro-commit
            mock_git.return_value = {"command": "git status --short", "stdout": "", "returncode": 0}
            clean_res = create_micro_commit("tester", cycle=1, summary="test commit", repo_root=self.temp_root)
            self.assertFalse(clean_res["created"])
            self.assertEqual(clean_res["reason"], "clean_worktree")

            # 2. Dirty worktree -> create commit
            mock_git.side_effect = lambda cmd: {
                ("git", "status", "--short"): {"stdout": " M src/app/index.tsx\n", "returncode": 0},
                ("git", "add", "-A"): {"stdout": "", "returncode": 0},
                ("git", "rev-parse", "HEAD"): {"stdout": "abc12345def\n", "returncode": 0},
                ("git", "clean", "-fd"): {"stdout": "", "returncode": 0},
            }[tuple(cmd)]

            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_sub.return_value = mock_proc

            commit_res = create_micro_commit("reviewer", cycle=1, summary="verified test", repo_root=self.temp_root)
            self.assertTrue(commit_res["created"])
            self.assertEqual(commit_res["sha"], "abc12345def")
            self.assertEqual(commit_res["stage"], "reviewer")

            # 3. Rollback mechanics
            rollback_res = rollback_to_micro_commit("abc12345def", repo_root=self.temp_root)
            self.assertTrue(rollback_res["success"])
            self.assertEqual(rollback_res["target_sha"], "abc12345def")


if __name__ == "__main__":
    unittest.main()
