"""Pinned release staging never executes an unverified engine folder or changes live state."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch


class EngineLifecycleTests(unittest.TestCase):
    def lifecycle(self):
        source = Path(__file__).resolve().parents[1] / 'dashboard/engine_lifecycle.py'
        self.assertTrue(source.is_file(), 'Missing pinned engine lifecycle')
        spec = importlib.util.spec_from_file_location('isolated_engine_lifecycle', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def archive(self, base, entries):
        # The engine ships as a plain folder inside the plugin; the manifest pins its content digest.
        folder = base / 'engine'
        folder.mkdir(parents=True, exist_ok=True)
        files = {}
        for name, content in entries:
            target = folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content.encode())
            files[name] = content.encode()
        digest = self.lifecycle().release_digest(files)
        return {'schema': 2, 'artifact': 'engine', 'revision': digest[:40], 'sha256': digest,
                'workflow_schema': {'min': 1, 'max': 1}, 'python_min': [3, 11]}

    def test_status_reads_native_state_and_keeps_active_revision_during_preview(self):
        module = self.lifecycle()
        package = Path(__file__).resolve().parents[1]
        manifest = json.loads((package / 'engine-release.json').read_bytes())
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from cron.jobs import use_cron_store, update_job
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home, wiki = Path(temp) / 'home', Path(temp) / 'wiki'
            home.mkdir()
            (home / 'config.yaml').write_bytes(b'{}')
            (wiki / '.llm-wiki').mkdir(parents=True)
            (wiki / '.llm-wiki/project.json').write_bytes(b'{"id":"status-fixture"}')
            (wiki / 'wiki').mkdir()
            (wiki / 'wiki/index.md').write_bytes(b'# Fixture\n')
            prepared = module.prepare_install(home, package, manifest, wiki, principal='first-fixture')
            module.apply_install(home, package, manifest, prepared['install_id'], prepared['plan_digest'], principal='first-fixture')
            token = set_hermes_home_override(home)
            try:
                with use_cron_store(home):
                    job = json.loads((home / 'cron/jobs.json').read_bytes())['jobs'][0]
                    update_job(job['id'], {'enabled': True, 'state': 'scheduled'})
            finally:
                reset_hermes_home_override(token)
            state = module.lifecycle_status(home, manifest)
            self.assertEqual(state['state'], 'installed_with_existing_jobs', state)
            update = module.prepare_install(home, package, manifest, wiki, principal='replacement-fixture')
            state = module.lifecycle_status(home, manifest)
            self.assertEqual(state['current_revision'], manifest['revision'], state)
            self.assertEqual(state['operation_state'], 'prepared', state)
            self.assertEqual(state['install_id'], update['install_id'], state)
            settings = Path(prepared['audit_dir']) / 'settings.json'
            original_settings = settings.read_bytes()
            other = Path(temp) / 'same-id-other-root'
            (other / '.llm-wiki').mkdir(parents=True)
            (other / '.llm-wiki/project.json').write_bytes(b'{"id":"status-fixture"}')
            (other / 'wiki').mkdir()
            (other / 'wiki/index.md').write_bytes(b'# Different root\n')
            changed = json.loads(original_settings)
            changed['project_root'] = str(other)
            settings.write_bytes(json.dumps(changed).encode())
            with self.assertRaises(module.LifecycleRefused):
                module.lifecycle_status(home, manifest)
            settings.write_bytes(original_settings)
            location = home / 'state/wiki-automation/location.json'
            location.write_bytes(b'{not-json')
            with self.assertRaises((ValueError, module.LifecycleRefused)):
                module.lifecycle_status(home, manifest)

    def test_status_accepts_a_retired_role_whose_job_is_gone(self):
        """An installation made before a role was retired still lists it; its deleted job is the wanted end state.

        Why: after the Wiki Session Harvest job was deleted, every status read of the 2.13.2 installation
        refused ("Owned native jobs did not pass engine readback"), so the panel could not offer the update
        that retires the role. Only a missing job of a role the selected package retires is accepted.
        """
        module = self.lifecycle()
        package = Path(__file__).resolve().parents[1]
        manifest = json.loads((package / 'engine-release.json').read_bytes())
        retired = module.retired_roles(package)
        self.assertEqual(retired, ['session_harvest'])
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home, wiki = Path(temp) / 'home', Path(temp) / 'wiki'
            home.mkdir()
            (home / 'config.yaml').write_bytes(b'{}')
            (wiki / '.llm-wiki').mkdir(parents=True)
            (wiki / '.llm-wiki/project.json').write_bytes(b'{"id":"retired-fixture"}')
            (wiki / 'wiki').mkdir()
            (wiki / 'wiki/index.md').write_bytes(b'# Fixture\n')
            prepared = module.prepare_install(home, package, manifest, wiki, principal='owner-fixture')
            module.apply_install(home, package, manifest, prepared['install_id'], prepared['plan_digest'], principal='owner-fixture')
            record_path = home / 'state/wiki-automation/installations' / (prepared['install_id'] + '.json')
            record = json.loads(record_path.read_bytes())
            record['plan']['job_definitions']['session_harvest'] = {
                'name': 'Wiki Session Harvest', 'kind': 'agent', 'launcher': 'palantir_wiki_session_harvest.py',
                'default_schedule': '0 21 * * *'}
            record_path.write_bytes(json.dumps(record).encode())
            settings = Path(prepared['audit_dir']) / 'settings.json'
            original = json.loads(settings.read_bytes())

            def status(jobs, roles):
                settings.write_bytes(json.dumps({**original, 'jobs': {**original['jobs'], **jobs}}).encode())
                return module.lifecycle_status(home, manifest, roles)

            with self.assertRaisesRegex(module.LifecycleRefused, 'did not pass engine readback'):
                status({'session_harvest': 'deleted-job'}, ())
            self.assertEqual(status({'session_harvest': 'deleted-job'}, retired)['state'], 'installed_paused')
            with self.assertRaisesRegex(module.LifecycleRefused, 'did not pass engine readback'):
                status({'session_harvest': original['jobs']['autocommit']}, retired)
            with self.assertRaisesRegex(module.LifecycleRefused, 'did not pass engine readback'):
                status({'session_harvest': 'deleted-job', 'watchdog': 'deleted-job'}, retired)

    def legacy_home(self, temp):
        """The real pre-panel shape: three script jobs and an enabled agent harvest job with a pre-run script
        (a role retired in 2.13.3, which the installation removes)."""
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from cron.jobs import use_cron_store, create_job
        legacy = {'autocommit': ('Wiki Auto-Commit', 'palantir_wiki_autocommit.py', True),
            'ingest_watch': ('Wiki Ingest Watch', 'palantir_wiki_ingest_watch.py', True),
            'watchdog': ('Watch Dog', 'palantir_wiki_watchdog.py', True),
            'session_harvest': ('Wiki Session Harvest', 'palantir_wiki_session_harvest.py', False)}
        home, wiki, data = Path(temp) / 'home', Path(temp) / 'wiki', Path(temp) / 'legacy-data'
        home.mkdir()
        data.mkdir()
        (home / 'config.yaml').write_bytes(b'{}')
        (wiki / '.llm-wiki').mkdir(parents=True)
        (wiki / '.llm-wiki/project.json').write_bytes(b'{"id":"legacy-fixture"}')
        (wiki / 'wiki').mkdir()
        (wiki / 'wiki/index.md').write_bytes(b'# Fixture\n')
        location = home / 'state/wiki-automation/location.json'
        location.parent.mkdir(parents=True)
        location.write_bytes(json.dumps({'audit_dir': str(data), 'written_by': 'install.py'}).encode())
        token = set_hermes_home_override(home)
        try:
            with use_cron_store(home):
                mapping = {role: create_job(prompt=name + ' (earlier prompt).', schedule='0 9 * * *', name=name,
                    script=script, no_agent=script_only, deliver='local')['id']
                    for role, (name, script, script_only) in legacy.items()}
        finally:
            reset_hermes_home_override(token)
        (data / 'settings.json').write_bytes(json.dumps({'project_root': str(wiki), 'project_id': 'legacy-fixture',
            'audit_dir': str(data), 'hermes_home': str(home), 'jobs': mapping}).encode())
        return home, wiki, data, mapping

    def jobs_of(self, home):
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from cron.jobs import use_cron_store, list_jobs
        token = set_hermes_home_override(home)
        try:
            with use_cron_store(home):
                return {job['id']: job for job in list_jobs(include_disabled=True)}
        finally:
            reset_hermes_home_override(token)

    def test_pre_panel_engine_is_reported_then_adopted_only_by_the_exact_plan(self):
        module = self.lifecycle()
        package = Path(__file__).resolve().parents[1]
        manifest = json.loads((package / 'engine-release.json').read_bytes())
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home, wiki, data, mapping = self.legacy_home(temp)
            location = (home / 'state/wiki-automation/location.json').read_bytes()
            status = module.lifecycle_status(home, manifest)
            self.assertEqual((status['state'], status['current_revision']), ('existing_unverified', None), status)
            self.assertEqual((home / 'state/wiki-automation/location.json').read_bytes(), location)
            prepared = module.prepare_install(home, package, manifest, wiki, principal='legacy-fixture')
            self.assertEqual(prepared['audit_dir'], str(data))
            self.assertEqual({job['role']: job['disposition'] for job in prepared['jobs']},
                {'autocommit': 'adopt_existing', 'ingest_watch': 'adopt_existing', 'watchdog': 'adopt_existing',
                 'session_harvest': 'retire', 'harvest_night': 'create_paused'})
            self.assertEqual(module.lifecycle_status(home, manifest)['state'], 'existing_unverified')
            result = module.apply_install(home, package, manifest, prepared['install_id'], prepared['plan_digest'],
                principal='legacy-fixture')
            self.assertEqual(result['state'], 'installed_with_existing_jobs', result)
            status = module.lifecycle_status(home, manifest)
            self.assertEqual((status['state'], status['current_revision']),
                ('installed_with_existing_jobs', manifest['revision']), status)
            jobs = self.jobs_of(home)
            retired = mapping.pop('session_harvest')
            self.assertNotIn(retired, jobs, 'the retired drafting job was not removed')
            self.assertTrue(set(mapping.values()) <= set(jobs))
            self.assertEqual({role: jobs[job_id]['enabled'] for role, job_id in mapping.items()},
                {'autocommit': True, 'ingest_watch': True, 'watchdog': True})
            self.assertNotIn('session_harvest', json.loads((data / 'settings.json').read_bytes())['jobs'])
            # The new nightly harvest arrives as a paused, script-only job; the owner switches it on.
            new = [job for job_id, job in jobs.items() if job_id not in mapping.values()]
            self.assertEqual([(j['name'], j['enabled'], bool(j.get('no_agent')), j['script']) for j in new],
                             [('Wiki Harvest', False, True, 'palantir_wiki_harvest_night.py')])

    def test_stale_legacy_preview_is_not_stranded_in_recovery(self):
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from cron.jobs import use_cron_store, update_job
        module = self.lifecycle()
        package = Path(__file__).resolve().parents[1]
        manifest = json.loads((package / 'engine-release.json').read_bytes())
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home, wiki, data, mapping = self.legacy_home(temp)
            prepared = module.prepare_install(home, package, manifest, wiki, principal='legacy-fixture')
            token = set_hermes_home_override(home)
            try:
                with use_cron_store(home):
                    update_job(mapping['watchdog'], {'schedule': '15 8 * * *'})
            finally:
                reset_hermes_home_override(token)
            changed = self.jobs_of(home)
            with self.assertRaises(module.LifecyclePlanStale):
                module.apply_install(home, package, manifest, prepared['install_id'], prepared['plan_digest'],
                    principal='legacy-fixture')
            self.assertEqual(self.jobs_of(home), changed)
            record = json.loads((home / 'state/wiki-automation/installations' / (prepared['install_id'] + '.json')).read_bytes())
            self.assertEqual(record['state'], 'stale')
            self.assertEqual(module.lifecycle_status(home, manifest)['state'], 'existing_unverified')
            again = module.prepare_install(home, package, manifest, wiki, principal='legacy-fixture')
            self.assertNotEqual(again['plan_digest'], prepared['plan_digest'])
            result = module.apply_install(home, package, manifest, again['install_id'], again['plan_digest'],
                principal='legacy-fixture')
            self.assertEqual(result['state'], 'installed_with_existing_jobs', result)
            self.assertEqual(self.jobs_of(home)[mapping['watchdog']]['schedule'], changed[mapping['watchdog']]['schedule'])

    def test_fresh_schema2_install_exposes_native_jobs_from_selected_code(self):
        module = self.lifecycle()
        package = Path(__file__).resolve().parents[1]
        manifest = json.loads((package / 'engine-release.json').read_bytes())
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from cron.jobs import use_cron_store
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home, wiki = Path(temp) / 'home', Path(temp) / 'wiki'
            home.mkdir()
            (home / 'config.yaml').write_bytes(b'{}')
            (wiki / '.llm-wiki').mkdir(parents=True)
            (wiki / '.llm-wiki/project.json').write_bytes(b'{"id":"jobs-fixture"}')
            (wiki / 'wiki').mkdir()
            (wiki / 'wiki/index.md').write_bytes(b'# Fixture\n')
            prepared = module.prepare_install(home, package, manifest, wiki, principal='fixture-session')
            module.apply_install(home, package, manifest, prepared['install_id'], prepared['plan_digest'], principal='fixture-session')
            spec = importlib.util.spec_from_file_location('installed_jobs_fixture', package / 'dashboard/plugin_api.py')
            api = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = api
            spec.loader.exec_module(api)
            token = set_hermes_home_override(home)
            try:
                with patch.dict(os.environ, {'WIKI_ENGINE_TEST_DIR': ''}), use_cron_store(home):
                    jobs = api.jobs_view_route()
                    self.assertTrue(jobs['ok'], jobs)
                    self.assertEqual(len(jobs['roles']), 4)  # three upkeep jobs + Wiki Harvest (Session Harvest retired in 2.13.3)
                    self.assertTrue(all(job['live'] and job['state'] == 'paused' for job in jobs['roles']))
                    self.assertEqual({job['id'] for job in jobs['roles']},
                        {job['id'] for job in json.loads((home / 'cron/jobs.json').read_bytes())['jobs']})
            finally:
                reset_hermes_home_override(token)

    def test_actual_project_controls_confirm_against_disposable_backend(self):
        import socket
        import threading
        import time
        import uvicorn
        from fastapi import FastAPI
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from hermes_cli import web_server
        package = Path(__file__).resolve().parents[1]
        module = self.lifecycle()
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home, wiki = Path(temp) / 'home', Path(temp) / 'wiki'
            home.mkdir()
            (home / 'config.yaml').write_bytes(b'{}')
            (wiki / '.llm-wiki').mkdir(parents=True)
            (wiki / '.llm-wiki/project.json').write_bytes(b'{"id":"ui-api-fixture"}')
            (wiki / 'wiki').mkdir()
            (wiki / 'wiki/index.md').write_bytes(b'# Fixture\n')
            app = FastAPI()
            app.state.auth_required = False
            @app.middleware('http')
            async def profile_scope(request, call_next):
                token = set_hermes_home_override(home)
                try:
                    return await call_next(request)
                finally:
                    reset_hermes_home_override(token)
            from test_install_recovery_http import current_source_test_package
            test_package, test_manifest = current_source_test_package(Path(temp))
            app.include_router(module.make_router(lambda: test_package,
                lambda: test_manifest), prefix='/api/plugins/wiki-automation/engine')
            listener = socket.socket()
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
            server = uvicorn.Server(uvicorn.Config(app, log_level='error', ws='none'))
            thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
            with patch.object(web_server, '_SESSION_TOKEN', 'installation-e2e-fixture'):
                thread.start()
                try:
                    deadline = time.monotonic() + 10
                    while not server.started and thread.is_alive() and time.monotonic() < deadline:
                        time.sleep(.01)
                    self.assertTrue(server.started)
                    env = {**os.environ, 'WIKI_LIFECYCLE_E2E': '1',
                        'HERMES_AGENT_DIR': os.environ['PYTHONPATH'], 'WIKI_HOST_HARNESS_DIR': temp,
                        'WIKI_LIFECYCLE_URL': 'http://127.0.0.1:' + str(port),
                        'WIKI_LIFECYCLE_ROOT': str(wiki).replace('\\', '/')}
                    result = __import__('subprocess').run(['node', 'render_check.mjs'], cwd=package / 'tests',
                        env=env, capture_output=True, text=True, timeout=45)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertTrue((home / 'state/wiki-automation/location.json').is_file())
                    jobs = json.loads((home / 'cron/jobs.json').read_bytes())['jobs']
                    self.assertEqual(len(jobs), 4)  # three upkeep jobs + Wiki Harvest (Session Harvest retired in 2.13.3)
                    self.assertTrue(all(job['enabled'] is False for job in jobs))
                    print(result.stdout.strip())
                    from cron.jobs import use_cron_store, update_job
                    token = set_hermes_home_override(home)
                    try:
                        with use_cron_store(home):
                            update_job(jobs[0]['id'], {'enabled': True, 'state': 'scheduled', 'schedule': '20 7 * * *'})
                    finally:
                        reset_hermes_home_override(token)
                    update = __import__('subprocess').run(['node', 'render_check.mjs'], cwd=package / 'tests',
                        env={**env, 'WIKI_LIFECYCLE_EXPECTED_STATE': 'installed_with_existing_jobs'},
                        capture_output=True, text=True, timeout=45)
                    self.assertEqual(update.returncode, 0, update.stdout + update.stderr)
                    actual_jobs = json.loads((home / 'cron/jobs.json').read_bytes())['jobs']
                    self.assertEqual(len(actual_jobs), 4)  # three upkeep jobs + Wiki Harvest (Session Harvest retired in 2.13.3)
                    self.assertTrue(next(job for job in actual_jobs if job['id'] == jobs[0]['id'])['enabled'])
                    print(update.stdout.strip())
                finally:
                    server.should_exit = True
                    thread.join(5)
                    listener.close()

    def test_real_process_death_recovers_the_original_confirmed_plan(self):
        module = self.lifecycle()
        self.assertTrue(callable(getattr(module, '_checkpoint', None)), 'Missing lifecycle recovery checkpoints')
        package = Path(__file__).resolve().parents[1]
        manifest = json.loads((package / 'engine-release.json').read_bytes())
        phases = ['applying_recorded', 'engine_applied', 'launcher_verified', 'installed_recorded']
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            for phase in phases:
                with self.subTest(phase=phase):
                    root = Path(temp) / phase
                    home, wiki = root / 'profile', root / 'wiki'
                    home.mkdir(parents=True)
                    (home / 'config.yaml').write_bytes(b'{}')
                    (wiki / '.llm-wiki').mkdir(parents=True)
                    (wiki / '.llm-wiki/project.json').write_bytes(b'{"id":"fixture"}')
                    (wiki / 'wiki').mkdir()
                    (wiki / 'wiki/index.md').write_bytes(b'# Fixture\n')
                    prepared = module.prepare_install(home, package, manifest, wiki, principal='owner-session')
                    worker = package / 'tests/lifecycle_apply_worker.py'
                    result = __import__('subprocess').run([sys.executable, '-B', str(worker), str(home),
                        str(package), prepared['install_id'], prepared['plan_digest'], phase], capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 91, result.stderr)
                    recovered = module.apply_install(home, package, manifest, prepared['install_id'],
                        prepared['plan_digest'], principal='owner-session')
                    self.assertEqual(recovered['state'], 'installed_paused')
                    jobs = json.loads((home / 'cron/jobs.json').read_bytes())['jobs']
                    self.assertEqual(len(jobs), 4)  # three upkeep jobs + Wiki Harvest (Session Harvest retired in 2.13.3)
                    self.assertTrue(all(job['enabled'] is False for job in jobs))
            print('LIFECYCLE_INTERRUPTION_CASES recovered=' + str(len(phases)))

    def test_concurrent_process_lock_refuses_second_installer(self):
        module = self.lifecycle()
        self.assertTrue(callable(getattr(module, 'installation_lock', None)), 'Missing cross-process installation lock')
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            worker = ('import importlib.util,sys; from pathlib import Path; '
                's=importlib.util.spec_from_file_location("lock_worker",sys.argv[1]); '
                'm=importlib.util.module_from_spec(s); s.loader.exec_module(m); '
                'lock=m.installation_lock(Path(sys.argv[2])); lock.__enter__()')
            with module.installation_lock(home):
                result = __import__('subprocess').run([sys.executable, '-B', '-c', worker,
                    str(Path(__file__).resolve().parents[1] / 'dashboard/engine_lifecycle.py'), str(home)],
                    capture_output=True, text=True, timeout=15)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Another installation is in progress', result.stderr)
            with module.installation_lock(home):
                self.assertTrue((home / 'state/wiki-automation/lifecycle.lock').is_file())

    def test_unified_plugin_mounts_installation_routes_without_engine(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from hermes_cli import web_server
        source = Path(__file__).resolve().parents[1] / 'dashboard/plugin_api.py'
        spec = importlib.util.spec_from_file_location('isolated_lifecycle_plugin_api', source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.assertIn('/engine/status', {route.path for route in module.router.routes})
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            (home / 'config.yaml').write_bytes(b'{}')
            app = FastAPI()
            app.state.auth_required = False
            app.include_router(module.router)
            token = set_hermes_home_override(home)
            try:
                with patch.object(web_server, '_SESSION_TOKEN', 'installation-session-fixture'):
                    reply = TestClient(app).get('/engine/status', headers={'X-Hermes-Session-Token': 'installation-session-fixture'})
                    self.assertEqual(reply.status_code, 200, reply.text)
                    self.assertEqual(reply.json()['state'], 'missing')
                    self.assertFalse((home / 'cron/jobs.json').exists())
                    self.assertFalse((home / 'state/wiki-automation/location.json').exists())
            finally:
                reset_hermes_home_override(token)

    def test_application_routes_require_session_and_exact_confirmation(self):
        module = self.lifecycle()
        self.assertTrue(callable(getattr(module, 'make_router', None)), 'Missing application-scoped installation routes')
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from hermes_cli import web_server
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            root = Path(temp)
            (root / 'config.yaml').write_bytes(b'{}')
            app = FastAPI()
            app.state.auth_required = False
            app.include_router(module.make_router(lambda: root, lambda: {}), prefix='/engine')
            client = TestClient(app)
            token = set_hermes_home_override(root)
            try:
                with patch.object(web_server, '_SESSION_TOKEN', 'installation-session-fixture'):
                    self.assertEqual(client.post('/engine/prepare', json={'project_root': str(root)}).status_code, 401)
                    headers = {'X-Hermes-Session-Token': 'installation-session-fixture'}
                    with patch.object(module, 'prepare_install', return_value={'ok': True, 'state': 'prepared'}) as prepare:
                        valid = client.post('/engine/prepare', headers=headers, json={'project_root': str(root)})
                        self.assertEqual(valid.status_code, 200, valid.text)
                        self.assertTrue(valid.json()['ok'])
                        self.assertEqual(prepare.call_args.args[0], root)
                        self.assertEqual(len(prepare.call_args.kwargs['principal']), 64)
                    with patch.object(module, 'apply_install') as apply:
                        self.assertEqual(client.post('/engine/apply', headers=headers,
                            json={'install_id': 'a' * 64, 'plan_digest': 'b' * 64, 'confirm': False}).status_code, 400)
                        self.assertEqual(client.post('/engine/apply', headers=headers,
                            json={'install_id': 'a' * 64, 'plan_digest': 'b' * 64, 'confirm': True, 'home': str(root)}).status_code, 400)
                        apply.assert_not_called()
            finally:
                reset_hermes_home_override(token)

    def test_real_prepare_confirm_and_repeat_use_bundled_engine(self):
        module = self.lifecycle()
        self.assertTrue(callable(getattr(module, 'prepare_install', None)), 'Missing engine-owned preparation')
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            root = Path(temp)
            home, wiki = root / 'profile', root / 'wiki'
            home.mkdir()
            (home / 'config.yaml').write_bytes(b'{}')
            (wiki / '.llm-wiki').mkdir(parents=True)
            (wiki / '.llm-wiki/project.json').write_bytes(b'{"id":"fixture"}')
            (wiki / 'wiki').mkdir()
            (wiki / 'wiki/index.md').write_bytes(b'# Fixture\n')
            from test_install_recovery_http import current_source_test_package
            test_package, manifest = current_source_test_package(root)
            prepared = module.prepare_install(home, test_package, manifest, wiki, principal='owner-session')
            self.assertEqual(prepared['state'], 'prepared')
            self.assertFalse((home / 'cron/jobs.json').exists())
            self.assertFalse((home / 'state/wiki-automation/location.json').exists())
            with self.assertRaises(module.LifecycleRefused):
                module.apply_install(home, test_package, manifest, prepared['install_id'], prepared['plan_digest'], principal='foreign-session')
            result = module.apply_install(home, test_package, manifest, prepared['install_id'], prepared['plan_digest'], principal='owner-session')
            self.assertEqual(result['state'], 'installed_paused')
            self.assertEqual(module.apply_install(home, test_package, manifest, prepared['install_id'], prepared['plan_digest'], principal='owner-session'), result)
            record = json.loads((home / 'state/wiki-automation/location.json').read_bytes())
            self.assertNotEqual(record['engine_dir'], record['audit_dir'])
            self.assertEqual(len(json.loads((home / 'cron/jobs.json').read_bytes())['jobs']), 4)  # three upkeep jobs + Wiki Harvest (Session Harvest retired in 2.13.3)
            self.assertTrue(all(job['enabled'] is False for job in json.loads((home / 'cron/jobs.json').read_bytes())['jobs']))
            self.assertEqual(module.lifecycle_status(home, manifest)['state'], 'installed_paused')
            from hermes_constants import set_hermes_home_override, reset_hermes_home_override
            from cron.jobs import use_cron_store, update_job
            token = set_hermes_home_override(home)
            try:
                with use_cron_store(home):
                    job = json.loads((home / 'cron/jobs.json').read_bytes())['jobs'][0]
                    update_job(job['id'], {'enabled': True, 'state': 'scheduled', 'schedule': '20 7 * * *'})
            finally:
                reset_hermes_home_override(token)
            update = module.prepare_install(home, test_package, manifest, wiki, principal='owner-session')
            updated = module.apply_install(home, test_package, manifest, update['install_id'], update['plan_digest'], principal='owner-session')
            self.assertEqual(updated['state'], 'installed_with_existing_jobs')
            live_jobs = json.loads((home / 'cron/jobs.json').read_bytes())['jobs']
            self.assertEqual(len(live_jobs), 4)  # three upkeep jobs + Wiki Harvest (Session Harvest retired in 2.13.3)
            self.assertTrue(next(item for item in live_jobs if item['id'] == job['id'])['enabled'])

    def test_incompatible_requirements_and_wrong_revision_never_stage(self):
        module = self.lifecycle()
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            root = Path(temp)
            baseline = self.archive(root, [('install.py', '# No execution\n')])
            for changed in ({'revision': 'b' * 40}, {'schema': 1}, {'artifact': '../engine'}, {'python_min': [99, 0]},
                    {'workflow_schema': {'min': 2, 'max': 9}}):
                with self.subTest(changed=changed):
                    with self.assertRaises(module.LifecycleRefused):
                        module.stage_release(root / 'home', root, {**baseline, **changed})
                    self.assertFalse((root / 'home/state/wiki-automation/releases').exists())

    def test_pinned_stage_repeat_and_dirty_release_refusal(self):
        module = self.lifecycle()
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            root = Path(temp)
            manifest = self.archive(root, [('install.py', '# Verified bytes\n')])
            staged = module.stage_release(root / 'home', root, manifest)
            self.assertEqual(module.stage_release(root / 'home', root, manifest), staged)
            (staged / 'install.py').write_bytes(b'# Owner edit\n')
            with self.assertRaises(module.LifecycleRefused):
                module.stage_release(root / 'home', root, manifest)
            self.assertEqual((staged / 'install.py').read_bytes(), b'# Owner edit\n')
            self.assertFalse((root / 'home/state/wiki-automation/location.json').exists())

    def test_archive_names_are_not_matched_against_unrelated_home_folders(self):
        # A live Hermes home held a user folder named "Docs" while the engine ships "docs/";
        # the engine is copied under releases/, so the home's own spelling must not refuse it.
        module = self.lifecycle()
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            root = Path(temp)
            (root / 'home/Docs').mkdir(parents=True)
            manifest = self.archive(root, [('install.py', '# Verified bytes\n'), ('docs/guide.md', '# Guide\n')])
            staged = module.stage_release(root / 'home', root, manifest)
            self.assertEqual((staged / 'docs/guide.md').read_bytes(), b'# Guide\n')
            self.assertEqual(sorted(p.name for p in (root / 'home').iterdir()), ['Docs', 'state'])

    def test_archive_escape_link_collision_and_bomb_are_refused(self):
        module = self.lifecycle()

        def hard_link(folder):
            os.link(folder / 'install.py', folder / 'twin.py')

        def soft_link(folder):
            os.symlink(folder / 'install.py', folder / 'linked.py')

        def case_twin(folder):
            (folder / 'A.py').write_bytes(b'x')
            (folder / 'a.py').write_bytes(b'y')
            if len(list(folder.iterdir())) < 3:
                raise unittest.SkipTest('case-insensitive file system')

        cases = [('artifact', {'artifact': '../escape'}), ('artifact', {'artifact': 'C:/drive'}),
            ('artifact', {'artifact': 'sub\\escape'}), ('artifact', {'artifact': 'CON'}),
            ('extra', hard_link), ('extra', soft_link), ('extra', case_twin),
            ('size', [('large.py', 'x' * 1025)]), ('count', [(str(n) + '.py', 'x') for n in range(5)])]
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            for number, (kind, change) in enumerate(cases):
                with self.subTest(case=number, kind=kind):
                    root = Path(temp) / str(number)
                    root.mkdir()
                    entries = change if kind in ('size', 'count') else [('install.py', '# Verified bytes\n')]
                    manifest = self.archive(root, entries)
                    if kind == 'artifact':
                        manifest.update(change)
                    elif kind == 'extra':
                        try:
                            change(root / 'engine')
                        except unittest.SkipTest:
                            continue
                        except (OSError, NotImplementedError):
                            continue  # this machine cannot create the link; the other runner covers it
                    with patch.object(module, 'MAX_EXPANDED', 1024, create=True), \
                            patch.object(module, 'MAX_ENTRIES', 3, create=True):
                        with self.assertRaises(module.LifecycleRefused) as refused:
                            module.stage_release(root / 'home', root, manifest)
                    # Refused by the rule under test, not by the digest mismatch the change also causes.
                    self.assertNotIn('digest', str(refused.exception))
                    self.assertFalse((root / 'home/state/wiki-automation/releases').exists())

    def test_wrong_digest_never_extracts_or_executes(self):
        module = self.lifecycle()
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            root = Path(temp)
            manifest = self.archive(root, [('install.py', 'raise SystemExit("must not run")')])
            manifest['sha256'] = '0' * 64
            with patch.object(module.subprocess, 'run') as run:
                with self.assertRaises(module.LifecycleRefused):
                    module.stage_release(root / 'home', root, manifest)
                run.assert_not_called()
            self.assertFalse((root / 'home/state/wiki-automation/releases').exists())


if __name__ == '__main__':
    unittest.main()
