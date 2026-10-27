"""Real disposable native jobs: role mappings never grant ownership."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from cron import jobs
from hermes_constants import set_hermes_home_override, reset_hermes_home_override

PACKAGE = Path(__file__).resolve().parents[1]


def load(name, source):
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class JobOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ['TMPDIR'])
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.home, wiki = root / 'home', root / 'wiki'
        self.home.mkdir()
        (self.home / 'config.yaml').write_bytes(b'{}')
        (wiki / '.llm-wiki').mkdir(parents=True)
        (wiki / '.llm-wiki/project.json').write_bytes(b'{"id":"ownership-fixture"}')
        (wiki / 'wiki').mkdir()
        (wiki / 'wiki/index.md').write_bytes(b'# Fixture\n')
        lifecycle = load('ownership_lifecycle', PACKAGE / 'dashboard/engine_lifecycle.py')
        manifest = json.loads((PACKAGE / 'engine-release.json').read_bytes())
        prepared = lifecycle.prepare_install(self.home, PACKAGE, manifest, wiki, principal='fixture-session')
        lifecycle.apply_install(self.home, PACKAGE, manifest, prepared['install_id'], prepared['plan_digest'], principal='fixture-session')
        self.settings = Path(prepared['audit_dir']) / 'settings.json'
        self.mapping = json.loads(self.settings.read_bytes())['jobs']
        self.api = load('ownership_api', PACKAGE / 'dashboard/plugin_api.py')
        env = patch.dict(os.environ, {'LLMWIKI_AUDIT_DIR': '', 'LLMWIKI_SETTINGS': '', 'WIKI_ENGINE_TEST_DIR': ''})
        env.start()
        self.addCleanup(env.stop)
        token = set_hermes_home_override(self.home)
        self.addCleanup(reset_hermes_home_override, token)
        context = jobs.use_cron_store(self.home)
        context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.unrelated = jobs.create_job(prompt='Owner unrelated task', schedule='13 8 * * *',
            name='Owner task', script='unrelated.py', no_agent=True, deliver='local', paused=True)
        self.panel_settings = self.home / 'state/wiki-automation/settings.json'

    def facts(self, role='watchdog'):
        settings = json.loads(self.settings.read_bytes())
        jid = (settings.get('jobs') or {}).get(role)
        record = jobs.get_job(jid) if isinstance(jid, str) else None
        if record is None:
            return {'id': str(jid or ''), 'state': 'absent', 'schedule': ''}
        return {'id': record['id'], 'state': jobs.effective_job_state(record),
                'schedule': record['schedule'].get('expr') or record.get('schedule_display') or ''}

    def act(self, action, role='watchdog', schedule='*/7 * * * *', expected=None):
        return self.api.jobs_act_route({'role': role, 'action': action, 'confirm': True,
                                       'schedule': schedule,
                                       'expected': self.facts(role) if expected is None else expected})

    def test_actions_without_the_reviewed_record_never_reach_native_mutators(self):
        original_jobs = jobs.list_jobs(include_disabled=True)
        before = {str(path): path.read_bytes() for path in self.home.parent.rglob('*') if path.is_file()}
        for role in ('watchdog', 'session_harvest', 'unknown', ''):
            for action in ('remove', 'pause', 'resume', 'schedule', 'create'):
                for payload in ({}, {'expected': None}, {'expected': {'id': 1}}, {'expected': 'x'}):
                    with self.subTest(role=role, action=action, payload=payload):
                        natives = [patch.object(jobs, name, side_effect=AssertionError('reached ' + name))
                                   for name in ('save_jobs', 'create_job', 'remove_job', 'pause_job',
                                                'resume_job', 'update_job')]
                        for guard in natives:
                            guard.start()
                        try:
                            result = self.api.jobs_act_route({'role': role, 'action': action, 'confirm': True,
                                                              'schedule': '*/7 * * * *', **payload})
                        finally:
                            for guard in natives:
                                guard.stop()
                        self.assertIs(result['ok'], False, result)
        self.assertEqual(jobs.list_jobs(include_disabled=True), original_jobs)
        after = {str(path): path.read_bytes() for path in self.home.parent.rglob('*') if path.is_file()}
        self.assertEqual(after, before)
        self.assertFalse(self.panel_settings.exists())

    def test_schedule_preview_uses_real_native_parser_without_store_access(self):
        from contextlib import ExitStack
        before = {str(path): (path.read_bytes(), path.stat().st_mtime_ns)
                  for path in self.home.parent.rglob('*') if path.is_file()}
        with ExitStack() as stack:
            guards = [stack.enter_context(patch.object(jobs, name,
                side_effect=AssertionError('Preview reached native ' + name)))
                for name in ('load_jobs', 'save_jobs', 'get_job', 'list_jobs', 'create_job',
                             'remove_job', 'pause_job', 'resume_job', 'update_job')]
            parse = stack.enter_context(patch.object(jobs, 'parse_schedule', wraps=jobs.parse_schedule))
            compute = stack.enter_context(patch.object(jobs, 'compute_next_run', wraps=jobs.compute_next_run))
            preview = self.api.jobs_preview_route({'schedule': '*/15 * * * *'})
            self.assertTrue(preview['ok'], preview)
            self.assertEqual(len(preview['next_runs']), 3)
            self.assertEqual(parse.call_count, 1)
            self.assertEqual(compute.call_count, 3)
            self.assertFalse(self.api.jobs_preview_route({'schedule': 'not a schedule'})['ok'])
            self.assertFalse(self.api.jobs_preview_route({})['ok'])
            self.assertTrue(all(guard.call_count == 0 for guard in guards))
        after = {str(path): (path.read_bytes(), path.stat().st_mtime_ns)
                 for path in self.home.parent.rglob('*') if path.is_file()}
        self.assertEqual(after, before)

    def test_role_view_declares_management_available_without_row_duplicates(self):
        view = self.api.jobs_view_route()
        self.assertTrue(view['ok'], view)
        self.assertIs(view.get('mutation_available'), True)
        self.assertIsNone(view.get('management_reason'))
        for row in view['roles']:
            self.assertNotIn('mutation_available', row)
            self.assertNotIn('management_reason', row)
        settings = json.loads(self.settings.read_bytes())
        settings['jobs']['watchdog'] = self.unrelated['id']
        self.settings.write_bytes(json.dumps(settings).encode())
        refused = self.api.jobs_view_route()
        self.assertFalse(refused['ok'], refused)
        self.assertEqual(refused['roles'], [])
        self.assertIs(refused.get('mutation_available'), False)

    def test_role_view_refuses_dirty_config_source_before_execution(self):
        location = json.loads((self.home / 'state/wiki-automation/location.json').read_bytes())
        marker = self.home / 'unverified-config-executed'
        source = Path(location['engine_dir']) / 'wikiconfig.py'
        source.write_bytes(('from pathlib import Path\nPath(' + repr(str(marker)) + ').write_bytes(b"executed")\nprint("{}")\n').encode())
        self.assertFalse(self.api.jobs_view_route()['ok'])
        self.assertFalse(marker.exists(), 'Role view executed an unapproved config source')

    def test_launcher_change_after_inspection_refuses_role_labels(self):
        verify = self.api._verified_native_jobs

        def changed(mapping):
            result = verify(mapping)
            (self.home / 'scripts/palantir_wiki_watchdog.py').write_bytes(b'raise SystemExit("changed launcher")\n')
            return result

        before = (self.home / 'cron/jobs.json').read_bytes()
        with patch.object(self.api, '_verified_native_jobs', side_effect=changed), patch.object(jobs, 'resume_job', wraps=jobs.resume_job) as native:
            self.assertFalse(self.api.jobs_view_route()['ok'], 'Changed launcher received a native role label')
        self.assertEqual(native.call_count, 0)
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)

    def test_changed_engine_policy_source_is_refused_before_import(self):
        location = json.loads((self.home / 'state/wiki-automation/location.json').read_bytes())
        source = Path(location['engine_dir']) / 'install.py'
        marker = self.home / 'unverified-policy-executed'
        source.write_bytes(source.read_bytes() + ('\n__import__("pathlib").Path(' + repr(str(marker)) + ').write_bytes(b"executed")\n').encode())
        before = (self.home / 'cron/jobs.json').read_bytes()
        self.assertFalse(self.act('resume')['ok'])
        self.assertFalse(self.api.jobs_view_route()['ok'])
        self.assertFalse(marker.exists(), 'Unapproved engine policy executed before source verification')
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)

    def test_two_roles_cannot_claim_the_same_native_id(self):
        settings = json.loads(self.settings.read_bytes())
        settings['jobs']['autocommit'] = self.mapping['watchdog']
        self.settings.write_bytes(json.dumps(settings).encode())
        before = (self.home / 'cron/jobs.json').read_bytes()
        self.assertFalse(self.act('resume')['ok'], 'Two engine roles claimed the same native ID')
        self.assertFalse(self.api.jobs_view_route()['ok'], 'Two roles labelled the same native ID')
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)

    def test_native_exact_id_readback_disagreement_refuses_role_labels(self):
        get_job = jobs.get_job
        before = (self.home / 'cron/jobs.json').read_bytes()

        def different(jid):
            result = get_job(jid)
            if result and jid == self.mapping['watchdog']:
                result['script'] = 'foreign.py'
            return result

        with patch.object(jobs, 'get_job', side_effect=different):
            result = self.api.jobs_view_route()
        self.assertFalse(result['ok'], 'Different exact-ID readback received an engine role label')
        self.assertEqual(result['roles'], [])
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)

    def test_all_actions_refuse_wrong_role_before_entering_native_mutators(self):
        settings = json.loads(self.settings.read_bytes())
        settings['jobs']['watchdog'] = self.unrelated['id']
        self.settings.write_bytes(json.dumps(settings).encode())
        before, owner = (self.home / 'cron/jobs.json').read_bytes(), self.settings.read_bytes()
        for action, name in (('create', 'create_job'), ('pause', 'pause_job'), ('resume', 'resume_job'),
                             ('schedule', 'update_job'), ('remove', 'remove_job')):
            with self.subTest(action=action), patch.object(jobs, name, wraps=getattr(jobs, name)) as native:
                result = self.act(action)
                self.assertFalse(result['ok'], result)
                self.assertEqual(native.call_count, 0, 'Wrong-role ID reached native mutation API')
                self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)
                self.assertEqual(self.settings.read_bytes(), owner)
                self.assertFalse(self.panel_settings.exists())
        self.assertFalse(self.api.jobs_view_route()['ok'], 'Wrong-role ID was labelled')

    def test_legacy_and_primary_id_conflicts_are_refused_without_repair(self):
        settings = json.loads(self.settings.read_bytes())
        settings['primary_job_ids'] = dict(self.mapping)
        settings['jobs']['watchdog'] = self.unrelated['id']
        self.settings.write_bytes(json.dumps(settings).encode())
        before, owner = (self.home / 'cron/jobs.json').read_bytes(), self.settings.read_bytes()
        for action in ('create', 'pause', 'resume', 'schedule', 'remove'):
            with self.subTest(action=action):
                result = self.act(action)
                self.assertFalse(result['ok'], result)
                self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)
                self.assertEqual(self.settings.read_bytes(), owner)
        refused = self.api.jobs_view_route()
        self.assertFalse(refused['ok'])
        self.assertIn('Conflicting', refused['reason'])

    def test_stale_id_never_falls_back_to_native_name_or_creates_duplicate(self):
        settings = json.loads(self.settings.read_bytes())
        settings['jobs']['watchdog'] = jobs.get_job(self.mapping['watchdog'])['name']
        self.settings.write_bytes(json.dumps(settings).encode())
        before, owner = (self.home / 'cron/jobs.json').read_bytes(), self.settings.read_bytes()
        for action in ('create', 'pause', 'resume', 'schedule', 'remove'):
            with self.subTest(action=action):
                self.assertFalse(self.act(action)['ok'])
                self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)
                self.assertEqual(self.settings.read_bytes(), owner)
        self.assertFalse(self.api.jobs_view_route()['ok'], 'Stale ID fell back to a native name')

    def test_changed_mapping_binding_refuses_role_labels(self):
        verify = self.api._verified_native_jobs
        captured = {}

        def changed(mapping):
            result = verify(mapping)
            self.panel_settings.write_bytes(json.dumps({'jobs': {'watchdog': self.unrelated['id']}}).encode())
            captured['bytes'] = (self.home / 'cron/jobs.json').read_bytes()
            return result

        with patch.object(self.api, '_verified_native_jobs', side_effect=changed), patch.object(jobs, 'remove_job', wraps=jobs.remove_job) as native:
            self.assertFalse(self.api.jobs_view_route()['ok'])
        self.assertEqual(native.call_count, 0)
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), captured['bytes'])

    def test_native_read_keeps_captured_home_despite_ambient_profile_switch(self):
        other = self.home.parent / 'other-home'
        other.mkdir()
        with jobs.use_cron_store(other):
            jobs.create_job(prompt='Other profile owner', schedule='13 8 * * *', name='Other owner',
                            script='unrelated.py', no_agent=True, deliver='local', paused=True)
        other_before = (other / 'cron/jobs.json').read_bytes()
        before = (self.home / 'cron/jobs.json').read_bytes()
        verify, native_get = self.api._verified_native_jobs, jobs.get_job
        tokens, targets = [], []

        def switched(mapping):
            result = verify(mapping)
            tokens.append(set_hermes_home_override(other))
            return result

        def get(jid):
            targets.append((jid, jobs._current_cron_store().cron_dir.resolve()))
            return native_get(jid)

        try:
            with patch.object(self.api, '_verified_native_jobs', side_effect=switched), patch.object(jobs, 'get_job', side_effect=get):
                result = self.api.jobs_view_route()
            self.assertTrue(result['ok'], result)
            self.assertIn((self.mapping['watchdog'], (self.home / 'cron').resolve()), targets)
            self.assertTrue(all(target[1] == (self.home / 'cron').resolve() for target in targets))
            self.assertEqual((other / 'cron/jobs.json').read_bytes(), other_before)
            self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)
        finally:
            for token in reversed(tokens):
                reset_hermes_home_override(token)

    def test_retired_drafting_role_is_neither_listed_nor_creatable(self):
        self.assertNotIn('session_harvest', self.mapping)
        self.assertTrue(all(job['no_agent'] for job in jobs.list_jobs(include_disabled=True)), 'an agent job was installed')
        before = (self.home / 'cron/jobs.json').read_bytes()
        view = self.api.jobs_view_route()
        self.assertTrue(view['ok'], view)
        self.assertNotIn('session_harvest', {row['role'] for row in view['roles']})
        for action in ('create', 'resume'):
            self.assertFalse(self.act(action, role='session_harvest')['ok'])
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)

    def test_remove_confirmation_and_invalid_schedules_do_not_mutate(self):
        before = (self.home / 'cron/jobs.json').read_bytes()
        unconfirmed = self.api.jobs_act_route({'role': 'watchdog', 'action': 'remove'})
        self.assertFalse(unconfirmed['ok'])
        self.assertNotIn('needs_confirm', unconfirmed)
        for payload in ({'role': 'watchdog', 'action': 'schedule', 'schedule': 'not a schedule'},
                        {'role': 'watchdog', 'action': 'schedule'},
                        {'role': 'unknown', 'action': 'pause'}, {'role': 'watchdog', 'action': 'unknown'}):
            self.assertFalse(self.api.jobs_act_route(payload)['ok'])
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)

    def test_native_run_state_and_dispatch_labels_are_preserved(self):
        jid = self.mapping['watchdog']
        for kind, expected in (('catch_up', 'missed'), ('late', 'late'), ('on_time', None)):
            jobs.update_job(jid, {'last_run_at': '2026-09-28T09:00:05+03:00', 'last_status': 'error',
                                 'last_dispatch': {'kind': kind, 'lateness_seconds': 9600}})
            row = next(row for row in self.api.jobs_view_route()['roles'] if row['role'] == 'watchdog')
            self.assertEqual(row['last_run_at'], '2026-09-28T09:00:05+03:00')
            self.assertEqual(row['last_status'], 'error')
            self.assertEqual((row['dispatch'] or {}).get('flag'), expected)
        for malformed in ('late', {'kind': 'unknown'}, None):
            self.assertIsNone(self.api._dispatch_flag({'last_dispatch': malformed}))

    def test_unreadable_owner_mapping_is_not_silently_ignored(self):
        self.panel_settings.write_bytes(b'{not-json')
        before = (self.home / 'cron/jobs.json').read_bytes()
        result = self.act('resume')
        self.assertFalse(result['ok'], 'Unreadable owner mapping was ignored')
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)
        self.assertEqual(self.panel_settings.read_bytes(), b'{not-json')
        self.assertFalse(self.api.jobs_view_route()['ok'], 'Unreadable mapping granted role labels')

    def test_selected_launcher_provenance_cannot_be_replaced(self):
        launcher = self.home / 'scripts/palantir_wiki_watchdog.py'
        launcher.write_bytes(b'raise SystemExit("foreign launcher")\n')
        location = self.home / 'state/wiki-automation/location.json'
        record = json.loads(location.read_bytes())
        record['launcher_hashes'][launcher.name] = __import__('hashlib').sha256(launcher.read_bytes()).hexdigest()
        location.write_bytes(json.dumps(record).encode())
        before = (self.home / 'cron/jobs.json').read_bytes()
        result = self.act('resume')
        self.assertFalse(result['ok'], 'Replaced launcher granted native role authority')
        self.assertFalse(self.api.jobs_view_route()['ok'], 'Replaced launcher received a role label')
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)

    def test_run_history_does_not_label_wrong_native_role(self):
        settings = json.loads(self.settings.read_bytes())
        settings['jobs']['watchdog'] = self.unrelated['id']
        self.settings.write_bytes(json.dumps(settings).encode())
        result = self.api.runs()
        self.assertFalse(result['ok'], 'Run history assigned engine role to an unrelated ID')

    def test_owned_native_jobs_remain_readable_with_owner_customizations(self):
        jid = self.mapping['watchdog']
        jobs.update_job(jid, {'schedule': '23 6 * * *', 'deliver': 'local'})
        settings_before = self.settings.read_bytes()
        before = (self.home / 'cron/jobs.json').read_bytes()
        original = jobs.get_job(jid)
        unrelated_before = jobs.get_job(self.unrelated['id'])
        view = self.api.jobs_view_route()
        self.assertTrue(view['ok'], view)
        row = next(row for row in view['roles'] if row['role'] == 'watchdog')
        self.assertEqual(row['id'], jid)
        self.assertEqual(row['schedule'], '23 6 * * *')
        self.assertEqual(row['deliver'], 'local', 'View replaced owner delivery with engine default')
        self.assertEqual(self.settings.read_bytes(), settings_before)
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)
        self.assertEqual(jobs.get_job(jid), original)
        self.assertEqual(jobs.get_job(self.unrelated['id']), unrelated_before)

    def test_pause_resume_and_schedule_change_only_the_owned_job(self):
        jid = self.mapping['watchdog']
        unrelated = jobs.get_job(self.unrelated['id'])
        owner = self.settings.read_bytes()
        resumed = self.act('resume')
        self.assertTrue(resumed['ok'], resumed)
        self.assertNotEqual(jobs.effective_job_state(jobs.get_job(jid)), 'paused')
        self.assertTrue(resumed['next_run_at'])
        moved = self.act('schedule', schedule='17 22 * * *')
        self.assertTrue(moved['ok'], moved)
        self.assertEqual(jobs.get_job(jid)['schedule']['expr'], '17 22 * * *')
        paused = self.act('pause')
        self.assertTrue(paused['ok'], paused)
        record = jobs.get_job(jid)
        self.assertEqual(jobs.effective_job_state(record), 'paused')
        self.assertEqual(record['paused_reason'], 'Paused from the Wiki Automation panel.')
        self.assertEqual(jobs.get_job(self.unrelated['id']), unrelated)
        self.assertEqual(self.settings.read_bytes(), owner)
        view = self.api.jobs_view_route()
        self.assertTrue(view['ok'], view)
        row = next(row for row in view['roles'] if row['role'] == 'watchdog')
        self.assertEqual((row['state'], row['schedule']), ('paused', '17 22 * * *'))

    def test_a_page_that_saw_an_older_record_is_refused(self):
        jid = self.mapping['watchdog']
        seen = self.facts()
        jobs.update_job(jid, {'schedule': '5 5 * * *'})
        before = (self.home / 'cron/jobs.json').read_bytes()
        for action in ('resume', 'pause', 'schedule', 'remove'):
            with self.subTest(action=action):
                result = self.act(action, expected=seen)
                self.assertFalse(result['ok'], result)
                self.assertIn('changed', result['reason'])
                self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)

    def test_a_change_after_inspection_is_seen_inside_the_store_lock(self):
        import threading
        jid = self.mapping['watchdog']
        verify = self.api._verified_native_jobs

        def raced(mapping):
            result = verify(mapping)

            def write():
                with jobs.use_cron_store(self.home):
                    jobs.update_job(jid, {'schedule': '9 9 * * *'})
            writer = threading.Thread(target=write)
            writer.start()
            writer.join()
            return result

        with patch.object(self.api, '_verified_native_jobs', side_effect=raced), \
                patch.object(jobs, 'resume_job', wraps=jobs.resume_job) as native:
            result = self.act('resume')
        self.assertFalse(result['ok'], result)
        self.assertEqual(native.call_count, 0)
        self.assertEqual(jobs.get_job(jid)['schedule']['expr'], '9 9 * * *')
        self.assertEqual(jobs.effective_job_state(jobs.get_job(jid)), 'paused')

    def test_the_change_waits_for_another_writer_holding_the_store_lock(self):
        import threading
        jid = self.mapping['watchdog']
        held, release, done = threading.Event(), threading.Event(), {}
        expected = self.facts()

        def holder():
            with jobs.use_cron_store(self.home), jobs._jobs_lock():
                held.set()
                release.wait(10)
                jobs.update_job(jid, {'schedule': '8 8 * * *'})

        def actor():
            token = set_hermes_home_override(self.home)
            try:
                done['result'] = self.act('resume', expected=expected)
            finally:
                reset_hermes_home_override(token)

        first = threading.Thread(target=holder)
        first.start()
        self.assertTrue(held.wait(10))
        second = threading.Thread(target=actor)
        second.start()
        second.join(3)
        self.assertTrue(second.is_alive(), 'The panel wrote while another writer held the store lock')
        release.set()
        first.join(10)
        second.join(60)
        self.assertFalse(done['result']['ok'], done['result'])
        self.assertEqual(jobs.get_job(jid)['schedule']['expr'], '8 8 * * *')
        self.assertEqual(jobs.effective_job_state(jobs.get_job(jid)), 'paused')

    def test_without_the_native_lock_changes_stay_off(self):
        lock = jobs._jobs_lock
        before = (self.home / 'cron/jobs.json').read_bytes()
        del jobs._jobs_lock
        try:
            view = self.api.jobs_view_route()
            self.assertIs(view['mutation_available'], False)
            self.assertTrue(view['management_reason'])
            result = self.act('resume')
        finally:
            jobs._jobs_lock = lock
        self.assertFalse(result['ok'], result)
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)

    def test_delete_forgets_the_role_and_the_reviewed_installation_recreates_it_paused(self):
        jid = self.mapping['watchdog']
        unrelated = jobs.get_job(self.unrelated['id'])
        self.assertFalse(self.api.jobs_act_route({'role': 'watchdog', 'action': 'remove',
                                                  'expected': self.facts()})['ok'])
        removed = self.act('remove')
        self.assertTrue(removed['ok'], removed)
        self.assertIsNone(jobs.get_job(jid))
        self.assertNotIn('watchdog', json.loads(self.settings.read_bytes())['jobs'])
        self.assertEqual(jobs.get_job(self.unrelated['id']), unrelated)
        view = self.api.jobs_view_route()
        self.assertTrue(view['ok'], view)
        row = next(row for row in view['roles'] if row['role'] == 'watchdog')
        self.assertFalse(row['live'])
        create = self.act('create')
        self.assertEqual((create['ok'], create.get('install')), (False, True))
        lifecycle = sys.modules['ownership_lifecycle']
        manifest = json.loads((PACKAGE / 'engine-release.json').read_bytes())
        wiki = json.loads(self.settings.read_bytes())['project_root']
        prepared = lifecycle.prepare_install(self.home, PACKAGE, manifest, wiki, principal='fixture-session')
        self.assertEqual(next(job for job in prepared['jobs'] if job['role'] == 'watchdog')['disposition'],
                         'create_paused')
        lifecycle.apply_install(self.home, PACKAGE, manifest, prepared['install_id'], prepared['plan_digest'],
                                principal='fixture-session')
        view = self.api.jobs_view_route()
        self.assertTrue(view['ok'], view)
        row = next(row for row in view['roles'] if row['role'] == 'watchdog')
        self.assertTrue(row['live'])
        self.assertNotEqual(row['id'], jid)
        self.assertEqual(row['state'], 'paused')
        self.assertEqual(jobs.get_job(self.unrelated['id']), unrelated)

    def test_unmapped_role_cannot_duplicate_existing_native_job(self):
        settings = json.loads(self.settings.read_bytes())
        del settings['jobs']['watchdog']
        self.settings.write_bytes(json.dumps(settings).encode())
        before = (self.home / 'cron/jobs.json').read_bytes()
        owner = self.settings.read_bytes()
        result = self.act('create')
        self.assertFalse(result['ok'], 'Missing mapping silently duplicated an existing native role')
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)
        self.assertEqual(self.settings.read_bytes(), owner)
        self.assertFalse(self.panel_settings.exists())

    def test_native_project_binding_cannot_be_retargeted(self):
        jobs.update_job(self.mapping['watchdog'], {'workdir': str(self.home)})
        before = (self.home / 'cron/jobs.json').read_bytes()
        result = self.act('resume')
        self.assertFalse(result['ok'], 'Native script project binding was ignored')
        self.assertFalse(self.api.jobs_view_route()['ok'], 'Foreign project job received a role label')
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)

    def test_changed_native_payload_refuses_role_labels(self):
        verify = self.api._verified_native_jobs
        captured = {}

        def changed(mapping):
            result = verify(mapping)
            jobs.update_job(self.mapping['watchdog'], {'script': 'unrelated.py'})
            captured['bytes'] = (self.home / 'cron/jobs.json').read_bytes()
            return result

        with patch.object(self.api, '_verified_native_jobs', side_effect=changed), patch.object(jobs, 'remove_job', wraps=jobs.remove_job) as remove:
            result = self.api.jobs_view_route()
        self.assertFalse(result['ok'], 'Changed native payload received a role label after inspection')
        self.assertEqual(remove.call_count, 0, 'Native mutator was entered with a changed record')
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), captured['bytes'])

    def test_same_role_with_foreign_authority_is_refused(self):
        original = jobs.get_job(self.mapping['watchdog'])
        replacement = jobs.create_job(prompt='Foreign owner role lookalike', schedule='13 8 * * *',
            name=original['name'], script=original['script'], no_agent=True, deliver='local',
            paused=True, workdir=original['workdir'],
            origin={'engine_installation': 'f' * 64, 'engine_role': 'watchdog'})
        settings = json.loads(self.settings.read_bytes())
        settings['jobs']['watchdog'] = replacement['id']
        self.settings.write_bytes(json.dumps(settings).encode())
        before = (self.home / 'cron/jobs.json').read_bytes()
        result = self.act('remove')
        self.assertFalse(result['ok'], 'Matching name/script granted foreign installation authority')
        self.assertFalse(self.api.jobs_view_route()['ok'], 'Foreign installation received a role label')
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)

    def test_wrong_native_role_is_not_labelled_as_watchdog(self):
        settings = json.loads(self.settings.read_bytes())
        settings['jobs']['watchdog'] = self.unrelated['id']
        self.settings.write_bytes(json.dumps(settings).encode())
        before = (self.home / 'cron/jobs.json').read_bytes()
        result = self.api.jobs_view_route()
        self.assertFalse(result['ok'], 'Unrelated job was labelled as a selected engine role')
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)

    def test_unrelated_mapping_cannot_remove_native_job(self):
        settings = json.loads(self.settings.read_bytes())
        settings['jobs']['watchdog'] = self.unrelated['id']
        self.settings.write_bytes(json.dumps(settings).encode())
        before = (self.home / 'cron/jobs.json').read_bytes()
        owner_settings = self.settings.read_bytes()
        result = self.act('remove')
        self.assertFalse(result['ok'], 'Unrelated native ID was accepted: ' + str(result))
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)
        self.assertEqual(self.settings.read_bytes(), owner_settings)

    def test_conflicting_map_cannot_remove_unrelated_native_job(self):
        self.panel_settings.write_bytes(json.dumps({'jobs': {'watchdog': self.unrelated['id']}}).encode())
        before = (self.home / 'cron/jobs.json').read_bytes()
        owner_settings = self.settings.read_bytes()
        panel_settings = self.panel_settings.read_bytes()
        result = self.act('remove')
        self.assertFalse(result['ok'], 'Wrong-role remove was accepted: ' + str(result))
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)
        self.assertEqual(self.settings.read_bytes(), owner_settings)
        self.assertEqual(self.panel_settings.read_bytes(), panel_settings)
        self.assertIsNotNone(jobs.get_job(self.unrelated['id']))
        self.assertFalse(self.api.jobs_view_route()['ok'], 'Conflicting mapping granted a role label')


if __name__ == '__main__':
    unittest.main()
