"""Read-only engine recovery inspection reuses native installation ownership rules."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import install
import test_engine_install as fixtures

class RecoveryValidationTests(unittest.TestCase):
    def test_applied_plan_has_read_only_exact_current_state_fingerprint(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            plan = fixtures.EngineInstallTests().prepared(home)
            install.apply_plan(plan, plan['digest'])
            before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in home.rglob('*') if p.is_file()}
            self.assertTrue(callable(getattr(install, 'validate_installation_recovery', None)),
                'Engine lacks read-only exact original installation recovery validator')
            result = install.validate_installation_recovery(plan, plan['digest'])
            self.assertEqual(result['state'], 'applied')
            self.assertRegex(result['current_state_digest'], '^[0-9a-f]{64}$')
            self.assertEqual(result, install.validate_installation_recovery(plan, plan['digest']))
            self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in home.rglob('*') if p.is_file()})

    def test_native_cli_wal_journals_refuse_without_sidecar_creation(self):
        import contextlib
        import sqlite3
        import subprocess
        from workflow_store import WorkflowStore
        for kind in ('source', 'installation'):
            for version in (1, 99):
                with self.subTest(kind=kind, version=version), tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
                    home = Path(temp)
                    plan = fixtures.EngineInstallTests().prepared(home)
                    journal = (Path(plan['audit_dir']) / 'workflow.sqlite' if kind == 'source'
                               else home / 'state/wiki-automation/installation.sqlite')
                    with WorkflowStore(journal) as store:
                        store.record_operation({'operation_id': 'fixture'})
                    with contextlib.closing(sqlite3.connect(journal)) as db:
                        db.execute(f'PRAGMA user_version={version}')
                        db.commit()
                        self.assertEqual(db.execute('PRAGMA journal_mode=WAL').fetchone(), ('wal',))
                    self.assertFalse(Path(str(journal) + '-wal').exists())
                    self.assertFalse(Path(str(journal) + '-shm').exists())
                    saved = home / 'plan.json'
                    saved.write_bytes(json.dumps(plan).encode())
                    before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                              for p in home.rglob('*') if p.is_file()}
                    result = subprocess.run([sys.executable, '-B', str(Path(plan['engine_dir']) / 'install.py'),
                        '--validate-recovery-plan', str(saved), '--expected-digest', plan['digest']],
                        capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertFalse(json.loads(result.stdout)['ok'])
                    self.assertEqual(result.stderr, '')
                    self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                                             for p in home.rglob('*') if p.is_file()})

    def test_native_cli_recovery_inspection_and_apply_state_binding(self):
        import subprocess
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            plan = fixtures.EngineInstallTests().prepared(home)
            install.apply_plan(plan, plan['digest'])
            saved = home / 'plan.json'
            saved.write_bytes(json.dumps(plan).encode())
            script = Path(plan['engine_dir']) / 'install.py'
            command = [sys.executable, '-B', str(script), '--validate-recovery-plan', str(saved), '--expected-digest', plan['digest']]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            checked = json.loads(result.stdout)
            self.assertEqual(checked['state'], 'applied')
            before = {str(p): p.read_bytes() for p in home.rglob('*') if p.is_file()}
            result = subprocess.run([sys.executable, '-B', str(script), '--apply-plan', str(saved),
                '--expected-digest', plan['digest'], '--expected-recovery-state', '0' * 64], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('review', json.loads(result.stdout)['reason'])
            self.assertEqual(before, {str(p): p.read_bytes() for p in home.rglob('*') if p.is_file()})
            result = subprocess.run([sys.executable, '-B', str(script), '--apply-plan', str(saved),
                '--expected-digest', plan['digest'], '--expected-recovery-state', checked['current_state_digest']], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_read_only_existing_source_journal_is_bound_without_repair(self):
        from workflow_store import WorkflowStore
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            plan = fixtures.EngineInstallTests().prepared(home)
            install.apply_plan(plan, plan['digest'])
            source = Path(plan['audit_dir']) / 'workflow.sqlite'
            with WorkflowStore(source) as store:
                store.record_operation({'operation_id': 'owner-pending', 'type': 'candidate'})
            before = source.read_bytes()
            checked = install.validate_installation_recovery(plan, plan['digest'])
            self.assertRegex(checked['current_state_digest'], '^[0-9a-f]{64}$')
            self.assertEqual(source.read_bytes(), before)

    def test_read_only_validation_checks_all_secondary_recaptures_on_noop_projection(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            plan = fixtures.EngineInstallTests().prepared(home)
            original = (Path(plan['audit_dir']) / 'settings.json').read_bytes()
            install.apply_plan(plan, plan['digest'])
            capture = Path(plan['audit_dir']) / ('.wiki-install-recovery/' + plan['digest'] + '/settings/captured.bin')
            self.assertEqual(capture.read_bytes(), original)
            secondary = capture.parent / 'recapture-fixture/captured.bin'
            secondary.parent.mkdir()
            secondary.write_bytes(original)
            install.validate_installation_recovery(plan, plan['digest'])
            secondary.write_bytes(b'Owner changed retained secondary handle')
            before = {str(p): p.read_bytes() for p in home.rglob('*') if p.is_file()}
            with self.assertRaisesRegex(install.wikiconfig.ConfigError, 'capture changed'):
                install.validate_installation_recovery(plan, plan['digest'])
            self.assertEqual(before, {str(p): p.read_bytes() for p in home.rglob('*') if p.is_file()})

    def test_expected_none_cannot_authorize_forged_capture_or_secondary(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            plan = fixtures.EngineInstallTests().prepared(home)
            install.apply_plan(plan, plan['digest'])
            name = next(iter(plan['launcher_payloads']))
            self.assertIsNone(plan['launcher_before'][name])
            capture = home / ('scripts/.wiki-install-recovery/' + plan['digest'] + '/launcher-' + name + '/recapture-fixture/captured.bin')
            capture.parent.mkdir(parents=True)
            capture.write_bytes(b'Owner retained prefix with no original before image')
            before = capture.read_bytes()
            with self.assertRaisesRegex(install.wikiconfig.ConfigError, 'capture changed'):
                install.validate_installation_recovery(plan, plan['digest'])
            self.assertEqual(capture.read_bytes(), before)

    def test_original_captured_owned_job_deletion_is_not_repaired_by_recovery(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            initial = fixtures.EngineInstallTests().prepared(home)
            settings = {**initial['settings'], 'install_options': {'no_plugin': True, 'no_cron': False}}
            first = install.build_plan(settings, home, Path(initial['engine_dir']), Path(initial['audit_dir']))
            install.apply_plan(first, first['digest'])
            current = json.loads((Path(first['audit_dir']) / 'settings.json').read_bytes())
            plan = install.build_plan(current, home, Path(first['engine_dir']), Path(first['audit_dir']))
            install.apply_plan(plan, plan['digest'])
            jobs_path = home / 'cron/jobs.json'
            jobs = json.loads(jobs_path.read_bytes())
            jobs['jobs'].pop()
            jobs_path.write_bytes(json.dumps(jobs).encode())
            before = jobs_path.read_bytes()
            with self.assertRaisesRegex(install.wikiconfig.ConfigError, 'job.*missing|job.*disappeared'):
                install.validate_installation_recovery(plan, plan['digest'])
            self.assertEqual(jobs_path.read_bytes(), before)

    def test_recorded_native_half_operation_job_loss_is_refused_before_resume(self):
        import subprocess
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            initial = fixtures.EngineInstallTests().prepared(home)
            settings = {**initial['settings'], 'install_options': {'no_plugin': True, 'no_cron': False}}
            plan = install.build_plan(settings, home, Path(initial['engine_dir']), Path(initial['audit_dir']))
            saved = home / 'plan.json'
            saved.write_bytes(json.dumps(plan).encode())
            worker = Path(__file__).parent / 'install_apply_worker.py'
            result = subprocess.run([sys.executable, '-B', str(worker), str(saved), 'after-create-job:ingest_watch'],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 91, result.stderr)
            jobs_path = home / 'cron/jobs.json'
            jobs = json.loads(jobs_path.read_bytes())
            self.assertEqual(len(jobs['jobs']), 2)
            jobs['jobs'] = [job for job in jobs['jobs'] if job['origin']['engine_role'] != 'autocommit']
            jobs_path.write_bytes(json.dumps(jobs).encode())
            before = jobs_path.read_bytes()
            with self.assertRaisesRegex(install.wikiconfig.ConfigError, 'job.*missing|job.*disappeared'):
                install.validate_installation_recovery(plan, plan['digest'])
            self.assertEqual(jobs_path.read_bytes(), before)

class UnstartedCaptureTests(unittest.TestCase):
    def test_incomplete_orphan_recapture_prefix_is_refused_without_repair(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            plan = fixtures.EngineInstallTests().prepared(home)
            prefix = Path(plan['audit_dir']) / ('.wiki-install-recovery/' + plan['digest'] + '/settings/recapture-orphan')
            prefix.mkdir(parents=True)
            before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in home.rglob('*') if p.is_file()}
            with self.assertRaises(install.wikiconfig.ConfigError):
                install.validate_installation_recovery(plan, plan['digest'])
            self.assertTrue(prefix.is_dir())
            self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in home.rglob('*') if p.is_file()})

    def test_secondary_capture_cannot_authorize_a_missing_primary_before_image(self):
        from workflow_store import WorkflowStore
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            plan = fixtures.EngineInstallTests().prepared(home)
            settings = Path(plan['audit_dir']) / 'settings.json'
            capture = settings.parent / ('.wiki-install-recovery/' + plan['digest'] + '/settings/recapture-fixture/captured.bin')
            capture.parent.mkdir(parents=True)
            capture.write_bytes(settings.read_bytes())
            settings.unlink()
            with WorkflowStore(home / 'state/wiki-automation/installation.sqlite') as store:
                store.record_operation({'operation_id': plan['digest'], 'type': 'installation', 'plan': plan})
            before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in home.rglob('*') if p.is_file()}
            with self.assertRaises(install.wikiconfig.ConfigError):
                install.validate_installation_recovery(plan, plan['digest'])
            self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in home.rglob('*') if p.is_file()})

    def test_unstarted_secondary_drift_is_refused_before_any_native_write(self):
        from candidate_apply import ApplyRefused
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            plan = fixtures.EngineInstallTests().prepared(home)
            reviewed = install.validate_installation_recovery(plan, plan['digest'])
            capture = Path(plan['audit_dir']) / ('.wiki-install-recovery/' + plan['digest'] + '/settings/recapture-fixture/captured.bin')
            capture.parent.mkdir(parents=True)
            capture.write_bytes(b'Owner drift must be preserved')
            before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in home.rglob('*') if p.is_file()}
            with self.assertRaises((install.wikiconfig.ConfigError, ApplyRefused)):
                install.validate_installation_recovery(plan, plan['digest'])
            with self.assertRaises((install.wikiconfig.ConfigError, ApplyRefused)):
                install.apply_plan(plan, plan['digest'], expected_recovery_state=reviewed['current_state_digest'])
            self.assertFalse((home / 'state/wiki-automation/installation.sqlite').exists())
            self.assertFalse((home / 'cron/jobs.json').exists())
            self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in home.rglob('*') if p.is_file()})

    def test_valid_unstarted_capture_is_bound_into_review_state(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            plan = fixtures.EngineInstallTests().prepared(home)
            reviewed = install.validate_installation_recovery(plan, plan['digest'])
            capture = Path(plan['audit_dir']) / ('.wiki-install-recovery/' + plan['digest'] + '/settings/captured.bin')
            capture.parent.mkdir(parents=True)
            capture.write_bytes((Path(plan['audit_dir']) / 'settings.json').read_bytes())
            changed = install.validate_installation_recovery(plan, plan['digest'])
            self.assertNotEqual(changed['current_state_digest'], reviewed['current_state_digest'])
            with self.assertRaisesRegex(install.wikiconfig.ConfigError, 'review'):
                install.apply_plan(plan, plan['digest'], expected_recovery_state=reviewed['current_state_digest'])
            self.assertFalse((home / 'state/wiki-automation/installation.sqlite').exists())

class JournalRefusalTests(unittest.TestCase):
    def test_native_cli_journal_refusals_are_bounded_json_without_repair(self):
        import sqlite3
        import subprocess
        from contextlib import closing
        from workflow_store import WorkflowStore
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            base = Path(temp)
            for kind in ('source', 'installation'):
                for invalid in ('newer', 'corrupt', 'json'):
                    with self.subTest(kind=kind, invalid=invalid):
                        home = base / (kind + invalid)
                        home.mkdir()
                        plan = fixtures.EngineInstallTests().prepared(home)
                        journal = (Path(plan['audit_dir']) / 'workflow.sqlite' if kind == 'source'
                            else home / 'state/wiki-automation/installation.sqlite')
                        journal.parent.mkdir(parents=True, exist_ok=True)
                        if invalid == 'corrupt':
                            journal.write_bytes(b'Owner corrupt journal')
                        else:
                            with WorkflowStore(journal) as store:
                                store.record_operation({'operation_id': plan['digest'], 'type': 'installation', 'plan': plan})
                            with closing(sqlite3.connect(journal)) as db:
                                if invalid == 'newer':
                                    db.execute('PRAGMA user_version=99')
                                else:
                                    db.execute('UPDATE operations SET identity=?', ('{secret-token-leak',))
                                db.commit()
                        saved = home / 'plan.json'
                        saved.write_bytes(json.dumps(plan).encode())
                        before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in home.rglob('*') if p.is_file()}
                        command = [sys.executable, '-B', str(Path(plan['engine_dir']) / 'install.py'),
                            '--validate-recovery-plan', str(saved), '--expected-digest', plan['digest']]
                        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                        self.assertEqual(result.stderr, '')
                        payload = json.loads(result.stdout)
                        self.assertIs(payload['ok'], False)
                        self.assertEqual(payload['state'], 'refused')
                        self.assertLessEqual(len(payload['reason']), 240)
                        self.assertNotIn('secret-token', payload['reason'])
                        self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in home.rglob('*') if p.is_file()})

class NativeParserTests(unittest.TestCase):
    def test_nullable_read_defaults_match_capture_review_and_apply_without_repair(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            initial = fixtures.EngineInstallTests().prepared(home)
            cfg = {**initial['settings'], 'install_options': {'no_plugin': True, 'no_cron': False}}
            first = install.build_plan(cfg, home, Path(initial['engine_dir']), Path(initial['audit_dir']))
            install.apply_plan(first, first['digest'])
            jobs_path = home / 'cron/jobs.json'
            document = json.loads(jobs_path.read_bytes())
            for job in document['jobs']:
                job['schedule_display'] = None
                job['skills'] = None
                job['state'] = None
            jobs_path.write_bytes(json.dumps(document).encode())
            before = (jobs_path.read_bytes(), jobs_path.stat().st_mtime_ns)
            cfg = json.loads((Path(first['audit_dir']) / 'settings.json').read_bytes())
            plan = install.build_plan(cfg, home, Path(first['engine_dir']), Path(first['audit_dir']))
            checked = install.validate_installation_recovery(plan, plan['digest'])
            self.assertEqual(checked['state'], 'unstarted')
            result = install.apply_plan(plan, plan['digest'], expected_recovery_state=checked['current_state_digest'])
            self.assertTrue(result['ok'])
            self.assertEqual((jobs_path.read_bytes(), jobs_path.stat().st_mtime_ns), before)

    def test_strict_parser_refuses_repair_shapes_and_duplicate_ids_read_only(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            initial = fixtures.EngineInstallTests().prepared(home)
            cfg = {**initial['settings'], 'install_options': {'no_plugin': True, 'no_cron': False}}
            first = install.build_plan(cfg, home, Path(initial['engine_dir']), Path(initial['audit_dir']))
            install.apply_plan(first, first['digest'])
            jobs_path = home / 'cron/jobs.json'
            document = json.loads(jobs_path.read_bytes())
            bad_repeat = json.loads(json.dumps(document))
            bad_repeat['jobs'][0]['repeat']['completed'] = None
            bad_schedule = json.loads(json.dumps(document))
            bad_schedule['jobs'][0]['schedule'] = {'kind': 'cron', 'expr': 7}
            bad_interval = json.loads(json.dumps(document))
            bad_interval['jobs'][0]['schedule'] = {'kind': 'interval', 'minutes': 'secret-settings'}
            shapes = [[], {'jobs': {}}, {'jobs': [document['jobs'][0]] * 2}, bad_repeat,
                bad_schedule, bad_interval,
                {'jobs': [{'id': 7}]}, {'jobs': None}, {'version': 999, 'jobs': document['jobs']}]
            cfg = json.loads((Path(first['audit_dir']) / 'settings.json').read_bytes())
            for shape in shapes:
                with self.subTest(shape=type(shape).__name__):
                    jobs_path.write_bytes(json.dumps(shape).encode())
                    before = (jobs_path.read_bytes(), jobs_path.stat().st_mtime_ns)
                    with self.assertRaises(install.wikiconfig.ConfigError):
                        install.build_plan(cfg, home, Path(first['engine_dir']), Path(first['audit_dir']))
                    self.assertEqual((jobs_path.read_bytes(), jobs_path.stat().st_mtime_ns), before)

class NativeRoleTests(unittest.TestCase):
    def test_original_plan_binds_the_selected_native_interpreter(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            plan = fixtures.EngineInstallTests().prepared(home)
            self.assertEqual(plan.get('installer_interpreter'), str(Path(sys.executable).resolve()))
            from unittest.mock import patch
            with patch.object(install.sys, 'executable', str(home / 'foreign.exe')):
                with self.assertRaises(install.wikiconfig.ConfigError):
                    install.validate_installation_recovery(plan, plan['digest'])

    def test_new_snapshot_step_preserves_original_native_provenance_step_schema(self):
        from workflow_store import WorkflowStore
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            initial = fixtures.EngineInstallTests().prepared(home)
            cfg = {**initial['settings'], 'install_options': {'no_plugin': True, 'no_cron': False}}
            plan = install.build_plan(cfg, home, Path(initial['engine_dir']), Path(initial['audit_dir']))
            install.apply_plan(plan, plan['digest'])
            rows = install.existing_job_snapshot(home)['jobs']
            with WorkflowStore(home / 'state/wiki-automation/installation.sqlite', read_only=True) as store:
                steps = {entry['step']: entry['result'] for entry in store.steps(plan['digest'])}
            for job in rows:
                role = job['origin']['engine_role']
                self.assertEqual(steps['job-' + role], {'job_id': job['id'], 'origin': job['origin']})
                self.assertEqual(steps['job-snapshot-' + role], {'job_snapshot': job})
            self.assertEqual(install.validate_installation_recovery(plan, plan['digest'])['state'], 'applied')

    def test_marked_script_interpreter_workdir_prompt_and_origin_drift_refuse_without_repair(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            base = Path(temp)
            for role, field, value in (
                    ('watchdog', 'interpreter', 'Z:/unapproved/python.exe'),
                    ('watchdog', 'workdir', 'Z:/foreign-project'),
                    ('watchdog', 'prompt', 'Unapproved script prompt'),
                    ('watchdog', 'enabled', True),
                    ('watchdog', 'schedule', {'kind': 'cron', 'expr': '13 7 * * *', 'display': '13 7 * * *'}),
                    ('watchdog', 'origin', {'engine_installation': 'f' * 64, 'engine_role': 'watchdog'}),
                    ('harvest_night', 'interpreter', 'Z:/unapproved/python.exe'),
                    ('harvest_night', 'origin', None)):
                with self.subTest(role=role, field=field):
                    home = base / (role + field)
                    home.mkdir()
                    initial = fixtures.EngineInstallTests().prepared(home)
                    cfg = {**initial['settings'], 'install_options': {'no_plugin': True, 'no_cron': False}}
                    plan = install.build_plan(cfg, home, Path(initial['engine_dir']), Path(initial['audit_dir']))
                    install.apply_plan(plan, plan['digest'])
                    path = home / 'cron/jobs.json'
                    document = json.loads(path.read_bytes())
                    job = next(job for job in document['jobs'] if job['origin']['engine_role'] == role)
                    job[field] = value
                    path.write_bytes(json.dumps(document).encode())
                    before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in home.rglob('*') if p.is_file()}
                    with self.assertRaises(install.wikiconfig.ConfigError):
                        install.validate_installation_recovery(plan, plan['digest'])
                    self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in home.rglob('*') if p.is_file()})

    def test_preexisting_custom_script_interpreter_is_refused_not_restored(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            initial = fixtures.EngineInstallTests().prepared(home)
            cfg = {**initial['settings'], 'install_options': {'no_plugin': True, 'no_cron': False}}
            first = install.build_plan(cfg, home, Path(initial['engine_dir']), Path(initial['audit_dir']))
            install.apply_plan(first, first['digest'])
            path = home / 'cron/jobs.json'
            cfg = json.loads((Path(first['audit_dir']) / 'settings.json').read_bytes())
            plan = install.build_plan(cfg, home, Path(first['engine_dir']), Path(first['audit_dir']))
            document = json.loads(path.read_bytes())
            document['jobs'][0]['interpreter'] = 'Z:/custom-executable.exe'
            path.write_bytes(json.dumps(document).encode())
            with self.assertRaises(install.wikiconfig.ConfigError):  # a fresh preview refuses it too
                install.build_plan(cfg, home, Path(first['engine_dir']), Path(first['audit_dir']))
            before = path.read_bytes()
            with self.assertRaises(install.wikiconfig.ConfigError):
                install.validate_installation_recovery(plan, plan['digest'])
            self.assertEqual(path.read_bytes(), before)

class RecoveryLockTests(unittest.TestCase):
    def test_current_state_is_revalidated_under_both_real_locks_before_journal_write(self):
        from contextlib import contextmanager
        from unittest.mock import patch
        import candidate_apply
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            plan = fixtures.EngineInstallTests().prepared(home)
            reviewed = install.validate_installation_recovery(plan, plan['digest'])
            locked, inspections = [], []
            real_lock = candidate_apply.operation_lock
            real_validate = install.validate_installation_recovery
            journal = home / 'state/wiki-automation/installation.sqlite'
            @contextmanager
            def lock(path):
                with real_lock(path):
                    locked.append(Path(path).resolve())
                    try:
                        yield
                    finally:
                        locked.pop()
            def inspect(*args):
                inspections.append(list(locked))
                self.assertFalse(journal.exists(), 'Writable native journal opened before locked inspection')
                return real_validate(*args)
            with patch.object(candidate_apply, 'operation_lock', side_effect=lock), patch.object(install,
                    'validate_installation_recovery', side_effect=inspect):
                result = install.apply_plan(plan, plan['digest'], expected_recovery_state=reviewed['current_state_digest'])
            self.assertTrue(result['ok'])
            self.assertEqual(inspections, [[], [(home / 'state/wiki-automation').resolve(), Path(plan['audit_dir']).resolve()]])

    def test_state_drift_between_preflight_and_real_data_lock_refuses_before_journal(self):
        from contextlib import contextmanager
        from unittest.mock import patch
        import candidate_apply
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            plan = fixtures.EngineInstallTests().prepared(home)
            reviewed = install.validate_installation_recovery(plan, plan['digest'])
            real_lock = candidate_apply.operation_lock
            data = Path(plan['audit_dir'])
            original = (data / 'settings.json').read_bytes()
            capture = data / ('.wiki-install-recovery/' + plan['digest'] + '/settings/captured.bin')
            @contextmanager
            def lock(path):
                with real_lock(path):
                    if Path(path).resolve() == data.resolve():
                        capture.parent.mkdir(parents=True)
                        capture.write_bytes(original)
                    yield
            with patch.object(candidate_apply, 'operation_lock', side_effect=lock):
                with self.assertRaisesRegex(install.wikiconfig.ConfigError, 'review'):
                    install.apply_plan(plan, plan['digest'], expected_recovery_state=reviewed['current_state_digest'])
            self.assertFalse((home / 'state/wiki-automation/installation.sqlite').exists())
            self.assertFalse((home / 'cron/jobs.json').exists())
            self.assertEqual((data / 'settings.json').read_bytes(), original)
            self.assertEqual(capture.read_bytes(), original)

if __name__ == '__main__':
    unittest.main()
