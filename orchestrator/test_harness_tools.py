import unittest
from pathlib import Path
import tempfile
import shutil
from orchestrator.harness_tools import (
    strip_ansi,
    extract_type_skeletons,
    sanitize_test_output,
)


class TestHarnessTools(unittest.TestCase):
    def test_strip_ansi(self):
        colored = "\x1b[31mFAIL\x1b[0m \x1b[32msrc/test.ts\x1b[0m"
        self.assertEqual(strip_ansi(colored), "FAIL src/test.ts")

    def test_sanitize_test_output(self):
        noisy_log = """
         RUN  v1.2.3 /home/user/project
        
        FAIL src/domain/__tests__/calc.test.ts
        ✕ calculates total volume (12ms)
          ● calculates total volume
            Expected: 100
            Received: 0
            at Object.<anonymous> (src/domain/calc.ts:25:12)
        
        Test Suites: 1 failed, 1 total
        Tests:       1 failed, 1 total
        """
        sanitized = sanitize_test_output(noisy_log)
        self.assertIn("FAIL src/domain/__tests__/calc.test.ts", sanitized)
        self.assertIn("Expected: 100", sanitized)
        self.assertIn("Received: 0", sanitized)
        self.assertNotIn("RUN  v1.2.3", sanitized)

    def test_extract_type_skeletons(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            types_dir = root / "src" / "domain"
            types_dir.mkdir(parents=True, exist_ok=True)
            
            ts_file = types_dir / "types.ts"
            ts_file.write_text(
                """
                export interface WorkoutSession {
                    id: string;
                    durationMinutes: number;
                }
                
                export type WeightUnit = 'kg' | 'lbs';
                
                export function helperFunc() {
                    return 42;
                }
                """,
                encoding="utf-8",
            )
            
            skeletons = extract_type_skeletons(root)
            self.assertIn("interface WorkoutSession", skeletons)
            self.assertIn("type WeightUnit", skeletons)
            self.assertNotIn("helperFunc", skeletons)


if __name__ == "__main__":
    unittest.main()
