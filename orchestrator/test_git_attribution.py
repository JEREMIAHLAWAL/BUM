import unittest
from unittest.mock import patch
from orchestrator.git_attribution import (
    _hash_file_content,
    capture_git_baseline,
    compute_run_git_attribution,
    format_git_attribution_context,
)


class TestGitAttribution(unittest.TestCase):
    def test_hash_content_deterministic(self):
        h1 = _hash_file_content("hello world")
        h2 = _hash_file_content("hello world")
        h3 = _hash_file_content("different content")
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)

    def test_clean_baseline_and_new_run_changes(self):
        # Case A: Clean repository at baseline
        baseline = {
            "status_short": "",
            "diff_stat": "",
            "diff_head": "",
            "tracked_modified": [],
            "tracked_deleted": [],
            "tracked_staged": [],
            "untracked_files": [],
            "snapshots": {},
        }

        # Mock current git commands indicating a new file was modified and a new file created
        with patch("orchestrator.git_attribution.run_safe_git_command") as mock_git, \
             patch("orchestrator.git_attribution._get_file_snapshot") as mock_snap, \
             patch("orchestrator.git_attribution.read_file") as mock_read:

            mock_git.side_effect = lambda cmd: {
                ("git", "status", "--short"): {"stdout": " M src/app/index.tsx\n?? src/components/NewWidget.tsx\n"},
                ("git", "diff", "--stat"): {"stdout": " 1 file changed\n"},
                ("git", "diff"): {"stdout": "diff --git a/src/app/index.tsx ...\n"},
                ("git", "diff", "HEAD"): {"stdout": "diff --git ...\n"},
            }[tuple(cmd)]

            mock_read.return_value = "// new file content"

            attr = compute_run_git_attribution(baseline)

            self.assertEqual(attr["pre_existing"]["tracked_modified"], [])
            self.assertEqual(attr["pre_existing"]["untracked_files"], [])
            self.assertEqual(attr["run_delta"]["modified"], ["src/app/index.tsx"])
            self.assertEqual(attr["run_delta"]["created"], ["src/components/NewWidget.tsx"])
            self.assertEqual(attr["run_delta"]["deleted"], [])

    def test_preexisting_dirty_files_separated_from_run_delta(self):
        # Case B: old.ts was already dirty before the run
        # Agent changes new.ts during the run
        baseline = {
            "status_short": " M package.json\n?? pre_existing_note.txt\n",
            "diff_stat": " 1 file changed\n",
            "diff_head": "diff ...\n",
            "tracked_modified": ["package.json"],
            "tracked_deleted": [],
            "tracked_staged": [],
            "untracked_files": ["pre_existing_note.txt"],
            "snapshots": {
                "package.json": {
                    "path": "package.json",
                    "exists": True,
                    "sha256": _hash_file_content("package-content-v1"),
                    "content": "package-content-v1",
                },
                "pre_existing_note.txt": {
                    "path": "pre_existing_note.txt",
                    "exists": True,
                    "sha256": _hash_file_content("note-v1"),
                    "content": "note-v1",
                },
            },
        }

        with patch("orchestrator.git_attribution.run_safe_git_command") as mock_git, \
             patch("orchestrator.git_attribution._get_file_snapshot") as mock_snap, \
             patch("orchestrator.git_attribution.read_file") as mock_read:

            # Current git status shows package.json (unmodified further), pre_existing_note.txt, and newly modified index.tsx
            mock_git.side_effect = lambda cmd: {
                ("git", "status", "--short"): {"stdout": " M package.json\n M src/app/index.tsx\n?? pre_existing_note.txt\n"},
                ("git", "diff", "--stat"): {"stdout": " 2 files changed\n"},
                ("git", "diff"): {"stdout": "diff ...\n"},
                ("git", "diff", "HEAD"): {"stdout": "diff ...\n"},
            }[tuple(cmd)]

            def snap_lookup(path):
                if path == "package.json":
                    return {"path": "package.json", "sha256": _hash_file_content("package-content-v1")}
                if path == "pre_existing_note.txt":
                    return {"path": "pre_existing_note.txt", "sha256": _hash_file_content("note-v1")}
                if path == "src/app/index.tsx":
                    return {"path": "src/app/index.tsx", "sha256": _hash_file_content("index-content-v1")}
                return None

            mock_snap.side_effect = snap_lookup
            mock_read.return_value = "file text"

            attr = compute_run_git_attribution(baseline)

            # package.json and pre_existing_note.txt are identified as pre-existing
            self.assertIn("package.json", attr["pre_existing"]["tracked_modified"])
            self.assertIn("pre_existing_note.txt", attr["pre_existing"]["untracked_files"])

            # ONLY src/app/index.tsx is in the current run delta!
            self.assertEqual(attr["run_delta"]["modified"], ["src/app/index.tsx"])
            self.assertEqual(attr["run_delta"]["created"], [])
            self.assertEqual(attr["run_delta"]["preexisting_modified_again"], [])

    def test_preexisting_file_modified_again_during_run(self):
        # Case D: screen.tsx was already dirty at baseline, but agent edited it further during run
        baseline = {
            "status_short": " M src/screen.tsx\n",
            "diff_stat": " 1 file changed\n",
            "diff_head": "diff ...\n",
            "tracked_modified": ["src/screen.tsx"],
            "tracked_deleted": [],
            "tracked_staged": [],
            "untracked_files": [],
            "snapshots": {
                "src/screen.tsx": {
                    "path": "src/screen.tsx",
                    "exists": True,
                    "sha256": _hash_file_content("content-at-start"),
                    "content": "content-at-start",
                },
            },
        }

        with patch("orchestrator.git_attribution.run_safe_git_command") as mock_git, \
             patch("orchestrator.git_attribution._get_file_snapshot") as mock_snap:

            mock_git.side_effect = lambda cmd: {
                ("git", "status", "--short"): {"stdout": " M src/screen.tsx\n"},
                ("git", "diff", "--stat"): {"stdout": " 1 file changed\n"},
                ("git", "diff"): {"stdout": "diff ...\n"},
                ("git", "diff", "HEAD"): {"stdout": "diff ...\n"},
            }[tuple(cmd)]

            # Current content has different hash!
            mock_snap.return_value = {
                "path": "src/screen.tsx",
                "sha256": _hash_file_content("content-modified-by-agent"),
            }

            attr = compute_run_git_attribution(baseline)

            self.assertIn("src/screen.tsx", attr["run_delta"]["modified"])
            self.assertIn("src/screen.tsx", attr["run_delta"]["preexisting_modified_again"])
            self.assertEqual(attr["pre_existing"]["tracked_modified"], [])

    def test_file_deletion_attribution(self):
        # Case F: Agent deletes a file that existed at baseline
        baseline = {
            "status_short": "",
            "diff_stat": "",
            "diff_head": "",
            "tracked_modified": [],
            "tracked_deleted": [],
            "tracked_staged": [],
            "untracked_files": [],
            "snapshots": {},
        }

        with patch("orchestrator.git_attribution.run_safe_git_command") as mock_git, \
             patch("orchestrator.git_attribution._get_file_snapshot") as mock_snap:

            mock_git.side_effect = lambda cmd: {
                ("git", "status", "--short"): {"stdout": " D src/old_component.tsx\n"},
                ("git", "diff", "--stat"): {"stdout": " 1 file changed\n"},
                ("git", "diff"): {"stdout": "diff ...\n"},
                ("git", "diff", "HEAD"): {"stdout": "diff ...\n"},
            }[tuple(cmd)]

            mock_snap.return_value = None

            attr = compute_run_git_attribution(baseline)

            self.assertEqual(attr["run_delta"]["deleted"], ["src/old_component.tsx"])

    def test_format_attribution_context_content(self):
        sample_attr = {
            "pre_existing": {
                "tracked_modified": ["package.json", "package-lock.json"],
                "tracked_deleted": [],
                "tracked_staged": [],
                "untracked_files": ["app.json", "src/app/profile.tsx"],
                "summary_count": 4,
            },
            "run_delta": {
                "created": [],
                "modified": ["src/app/(app)/index.tsx"],
                "deleted": [],
                "preexisting_modified_again": [],
                "is_clean": False,
            },
            "current_git_state": {
                "status_short": " M package.json\n M src/app/(app)/index.tsx\n?? app.json\n",
                "diff_stat": " 2 files changed\n",
                "diff": "...",
                "diff_head": "...",
                "untracked_files": ["app.json", "src/app/profile.tsx"],
            },
        }

        formatted = format_git_attribution_context(sample_attr)
        self.assertIn("TASK-SCOPED GIT WORKTREE ATTRIBUTION", formatted)
        self.assertIn("PRE-EXISTING WORKTREE STATE", formatted)
        self.assertIn("package.json", formatted)
        self.assertIn("CURRENT RUN DELTA", formatted)
        self.assertIn("src/app/(app)/index.tsx", formatted)
        self.assertIn("DO NOT flag or fail the current task merely because pre-existing changes exist", formatted)


if __name__ == "__main__":
    unittest.main()
