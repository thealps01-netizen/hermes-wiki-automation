"""Selected code and mutable data are exercised through the actual engine."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_api():
    spec = importlib.util.spec_from_file_location('wiki_separated_paths_api', ROOT / 'dashboard/plugin_api.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class EnginePathsTests(unittest.TestCase):
    def test_schema2_config_reads_selected_data_without_writing_code(self):
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        api = load_api()
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            code, data, wiki = home / 'code', home / 'data', home / 'wiki'
            code.mkdir()
            data.mkdir()
            (wiki / '.llm-wiki').mkdir(parents=True)
            (wiki / '.llm-wiki/project.json').write_bytes(b'{"id":"selected-fixture"}')
            for source in Path(os.environ['WIKI_ENGINE_TEST_DIR']).glob('*.py'):
                shutil.copy2(source, code / source.name)
            settings = {'project_root': str(wiki), 'project_id': 'selected-fixture',
                        'audit_dir': str(data), 'hermes_home': str(home)}
            (data / 'settings.json').write_bytes(json.dumps(settings).encode())
            location = home / 'state/wiki-automation/location.json'
            location.parent.mkdir(parents=True)
            location.write_bytes(json.dumps({'schema': 2, 'engine_dir': str(code), 'audit_dir': str(data)}).encode())
            before = {str(p.relative_to(home)): p.read_bytes() for p in home.rglob('*') if p.is_file()}
            token = set_hermes_home_override(home)
            try:
                with patch.dict(os.environ, {'LLMWIKI_AUDIT_DIR': '', 'LLMWIKI_SETTINGS': ''}):
                    result = api.automation()
                    self.assertTrue(result['available'], result)
                    self.assertEqual(result['settings']['project_root'], str(wiki), result)
                    self.assertEqual(result['audit_dir'], str(data))
                    self.assertTrue(result['scripts']['wiki_autocommit.py'])
            finally:
                reset_hermes_home_override(token)
            after = {str(p.relative_to(home)): p.read_bytes() for p in home.rglob('*') if p.is_file()}
            self.assertEqual(after, before, 'A read-only config request mutated selected code/data')

    def test_schema2_panel_consumers_execute_code_with_selected_settings(self):
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        api = load_api()
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            code, data, wiki = home / 'code', home / 'data', home / 'wiki'
            code.mkdir()
            data.mkdir()
            (wiki / '.llm-wiki').mkdir(parents=True)
            (wiki / '.llm-wiki/project.json').write_bytes(b'{"id":"selected-fixture"}')
            (wiki / 'raw/sources').mkdir(parents=True)
            (wiki / 'raw/evidence').mkdir()
            (wiki / 'wiki').mkdir()
            (wiki / 'wiki/fixture.md').write_bytes(b'# Selected fixture\n')
            for source in Path(os.environ['WIKI_ENGINE_TEST_DIR']).glob('*.py'):
                shutil.copy2(source, code / source.name)
            settings_path = data / 'settings.json'
            settings_path.write_bytes(json.dumps({'project_root': str(wiki), 'project_id': 'selected-fixture',
                'audit_dir': str(data), 'hermes_home': str(home), 'owner_approval_enabled': True,
                'owner_approval_owner': {'mode': 'local_owner', 'home': str(home)}}).encode())
            (code / 'jobs.json').write_bytes(json.dumps({'jobs': {'fixture': {'kind': 'script',
                'impl': 'wiki_audit.py', 'launcher': 'fixture.py'}}}).encode())
            location = home / 'state/wiki-automation/location.json'
            location.parent.mkdir(parents=True)
            location.write_bytes(json.dumps({'schema': 2, 'engine_dir': str(code), 'audit_dir': str(data)}).encode())
            token = set_hermes_home_override(home)
            calls = []
            real_run = api.subprocess.run
            def record(command, **kwargs):
                calls.append((command, kwargs.get('env')))
                return real_run(command, **kwargs)
            try:
                with patch.dict(os.environ, {'LLMWIKI_AUDIT_DIR': '', 'LLMWIKI_SETTINGS': ''}), patch.object(api.subprocess, 'run', side_effect=record):
                    self.assertTrue(api._owner_run('initialize', {})['ok'])
                    self.assertTrue(api.candidates_list()['ok'])
                    self.assertTrue(api.harvest_status()['ok'])
                    self.assertTrue(api.automation_validate({'path': str(wiki)})['ok'])
                    self.assertTrue(api.automation_derive({'picked': str(wiki)})['ok'])
                    self.assertTrue(api.automation_candidates(root=str(home))['ok'])
                    jobs = api.jobs_view_route()
                    self.assertTrue(jobs['roles'][0]['target']['impl_ok'], jobs)
                    calls = [(command, env) for command, env in calls if any(str(a).endswith('.py') for a in command)]
                    self.assertGreaterEqual(len(calls), 7)
                    for command, env in calls:
                        script = next(Path(a) for a in command if str(a).endswith('.py'))
                        self.assertEqual(script.parent, code)
                        self.assertEqual(env['LLMWIKI_SETTINGS'], str(settings_path))
                        self.assertEqual(env['HERMES_HOME'], str(home))
                        self.assertIn('-B', command)
                    before_settings = settings_path.read_bytes()
                    original_location = location.read_bytes()
                    calls.clear()
                    def rebind(command, **kwargs):
                        result = record(command, **kwargs)
                        if len(calls) == 1:
                            location.write_bytes(b'{"schema":999}')
                        return result
                    try:
                        with patch.object(api.subprocess, 'run', side_effect=rebind), patch.object(api, 'resolve_engine_paths', wraps=api.resolve_engine_paths) as resolved:
                            saved = api.automation_settings({'project_root': str(wiki)})
                            self.assertTrue(saved['ok'], saved)
                            self.assertEqual(resolved.call_count, 1)
                            self.assertEqual(len(calls), 4)
                            self.assertTrue(all(env['LLMWIKI_SETTINGS'] == str(settings_path) for command, env in calls))
                    finally:
                        location.write_bytes(original_location)
                        settings_path.write_bytes(before_settings)
                    with patch.object(api, 'resolve_engine_paths', wraps=api.resolve_engine_paths) as resolved:
                        health = api.health_watchdog()
                        self.assertEqual(health['log'], str(data / 'alerts.log'))
                        self.assertEqual(resolved.call_count, 1, 'Health read re-resolved its data selection')
            finally:
                reset_hermes_home_override(token)

    def test_selected_settings_and_override_locations_fail_closed(self):
        api = load_api()
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            code, data = home / 'code', home / 'data'
            code.mkdir()
            data.mkdir()
            (code / 'wikiconfig.py').write_bytes(b'raise AssertionError("must not run")\n')
            location = home / 'state/wiki-automation/location.json'
            location.parent.mkdir(parents=True)
            location.write_bytes(json.dumps({'schema': 2, 'engine_dir': str(code), 'audit_dir': str(data)}).encode())
            with patch.object(api, '_hermes_home', return_value=home), patch.dict(os.environ, {'LLMWIKI_AUDIT_DIR': '', 'LLMWIKI_SETTINGS': ''}), patch.object(api.subprocess, 'run', return_value=api.subprocess.CompletedProcess([], 2, '', 'blocked')) as spawned:
                for content in (None, b'{broken', b'[]'):
                    with self.subTest(settings=content):
                        if content is not None:
                            (data / 'settings.json').write_bytes(content)
                        reply = api.automation()
                        self.assertFalse(reply['available'], reply)
                        self.assertIn('settings', reply['error'].lower())
                self.assertEqual(spawned.call_count, 0, 'Invalid selection spawned a subprocess')
            with patch.dict(os.environ, {'LLMWIKI_AUDIT_DIR': str(home / 'missing'), 'LLMWIKI_SETTINGS': ''}):
                with self.assertRaises(ValueError):
                    api._engine_paths()
            with patch.dict(os.environ, {'LLMWIKI_AUDIT_DIR': str(code), 'LLMWIKI_SETTINGS': str(home / 'missing.json')}):
                with self.assertRaises(ValueError):
                    api._engine_paths()

    def test_legacy_code_override_and_explicit_settings_keep_their_meaning(self):
        api = load_api()
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            selected, explicit = home / 'selected', home / 'explicit'
            selected.mkdir()
            explicit.mkdir()
            settings = explicit / 'settings.json'
            settings.write_bytes(b'{}')
            with patch.object(api, '_hermes_home', return_value=home), patch.dict(os.environ, {'LLMWIKI_AUDIT_DIR': str(selected), 'LLMWIKI_SETTINGS': str(settings)}):
                paths = api._engine_paths()
                self.assertEqual(paths.engine_dir, selected)
                self.assertEqual(paths.audit_dir, selected)
                self.assertEqual(paths.settings_path, settings)
                self.assertEqual(paths.environment()['LLMWIKI_SETTINGS'], str(settings))
            with patch.object(api, '_hermes_home', return_value=home), patch.dict(os.environ, {'LLMWIKI_AUDIT_DIR': '.', 'LLMWIKI_SETTINGS': str(settings)}):
                self.assertEqual(api._engine_paths().engine_dir, Path.cwd().resolve(), 'Existing relative test code overrides changed meaning')
            location = home / 'state/wiki-automation/location.json'
            location.parent.mkdir(parents=True)
            (selected / 'settings.json').write_bytes(b'{}')
            for schema in (None, 1):
                record = {'audit_dir': str(selected)}
                if schema is not None:
                    record['schema'] = schema
                location.write_bytes(json.dumps(record).encode())
                with patch.object(api, '_hermes_home', return_value=home), patch.dict(os.environ, {'LLMWIKI_AUDIT_DIR': '', 'LLMWIKI_SETTINGS': ''}):
                    paths = api._engine_paths()
                    self.assertEqual(paths.engine_dir, selected)
                    self.assertEqual(paths.audit_dir, selected)
                    self.assertEqual(paths.settings_path, selected / 'settings.json')

    def test_invalid_selected_record_never_uses_default_or_executes(self):
        api = load_api()
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            fallback = home / 'fallback'
            fallback.mkdir()
            location = home / 'state/wiki-automation/location.json'
            location.parent.mkdir(parents=True)
            records = [b'{broken', b'[]', b'{"schema":3}', b'{"schema":true}',
                       json.dumps({'schema': 2, 'engine_dir': str(home / 'missing'), 'audit_dir': str(fallback)}).encode(),
                       json.dumps({'schema': 1, 'audit_dir': 'relative'}).encode()]
            with patch.object(api, '_hermes_home', return_value=home), patch.object(api, 'AUDIT_DIR', fallback), patch.dict(os.environ, {'LLMWIKI_AUDIT_DIR': '', 'LLMWIKI_SETTINGS': ''}), patch.object(api.subprocess, 'run', return_value=api.subprocess.CompletedProcess([], 2, '', 'blocked')) as spawned:
                for record in records:
                    with self.subTest(record=record):
                        location.write_bytes(record)
                        self.assertFalse(api.automation()['available'])
                        with self.assertRaises(ValueError):
                            api._audit_dir()
                location.unlink()
                location.mkdir()
                self.assertFalse(api.automation()['available'])
                self.assertEqual(spawned.call_count, 0, 'Invalid selection spawned a subprocess')

    def test_runtime_proof_fingerprints_selected_code_not_mutable_data(self):
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from types import SimpleNamespace
        spec = importlib.util.spec_from_file_location('wiki_selected_engine_probe', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
        native = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = native
        spec.loader.exec_module(native)
        probe = sys.modules[spec.name + '.runtime_probe']
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            code, data = home / 'code', home / 'data'
            code.mkdir()
            data.mkdir()
            for source in Path(os.environ['WIKI_ENGINE_TEST_DIR']).glob('*.py'):
                shutil.copy2(source, code / source.name)
            (data / 'settings.json').write_bytes(b'{}')
            location = home / 'state/wiki-automation/location.json'
            location.parent.mkdir(parents=True)
            location.write_bytes(json.dumps({'schema': 2, 'engine_dir': str(code), 'audit_dir': str(data)}).encode())
            token = set_hermes_home_override(home)
            try:
                with patch.dict(os.environ, {'LLMWIKI_AUDIT_DIR': '', 'LLMWIKI_SETTINGS': ''}):
                    ctx = SimpleNamespace(get_config=lambda name, default=None: default)
                    initial = probe.probe(ctx, '1' * 64)
                    selected = initial.get('engine_identity')
                    self.assertIsInstance(selected, dict, initial)
                    self.assertEqual(selected['engine_dir'], str(code))
                    self.assertEqual(selected['settings_path'], str(data / 'settings.json'))
                    self.assertEqual(selected['audit_dir'], str(data))
                    (data / 'draft_adapter.py').write_bytes(b'Not executable engine code')
                    self.assertEqual(probe.probe(ctx, '2' * 64)['engine_identity'], selected)
                    (code / 'draft_adapter.py').write_bytes((code / 'draft_adapter.py').read_bytes() + b'\n')
                    changed = probe.probe(ctx, '3' * 64)
                    self.assertNotEqual(changed['engine_identity']['code_hash'], selected['code_hash'])
                    self.assertEqual(changed['loaded_code_hash'], initial['loaded_code_hash'])
                    self.assertEqual(changed['incarnation'], initial['incarnation'])
            finally:
                reset_hermes_home_override(token)

    def test_parallel_profiles_keep_context_bound_settings_in_subprocesses(self):
        from concurrent.futures import ThreadPoolExecutor
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        api = load_api()
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            root = Path(tmp)
            code = root / 'code'
            code.mkdir()
            for source in Path(os.environ['WIKI_ENGINE_TEST_DIR']).glob('*.py'):
                shutil.copy2(source, code / source.name)
            homes = [root / name for name in ('first-profile', 'second-profile')]
            for home in homes:
                data = home / 'data'
                data.mkdir(parents=True)
                (data / 'settings.json').write_bytes(json.dumps({'audit_dir': str(data),
                    'hermes_home': str(home), 'project_id': home.name}).encode())
                location = home / 'state/wiki-automation/location.json'
                location.parent.mkdir(parents=True)
                location.write_bytes(json.dumps({'schema': 2, 'engine_dir': str(code), 'audit_dir': str(data)}).encode())
            original_home = os.environ.get('HERMES_HOME')
            def read(home):
                token = set_hermes_home_override(home)
                try:
                    return api.automation()
                finally:
                    reset_hermes_home_override(token)
            with patch.dict(os.environ, {'LLMWIKI_AUDIT_DIR': '', 'LLMWIKI_SETTINGS': ''}), ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(read, homes))
            for home, result in zip(homes, results):
                self.assertTrue(result['available'], result)
                self.assertEqual(result['settings']['project_id'], home.name)
                self.assertEqual(result['settings']['hermes_home'], str(home))
                self.assertEqual(result['settings']['settings_path'], str(home / 'data/settings.json'))
            self.assertEqual(os.environ.get('HERMES_HOME'), original_home)


if __name__ == '__main__':
    unittest.main()
