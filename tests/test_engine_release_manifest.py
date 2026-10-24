"""The committed engine-release.json names exactly the engine folder that ships."""
import subprocess
import sys
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
TOOL = PACKAGE / 'tools/engine_release.py'


class EngineReleaseManifestTests(unittest.TestCase):
    def check(self):
        return subprocess.run([sys.executable, '-B', str(TOOL), '--check'], capture_output=True, text=True)

    def test_manifest_matches_the_bundled_engine(self):
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_changed_engine_byte_fails_the_check(self):
        # Negative control: the check must be able to fail, and the file is restored byte for byte.
        target = PACKAGE / 'engine/watchdog.py'
        original = target.read_bytes()
        try:
            target.write_bytes(original + b'#')
            result = self.check()
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('does not match engine/', result.stderr)
        finally:
            target.write_bytes(original)
        self.assertEqual(target.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
