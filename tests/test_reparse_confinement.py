"""Confinement uses real junctions on Windows, not mocked Path predicates."""
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


def load_module(name, relative):
    source = Path(__file__).resolve().parents[1] / relative
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lifecycle = load_module('reparse_lifecycle', 'dashboard/engine_lifecycle.py')
paths = load_module('reparse_engine_paths', 'engine_paths.py')


class ReparseConfinementTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='panel-reparse-', dir=os.environ.get('TMPDIR'))
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        environment = patch.dict(os.environ, {'LLMWIKI_AUDIT_DIR': '', 'LLMWIKI_SETTINGS': ''})
        environment.start()
        self.addCleanup(environment.stop)

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

    def selection(self, folder):
        home, code, data = (folder / name for name in ('home', 'code', 'data'))
        for directory in (home, code, data):
            directory.mkdir(parents=True)
        (data / 'settings.json').write_bytes(b'{}')
        location = home / 'state/wiki-automation/location.json'
        location.parent.mkdir(parents=True)
        record = {'schema': 2, 'engine_dir': str(code), 'audit_dir': str(data)}
        location.write_text(json.dumps(record), encoding='utf-8')
        return home, code, data, location, record

    def test_selected_code_and_data_reject_junctions_before_resolving(self):
        for field in ('engine_dir', 'audit_dir'):
            with self.subTest(field=field):
                home, code, data, location, record = self.selection(self.base / field)
                target = code if field == 'engine_dir' else data
                with self.directory_link(self.base / field / 'linked', target) as link:
                    for selected in (link, link / 'nested'):
                        selected.mkdir(exist_ok=True)
                        (selected / 'settings.json').write_bytes(b'{}')
                        record[field] = str(selected)
                        location.write_text(json.dumps(record), encoding='utf-8')
                        with self.subTest(selected=selected.name), self.assertRaises(paths.EnginePathError):
                            paths.resolve_engine_paths(home)

    def test_profile_home_rejects_junctions_before_resolving(self):
        home, code, data, location, record = self.selection(self.base / 'fixture')
        with self.directory_link(self.base / 'linked', home.parent) as link:
            with self.assertRaises(paths.EnginePathError):
                paths.resolve_engine_paths(link / home.name)

    def test_location_parent_rejects_junction_before_reading(self):
        home, code, data, location, record = self.selection(self.base / 'fixture')
        outside = self.base / 'outside-state'
        (home / 'state').rename(outside)
        with self.directory_link(home / 'state', outside):
            with self.assertRaises(paths.EnginePathError):
                paths.resolve_engine_paths(home)

    def test_settings_override_rejects_junction_before_resolving(self):
        home, code, data, location, record = self.selection(self.base / 'fixture')
        with self.directory_link(self.base / 'linked', data) as link:
            with patch.dict(os.environ, {'LLMWIKI_SETTINGS': str(link / 'settings.json')}):
                with self.assertRaises(paths.EnginePathError):
                    paths.resolve_engine_paths(home)

    def test_location_and_settings_reject_hardlinks(self):
        for leaf in ('location', 'settings'):
            with self.subTest(leaf=leaf):
                home, code, data, location, record = self.selection(self.base / leaf)
                target = location if leaf == 'location' else data / 'settings.json'
                os.link(target, self.base / (leaf + '.alias'))
                self.assertGreater(target.lstat().st_nlink, 1)
                with self.assertRaises(paths.EnginePathError):
                    paths.resolve_engine_paths(home)

    def test_code_identity_rejects_hardlinked_sources(self):
        home, code, data, location, record = self.selection(self.base / 'fixture')
        source = code / 'install.py'
        source.write_bytes(b'# fixture')
        os.link(source, self.base / 'outside.py')
        selected = paths.resolve_engine_paths(home)
        with self.assertRaises(paths.EnginePathError):
            selected.code_identity()

    def test_confined_refuses_linked_roots_ancestors_and_descendants(self):
        relatives = ('state/wiki-automation/releases/revision/install.py',
            'scripts/palantir_wiki_watchdog.py', 'state/wiki-automation/data/settings.json',
            'state/wiki-automation/data/owner-decisions.sqlite', 'state/wiki-automation/data/workflow.sqlite')
        for index, relative in enumerate(relatives):
            with self.subTest(relative=relative):
                folder = self.base / str(index)
                with self.directory_link(folder / 'linked', folder / 'outside') as link:
                    for root in (link, link / 'missing-root'):
                        with self.subTest(root=root.name), self.assertRaises(lifecycle.LifecycleRefused):
                            lifecycle.confined(root, relative)
                    with self.assertRaises(lifecycle.LifecycleRefused):
                        lifecycle.confined(folder, 'linked/' + relative)

    def test_release_staging_refuses_junction_without_outside_writes(self):
        home, package, outside = (self.base / name for name in ('home', 'package', 'outside'))
        home.mkdir()
        package.mkdir()
        (package / 'engine').mkdir()
        (package / 'engine/install.py').write_bytes(b'# scratch fixture')
        digest = lifecycle.release_digest({'install.py': b'# scratch fixture'})
        manifest = {'schema': 2, 'artifact': 'engine', 'revision': digest[:40], 'sha256': digest,
            'python_min': [3, 11], 'workflow_schema': {'min': 1, 'max': 1}}
        with self.directory_link(home / 'state/wiki-automation/releases', outside):
            with self.assertRaises(lifecycle.LifecycleRefused):
                lifecycle.stage_release(home, package, manifest)
            self.assertEqual(list(outside.iterdir()), [])
            self.assertFalse((home / 'state/wiki-automation/staging').exists())

    def test_dangling_directory_link_refused_for_missing_leaf(self):
        target = self.base / 'removed'
        with self.directory_link(self.base / 'linked', target) as link:
            target.rmdir()
            self.assertFalse(link.exists())
            with self.assertRaises(lifecycle.LifecycleRefused):
                lifecycle.confined(self.base, 'linked/new/workflow.sqlite')
            with patch.dict(os.environ, {'LLMWIKI_AUDIT_DIR': str(link)}):
                with self.assertRaisesRegex(paths.EnginePathError, 'Linked'):
                    paths.resolve_engine_paths(self.base)

    def test_confined_refuses_hardlinked_sensitive_files(self):
        for name in ('install.py', 'palantir_wiki_watchdog.py', 'settings.json',
                'owner-decisions.sqlite', 'workflow.sqlite', 'location.json'):
            with self.subTest(name=name):
                source = self.base / name
                source.write_bytes(b'fixture')
                os.link(source, self.base / (name + '.alias'))
                self.assertGreater(source.lstat().st_nlink, 1)
                with self.assertRaises(lifecycle.LifecycleRefused):
                    lifecycle.confined(self.base, name)

    def test_plain_selection_and_missing_paths_remain_usable(self):
        home, code, data, location, record = self.selection(self.base / 'fixture')
        (code / 'install.py').write_bytes(b'# fixture')
        selected = paths.resolve_engine_paths(home)
        self.assertEqual((selected.home, selected.engine_dir, selected.audit_dir), (home, code, data))
        self.assertEqual(selected.settings_path, data / 'settings.json')
        self.assertEqual(set(selected.code_identity()), {'engine_dir', 'audit_dir', 'settings_path', 'code_hash'})
        self.assertEqual(lifecycle.confined(self.base / 'missing-root', 'nested/workflow.sqlite'),
            self.base / 'missing-root/nested/workflow.sqlite')

    def test_explicit_and_default_engine_roots_reject_junctions(self):
        with self.directory_link(self.base / 'linked', self.base / 'outside') as link:
            with patch.dict(os.environ, {'LLMWIKI_AUDIT_DIR': str(link)}):
                with self.assertRaises(paths.EnginePathError):
                    paths.resolve_engine_paths(self.base)
            with self.assertRaises(paths.EnginePathError):
                paths.resolve_engine_paths(self.base, default=link)

    def test_symlinks_refused_without_windows_attributes(self):
        if os.name == 'nt':
            self.skipTest('POSIX symlink compatibility; Windows is covered by real junctions')
        for target in (self.base / 'existing', self.base / 'missing'):
            if target.name == 'existing':
                target.write_bytes(b'{}')
            link = self.base / (target.name + '-link')
            link.symlink_to(target)
            with self.subTest(target=target.name):
                with self.assertRaises(lifecycle.LifecycleRefused):
                    lifecycle.confined(self.base, link.name)
                with patch.dict(os.environ, {'LLMWIKI_SETTINGS': str(link)}):
                    with self.assertRaises(paths.EnginePathError):
                        paths.resolve_engine_paths(self.base, default=self.base)


if __name__ == '__main__':
    unittest.main()
