"""Real native installation and host-auth recovery contract in disposable profiles."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from dataclasses import replace
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from hermes_cli import web_server
from hermes_cli.dashboard_auth.base import DashboardAuthProvider, Session
from hermes_cli.dashboard_auth.middleware import gated_auth_middleware

class FixtureSessionProvider(DashboardAuthProvider):
    name = 'installation-recovery-test'
    display_name = 'Disposable installation recovery auth fixture'
    def __init__(self):
        self.sessions = {}
    def start_login(self, **kwargs):
        raise NotImplementedError
    def complete_login(self, **kwargs):
        raise NotImplementedError
    def verify_session(self, *, access_token):
        return self.sessions.get(access_token)
    def refresh_session(self, **kwargs):
        raise NotImplementedError
    def revoke_session(self, **kwargs):
        raise NotImplementedError

PACKAGE = Path(__file__).resolve().parents[1]

class InstallationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ['TMPDIR'])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home, self.wiki = self.root / 'home', self.root / 'wiki'
        self.home.mkdir()
        (self.home / 'config.yaml').write_bytes(b'{}')
        (self.wiki / '.llm-wiki').mkdir(parents=True)
        (self.wiki / '.llm-wiki/project.json').write_bytes(b'{"id":"recovery-fixture"}')
        (self.wiki / 'wiki').mkdir()
        (self.wiki / 'wiki/index.md').write_bytes(b'# Owner content\n')
        source = PACKAGE / 'dashboard/engine_lifecycle.py'
        spec = importlib.util.spec_from_file_location('recovery_test_lifecycle', source)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.package = Path(os.environ.get('RECOVERY_ENGINE_PACKAGE', PACKAGE))
        self.manifest = json.loads((self.package / 'engine-release.json').read_bytes())
        app = FastAPI()
        app.state.auth_required = False
        self.app = app
        self.service = False
        self.cron = False
        @app.middleware('http')
        async def profile_scope(request, call_next):
            token = set_hermes_home_override(self.home)
            from cron.execution_identity import enter_cron_execution, exit_cron_execution
            cron_token = enter_cron_execution({'id': 'fixture-job'}, 'fixture-execution', {}) if self.cron else None
            try:
                request.state.token_authenticated = self.service
                return await gated_auth_middleware(request, call_next)
            finally:
                exit_cron_execution(cron_token)
                reset_hermes_home_override(token)
        app.include_router(self.module.make_router(lambda: self.package, lambda: self.manifest), prefix='/engine')
        self.client = TestClient(app)
        self.session = patch.object(web_server, '_SESSION_TOKEN', 'original-app-session')
        self.session.start()
        self.addCleanup(self.session.stop)
        self.headers = {'X-Hermes-Session-Token': 'original-app-session'}

    def post(self, route, payload):
        return self.client.post('/engine/' + route, json=payload, headers=self.headers)

    def prepare(self):
        response = self.post('prepare', {'project_root': str(self.wiki)})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def crash(self, prepared, phase='engine_applied'):
        record = self.home / ('state/wiki-automation/installations/' + prepared['install_id'] + '.json')
        principal = json.loads(record.read_bytes())['principal']
        worker = ('import importlib.util,sys,json,os; from pathlib import Path; '
            's=importlib.util.spec_from_file_location("worker",sys.argv[1]); '
            'm=importlib.util.module_from_spec(s); s.loader.exec_module(m); '
            'm._checkpoint=lambda phase: os._exit(91) if phase==sys.argv[8] else None; '
            'm.apply_install(Path(sys.argv[2]),Path(sys.argv[3]),json.loads(sys.argv[4]),'
            'sys.argv[5],sys.argv[6],principal=sys.argv[7])')
        result = subprocess.run([sys.executable, '-B', '-c', worker,
            str(PACKAGE / 'dashboard/engine_lifecycle.py'), str(self.home), str(self.package),
            json.dumps(self.manifest), prepared['install_id'], prepared['plan_digest'], principal, phase],
            capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 91, result.stderr)
        self.assertEqual(json.loads(record.read_bytes())['state'], 'applying')
        return record

    def fresh_session(self):
        web_server._SESSION_TOKEN = 'fresh-app-session'
        self.headers = {'X-Hermes-Session-Token': 'fresh-app-session'}

    def review(self, prepared):
        response = self.post('recovery/prepare', {'install_id': prepared['install_id']})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def confirm_payload(self, review):
        return {**{key: review[key] for key in ('install_id', 'plan_digest', 'recovery_review_id', 'recovery_review_digest')}, 'confirm': True}

    def remote(self):
        from hermes_cli.dashboard_auth.registry import register_provider, restore_registration
        provider = FixtureSessionProvider()
        register_provider(provider, scope=str(self.home))
        self.addCleanup(lambda: restore_registration(provider.name, provider, None, scope=str(self.home)))
        session = Session(user_id='verified-admin', email='fixture@example.invalid', display_name='Fixture',
            org_id='verified-org', provider=provider.name, expires_at=int(time.time()) + 3600,
            access_token='fixture-original-access', refresh_token='fixture-refresh')
        provider.sessions[session.access_token] = session
        self.app.state.auth_required = True
        self.headers = {'Authorization': 'Bearer ' + session.access_token}
        return provider, session

    def test_approved_death_new_session_rereviews_exact_original_plan_and_resumes(self):
        prepared = self.prepare()
        record_path = self.crash(prepared)
        before_record = json.loads(record_path.read_bytes())
        jobs = (self.home / 'cron/jobs.json').read_bytes()
        settings = (Path(prepared['audit_dir']) / 'settings.json').read_bytes()
        content = (self.wiki / 'wiki/index.md').read_bytes()
        wiki_files = {p.relative_to(self.wiki).as_posix(): p.read_bytes() for p in self.wiki.rglob('*') if p.is_file()}
        self.fresh_session()
        old = self.post('apply', {'install_id': prepared['install_id'], 'plan_digest': prepared['plan_digest'], 'confirm': True})
        self.assertEqual(old.status_code, 409, old.text)
        self.assertIn('session', old.json()['reason'])
        print('OLD_INABILITY reproduced: new session cannot retry approved engine_applied death')
        review = self.post('recovery/prepare', {'install_id': prepared['install_id']})
        self.assertEqual(review.status_code, 200, review.text)
        review = review.json()
        self.assertEqual(review['state'], 'recovery_prepared')
        for key in ('install_id', 'plan_digest', 'revision', 'project_root', 'project_id',
                'requested_project_root', 'engine_dir', 'audit_dir', 'jobs', 'activation'):
            self.assertEqual(review[key], prepared[key], key)
        self.assertEqual(json.loads(record_path.read_bytes()), before_record)
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), jobs)
        self.assertEqual((Path(prepared['audit_dir']) / 'settings.json').read_bytes(), settings)
        payload = {key: review[key] for key in ('install_id', 'plan_digest', 'recovery_review_id', 'recovery_review_digest')}
        result = self.post('recovery/apply', {**payload, 'confirm': True})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json(), {'ok': True, 'state': 'installed_paused',
            'revision': prepared['revision'], 'install_id': prepared['install_id'], 'activation_required': True})
        after = json.loads(record_path.read_bytes())
        for key in ('principal', 'plan', 'install_id', 'manifest'):
            self.assertEqual(after[key], before_record[key])
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), jobs)
        self.assertEqual((Path(prepared['audit_dir']) / 'settings.json').read_bytes(), settings)
        self.assertEqual((self.wiki / 'wiki/index.md').read_bytes(), content)
        self.assertEqual(wiki_files, {p.relative_to(self.wiki).as_posix(): p.read_bytes() for p in self.wiki.rglob('*') if p.is_file()})
        self.assertFalse((self.wiki / '.llm-wiki/owner.json').exists())
        self.assertEqual(self.client.get('/engine/status', headers=self.headers).json()['state'], 'installed_paused')

    def test_original_admin_binding_cannot_be_rewritten_to_adopt_half_operation(self):
        prepared = self.prepare()
        record_path = self.crash(prepared)
        original = json.loads(record_path.read_bytes())
        forged = {**original, 'original_administrator': 'f' * 64}
        record_path.write_bytes(json.dumps(forged).encode())
        self.fresh_session()
        with self.assertRaises(self.module.LifecycleRefused):
            self.module.prepare_recovery(self.home, self.package, self.manifest, prepared['install_id'],
                principal='fresh-principal', administrator='f' * 64)
        self.assertEqual(json.loads(record_path.read_bytes()), forged)

    def test_unfinished_status_keeps_original_id_when_partial_readback_refuses(self):
        prepared = self.prepare()
        self.crash(prepared)
        launcher = self.home / 'scripts/palantir_wiki_watchdog.py'
        launcher.write_bytes(b'# Owner drift preserved\n')
        response = self.client.get('/engine/status', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['state'], 'applying')
        self.assertEqual(response.json()['install_id'], prepared['install_id'])
        self.assertEqual(launcher.read_bytes(), b'# Owner drift preserved\n')

    def test_unfinished_status_keeps_identity_and_bounded_readonly_diagnostic_for_drift(self):
        prepared = self.prepare()
        self.crash(prepared)
        location = self.home / 'state/wiki-automation/location.json'
        launcher = self.home / 'scripts/palantir_wiki_watchdog.py'
        settings = Path(prepared['audit_dir']) / 'settings.json'
        jobs = self.home / 'cron/jobs.json'
        original = {path: path.read_bytes() for path in (location, launcher, settings, jobs)}
        unmatched = json.loads(original[location])
        unmatched['owner_note'] = 'Never lose unfinished identity'
        malformed_jobs = json.loads(original[jobs])
        malformed_jobs['jobs'][0]['repeat']['completed'] = None
        for path, value in ((launcher, b'# Owner drift\n'),
                (location, json.dumps(unmatched).encode()), (location, b'{owner-secret-settings'),
                (location, None), (settings, None), (jobs, json.dumps(malformed_jobs).encode())):
            with self.subTest(path=path.name, missing=value is None):
                for target, content in original.items():
                    target.write_bytes(content)
                if value is None:
                    path.unlink()
                else:
                    path.write_bytes(value)
                before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()}
                response = self.client.get('/engine/status', headers=self.headers)
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(result['state'], 'applying')
                self.assertEqual(result['install_id'], prepared['install_id'])
                self.assertEqual(result['plan_digest'], prepared['plan_digest'])
                self.assertEqual(result['operation_state'], 'applying')
                self.assertIsNone(result['active_state'])
                self.assertEqual(result.get('active_verification'), 'unverified')
                diagnostic = result.get('read_only_diagnostic')
                self.assertIsInstance(diagnostic, dict)
                self.assertIs(diagnostic['ok'], False)
                self.assertTrue(diagnostic['reason'])
                self.assertLessEqual(len(diagnostic['reason']), 240)
                self.assertNotIn('owner-secret', diagnostic['reason'])
                self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()})

    def test_installed_readback_refuses_native_repair_shape_without_writing(self):
        prepared = self.prepare()
        applied = self.post('apply', {'install_id': prepared['install_id'],
            'plan_digest': prepared['plan_digest'], 'confirm': True})
        self.assertEqual(applied.status_code, 200, applied.text)
        path = self.home / 'cron/jobs.json'
        document = json.loads(path.read_bytes())
        document['jobs'][0]['repeat']['completed'] = None
        path.write_bytes(json.dumps(document).encode())
        before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()}
        response = self.client.get('/engine/status', headers=self.headers)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()})

    def test_unstarted_death_capture_drift_refuses_review_and_apply_before_native_writes(self):
        prepared = self.prepare()
        self.crash(prepared, 'applying_recorded')
        self.fresh_session()
        native_journal = self.home / 'state/wiki-automation/installation.sqlite'
        jobs = self.home / 'cron/jobs.json'
        capture = Path(prepared['audit_dir']) / ('.wiki-install-recovery/' + prepared['plan_digest'] + '/settings/recapture-fixture/captured.bin')
        capture.parent.mkdir(parents=True)
        capture.write_bytes(b'Owner bad capture retained before review')
        before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()}
        refused = self.post('recovery/prepare', {'install_id': prepared['install_id']})
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()})
        self.assertFalse(native_journal.exists())
        self.assertFalse(jobs.exists())
        capture.unlink()
        capture.parent.rmdir()
        review = self.review(prepared)
        capture.parent.mkdir()
        capture.write_bytes(b'Owner bad capture retained after review')
        before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()}
        refused = self.post('recovery/apply', self.confirm_payload(review))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertFalse(native_journal.exists())
        self.assertFalse(jobs.exists())
        self.assertFalse((self.home / 'state/wiki-automation/location.json').exists())
        self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()})

    def test_status_discovers_readable_unfinished_identity_despite_newer_unreadable_record(self):
        prepared = self.prepare()
        self.crash(prepared)
        unreadable = self.home / ('state/wiki-automation/installations/' + 'f' * 64 + '.json')
        unreadable.write_bytes(b'{owner-secret-unreadable-record')
        before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()}
        response = self.client.get('/engine/status', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result['install_id'], prepared['install_id'])
        self.assertEqual(result['plan_digest'], prepared['plan_digest'])
        self.assertEqual(result['state'], 'applying')
        self.assertEqual(result.get('active_verification'), 'unverified')
        self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()})
        unreadable.unlink()
        owner_file = self.root / 'owner-sibling-record.bin'
        owner_file.write_bytes(b'{private-owner-record-not-installation')
        os.link(owner_file, unreadable)
        owner_before = (owner_file.read_bytes(), owner_file.stat().st_mtime_ns)
        response = self.client.get('/engine/status', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['install_id'], prepared['install_id'])
        self.assertEqual(response.json()['plan_digest'], prepared['plan_digest'])
        self.assertEqual((owner_file.read_bytes(), owner_file.stat().st_mtime_ns), owner_before)

    def test_raw_linked_profile_is_refused_before_session_principal_normalization(self):
        from fastapi import HTTPException, Request
        from test_reparse_confinement import ReparseConfinementTests
        link = self.root / 'raw-linked-profile'
        request = Request({'type': 'http', 'method': 'GET', 'path': '/engine/status',
            'headers': [(b'x-hermes-session-token', b'original-app-session')], 'app': self.app})
        before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()}
        with ReparseConfinementTests().directory_link(link, self.home):
            token = set_hermes_home_override(link)
            try:
                with self.assertRaises(HTTPException) as caught:
                    self.module.installation_principal(request)
                self.assertEqual(caught.exception.status_code, 409)
            finally:
                reset_hermes_home_override(token)
        self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()})

    def test_prepared_unapproved_record_cannot_be_adopted_even_if_marked_applying(self):
        prepared = self.prepare()
        path = self.home / ('state/wiki-automation/installations/' + prepared['install_id'] + '.json')
        saved = json.loads(path.read_bytes())
        self.assertNotIn('approved', saved)
        saved['state'] = 'applying'
        path.write_bytes(json.dumps(saved).encode())
        self.fresh_session()
        response = self.post('recovery/prepare', {'install_id': prepared['install_id']})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(json.loads(path.read_bytes()), saved)
        self.assertFalse((self.home / 'cron/jobs.json').exists())

    def test_legacy_missing_original_admin_or_durable_approval_never_retrofits(self):
        prepared = self.prepare()
        path = self.crash(prepared)
        saved = json.loads(path.read_bytes())
        self.assertIs(saved['approved'], True)
        self.assertRegex(saved['original_administrator'], '^[0-9a-f]{64}$')
        self.fresh_session()
        for key in ('approved', 'original_administrator'):
            for value in ('missing', None, False, 1):
                with self.subTest(key=key, value=value):
                    legacy = dict(saved)
                    if value == 'missing':
                        legacy.pop(key)
                    else:
                        legacy[key] = value
                    path.write_bytes(json.dumps(legacy).encode())
                    response = self.post('recovery/prepare', {'install_id': prepared['install_id']})
                    self.assertEqual(response.status_code, 409, response.text)
                    self.assertEqual(json.loads(path.read_bytes()), legacy)
        self.assertFalse((self.home / 'state/wiki-automation/recovery-reviews').exists())

    def test_remote_host_verified_same_admin_token_refresh_and_incarnation_binding(self):
        provider, session = self.remote()
        prepared = self.prepare()
        path = self.crash(prepared)
        original = json.loads(path.read_bytes())
        web_server._SESSION_TOKEN = 'remote-fresh-server-incarnation'
        refreshed = replace(session, access_token='fixture-refreshed-access')
        provider.sessions[refreshed.access_token] = refreshed
        self.headers = {'Authorization': 'Bearer ' + refreshed.access_token}
        review = self.review(prepared)
        self.assertEqual(json.loads(path.read_bytes())['original_administrator'], original['original_administrator'])
        next_token = replace(refreshed, access_token='fixture-next-token')
        provider.sessions[next_token.access_token] = next_token
        self.headers = {'Authorization': 'Bearer ' + next_token.access_token}
        rejected = self.post('recovery/apply', self.confirm_payload(review))
        self.assertEqual(rejected.status_code, 409, rejected.text)
        review = self.review(prepared)
        web_server._SESSION_TOKEN = 'remote-another-server-incarnation'
        rejected = self.post('recovery/apply', self.confirm_payload(review))
        self.assertEqual(rejected.status_code, 409, rejected.text)
        review = self.review(prepared)
        result = self.post('recovery/apply', self.confirm_payload(review))
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['state'], 'installed_paused')

    def test_remote_foreign_verified_user_org_or_provider_cannot_adopt(self):
        provider, session = self.remote()
        prepared = self.prepare()
        path = self.crash(prepared)
        before = path.read_bytes()
        for field in ('user_id', 'org_id', 'provider'):
            with self.subTest(field=field):
                foreign = replace(session, **{field: 'foreign-' + field, 'access_token': 'fixture-' + field})
                provider.sessions[foreign.access_token] = foreign
                self.headers = {'Authorization': 'Bearer ' + foreign.access_token}
                response = self.post('recovery/prepare', {'install_id': prepared['install_id']})
                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(path.read_bytes(), before)
        response = self.client.post('/engine/recovery/prepare', json={'install_id': prepared['install_id']},
            headers={'Authorization': 'Bearer invalid-fixture-token'}, follow_redirects=False)
        self.assertIn(response.status_code, (401, 302), response.text)
        self.assertFalse((self.home / 'state/wiki-automation/recovery-reviews').exists())

    def test_new_review_does_not_bind_wiki_owner_or_disclose_original_settings(self):
        data = self.home / 'state/wiki-automation/data'
        data.mkdir(parents=True)
        secret_settings = {'owner_session': {'principal': 'content-owner-only'}, 'unrelated_secret': 'do-not-emit-fixture'}
        (data / 'settings.json').write_bytes(json.dumps(secret_settings).encode())
        owner = self.wiki / '.llm-wiki/owner-fixture.json'
        owner.write_bytes(b'{"wiki_owner":"not-admin"}')
        prepared = self.prepare()
        path = self.crash(prepared)
        before_settings = (data / 'settings.json').read_bytes()
        self.fresh_session()
        review = self.review(prepared)
        self.assertNotIn('do-not-emit-fixture', json.dumps(review))
        self.assertNotIn('content-owner-only', json.dumps(review))
        self.assertEqual((data / 'settings.json').read_bytes(), before_settings)
        result = self.post('recovery/apply', self.confirm_payload(review))
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual((data / 'settings.json').read_bytes(), before_settings)
        self.assertEqual(owner.read_bytes(), b'{"wiki_owner":"not-admin"}')

    def test_profile_release_project_and_code_drift_refuse_without_repair(self):
        prepared = self.prepare()
        path = self.crash(prepared)
        self.fresh_session()
        record = path.read_bytes()
        original_home = self.home
        foreign_home = self.root / 'foreign-profile'
        foreign_home.mkdir()
        (foreign_home / 'config.yaml').write_bytes(b'{}')
        self.home = foreign_home
        response = self.post('recovery/prepare', {'install_id': prepared['install_id']})
        self.assertEqual(response.status_code, 409, response.text)
        self.home = original_home
        manifest = self.manifest
        self.manifest = {**manifest, 'revision': 'e' * 40}
        response = self.post('recovery/prepare', {'install_id': prepared['install_id']})
        self.assertEqual(response.status_code, 409, response.text)
        self.manifest = manifest
        project = self.wiki / '.llm-wiki/project.json'
        old_project = project.read_bytes()
        project.write_bytes(b'{"id":"foreign-project"}')
        response = self.post('recovery/prepare', {'install_id': prepared['install_id']})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(project.read_bytes(), b'{"id":"foreign-project"}')
        project.write_bytes(old_project)
        code = Path(prepared['engine_dir']) / 'jobs.json'
        code.write_bytes(b'{"owner":"dirty"}')
        response = self.post('recovery/prepare', {'install_id': prepared['install_id']})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(code.read_bytes(), b'{"owner":"dirty"}')
        self.assertEqual(path.read_bytes(), record)

    def test_current_native_state_change_invalidates_review_without_overwrite(self):
        prepared = self.prepare()
        self.crash(prepared)
        self.fresh_session()
        review = self.review(prepared)
        jobs = self.home / 'cron/jobs.json'
        changed = json.loads(jobs.read_bytes())
        changed['jobs'][0]['enabled'] = True
        changed['jobs'][0]['state'] = 'scheduled'
        jobs.write_bytes(json.dumps(changed).encode())
        before = jobs.read_bytes()
        response = self.post('recovery/apply', self.confirm_payload(review))
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn('changed', response.json()['reason'])
        self.assertEqual(jobs.read_bytes(), before)

    def test_exact_json_confirmation_expiration_and_service_cron_isolation_guards(self):
        prepared = self.prepare()
        self.crash(prepared)
        self.fresh_session()
        review = self.review(prepared)
        payload = self.confirm_payload(review)
        self.assertEqual(self.client.post('/engine/recovery/prepare', json={'install_id': prepared['install_id']}).status_code, 401)
        for changed in ({**payload, 'confirm': False}, {**payload, 'confirm': 1}, {**payload, 'home': str(self.home)},
                {**payload, 'plan_digest': '0' * 64}, {**payload, 'recovery_review_digest': '0' * 64}):
            with self.subTest(changed=changed):
                response = self.post('recovery/apply', changed)
                self.assertIn(response.status_code, (400, 409), response.text)
        for invalid in ({'install_id': 'A' * 64}, {'install_id': 'a' * 63}, {'install_id': prepared['install_id'], 'principal': 'foreign'}):
            self.assertEqual(self.post('recovery/prepare', invalid).status_code, 400)
        with patch.object(self.module.time, 'time', return_value=review['review_expires_at'] + 1):
            response = self.post('recovery/apply', payload)
            self.assertEqual(response.status_code, 409, response.text)
        for flag in ('service', 'cron'):
            setattr(self, flag, True)
            for route, body in (('recovery/prepare', {'install_id': prepared['install_id']}), ('recovery/apply', payload)):
                response = self.post(route, body)
                self.assertEqual(response.status_code, 403, response.text)
            setattr(self, flag, False)
        (self.home / 'config.yaml').write_bytes(b'plugins:\n  isolation: host\n')
        for route, body in (('recovery/prepare', {'install_id': prepared['install_id']}), ('recovery/apply', payload)):
            response = self.post(route, body)
            self.assertEqual(response.status_code, 403, response.text)

    def test_original_approved_death_before_engine_mutation_resumes(self):
        prepared = self.prepare()
        self.crash(prepared, phase='applying_recorded')
        self.assertFalse((self.home / 'cron/jobs.json').exists())
        self.fresh_session()
        review = self.review(prepared)
        self.assertEqual(review['native_operation_state'], 'unstarted')
        response = self.post('recovery/apply', self.confirm_payload(review))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['state'], 'installed_paused')
        self.assertEqual(len(json.loads((self.home / 'cron/jobs.json').read_bytes())['jobs']), 4)
        self.assertEqual(self.post('recovery/apply', self.confirm_payload(review)).status_code, 409)

    def test_real_native_job_save_death_resumes_original_half_operation_once(self):
        prepared = self.prepare()
        path = self.crash(prepared, phase='applying_recorded')
        plan_file = path.with_suffix('.plan.json')
        worker = ('import sys,json,os; from pathlib import Path; sys.path.insert(0,sys.argv[1]); '
            'import install,candidate_apply; '
            'candidate_apply._checkpoint=lambda phase: os._exit(92) if phase=="after-create-job:autocommit" else None; '
            'p=json.loads(Path(sys.argv[2]).read_bytes()); install.apply_plan(p,p["digest"])')
        result = subprocess.run([sys.executable, '-B', '-c', worker, prepared['engine_dir'], str(plan_file)],
            capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 92, result.stderr)
        jobs_path = self.home / 'cron/jobs.json'
        partial = json.loads(jobs_path.read_bytes())['jobs']
        self.assertEqual(len(partial), 1)
        saved_id = partial[0]['id']
        self.fresh_session()
        review = self.review(prepared)
        self.assertEqual(review['native_operation_state'], 'applying')
        response = self.post('recovery/apply', self.confirm_payload(review))
        self.assertEqual(response.status_code, 200, response.text)
        jobs = json.loads(jobs_path.read_bytes())['jobs']
        self.assertEqual(len(jobs), 4)
        self.assertIn(saved_id, {job['id'] for job in jobs})
        self.assertTrue(all(job['enabled'] is False for job in jobs))
        self.assertEqual((self.wiki / 'wiki/index.md').read_bytes(), b'# Owner content\n')

    def test_bundled_old_release_without_read_only_helper_is_not_silently_upgraded(self):
        import shutil
        revision = '6f7f4df2193e41407673632a2cc52dcd0cf98497'
        self.package = self.root / 'legacy-release-fixture'
        self.package.mkdir()
        import zipfile
        from test_install_recovery_http import lifecycle_module
        archive = self.root / ('engine-no-session-recovery-' + revision + '.zip')
        shutil.copyfile(PACKAGE / 'tests/fixtures' / archive.name, archive)
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),
                         '6964e52964db3a43def0c8ab9380b35b9b2d69375103ed529d5e6ea5a49c9da0')
        # The old release is kept as an archived fixture and shipped the way releases ship now: a folder.
        with zipfile.ZipFile(archive) as bundle:
            files = {entry.filename: bundle.read(entry) for entry in bundle.infolist() if not entry.is_dir()}
        for name, content in files.items():
            target = self.package / 'engine' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        digest = lifecycle_module().release_digest(files)
        self.manifest = {'schema': 2, 'artifact': 'engine', 'revision': digest[:40], 'sha256': digest,
            'workflow_schema': {'min': 1, 'max': 1}, 'python_min': [3, 11]}
        prepared = self.prepare()
        path = self.crash(prepared)
        before = {str(p): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        self.fresh_session()
        response = self.post('recovery/prepare', {'install_id': prepared['install_id']})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()['state'], 'refused')
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.home.rglob('*') if p.is_file()})
        self.assertFalse((self.home / 'state/wiki-automation/recovery-reviews').exists())

    def test_recovery_native_readback_refuses_secondary_capture_drift_after_engine_apply(self):
        data = self.home / 'state/wiki-automation/data'
        data.mkdir(parents=True)
        (data / 'settings.json').write_bytes(b'{"owner_note":"preserve"}')
        prepared = self.prepare()
        self.crash(prepared)
        self.fresh_session()
        review = self.review(prepared)
        capture = data / ('.wiki-install-recovery/' + prepared['plan_digest'] + '/settings/recapture-fixture/captured.bin')
        def owner_handle_write(phase):
            if phase == 'engine_applied':
                capture.parent.mkdir(parents=True, exist_ok=True)
                capture.write_bytes(b'Owner drift after engine mutation boundary')
        with patch.object(self.module, '_checkpoint', side_effect=owner_handle_write):
            response = self.post('recovery/apply', self.confirm_payload(review))
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(capture.read_bytes(), b'Owner drift after engine mutation boundary')
        self.assertEqual(self.client.get('/engine/status', headers=self.headers).json()['state'], 'recovery_required')

    def test_original_approved_update_resumes_with_existing_enabled_jobs_unchanged(self):
        from cron.jobs import use_cron_store, update_job
        first = self.prepare()
        response = self.post('apply', {'install_id': first['install_id'], 'plan_digest': first['plan_digest'], 'confirm': True})
        self.assertEqual(response.status_code, 200, response.text)
        token = set_hermes_home_override(self.home)
        try:
            with use_cron_store(self.home):
                jobs = json.loads((self.home / 'cron/jobs.json').read_bytes())['jobs']
                update_job(jobs[0]['id'], {'enabled': True, 'state': 'scheduled', 'schedule': '20 7 * * *'})
        finally:
            reset_hermes_home_override(token)
        prepared = self.prepare()
        self.crash(prepared)
        before = (self.home / 'cron/jobs.json').read_bytes()
        self.fresh_session()
        review = self.review(prepared)
        response = self.post('recovery/apply', self.confirm_payload(review))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['state'], 'installed_with_existing_jobs')
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), before)

    def test_recovery_serialization_and_unresolved_junction_profile_refuse(self):
        prepared = self.prepare()
        self.crash(prepared)
        self.fresh_session()
        with self.module.installation_lock(self.home):
            response = self.post('recovery/prepare', {'install_id': prepared['install_id']})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn('Another installation', response.json()['reason'])
        from test_reparse_confinement import ReparseConfinementTests
        link = self.root / 'linked-profile'
        before = {str(p): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        with ReparseConfinementTests().directory_link(link, self.home):
            with self.assertRaisesRegex(self.module.LifecycleRefused, 'Linked'):
                self.module.prepare_recovery(link, self.package, self.manifest, prepared['install_id'],
                    principal='fresh-fixture', administrator='a' * 64)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.home.rglob('*') if p.is_file()})

if __name__ == '__main__':
    unittest.main()
