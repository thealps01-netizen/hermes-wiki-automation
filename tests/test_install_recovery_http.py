"""React -> real host SDK REST -> loopback HTTP -> lifecycle -> pinned release bundle."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import unittest
from dataclasses import replace
from unittest.mock import patch
import uvicorn
from hermes_cli import web_server
import test_install_session_recovery as native_fixture

PACKAGE = Path(__file__).resolve().parents[1]


def lifecycle_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location('fixture_engine_lifecycle', PACKAGE / 'dashboard/engine_lifecycle.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def current_source_test_package(root):
    """Content-addressed TEST snapshot, explicitly not a released Git revision."""
    source = Path(os.environ['WIKI_ENGINE_TEST_DIR'])
    package = Path(root) / 'TEST-current-source-package'
    package.mkdir()
    payloads = {p.relative_to(source).as_posix(): p.read_bytes()
        for p in sorted(source.rglob('*')) if p.is_file()
        and not any(part in ('.git', '__pycache__', 'node_modules', '.pytest_cache', '.venv', 'venv')
                    for part in p.relative_to(source).parts)}
    hashes = {name: hashlib.sha256(content).hexdigest() for name, content in payloads.items()}
    for name, content in payloads.items():
        target = package / 'engine' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    digest = lifecycle_module().release_digest(payloads)
    identifier = digest[:40]
    manifest = {'schema': 2, 'artifact': 'engine', 'revision': identifier, 'sha256': digest,
        'workflow_schema': {'min': 1, 'max': 1}, 'python_min': [3, 11]}
    (package / 'engine-release.json').write_bytes(json.dumps(manifest).encode())
    (package / 'TEST-SNAPSHOT-NOT-A-RELEASE.json').write_bytes(json.dumps({
        'test_only': True, 'git_commit': False, 'production_release': False,
        'source_worktree': str(source), 'content_identifier': identifier, 'files': hashes}).encode())
    print('TEST_SOURCE_BUNDLE', json.dumps({'content_identifier': identifier, 'git_commit': False,
        'production_release': False, 'sha256': manifest['sha256']}))
    return package, manifest


class InstallationRecoveryHTTPTests(unittest.TestCase):
    # Reuse the native disposable profile/auth/death fixture, not its inherited test suite.
    post = native_fixture.InstallationRecoveryTests.post
    prepare = native_fixture.InstallationRecoveryTests.prepare
    crash = native_fixture.InstallationRecoveryTests.crash
    fresh_session = native_fixture.InstallationRecoveryTests.fresh_session
    remote = native_fixture.InstallationRecoveryTests.remote

    def setUp(self):
        native_fixture.InstallationRecoveryTests.setUp(self)
        self.package = PACKAGE
        self.manifest = json.loads((PACKAGE / 'engine-release.json').read_bytes())
        self.app.include_router(self.module.make_router(lambda: self.package, lambda: self.manifest),
            prefix='/api/plugins/wiki-automation/engine')
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        self.url = 'http://127.0.0.1:' + str(listener.getsockname()[1])
        server = uvicorn.Server(uvicorn.Config(self.app, log_level='error', ws='none'))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        thread.start()
        def stop():
            server.should_exit = True
            thread.join(10)
            listener.close()
            self.assertFalse(thread.is_alive(), 'Disposable HTTP server leaked')
        self.addCleanup(stop)
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(server.started)

    def render(self, **environment):
        core = Path(os.environ['PYTHONPATH'])
        env = {**os.environ, 'WIKI_LIFECYCLE_E2E': '1', 'HERMES_AGENT_DIR': str(core),
            'WIKI_HOST_HARNESS_DIR': str(self.root), 'WIKI_LIFECYCLE_URL': self.url,
            'WIKI_HTTP_CREDENTIAL': web_server._SESSION_TOKEN,
            'WIKI_LIFECYCLE_ROOT': str(self.wiki).replace('\\', '/'), **environment}
        result = subprocess.run(['node', 'render_check.mjs'], cwd=PACKAGE / 'tests',
            env=env, capture_output=True, text=True, timeout=60)
        print(result.stdout.strip())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('REAL_HOST_INITIAL_SCOPE {"connectionId":null,"profile":"default","cwd":""}', result.stdout)
        http_lines = '\n'.join(line for line in result.stdout.splitlines()
            if line.startswith(('REAL_RECOVERY_UI_HTTP', 'REAL_LIFECYCLE_UI_API')))
        self.assertNotIn('"connectionId":"local"', http_lines,
            'Native untagged connection must not be guessed/pinned as local')
        return result

    def test_first_install_actual_host_initial_detached_scope_is_actionable(self):
        self.render()
        jobs = json.loads((self.home / 'cron/jobs.json').read_bytes())['jobs']
        self.assertEqual(len(jobs), 4)
        self.assertTrue(all(job['enabled'] is False for job in jobs))
        self.assertEqual((self.wiki / 'wiki/index.md').read_bytes(), b'# Owner content\n')
        self.assertFalse((self.wiki / '.llm-wiki/owner.json').exists())

    def test_approved_process_death_new_session_recovery_actual_http_same_admin_once(self):
        prepared = self.prepare()
        record = self.crash(prepared, 'engine_applied')
        original = json.loads(record.read_bytes())
        jobs = (self.home / 'cron/jobs.json').read_bytes()
        content = {p.relative_to(self.wiki).as_posix(): p.read_bytes() for p in self.wiki.rglob('*') if p.is_file()}
        self.fresh_session()
        result = self.render(WIKI_RECOVERY_HTTP='1')
        self.assertIn('REAL_RECOVERY_UI_HTTP', result.stdout)
        self.assertIn('"http":409', result.stdout)
        updated = json.loads(record.read_bytes())
        for key in ('principal', 'original_administrator', 'plan', 'install_id', 'manifest'):
            self.assertEqual(updated[key], original[key])
        self.assertEqual((self.home / 'cron/jobs.json').read_bytes(), jobs)
        self.assertEqual(content, {p.relative_to(self.wiki).as_posix(): p.read_bytes() for p in self.wiki.rglob('*') if p.is_file()})

    def test_verified_remote_different_admin_refused_then_same_admin_http_resume(self):
        import httpx
        provider, session = self.remote()
        prepared = self.prepare()
        record = self.crash(prepared, 'engine_applied')
        original = record.read_bytes()
        web_server._SESSION_TOKEN = 'fresh-http-server-incarnation'
        foreign = replace(session, user_id='different-admin', access_token='foreign-http-admin')
        provider.sessions[foreign.access_token] = foreign
        with httpx.Client(base_url=self.url) as client:
            refused = client.post('/api/plugins/wiki-automation/engine/recovery/prepare',
                headers={'Authorization': 'Bearer ' + foreign.access_token},
                json={'install_id': prepared['install_id']})
            self.assertEqual(refused.status_code, 409, refused.text)
            self.assertEqual(record.read_bytes(), original)
        refreshed = replace(session, access_token='fresh-http-same-admin')
        provider.sessions[refreshed.access_token] = refreshed
        # Explicit remote scope is preserved by the real host REST door, never replaced with local.
        result = self.render(WIKI_RECOVERY_HTTP='1', WIKI_HTTP_AUTH='bearer',
            WIKI_HTTP_CREDENTIAL=refreshed.access_token,
            WIKI_HOST_SCOPE=json.dumps({'connectionId': 'fixture-remote', 'profile': 'default', 'cwd': ''}))
        self.assertIn('"connectionId":"fixture-remote"', result.stdout)
        jobs = json.loads((self.home / 'cron/jobs.json').read_bytes())['jobs']
        self.assertEqual(len(jobs), 4)
        self.assertTrue(all(job['enabled'] is False for job in jobs))
        print('REAL_HTTP_DIFFERENT_ADMIN refused=409 SAME_ADMIN resumed=200 REPLAY refused=409')


if __name__ == '__main__':
    unittest.main()
