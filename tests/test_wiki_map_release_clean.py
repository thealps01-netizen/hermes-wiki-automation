"""Reading the wiki map never writes into the installed engine release.

Why: the panel hashes every file under releases/<engine sha>/ and refuses all work when the folder
differs from its install record ("Installed code release is dirty or lacks verified file identity").
`GET /wiki/map` (2.11.0) loaded app_graph_isolated.py from that folder through the import system,
so Python wrote __pycache__/app_graph_isolated.cpython-*.pyc into the release on the first sphere
read and locked the panel. Rule: the dashboard compiles engine code in memory and never imports it
through a loader that may cache bytecode beside the source.
"""
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_api():
    spec = importlib.util.spec_from_file_location('wiki_map_release_api', ROOT / 'dashboard/plugin_api.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WikiMapReleaseTests(unittest.TestCase):
    def test_graph_rule_leaves_the_release_folder_unchanged(self):
        api = load_api()
        engine = Path(os.environ.get('WIKI_ENGINE_TEST_DIR') or ROOT / 'engine')
        saved = sys.dont_write_bytecode
        sys.dont_write_bytecode = False
        try:
            with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as tmp:
                release = Path(tmp) / 'release'
                release.mkdir()
                shutil.copy2(engine / 'app_graph_isolated.py', release / 'app_graph_isolated.py')
                before = sorted(p.relative_to(release).as_posix() for p in release.rglob('*'))
                rule = api._graph_rule(release)
                after = sorted(p.relative_to(release).as_posix() for p in release.rglob('*'))
        finally:
            sys.dont_write_bytecode = saved
        self.assertEqual(before, after, 'reading the graph rule added files to the release folder')
        for name in ('FRONTMATTER', 'WIKILINK', '_related'):
            self.assertTrue(hasattr(rule, name), name)

    def test_missing_rule_is_an_import_error(self):
        api = load_api()
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as tmp:
            with self.assertRaises(ImportError):
                api._graph_rule(Path(tmp))


if __name__ == '__main__':
    unittest.main()
