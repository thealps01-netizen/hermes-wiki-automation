"""Real filesystem links must not be laundered through a checked root."""
from contextlib import contextmanager
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

from workflow_paths import PathRefused, checked_path


class ReparseConfinementTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='engine-reparse-', dir=os.environ.get('TMPDIR'))
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()

    @contextmanager
    def directory_link(self, link, target):
        link.parent.mkdir(parents=True, exist_ok=True)
        target.mkdir(parents=True, exist_ok=True)
        if os.name == 'nt':
            reply = subprocess.run([os.environ['COMSPEC'], '/d', '/c', 'mklink', '/J', str(link), str(target)],
                capture_output=True, text=True, check=True)
            self.assertIn('<<===>>', reply.stdout)
            self.assertFalse(link.is_symlink())
            self.assertTrue(link.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        else:
            link.symlink_to(target, target_is_directory=True)
        try:
            yield link
        finally:
            if os.name == 'nt':
                link.rmdir()
            else:
                link.unlink()

    def test_linked_roots_and_ancestors_refused_for_sensitive_paths(self):
        relatives = ('releases/revision/install.py', 'scripts/palantir_wiki_watchdog.py',
            'data/settings.json', 'owner-decisions.sqlite', 'workflow.sqlite')
        for index, relative in enumerate(relatives):
            with self.subTest(relative=relative):
                with self.directory_link(self.base / str(index) / 'linked', self.base / str(index) / 'outside') as link:
                    for root in (link, link / 'missing-root'):
                        with self.subTest(root=root.name), self.assertRaises(PathRefused):
                            checked_path(root, relative)

    def test_internal_junction_cannot_alias_sensitive_descendants(self):
        for index, relative in enumerate(('install.py', 'palantir_wiki_watchdog.py',
                'settings.json', 'owner-decisions.sqlite', 'workflow.sqlite')):
            root = self.base / str(index)
            with self.subTest(relative=relative), self.directory_link(root / 'linked', root / 'original'):
                with self.assertRaises(PathRefused):
                    checked_path(root, 'linked/' + relative)

    def test_dangling_directory_link_refused_for_missing_leaf(self):
        target = self.base / 'removed'
        with self.directory_link(self.base / 'linked', target) as link:
            target.rmdir()
            self.assertFalse(link.exists())
            with self.assertRaises(PathRefused):
                checked_path(self.base, 'linked/new/workflow.sqlite')

    def test_hardlinked_sensitive_files_refused(self):
        for name in ('install.py', 'palantir_wiki_watchdog.py', 'settings.json',
                'owner-decisions.sqlite', 'workflow.sqlite'):
            with self.subTest(name=name):
                source = self.base / name
                source.write_bytes(b'fixture')
                os.link(source, self.base / (name + '.alias'))
                self.assertGreater(source.lstat().st_nlink, 1)
                with self.assertRaises(PathRefused):
                    checked_path(self.base, name)

    def test_owner_authority_initialization_refuses_linked_data_root(self):
        from owner_decisions import DecisionRefused, OwnerDecisions
        target = self.base / 'outside'
        with self.directory_link(self.base / 'linked', target) as link:
            with self.assertRaises(DecisionRefused):
                with OwnerDecisions(link, initialize=True):
                    self.fail('Linked authority opened')
            self.assertFalse((target / 'owner-decisions.sqlite').exists())

    def test_plain_existing_and_missing_paths_remain_usable(self):
        source = self.base / 'settings.json'
        source.write_bytes(b'{}')
        self.assertEqual(checked_path(self.base, 'settings.json'), source)
        self.assertEqual(checked_path(self.base / 'missing-root', 'nested/workflow.sqlite'),
            self.base / 'missing-root/nested/workflow.sqlite')

    def test_symlinks_refused_without_windows_attributes(self):
        if os.name == 'nt':
            self.skipTest('POSIX symlink compatibility; Windows is covered by real junctions')
        for target in (self.base / 'existing', self.base / 'missing'):
            target.parent.mkdir(exist_ok=True)
            if target.name == 'existing':
                target.write_bytes(b'fixture')
            link = self.base / (target.name + '-link')
            link.symlink_to(target)
            with self.subTest(target=target.name), self.assertRaises(PathRefused):
                checked_path(self.base, link.name)


if __name__ == '__main__':
    unittest.main()
