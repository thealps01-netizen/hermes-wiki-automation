"""Engine-owned setup uses isolated profile, code, project and data roots."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
import json
import install
import wikiconfig


class EngineInstallTests(unittest.TestCase):
    def prepared(self, home):
        import shutil
        root = Path(__file__).resolve().parents[1]
        code, wiki, data = home / 'code', home / 'wiki', home / 'data'
        code.mkdir()
        for source in [*root.glob('*.py'), *[root / name for name in ('jobs.json', 'panels.json', 'harvest_prompt.md')]]:
            shutil.copy2(source, code / source.name)
        shutil.copytree(root / 'launchers', code / 'launchers')
        (wiki / '.llm-wiki').mkdir(parents=True)
        (wiki / '.llm-wiki/project.json').write_text('{"id":"fixture"}')
        (wiki / 'wiki').mkdir()
        (wiki / 'wiki/index.md').write_text('# Fixture index\n')
        data.mkdir()
        cfg = {'project_root': str(wiki), 'project_id': 'fixture', 'hermes_home': str(home), 'audit_dir': str(data),
            'install_options': {'no_plugin': True, 'no_cron': True}}
        (data / 'settings.json').write_bytes(json.dumps(cfg).encode())
        return install.build_plan(cfg, home, code, data)

    def test_legacy_no_plugin_previews_location_without_panel_install(self):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            plan = self.prepared(home)
            with ExitStack() as stack:
                stack.enter_context(patch.object(wikiconfig, 'load', return_value=plan['settings']))
                for name in ('copy_launchers', 'install_wiki_hooks'):
                    stack.enter_context(patch.object(install, name))
                stack.enter_context(patch.object(install, 'note'))
                stack.enter_context(patch.object(install, 'report', []))
                stack.enter_context(patch.object(install, 'verify', return_value=True))
                panel = stack.enter_context(patch.object(install, 'install_panels'))
                location = stack.enter_context(patch.object(install, 'write_location'))
                self.assertEqual(install.main(['install.py', '--project-root', plan['settings']['project_root'],
                    '--hermes-home', str(home), '--dry-run', '--no-plugin', '--no-cron']), 0)
                panel.assert_not_called()
                location.assert_called_once_with(home, True)

    def test_real_cli_shared_data_metadata_root_preserves_existing_data(self):
        import shutil
        import subprocess
        from workflow_store import WorkflowStore
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            initial = self.prepared(home)
            data = home / 'state/wiki-automation'
            data.parent.mkdir()
            shutil.move(initial['audit_dir'], data)
            cfg = {**initial['settings'], 'audit_dir': str(data)}
            (data / 'settings.json').write_bytes(json.dumps(cfg).encode())
            retained = data / 'inbox/retained/source.md'
            retained.parent.mkdir(parents=True)
            retained.write_bytes(b'Existing owner draft must survive shared-root installation\n')
            with WorkflowStore(data / 'workflow.sqlite') as store:
                store.record_operation({'operation_id': 'owner-pending', 'type': 'candidate'})
                original_operation = store.get_operation('owner-pending')
            before = {path: path.read_bytes() for path in data.rglob('*') if path.is_file()}
            script = Path(initial['engine_dir']) / 'install.py'
            command = [sys.executable, '-B', str(script), '--project-root', cfg['project_root'],
                '--hermes-home', str(home), '--data-root', str(data.parent / '.' / data.name),
                '--no-cron', '--no-plugin', '--plan-json']
            preview = subprocess.run(command, capture_output=True, text=True, timeout=20)
            self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
            plan = json.loads(preview.stdout)
            self.assertEqual(before, {path: path.read_bytes() for path in data.rglob('*') if path.is_file()})
            artifact = home / 'shared-root-plan.json'
            artifact.write_bytes(json.dumps(plan).encode())
            apply = [sys.executable, '-B', str(script), '--apply-plan', str(artifact),
                '--expected-digest', plan['digest']]
            result = subprocess.run(apply, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(json.loads(result.stdout)['ok'])
            self.assertEqual(json.loads((data / 'location.json').read_bytes())['audit_dir'], str(data.resolve()))
            self.assertEqual(retained.read_bytes(), before[retained])
            with WorkflowStore(data / 'workflow.sqlite', read_only=True) as store:
                self.assertEqual(store.get_operation('owner-pending'), original_operation)
            settings_stamp = (data / 'settings.json').stat().st_mtime_ns
            repeated = subprocess.run(apply, capture_output=True, text=True, timeout=20)
            self.assertEqual(repeated.returncode, 0, repeated.stdout + repeated.stderr)
            self.assertEqual(json.loads(repeated.stdout), json.loads(result.stdout))
            self.assertEqual((data / 'settings.json').stat().st_mtime_ns, settings_stamp)
            self.assertFalse((home / 'cron/jobs.json').exists())

    def test_real_cli_shared_root_lock_contention_is_structured_and_preserves_owner(self):
        import shutil
        import subprocess
        from candidate_apply import operation_lock
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            initial = self.prepared(home)
            data = home / 'state/wiki-automation'
            data.parent.mkdir()
            shutil.move(initial['audit_dir'], data)
            cfg = {**initial['settings'], 'audit_dir': str(data)}
            settings = data / 'settings.json'
            settings.write_bytes(json.dumps(cfg).encode())
            plan = install.build_plan(cfg, home, Path(initial['engine_dir']), data)
            artifact = home / 'plan.json'
            artifact.write_bytes(json.dumps(plan).encode())
            before = settings.read_bytes()
            with operation_lock(data):
                result = subprocess.run([sys.executable, '-B', str(Path(initial['engine_dir']) / 'install.py'),
                    '--apply-plan', str(artifact), '--expected-digest', plan['digest']],
                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(result.stderr, '', 'Lock refusal leaked a traceback instead of the CLI JSON contract')
            refusal = json.loads(result.stdout)
            self.assertIs(refusal['ok'], False)
            self.assertEqual(refusal['state'], 'refused')
            self.assertIn('lock is busy', refusal['reason'].lower())
            self.assertEqual(settings.read_bytes(), before)
            self.assertFalse((data / 'location.json').exists())
            self.assertFalse((data / 'installation.sqlite').exists())

    def test_installation_journal_records_applied_projections_not_activation(self):
        from workflow_store import WorkflowStore
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            plan = self.prepared(home)
            result = install.apply_plan(plan, plan['digest'])
            with WorkflowStore(home / 'state/wiki-automation/installation.sqlite', read_only=True) as store:
                operation = store.get_operation(plan['digest'])
                self.assertEqual(operation['state'], 'applied')
                self.assertEqual(operation['result'], result)
                self.assertEqual(result['state'], 'location_recorded')
                self.assertNotIn('activated', result)
            self.assertEqual(install.apply_plan(plan, plan['digest']), result)

    def test_unrelated_mapped_native_job_is_preserved_and_refused(self):
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from cron.jobs import use_cron_store, create_job, get_job, list_jobs
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            previous = self.prepared(home)
            token = set_hermes_home_override(home)
            try:
                with use_cron_store(home):
                    unrelated = create_job(prompt='Owner unrelated task', schedule='0 6 * * *',
                        name='Owner task', no_agent=True, script='owner_task.py', paused=True)
                    cfg = {**previous['settings'], 'jobs': {'watchdog': unrelated['id']},
                        'install_options': {'no_plugin': True, 'no_cron': False}}
                    (Path(previous['audit_dir']) / 'settings.json').write_bytes(json.dumps(cfg).encode())
                    with self.assertRaises(wikiconfig.ConfigError):  # refused at preview, before any journal
                        install.build_plan(cfg, home, Path(previous['engine_dir']), Path(previous['audit_dir']))
                    self.assertFalse((home / 'state/wiki-automation/installation.sqlite').exists())
                    self.assertEqual(get_job(unrelated['id']), unrelated)
                    self.assertEqual(len(list_jobs(include_disabled=True)), 1)
                    self.assertFalse((home / 'state/wiki-automation/location.json').exists())
            finally:
                reset_hermes_home_override(token)

    def test_invalid_location_never_resets_or_changes_retained_data(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            previous = self.prepared(home)
            location = home / 'state/wiki-automation/location.json'
            location.parent.mkdir(parents=True)
            for record in ({}, {'schema': 999, 'audit_dir': previous['audit_dir']},
                    {'schema': 2, 'engine_dir': previous['engine_dir'], 'audit_dir': 'relative-data'}):
                with self.subTest(record=record):
                    original = json.dumps(record).encode()
                    location.write_bytes(original)
                    with self.assertRaises(wikiconfig.ConfigError):
                        install.build_plan(previous['settings'], home, Path(previous['engine_dir']), Path(previous['audit_dir']))
                    self.assertEqual(location.read_bytes(), original)
            location.write_bytes(json.dumps(previous['location']).encode())
            other = home / 'other-data'
            with self.assertRaises(wikiconfig.ConfigError):
                install.build_plan(previous['settings'], home, Path(previous['engine_dir']), other)
            self.assertFalse(other.exists())

    def test_explicit_install_choices_override_saved_choices(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            previous = self.prepared(home)
            requested = {**previous['settings'], 'install_options': {'no_plugin': True, 'no_cron': False}}
            plan = install.build_plan(requested, home, Path(previous['engine_dir']), Path(previous['audit_dir']))
            self.assertIs(plan['settings']['install_options']['no_cron'], False)
            self.assertIs(plan['settings']['install_options']['no_plugin'], True)

    def test_real_install_projection_death_reuses_the_same_plan(self):
        import subprocess
        import sqlite3
        from contextlib import closing
        import candidate_apply
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            base = Path(tmp)
            trace = base / 'trace'
            trace.mkdir()
            plan = self.prepared(trace)
            points = []
            with patch.object(candidate_apply, '_checkpoint', side_effect=points.append):
                install.apply_plan(plan, plan['digest'])
            recovered = 0
            for number, point in enumerate(dict.fromkeys(points)):
                with self.subTest(checkpoint=point):
                    home = base / f'case-{number}'
                    home.mkdir()
                    pending = self.prepared(home)
                    artifact = home / 'install-plan.json'
                    artifact.write_bytes(json.dumps(pending).encode())
                    proc = subprocess.run([sys.executable, str(Path(__file__).with_name('install_apply_worker.py')),
                        str(artifact), point], capture_output=True, timeout=20)
                    self.assertEqual(proc.returncode, 91, proc.stderr.decode(errors='replace'))
                    result = install.apply_plan(pending, pending['digest'])
                    self.assertTrue(result['ok'])
                    location = json.loads((home / 'state/wiki-automation/location.json').read_bytes())
                    self.assertEqual(location['engine_dir'], pending['engine_dir'])
                    self.assertEqual(install.apply_plan(pending, pending['digest']), result)
                    with closing(sqlite3.connect(home / 'state/wiki-automation/installation.sqlite')) as database:
                        self.assertEqual(database.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 1)
                    recovered += 1
            self.assertGreaterEqual(recovered, 6)
            print(f'INSTALL_PROJECTION_INTERRUPTION_CASES recovered={recovered}')

    def test_install_does_not_cross_an_unfinished_source_application(self):
        from workflow_store import WorkflowStore
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            plan = self.prepared(home)
            with WorkflowStore(Path(plan['audit_dir']) / 'workflow.sqlite') as store:
                store.record_operation({'operation_id': 'busy-source', 'type': 'candidate'})
                for old, new in (('collected', 'drafted'), ('drafted', 'awaiting_approval'), ('awaiting_approval', 'applying')):
                    store.transition('busy-source', old, new)
            with self.assertRaises(wikiconfig.ConfigError):
                install.apply_plan(plan, plan['digest'])
            self.assertFalse((home / 'state/wiki-automation/location.json').exists())

    def test_resume_refuses_changed_project_identity(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            plan = self.prepared(home)
            install.apply_plan(plan, plan['digest'])
            identity = Path(plan['settings']['project_root']) / '.llm-wiki/project.json'
            identity.write_text('{"id":"different-owner-project"}')
            with self.assertRaises(wikiconfig.ConfigError):
                install.apply_plan(plan, plan['digest'])
            self.assertEqual(json.loads(identity.read_bytes())['id'], 'different-owner-project')

    def test_job_save_before_id_record_reconciles_without_duplicate_creation(self):
        import subprocess
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from cron.jobs import use_cron_store, list_jobs
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            base = Path(tmp)
            for role in ('autocommit', 'ingest_watch', 'watchdog', 'session_harvest'):
                with self.subTest(role=role):
                    home = base / role
                    home.mkdir()
                    initial = self.prepared(home)
                    cfg = {**initial['settings'], 'install_options': {'no_plugin': True, 'no_cron': False}}
                    (Path(initial['audit_dir']) / 'settings.json').write_bytes(json.dumps(cfg).encode())
                    plan = install.build_plan(cfg, home, Path(initial['engine_dir']), Path(initial['audit_dir']))
                    artifact = home / 'plan.json'
                    artifact.write_bytes(json.dumps(plan).encode())
                    process = subprocess.run([sys.executable, str(Path(__file__).with_name('install_apply_worker.py')),
                        str(artifact), 'after-create-job:' + role], capture_output=True, timeout=20)
                    self.assertEqual(process.returncode, 91, process.stderr.decode(errors='replace'))
                    install.apply_plan(plan, plan['digest'])
                    token = set_hermes_home_override(home)
                    try:
                        with use_cron_store(home):
                            jobs = list_jobs(include_disabled=True)
                            self.assertEqual(len(jobs), len(plan['job_definitions']))
                            self.assertEqual(len({job['id'] for job in jobs}), len(jobs))
                            self.assertTrue(all(job['enabled'] is False for job in jobs))
                    finally:
                        reset_hermes_home_override(token)
            print('INSTALL_NATIVE_JOB_INTERRUPTION_CASES recovered=4')

    def test_real_engine_only_cli_uses_selected_profile_and_records_location(self):
        import subprocess
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            selected = self.prepared(home)
            script = Path(selected['engine_dir']) / 'install.py'
            command = [sys.executable, '-B', str(script), '--project-root', selected['settings']['project_root'],
                '--hermes-home', str(home), '--data-root', selected['audit_dir'], '--no-cron', '--no-plugin']
            preview = subprocess.run([*command, '--plan-json'], capture_output=True, text=True, timeout=20)
            self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
            plan = json.loads(preview.stdout)
            self.assertFalse((home / 'state/wiki-automation/location.json').exists())
            applied = subprocess.run([*command, '--expected-digest', plan['digest']], capture_output=True, text=True, timeout=20)
            self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
            self.assertTrue(json.loads(applied.stdout)['ok'])
            self.assertEqual(json.loads((home / 'state/wiki-automation/location.json').read_bytes())['audit_dir'], selected['audit_dir'])
            self.assertFalse((home / 'plugins').exists())

    def test_update_preserves_real_job_ids_and_custom_schedules(self):
        import shutil
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from cron.jobs import use_cron_store, list_jobs, update_job
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            initial = self.prepared(home)
            cfg = {**initial['settings'], 'install_options': {'no_plugin': True, 'no_cron': False}}
            settings_file = Path(initial['audit_dir']) / 'settings.json'
            settings_file.write_bytes(json.dumps(cfg).encode())
            first = install.build_plan(cfg, home, Path(initial['engine_dir']), Path(initial['audit_dir']))
            install.apply_plan(first, first['digest'])
            token = set_hermes_home_override(home)
            try:
                with use_cron_store(home):
                    jobs = list_jobs(include_disabled=True)
                    watchdog = next(job for job in jobs if job['name'] == 'Watch Dog')
                    update_job(watchdog['id'], {'schedule': '20 7 * * *'})
                    original = {job['id']: job['schedule'] for job in list_jobs(include_disabled=True)}
                    new_code = home / 'code-updated'
                    shutil.copytree(Path(initial['engine_dir']), new_code)
                    cfg = json.loads(settings_file.read_bytes())
                    plan = install.build_plan(cfg, home, new_code, Path(initial['audit_dir']))
                    install.apply_plan(plan, plan['digest'])
                    self.assertEqual({job['id']: job['schedule'] for job in list_jobs(include_disabled=True)}, original)
                    self.assertEqual(json.loads(settings_file.read_bytes())['audit_dir'], initial['audit_dir'])
            finally:
                reset_hermes_home_override(token)

    def test_real_native_jobs_are_created_paused_and_not_duplicated(self):
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from cron.jobs import use_cron_store, list_jobs
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            before = self.prepared(home)
            cfg = {**before['settings'], 'install_options': {'no_plugin': True, 'no_cron': False},
                'schedule': {'watchdog': '15 8 * * *'}}
            (Path(before['audit_dir']) / 'settings.json').write_bytes(json.dumps(cfg).encode())
            plan = install.build_plan(cfg, home, Path(before['engine_dir']), Path(before['audit_dir']))
            result = install.apply_plan(plan, plan['digest'])
            self.assertTrue(result['ok'])
            token = set_hermes_home_override(home)
            try:
                with use_cron_store(home):
                    jobs = list_jobs(include_disabled=True)
                    self.assertEqual(len(jobs), len(plan['job_definitions']))
                    self.assertTrue(all(job['enabled'] is False and job['state'] == 'paused' for job in jobs))
                    agent = [job for job in jobs if not job['no_agent']]
                    self.assertEqual(len(agent), 1)
                    self.assertEqual(set(agent[0]['enabled_toolsets']), {'wiki_draft', 'no_mcp'})
                    ids = {job['id'] for job in jobs}
                    self.assertEqual(install.apply_plan(plan, plan['digest']), result)
                    self.assertEqual({job['id'] for job in list_jobs(include_disabled=True)}, ids)
            finally:
                reset_hermes_home_override(token)

    def test_unowned_same_name_launcher_is_preserved_and_refused(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            plan = self.prepared(home)
            script = home / 'scripts/palantir_wiki_watchdog.py'
            script.parent.mkdir()
            original = b'Owner customized this launcher; it is not engine-owned\n'
            script.write_bytes(original)
            with self.assertRaises(wikiconfig.ConfigError):
                install.build_plan(plan['settings'], home, Path(plan['engine_dir']), Path(plan['audit_dir']))
            self.assertEqual(script.read_bytes(), original)
            self.assertFalse((home / 'state/wiki-automation/location.json').exists())

    def test_generated_launcher_reads_the_selected_code_and_data(self):
        import subprocess
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            plan = self.prepared(home)
            install.apply_plan(plan, plan['digest'])
            launcher = home / 'scripts/palantir_wiki_watchdog.py'
            proc = subprocess.run([sys.executable, str(launcher), '--launcher-check'],
                capture_output=True, text=True, timeout=20)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            snapshot = json.loads(proc.stdout)
            self.assertEqual(snapshot['audit_dir'], plan['audit_dir'])
            self.assertEqual(snapshot['project_id'], plan['project_id'])
            self.assertEqual(snapshot['hermes_home'], plan['hermes_home'])
            self.assertFalse((home / 'cron/jobs.json').exists())

    def test_resume_refuses_a_changed_code_release(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            plan = self.prepared(home)
            install.apply_plan(plan, plan['digest'])
            code_file = Path(plan['engine_dir']) / 'wikiconfig.py'
            code_file.write_bytes(code_file.read_bytes() + b'\n# Different unreviewed release\n')
            with self.assertRaises(wikiconfig.ConfigError):
                install.apply_plan(plan, plan['digest'])

    def test_engine_only_apply_records_location_and_preserves_inbox(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            wiki, data = home / 'wiki', home / 'data'
            (wiki / '.llm-wiki').mkdir(parents=True)
            (wiki / '.llm-wiki/project.json').write_text('{"id":"fixture"}')
            (wiki / 'wiki').mkdir()
            (wiki / 'wiki/index.md').write_text('# Fixture index\n')
            (data / 'inbox/retained').mkdir(parents=True)
            retained = data / 'inbox/retained/source.md'
            retained.write_bytes(b'Owner work that must survive installation\n')
            cfg = {'project_root': str(wiki), 'project_id': 'fixture', 'hermes_home': str(home),
                'audit_dir': str(data), 'install_options': {'no_plugin': True, 'no_cron': True},
                'schedule': {'watchdog': '15 8 * * *'}}
            (data / 'settings.json').write_bytes(json.dumps(cfg).encode())
            plan = install.build_plan(cfg, home, Path(__file__).resolve().parents[1], data)
            with patch.object(install, 'hermes_cli', side_effect=AssertionError('Engine-only setup must not reinstall panels')):
                result = install.apply_plan(plan, plan['digest'])
            self.assertTrue(result['ok'])
            location = json.loads((home / 'state/wiki-automation/location.json').read_bytes())
            self.assertEqual(location['engine_dir'], plan['engine_dir'])
            self.assertEqual(location['audit_dir'], str(data.resolve()))
            self.assertEqual(retained.read_bytes(), b'Owner work that must survive installation\n')
            self.assertEqual(json.loads((data / 'settings.json').read_bytes())['schedule']['watchdog'], '15 8 * * *')
            self.assertFalse((home / 'cron/jobs.json').exists())
            settings_stamp = (data / 'settings.json').stat().st_mtime_ns
            location_stamp = (home / 'state/wiki-automation/location.json').stat().st_mtime_ns
            self.assertEqual(install.apply_plan(plan, plan['digest']), result)
            self.assertEqual((data / 'settings.json').stat().st_mtime_ns, settings_stamp)
            self.assertEqual((home / 'state/wiki-automation/location.json').stat().st_mtime_ns, location_stamp)
            import sqlite3
            from contextlib import closing
            with closing(sqlite3.connect(home / 'state/wiki-automation/installation.sqlite')) as database:
                self.assertEqual(database.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 1)

    def test_install_preview_is_readonly_and_binds_all_existing_state(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            wiki, data = home / 'wiki', home / 'data'
            (wiki / '.llm-wiki').mkdir(parents=True)
            (wiki / '.llm-wiki/project.json').write_text('{"id":"fixture"}')
            (wiki / 'raw').mkdir()
            (wiki / 'wiki').mkdir()
            (wiki / 'wiki/index.md').write_text('# Fixture index\n')
            data.mkdir()
            settings = data / 'settings.json'
            cfg = {'project_root': str(wiki), 'project_id': 'fixture', 'hermes_home': str(home),
                'audit_dir': str(data), 'schedule': {'watchdog': '15 8 * * *'}}
            settings.write_bytes(json.dumps(cfg).encode())
            before = {str(path): path.read_bytes() for path in home.rglob('*') if path.is_file()}
            plan = install.build_plan(cfg, home, Path(__file__).resolve().parents[1], data)
            self.assertEqual(plan['audit_dir'], str(data.resolve()))
            self.assertEqual(plan['settings']['schedule']['watchdog'], '15 8 * * *')
            self.assertEqual(install.build_plan(cfg, home, Path(__file__).resolve().parents[1], data), plan)
            self.assertEqual(len(plan['digest']), 64)
            self.assertEqual(before, {str(path): path.read_bytes() for path in home.rglob('*') if path.is_file()})
            settings.write_bytes(json.dumps({**cfg, 'schedule': {'watchdog': '0 7 * * *'}}).encode())
            changed = install.build_plan(cfg, home, Path(__file__).resolve().parents[1], data)
            self.assertNotEqual(changed['digest'], plan['digest'])

    def test_configured_missing_profile_never_selects_a_different_home(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            with patch.dict(os.environ, {'HERMES_HOME': str(home)}), self.assertRaises(wikiconfig.ConfigError):
                wikiconfig.hermes_home({'hermes_home': str(home / 'missing-profile')})

    def test_profile_location_selects_code_without_replacing_data(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            code, data = home / 'releases/fixture', home / 'data'
            code.mkdir(parents=True)
            data.mkdir()
            location = home / 'state/wiki-automation/location.json'
            location.parent.mkdir(parents=True)
            for record in ({'audit_dir': str(code)}, {'schema': 2, 'engine_dir': str(code), 'audit_dir': str(data)}):
                location.write_bytes(json.dumps(record).encode())
                cfg = {'hermes_home': str(home), 'audit_dir': str(data)}
                before = location.read_bytes()
                self.assertEqual(wikiconfig.engine_dir(cfg), code)
                self.assertEqual(wikiconfig.audit_dir(cfg), data)
                self.assertEqual(location.read_bytes(), before)

    def test_corrupt_existing_settings_are_never_reset_on_save(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            path = Path(tmp) / 'settings.json'
            original = b'{broken owner settings'
            path.write_bytes(original)
            with patch.dict(os.environ, {'LLMWIKI_SETTINGS': str(path)}), self.assertRaises(wikiconfig.ConfigError):
                wikiconfig.save({'project_root': str(Path(tmp) / 'wiki')})
            self.assertEqual(path.read_bytes(), original)

    def legacy(self, home, *, customize=None):
        """Recreate what the pre-panel install.py left: CLI-created script jobs, an enabled agent
        harvest job with a pre-run script, and a bare location."""
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from cron.jobs import use_cron_store, create_job
        previous = self.prepared(home)
        data = Path(previous['audit_dir'])
        location = home / 'state/wiki-automation/location.json'
        location.parent.mkdir(parents=True)
        location.write_bytes(json.dumps({'audit_dir': str(data), 'written_by': 'install.py'}).encode())
        definitions = previous['job_definitions']
        token = set_hermes_home_override(home)
        try:
            with use_cron_store(home):
                mapping = {}
                for role, spec in definitions.items():
                    agent = spec['kind'] == 'agent'
                    fields = dict(prompt='Earlier harvest prompt.' if agent else spec['description'],
                        schedule=spec['default_schedule'], name=spec['name'], script=spec['launcher'],
                        deliver='local', no_agent=not agent)
                    fields.update((customize or {}).get(role, {}))
                    mapping[role] = create_job(**fields)['id']
        finally:
            reset_hermes_home_override(token)
        cfg = {**previous['settings'], 'jobs': mapping, 'install_options': {'no_plugin': True, 'no_cron': False}}
        (data / 'settings.json').write_bytes(json.dumps(cfg).encode())
        return cfg, mapping, Path(previous['engine_dir']), data

    def native_jobs(self, home):
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from cron.jobs import use_cron_store, list_jobs
        token = set_hermes_home_override(home)
        try:
            with use_cron_store(home):
                return {job['id']: job for job in list_jobs(include_disabled=True)}
        finally:
            reset_hermes_home_override(token)

    def edit_job(self, home, job_id, updates):
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from cron.jobs import use_cron_store, update_job
        token = set_hermes_home_override(home)
        try:
            with use_cron_store(home):
                update_job(job_id, updates)
        finally:
            reset_hermes_home_override(token)

    def journaled(self, home, digest):
        from workflow_store import WorkflowStore
        journal = home / 'state/wiki-automation/installation.sqlite'
        if not journal.exists():
            return None
        with WorkflowStore(journal, read_only=True) as store:
            return store.get_operation(digest)

    def assert_adopted(self, home, plan, mapping, before):
        after = self.native_jobs(home)
        self.assertEqual(set(after), set(before), 'adoption must not create or remove jobs')
        for role, job_id in mapping.items():
            job, old = after[job_id], before[job_id]
            install.verify_job_role(job, role, plan)
            for key in ('schedule', 'name', 'deliver', 'created_at'):
                self.assertEqual(job[key], old[key], key)
            if plan['job_definitions'][role]['kind'] == 'agent':
                self.assertEqual((job['enabled'], job['state'], job['script'], job['next_run_at']), (False, 'paused', None, None))
                self.assertEqual(job['paused_reason'], install.LEGACY_AGENT_PAUSED_REASON)
            else:
                self.assertEqual((job['enabled'], job['state'], job['prompt']), (old['enabled'], old['state'], old['prompt']))
                self.assertEqual(Path(job['interpreter']).resolve(), Path(plan['installer_interpreter']).resolve())
        return after

    def test_legacy_jobs_are_adopted_in_place_by_the_exact_plan(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            cfg, mapping, code, data = self.legacy(home)
            self.assertIn('agent', {spec['kind'] for spec in json.loads((code / 'jobs.json').read_bytes())['jobs'].values()})
            before = self.native_jobs(home)
            plan = install.build_plan(cfg, home, code, data)
            self.assertEqual(plan['legacy_adoptions'], mapping)
            result = install.apply_plan(plan, plan['digest'])
            self.assertTrue(result['ok'])
            after = self.assert_adopted(home, plan, mapping, before)
            self.assertEqual(json.loads((data / 'settings.json').read_bytes())['jobs'], mapping)
            self.assertEqual(install.apply_plan(plan, plan['digest']), result)
            self.assertEqual(self.native_jobs(home), after)

    def test_legacy_adoption_recovers_through_read_only_validation_after_dying(self):
        import candidate_apply

        class Died(Exception):
            pass

        def die(point):
            if point.startswith('after-adopt-job:'):
                raise Died(point)
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            cfg, mapping, code, data = self.legacy(home)
            before = self.native_jobs(home)
            plan = install.build_plan(cfg, home, code, data)
            with patch.object(candidate_apply, '_checkpoint', side_effect=die), self.assertRaises(Died):
                install.apply_plan(plan, plan['digest'])
            half = self.native_jobs(home)
            pending = [job_id for job_id in mapping.values() if half[job_id].get('origin') is None]
            self.assertEqual(len(pending), len(mapping) - 1)
            from hermes_constants import set_hermes_home_override, reset_hermes_home_override
            from cron.jobs import use_cron_store, mark_job_run
            token = set_hermes_home_override(home)
            try:
                with use_cron_store(home):
                    for index, job_id in enumerate(pending):  # scheduled runs, failed or not, are not owner edits
                        mark_job_run(job_id, index % 2 == 1, None if index % 2 else 'scheduled run failed')
            finally:
                reset_hermes_home_override(token)
            for job_id in pending:
                self.assertNotEqual(self.native_jobs(home)[job_id], half[job_id])
                before[job_id] = self.native_jobs(home)[job_id]
            facts = install.validate_installation_recovery(plan, plan['digest'])
            self.assertEqual(facts['state'], 'applying')
            self.assertTrue(install.apply_plan(plan, plan['digest'], expected_recovery_state=facts['current_state_digest'])['ok'])
            self.assert_adopted(home, plan, mapping, before)

    def test_owner_edit_of_a_pending_legacy_job_after_the_journal_is_refused_and_preserved(self):
        import candidate_apply

        class Died(Exception):
            pass

        def die(point):
            if point.startswith('after-adopt-job:'):
                raise Died(point)
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            cfg, mapping, code, data = self.legacy(home)
            plan = install.build_plan(cfg, home, code, data)
            with patch.object(candidate_apply, '_checkpoint', side_effect=die), self.assertRaises(Died):
                install.apply_plan(plan, plan['digest'])
            self.assertIsNotNone(self.journaled(home, plan['digest']))
            pending = next(job_id for job_id in mapping.values() if self.native_jobs(home)[job_id].get('origin') is None)
            self.edit_job(home, pending, {'deliver': 'telegram'})
            edited = self.native_jobs(home)
            with self.assertRaisesRegex(wikiconfig.ConfigError, 'Legacy job changed after preview'):
                install.validate_installation_recovery(plan, plan['digest'])
            with self.assertRaisesRegex(wikiconfig.ConfigError, 'Legacy job changed after preview'):
                install.apply_plan(plan, plan['digest'])
            self.assertEqual(self.native_jobs(home), edited)

    def test_customized_legacy_job_is_refused_at_preview_before_anything_is_written(self):
        for customize in ({'watchdog': {'skills': ['owner-skill']}}, {'watchdog': {'deliver': 'telegram'}},
                {'session_harvest': {'enabled_toolsets': ['web']}}):
            with self.subTest(customize=customize), tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
                home = Path(tmp)
                cfg, mapping, code, data = self.legacy(home, customize=customize)
                before = self.native_jobs(home)
                location = (home / 'state/wiki-automation/location.json').read_bytes()
                with self.assertRaises(wikiconfig.ConfigError):
                    install.build_plan(cfg, home, code, data)
                self.assertEqual(self.native_jobs(home), before)
                self.assertEqual((home / 'state/wiki-automation/location.json').read_bytes(), location)
                self.assertFalse((home / 'state/wiki-automation/installation.sqlite').exists())

    def test_legacy_job_changed_after_preview_is_refused_as_stale_before_the_journal(self):
        import contextlib, io
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            cfg, mapping, code, data = self.legacy(home)
            plan = install.build_plan(cfg, home, code, data)
            self.edit_job(home, mapping['autocommit'], {'schedule': '45 6 * * *'})
            changed = self.native_jobs(home)
            with self.assertRaises(install.PlanStale):
                install.apply_plan(plan, plan['digest'])
            self.assertIsNone(self.journaled(home, plan['digest']))
            self.assertEqual(self.native_jobs(home), changed)
            plan_file = home / 'stale-plan.json'
            plan_file.write_bytes(json.dumps(plan).encode())
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code_exit = install.main(['install.py', '--apply-plan', str(plan_file), '--expected-digest', plan['digest']])
            self.assertEqual((code_exit, json.loads(out.getvalue())['state']), (1, 'stale'))
            self.assertIsNone(self.journaled(home, plan['digest']))

    def test_legacy_shaped_jobs_are_not_adopted_without_a_legacy_location(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            cfg, mapping, code, data = self.legacy(home)
            (home / 'state/wiki-automation/location.json').unlink()
            before = self.native_jobs(home)
            with self.assertRaises(wikiconfig.ConfigError):
                install.build_plan(cfg, home, code, data)
            self.assertEqual(self.native_jobs(home), before)

    def test_configured_missing_data_never_falls_back_into_code(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            missing = Path(tmp) / 'missing-data'
            with self.assertRaises(wikiconfig.ConfigError):
                wikiconfig.audit_dir({'audit_dir': str(missing)})
            self.assertFalse(missing.exists())


    def installed_with_jobs(self, home):
        """First install with native jobs; returns (settings file, code dir, data dir)."""
        initial = self.prepared(home)
        cfg = {**initial['settings'], 'install_options': {'no_plugin': True, 'no_cron': False}}
        settings_file = Path(initial['audit_dir']) / 'settings.json'
        settings_file.write_bytes(json.dumps(cfg).encode())
        first = install.build_plan(cfg, home, Path(initial['engine_dir']), Path(initial['audit_dir']))
        install.apply_plan(first, first['digest'])
        return settings_file, Path(initial['engine_dir']), Path(initial['audit_dir'])

    def release_copy(self, home, code, name, new_prompt=False):
        import shutil
        new_code = home / name
        shutil.copytree(code, new_code)
        if new_prompt:
            prompt = new_code / 'harvest_prompt.md'
            prompt.write_text(prompt.read_text(encoding='utf-8') + '\nNew release instruction.\n', encoding='utf-8')
        return new_code

    def native(self, home):
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from cron.jobs import use_cron_store, list_jobs
        token = set_hermes_home_override(home)
        try:
            with use_cron_store(home):
                return {job['id']: job for job in list_jobs(include_disabled=True)}
        finally:
            reset_hermes_home_override(token)

    def drafting_job(self, home):
        return next(job for job in self.native(home).values() if not job['no_agent'])

    def edit_job(self, home, job_id, updates):
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from cron.jobs import use_cron_store, update_job
        token = set_hermes_home_override(home)
        try:
            with use_cron_store(home):
                update_job(job_id, updates)
        finally:
            reset_hermes_home_override(token)

    def test_update_carries_a_new_release_prompt_into_the_owned_drafting_job(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            settings_file, code, data = self.installed_with_jobs(home)
            job = self.drafting_job(home)
            self.edit_job(home, job['id'], {'schedule': '30 21 * * *', 'enabled': True, 'state': 'scheduled'})
            before = self.drafting_job(home)
            new_code = self.release_copy(home, code, 'code-new-prompt', new_prompt=True)
            plan = install.build_plan(json.loads(settings_file.read_bytes()), home, new_code, data)
            self.assertEqual({role: entry['field'] for role, entry in plan['job_refresh'].items()},
                             {'session_harvest': 'prompt'})
            result = install.apply_plan(plan, plan['digest'])
            self.assertTrue(result['ok'])
            after = self.drafting_job(home)
            self.assertEqual(after['prompt'], (new_code / 'harvest_prompt.md').read_text(encoding='utf-8').strip())
            for key in ('id', 'schedule', 'enabled', 'state', 'origin', 'enabled_toolsets'):
                self.assertEqual(after[key], before[key], key)
            self.assertEqual(install.apply_plan(plan, plan['digest']), result)
            self.assertEqual(self.drafting_job(home)['prompt'], after['prompt'])

    def test_unchanged_release_plans_no_job_refresh(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            settings_file, code, data = self.installed_with_jobs(home)
            plan = install.build_plan(json.loads(settings_file.read_bytes()), home,
                                      self.release_copy(home, code, 'code-same'), data)
            self.assertNotIn('job_refresh', plan)

    def test_hand_edited_drafting_prompt_is_still_refused_and_preserved(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            settings_file, code, data = self.installed_with_jobs(home)
            job = self.drafting_job(home)
            self.edit_job(home, job['id'], {'prompt': 'Owner wrote this prompt.'})
            new_code = self.release_copy(home, code, 'code-new-prompt', new_prompt=True)
            with self.assertRaisesRegex(wikiconfig.ConfigError, 'customized drafting job'):
                install.build_plan(json.loads(settings_file.read_bytes()), home, new_code, data)
            self.assertEqual(self.drafting_job(home)['prompt'], 'Owner wrote this prompt.')

    def test_owner_edit_after_preview_is_refused_before_the_prompt_is_replaced(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            settings_file, code, data = self.installed_with_jobs(home)
            new_code = self.release_copy(home, code, 'code-new-prompt', new_prompt=True)
            plan = install.build_plan(json.loads(settings_file.read_bytes()), home, new_code, data)
            job = self.drafting_job(home)
            self.edit_job(home, job['id'], {'prompt': 'Owner edit after preview.'})
            with self.assertRaises(wikiconfig.ConfigError):
                install.apply_plan(plan, plan['digest'])
            self.assertEqual(self.drafting_job(home)['prompt'], 'Owner edit after preview.')

    def test_prompt_refresh_recovers_after_dying_once_the_prompt_was_written(self):
        import candidate_apply

        class Died(Exception):
            pass

        def die(point):
            if point.startswith('after-job-refresh:'):
                raise Died(point)
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            settings_file, code, data = self.installed_with_jobs(home)
            new_code = self.release_copy(home, code, 'code-new-prompt', new_prompt=True)
            plan = install.build_plan(json.loads(settings_file.read_bytes()), home, new_code, data)
            with patch.object(candidate_apply, '_checkpoint', side_effect=die), self.assertRaises(Died):
                install.apply_plan(plan, plan['digest'])
            new_prompt = (new_code / 'harvest_prompt.md').read_text(encoding='utf-8').strip()
            self.assertEqual(self.drafting_job(home)['prompt'], new_prompt)
            facts = install.validate_installation_recovery(plan, plan['digest'])
            self.assertTrue(install.apply_plan(plan, plan['digest'], expected_recovery_state=facts['current_state_digest'])['ok'])
            self.assertEqual(self.drafting_job(home)['prompt'], new_prompt)

    def test_hermes_python_change_moves_owned_script_jobs_to_the_new_interpreter(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            old_python = str(home / 'old-python' / 'python.exe')
            with patch.object(install.sys, 'executable', old_python):
                settings_file, code, data = self.installed_with_jobs(home)
            before = self.native(home)
            scripts = {i for i, job in before.items() if job['no_agent']}
            self.assertTrue(scripts and all(before[i]['interpreter'] == old_python for i in scripts))
            plan = install.build_plan(json.loads(settings_file.read_bytes()), home,
                                      self.release_copy(home, code, 'code-same'), data)
            self.assertEqual({entry['field'] for entry in plan['job_refresh'].values()}, {'interpreter'})
            self.assertTrue(install.apply_plan(plan, plan['digest'])['ok'])
            after = self.native(home)
            for i in scripts:
                self.assertTrue(install._same_path(after[i]['interpreter'], install.sys.executable))
                for key in ('schedule', 'enabled', 'state', 'origin', 'script'):
                    self.assertEqual(after[i][key], before[i][key], key)

    def test_hand_chosen_interpreter_is_still_refused_and_preserved(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            settings_file, code, data = self.installed_with_jobs(home)
            job_id = next(i for i, job in self.native(home).items() if job['no_agent'])
            mine = str(home / 'my-own-python' / 'python.exe')
            self.edit_job(home, job_id, {'interpreter': mine})
            with self.assertRaisesRegex(wikiconfig.ConfigError, 'interpreter or execution role changed'):
                install.build_plan(json.loads(settings_file.read_bytes()), home,
                                   self.release_copy(home, code, 'code-same'), data)
            self.assertEqual(self.native(home)[job_id]['interpreter'], mine)

if __name__ == '__main__':
    unittest.main()
