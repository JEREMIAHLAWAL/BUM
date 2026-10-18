"""Fail-closed preparation contracts; no worktree creation or live npm smoke."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('bum05_preparation', HERE / 'run_preparation.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class PreparationContracts(unittest.TestCase):
    def test_credential_paths_refused_except_public_template(self):
        for name in ['.env', '.env.local', 'nested/.env.production', '.ssh/id_rsa', 'credentials.json']:
            self.assertTrue(runner.credential_path(name))
        self.assertFalse(runner.credential_path('.env.example'))

    def test_child_environment_has_no_credentials_or_injected_tools(self):
        private = runner.SCRATCH_BASE / 'dummy-environment'
        env = runner.sanitized_env({'PATH': os.environ['PATH'], 'OPENROUTER_API_KEY': 'fake',
                                   'ANTHROPIC_API_KEY': 'fake', 'NODE_OPTIONS': '--require evil.js',
                                   'GIT_CONFIG_COUNT': '999', 'npm_token': 'fake'}, private, private / 'hooks')
        self.assertFalse(any(k in env for k in ['OPENROUTER_API_KEY', 'ANTHROPIC_API_KEY', 'NODE_OPTIONS', 'npm_token']))
        self.assertEqual(env['GIT_CONFIG_COUNT'], '2')
        self.assertEqual(env['PYTHON_DOTENV_DISABLED'], '1')
        self.assertEqual(env['COREPACK_ENABLE_NETWORK'], '0')

    def test_wrong_head_persists_failure_without_attempting_worktree(self):
        with tempfile.TemporaryDirectory(dir=runner.SCRATCH_BASE, prefix='bum05-prep-negative-') as folder:
            output = Path(folder) / 'report.json'
            args = argparse.Namespace(scratch=folder, output=str(output), expected_bum_head='0' * 40,
                                      expected_finder_head='0' * 40)
            self.assertEqual(runner.run(args), 1)
            report = json.loads(output.read_text(encoding='utf-8'))
            self.assertFalse(report['success'])
            self.assertTrue(report['cleanup_api']['not_attempted'])
            self.assertEqual(report['commands'], [])
            self.assertFalse(Path(report['worktree_path']).exists())
            self.assertEqual(report['errors'][0]['label'], 'bum_not_clean_expected_committed_head')


if __name__ == '__main__':
    unittest.main(verbosity=2)
