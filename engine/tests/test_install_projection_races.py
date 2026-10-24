"""Independent owner edits at the install mutation seam must survive."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
import candidate_apply
import install
import wikiconfig
import test_engine_install as fixtures


class InstallProjectionRaceTests(unittest.TestCase):
    def test_new_launcher_and_location_owner_entries_are_preserved(self):
        for relative in ('scripts/palantir_wiki_watchdog.py', 'state/wiki-automation/location.json'):
            with self.subTest(path=relative), tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
                home = Path(temp)
                plan = fixtures.EngineInstallTests().prepared(home)
                target = home / relative
                newer = b'Owner-created entry after preview\n'
                written = []

                def owner(point):
                    if point == 'before-replace:' + target.name and not written:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        reply = subprocess.run([sys.executable, '-B', '-c',
                            'import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(bytes.fromhex(sys.argv[2]))',
                            str(target), newer.hex()], capture_output=True, text=True, timeout=15)
                        self.assertEqual(reply.returncode, 0, reply.stderr)
                        written.append(True)

                with patch.object(candidate_apply, '_checkpoint', owner):
                    with self.assertRaises((candidate_apply.ApplyRefused, wikiconfig.ConfigError)):
                        install.apply_plan(plan, plan['digest'])
                self.assertEqual(written, [True])
                self.assertEqual(target.read_bytes(), newer)

    def test_owner_settings_recreation_during_capture_gap_is_preserved(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            plan = fixtures.EngineInstallTests().prepared(home)
            target = Path(plan['audit_dir']) / 'settings.json'
            before = target.read_bytes()
            newer = json.dumps({**json.loads(before), 'owner_note': 'Recreated during the publication gap'}).encode()
            written = []

            def owner(point):
                if point == 'after-capture:source' and not written:
                    self.assertFalse(target.exists())
                    result = subprocess.run([sys.executable, '-B', '-c',
                        'import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(bytes.fromhex(sys.argv[2]))',
                        str(target), newer.hex()], capture_output=True, text=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    written.append(True)

            with patch.object(candidate_apply, '_checkpoint', owner):
                with self.assertRaises(candidate_apply.ApplyRefused):
                    install.apply_plan(plan, plan['digest'])
            self.assertEqual(target.read_bytes(), newer)
            self.assertEqual(written, [True])
            captures = list(target.parent.rglob('captured.bin'))
            self.assertEqual(len(captures), 1)
            self.assertEqual(captures[0].read_bytes(), before)

    def test_real_settings_capture_deaths_replay_original_plan(self):
        phases = ['before-capture:source', 'after-capture:source', 'before-publish:source', 'after-publish:source']
        for point in phases:
            with self.subTest(point=point), tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
                home = Path(temp)
                plan = fixtures.EngineInstallTests().prepared(home)
                request = home / 'plan.json'
                request.write_bytes(json.dumps(plan).encode())
                result = subprocess.run([sys.executable, '-B', str(ROOT / 'tests/install_apply_worker.py'),
                    str(request), point], capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 91, result.stdout + result.stderr)
                recovered = install.apply_plan(plan, plan['digest'])
                self.assertTrue(recovered['ok'])
                self.assertEqual(install.apply_plan(plan, plan['digest']), recovered)
                self.assertEqual(json.loads((home / 'state/wiki-automation/location.json').read_bytes()), plan['location'])
        print('INSTALL_CAPTURE_INTERRUPTION_CASES recovered=' + str(len(phases)))

    def test_settings_edit_after_hash_check_is_preserved(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            plan = fixtures.EngineInstallTests().prepared(home)
            target = Path(plan['audit_dir']) / 'settings.json'
            newer = json.dumps({**json.loads(target.read_bytes()),
                'deliver': 'owner-selected-delivery', 'owner_note': 'Changed after preview'}).encode()
            raced = []

            def owner(point):
                if point == 'before-replace:settings.json' and not raced:
                    writer = subprocess.run([sys.executable, '-B', '-c',
                        'import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(bytes.fromhex(sys.argv[2]))',
                        str(target), newer.hex()], capture_output=True, text=True, timeout=15)
                    self.assertEqual(writer.returncode, 0, writer.stderr)
                    raced.append(True)

            with patch.object(candidate_apply, '_checkpoint', owner):
                with self.assertRaises((candidate_apply.ApplyRefused, wikiconfig.ConfigError)):
                    install.apply_plan(plan, plan['digest'])
            self.assertEqual(raced, [True])
            preserved = target.exists() and target.read_bytes() == newer
            retained = [path for path in target.parent.rglob('captured.bin') if path.read_bytes() == newer]
            self.assertTrue(preserved or retained, 'The independently written owner settings disappeared')
            self.assertFalse((home / 'state/wiki-automation/location.json').exists())


if __name__ == '__main__':
    unittest.main()
