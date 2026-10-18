"""Capture-revalidation fixtures only; no live provider, dotenv, or service."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('bum05_capture', HERE / 'serve_capture.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class CaptureContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=runner.SCRATCH, prefix='bum05-capture-contract-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'BUM'
        self.finder = self.root.parent / 'FinderShip'
        self.run_id = 'run_bum05_readiness_fixture'
        self.artifact = self.root / '.bum/runs' / self.run_id / 'pipeline'
        self.artifact.mkdir(parents=True)
        (self.artifact / 'spec.md').write_text('read-only fixture', encoding='utf-8')
        prompt = self.finder / 'pipeline/FS-011_PLANNER_READINESS.md'
        prompt.parent.mkdir(parents=True)
        prompt.write_text('fixture prompt', encoding='utf-8')
        metadata = {'artifact_dir': str(self.artifact), 'project_repo_path': str(self.finder),
                    'mode': 'read-only-planner-probe-no-worktree-no-implementation'}
        (self.artifact.parent / 'artifact_context.json').write_text(json.dumps(metadata), encoding='utf-8')
        self.capture = {'head': 'a' * 40, 'run_id': self.run_id,
                        'planner_validation': {'valid': True, 'reason': ''},
                        'planner_contract': {'file_boundaries': []}, 'artifact_context': metadata,
                        'planner_output_sha256': runner.digest(self.artifact / 'spec.md'),
                        'source_prompt': {'sha256': runner.digest(prompt)}}
        self.path = Path(self.temp.name) / 'capture.json'
        self.path.write_text(json.dumps(self.capture), encoding='utf-8')
        self.sha = runner.digest(self.path)
        self.root_patch = patch.object(runner, 'ROOT', self.root)
        self.finder_patch = patch.object(runner, 'FINDER', self.finder)
        self.root_patch.start()
        self.finder_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.addCleanup(self.finder_patch.stop)

    def test_hash_pinned_artifact_and_unchanged_production_required(self):
        with patch.object(runner.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')) as git:
            observed, artifact = runner.read_capture(self.path, self.sha)
        self.assertEqual(observed, self.capture)
        self.assertEqual(artifact, self.artifact.resolve())
        argv = git.call_args.args[0]
        self.assertEqual(argv[:5], ['git', 'diff', '--exit-code', 'a' * 40, 'HEAD'])
        self.assertIn('orchestrator', argv)

    def test_modified_capture_or_actual_spec_fails_before_source_query(self):
        with patch.object(runner.subprocess, 'run') as git:
            with self.assertRaisesRegex(RuntimeError, 'report hash mismatch'):
                runner.read_capture(self.path, '0' * 64)
            (self.artifact / 'spec.md').write_text('changed fixture', encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'output hash mismatch'):
                runner.read_capture(self.path, self.sha)
            git.assert_not_called()

    def test_production_drift_refused(self):
        with patch.object(runner.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, 'changed', '')):
            with self.assertRaisesRegex(RuntimeError, 'differs from genuine call revision'):
                runner.read_capture(self.path, self.sha)

    def test_writable_capture_cannot_be_promoted_to_read_only_readiness(self):
        self.capture['planner_contract']['file_boundaries'] = ['future.ts']
        self.path.write_text(json.dumps(self.capture), encoding='utf-8')
        with patch.object(runner.subprocess, 'run') as git:
            with self.assertRaisesRegex(RuntimeError, 'not the zero-authority'):
                runner.read_capture(self.path, runner.digest(self.path))
            git.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
