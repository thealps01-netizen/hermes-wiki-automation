"""The broker trusts host-authenticated owner sessions, not body labels or callbacks."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


class OwnerBrokerTests(unittest.TestCase):
    def test_http_authentication_and_exact_review_binding(self):
        source = Path(__file__).resolve().parents[1] / 'dashboard/owner_broker.py'
        self.assertTrue(source.exists(), 'Missing authenticated owner broker')
        spec = importlib.util.spec_from_file_location('isolated_owner_broker', source)
        broker = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = broker
        spec.loader.exec_module(broker)
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            (home / 'config.yaml').write_text('{}')
            token = set_hermes_home_override(home)
            try:
                from hermes_cli import web_server
                engine = Path(os.environ['WIKI_ENGINE_TEST_DIR'])
                data, wiki = home / 'data', home / 'wiki'
                (wiki / '.llm-wiki').mkdir(parents=True)
                (wiki / '.llm-wiki/project.json').write_text('{"id":"fixture"}')
                (wiki / 'raw/sources').mkdir(parents=True)
                (wiki / 'raw/evidence').mkdir(parents=True)
                candidate = data / 'inbox/run/candidates/draft'
                candidate.mkdir(parents=True)
                (candidate / 'candidate.json').write_text(json.dumps({'kind': 'new', 'target': '2026-10-06-fixture.md', 'summary': 'Fixture', 'why': 'Owner choice', 'evidence_ids': []}))
                (candidate / 'source.md').write_bytes(b'# Fixture\n\n## Decisions\n\n**1. Fixture.**\nEvidence: none (owner-directed).\n')
                settings = home / 'engine-settings.json'
                settings.write_text(json.dumps({'hermes_home': str(home), 'project_root': str(wiki), 'project_id': 'fixture', 'audit_dir': str(data), 'owner_approval_enabled': True}))
                def run(operation, payload):
                    proc = subprocess.run([sys.executable, '-B', str(engine / 'owner_decisions.py'), operation,
                                           '--home', str(home), '--settings', str(settings)],
                                          input=json.dumps(payload), capture_output=True, text=True, timeout=15)
                    self.assertIn(proc.returncode, (0, 1), proc.stdout + proc.stderr)
                    return json.loads(proc.stdout)
                run('initialize', {})
                shown = subprocess.run([sys.executable, '-B', str(engine / 'wiki_candidates.py'), 'show', 'run/draft', '--json'],
                    env={**os.environ, 'LLMWIKI_SETTINGS': str(settings)}, capture_output=True, text=True, timeout=15)
                self.assertEqual(shown.returncode, 0, shown.stdout + shown.stderr)
                digest = json.loads(shown.stdout)['review_digest']
                app = FastAPI()
                app.state.auth_required = False
                binding = [None]
                app.include_router(broker.make_router(run, lambda: True, lambda: binding[0]), prefix='/owner')
                client = TestClient(app)
                auth_patch = patch.object(web_server, '_SESSION_TOKEN', 'isolated-owner-session-fixture')
                auth_patch.start()
                self.addCleanup(auth_patch.stop)
                body = {'ref': 'run/draft', 'review_digest': digest, 'confirm': False}
                self.assertEqual(client.post('/owner/decision', json={**body, 'actor': 'owner'}).status_code, 401)
                headers = {'X-Hermes-Session-Token': 'isolated-owner-session-fixture'}
                self.assertEqual(client.post('/owner/decision', headers=headers, json=body).status_code, 403)
                binding[0] = {'mode': 'local_owner', 'home': str(home)}
                prepared = client.post('/owner/decision', headers=headers, json=body)
                self.assertEqual(prepared.status_code, 200, prepared.text)
                pending = prepared.json()
                self.assertTrue(pending['needs_confirm'])
                self.assertFalse(pending['ok'])
                self.assertNotIn('receipt', pending)
                request_id = pending['request_id']
                self.assertEqual(client.post('/owner/decision', json={**body, 'confirm': True, 'request_id': request_id}).status_code, 401)
                bad_fields = client.post('/owner/decision', headers=headers, json={**body, 'confirm': 'true'})
                self.assertEqual(bad_fields.status_code, 400)
                original = (candidate / 'source.md').read_bytes()
                (candidate / 'source.md').write_bytes(original + b'\nModified after review\n')
                stale = client.post('/owner/decision', headers=headers, json={**body, 'confirm': True, 'request_id': request_id})
                self.assertFalse(stale.json().get('authorized', False))
                self.assertIn('stale', stale.json()['reason'])
                (candidate / 'source.md').write_bytes(original)
                from starlette.requests import Request
                original_session = Request({'type': 'http', 'headers': [(b'x-hermes-session-token', b'isolated-owner-session-fixture')], 'app': app})
                first_principal = broker.owner_principal(original_session, binding[0])
                with patch.object(web_server, '_SESSION_TOKEN', 'isolated-restarted-owner-session-fixture'):
                    fresh_session = Request({'type': 'http', 'headers': [(b'x-hermes-session-token', b'isolated-restarted-owner-session-fixture')], 'app': app})
                    self.assertNotEqual(first_principal, broker.owner_principal(fresh_session, binding[0]),
                        'Characterization: a replaced local session does not retain the earlier principal')
                    replaced = client.post('/owner/decision', headers={'X-Hermes-Session-Token': 'isolated-restarted-owner-session-fixture'},
                        json={**body, 'confirm': True, 'request_id': request_id})
                    self.assertFalse(replaced.json().get('authorized', False))
                    self.assertIn('wrong-session', replaced.json()['reason'])
                service_request = Request({'type': 'http', 'headers': [(b'x-hermes-session-token', b'isolated-owner-session-fixture')], 'app': app})
                service_request.state.token_authenticated = True
                from fastapi import HTTPException
                with self.assertRaises(HTTPException) as service_denied:
                    broker.owner_principal(service_request)
                self.assertEqual(service_denied.exception.status_code, 403)
                from cron.execution_identity import enter_cron_execution, exit_cron_execution
                cron_token = enter_cron_execution({'id': 'fixture-draft-job'}, 'fixture-execution', {})
                try:
                    forged_request = Request({'type': 'http', 'headers': [(b'x-hermes-session-token', b'isolated-owner-session-fixture')], 'app': app})
                    from fastapi import HTTPException
                    with self.assertRaises(HTTPException) as denied:
                        broker.owner_principal(forged_request)
                    self.assertEqual(denied.exception.status_code, 403)
                finally:
                    exit_cron_execution(cron_token)
                confirmed = client.post('/owner/decision', headers=headers,
                    json={**body, 'confirm': True, 'request_id': request_id})
                self.assertEqual(confirmed.status_code, 200, confirmed.text)
                self.assertTrue(confirmed.json()['authorized'])
                self.assertFalse(confirmed.json()['ok'])
                self.assertNotIn('receipt', confirmed.json())
                self.assertFalse((wiki / 'raw/sources/2026-10-06-fixture.md').exists())
                replay = client.post('/owner/decision', headers=headers,
                    json={**body, 'confirm': True, 'request_id': request_id})
                self.assertFalse(replay.json().get('authorized', False))
                stage = home / 'engine'
                stage.mkdir()
                for code in engine.glob('*.py'):
                    (stage / code.name).write_bytes(code.read_bytes())
                raw_settings = json.loads(settings.read_bytes())
                raw_settings['owner_approval_owner'] = binding[0]
                (stage / 'settings.json').write_text(json.dumps(raw_settings))
                api_spec = importlib.util.spec_from_file_location('mounted_wiki_owner_fixture', source.parent / 'plugin_api.py')
                api = importlib.util.module_from_spec(api_spec)
                sys.modules[api_spec.name] = api
                api_spec.loader.exec_module(api)
                mounted = FastAPI()
                mounted.state.auth_required = False
                mounted.include_router(api.router, prefix='/api/plugins/wiki-automation')
                mounted_client = TestClient(mounted)
                path = '/api/plugins/wiki-automation/owner/decision'
                with patch.dict(os.environ, {'LLMWIKI_AUDIT_DIR': str(stage)}):
                    self.assertEqual(mounted_client.post(path, json=body).status_code, 401)
                    with patch.object(api, '_owner_ready', return_value=True):
                        prepared_live_facade = mounted_client.post(path, json=body, headers=headers)
                        self.assertEqual(prepared_live_facade.status_code, 200, prepared_live_facade.text)
                        self.assertTrue(prepared_live_facade.json()['needs_confirm'])
                        confirmed_live_facade = mounted_client.post(path, headers=headers,
                            json={**body, 'confirm': True, 'request_id': prepared_live_facade.json()['request_id']})
                        self.assertTrue(confirmed_live_facade.json()['authorized'])
                        self.assertFalse(confirmed_live_facade.json()['ok'])
                    with patch.object(api, '_candidates_run', side_effect=AssertionError('Legacy confirmation must not invoke an unbound engine command')):
                        refused_legacy = mounted_client.post('/api/plugins/wiki-automation/candidates/act', headers=headers,
                            json={'ref': 'run/draft', 'action': 'approve', 'confirm': True, 'actor': 'owner'})
                        self.assertEqual(refused_legacy.status_code, 200)
                        self.assertFalse(refused_legacy.json()['ok'])
                self.assertFalse((wiki / 'raw/sources/2026-10-06-fixture.md').exists())
            finally:
                reset_hermes_home_override(token)

    def test_owner_setup_binds_only_the_host_session_after_the_reviewed_plan_is_confirmed(self):
        source = Path(__file__).resolve().parents[1] / 'dashboard/owner_broker.py'
        spec = importlib.util.spec_from_file_location('owner_setup_route_fixture', source)
        broker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(broker)
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from hermes_cli import web_server
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            (home / 'config.yaml').write_text('{}')
            token = set_hermes_home_override(home)
            try:
                seen, engine = [], []
                digest = ['f' * 64]
                class Setup:
                    def plan(self, binding):
                        seen.append(binding)
                        return {'ok': True, 'active': False, 'ready': False, 'plan_digest': digest[0]}
                def run(operation, payload):
                    engine.append((operation, payload))
                    return {'ok': True, 'activated': True}
                app = FastAPI()
                app.state.auth_required = False
                app.include_router(broker.make_router(run, lambda: True, lambda: None,
                                                      activation=Setup()), prefix='/owner')
                client = TestClient(app)
                with patch.object(web_server, '_SESSION_TOKEN', 'owner-setup-session'):
                    headers = {'X-Hermes-Session-Token': 'owner-setup-session'}
                    self.assertEqual(client.get('/owner/activation').status_code, 401)
                    shown = client.get('/owner/activation', headers=headers)
                    self.assertEqual(shown.status_code, 200, shown.text)
                    self.assertEqual(seen, [{'mode': 'local_owner', 'home': str(home.resolve())}])
                    for body in ({'confirm': True}, {'confirm': 'true', 'plan_digest': 'f' * 64},
                                 {'confirm': True, 'plan_digest': 'f' * 64, 'binding': {'mode': 'local_owner'}}):
                        self.assertEqual(client.post('/owner/activation', headers=headers, json=body).status_code, 400)
                    digest[0] = 'a' * 64
                    stale = client.post('/owner/activation', headers=headers, json={'confirm': True, 'plan_digest': 'f' * 64})
                    self.assertFalse(stale.json()['ok'])
                    self.assertEqual(engine, [], 'A changed setup was applied without a fresh review')
                    done = client.post('/owner/activation', headers=headers, json={'confirm': True, 'plan_digest': 'a' * 64})
                    # No restart: turning owner approval on writes only the engine's own settings.
                    self.assertEqual(done.json(), {'ok': True, 'activated': True})
                    self.assertEqual(engine, [('activate', {'binding': {'mode': 'local_owner', 'home': str(home.resolve())}})])
                    refused = {'ok': False, 'reason': 'Engine settings belong to another profile'}
                    app.router.routes.clear()
                    app.include_router(broker.make_router(lambda *a: refused, lambda: True, lambda: None,
                                                          activation=Setup()), prefix='/owner')
                    self.assertEqual(client.post('/owner/activation', headers=headers,
                        json={'confirm': True, 'plan_digest': 'a' * 64}).json(), refused)
                    app.router.routes.clear()
                    app.include_router(broker.make_router(lambda *a: {'ok': True, 'activated': True, 'secret': 'x'},
                        lambda: True, lambda: None, activation=Setup()), prefix='/owner')
                    self.assertFalse(client.post('/owner/activation', headers=headers,
                        json={'confirm': True, 'plan_digest': 'a' * 64}).json()['ok'])
                    from cron.execution_identity import enter_cron_execution, exit_cron_execution
                    cron = enter_cron_execution({'id': 'fixture-draft-job'}, 'fixture-execution', {})
                    try:
                        self.assertEqual(client.post('/owner/activation', headers=headers,
                            json={'confirm': True, 'plan_digest': 'a' * 64}).status_code, 403)
                    finally:
                        exit_cron_execution(cron)
                    self.assertEqual(len(engine), 1)
                remote = FastAPI()
                remote.state.auth_required = True
                @remote.middleware('http')
                async def signed_in(request, call_next):
                    from types import SimpleNamespace
                    request.state.session = SimpleNamespace(provider='nous', user_id='owner-1', org_id=None, access_token='t')
                    return await call_next(request)
                remote.include_router(broker.make_router(lambda *a: {'ok': True}, lambda: True, lambda: None,
                                                         activation=Setup()), prefix='/owner')
                with patch.object(web_server, '_SESSION_TOKEN', 'owner-setup-session'):
                    TestClient(remote).get('/owner/activation', headers=headers)
                self.assertEqual(seen[-1], {'mode': 'interactive_owner', 'home': str(home.resolve()),
                                            'provider': 'nous', 'user_id': 'owner-1', 'org_id': None})
            finally:
                reset_hermes_home_override(token)

    def test_new_session_recovery_uses_server_owner_binding_not_client_claims(self):
        source = Path(__file__).resolve().parents[1] / 'dashboard/owner_broker.py'
        spec = importlib.util.spec_from_file_location('owner_recovery_route_fixture', source)
        broker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(broker)
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from hermes_cli import web_server
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            (home / 'config.yaml').write_text('{}')
            token = set_hermes_home_override(home)
            try:
                calls = []
                ready = [True]
                reply = [{'ok': True}]
                def run(operation, payload):
                    calls.append((operation, payload))
                    return reply[0]
                app = FastAPI()
                app.state.auth_required = False
                app.include_router(broker.make_router(run, lambda: ready[0],
                    lambda: {'mode': 'local_owner', 'home': str(home)}), prefix='/owner')
                client = TestClient(app)
                with patch.object(web_server, '_SESSION_TOKEN', 'first-owner-fixture'):
                    client.post('/owner/decision', headers={'X-Hermes-Session-Token': 'first-owner-fixture'},
                        json={'ref': 'run/draft', 'review_digest': 'a' * 64, 'confirm': False})
                with patch.object(web_server, '_SESSION_TOKEN', 'restarted-owner-fixture'):
                    body = {'request_id': 'b' * 64}
                    headers = {'X-Hermes-Session-Token': 'restarted-owner-fixture'}
                    self.assertEqual(client.post('/owner/recover', json=body).status_code, 401)
                    result = client.post('/owner/recover', headers=headers, json=body)
                    self.assertEqual(result.status_code, 200, result.text)
                    self.assertEqual(calls[-1][0], 'recover')
                    self.assertEqual(calls[0][1]['owner_key'], calls[-1][1]['owner_key'])
                    self.assertNotEqual(calls[0][1]['principal'], calls[-1][1]['principal'])
                    self.assertEqual(client.get('/owner/recoverable').status_code, 401)
                    inventory = client.get('/owner/recoverable', headers=headers)
                    self.assertEqual(inventory.status_code, 200, inventory.text)
                    self.assertEqual(calls[-1][0], 'recoverable')
                    self.assertEqual(calls[-1][1]['owner_key'], calls[0][1]['owner_key'])
                    count = len(calls)
                    for invalid in ({**body, 'owner_key': 'c' * 64}, {**body, 'principal': 'd' * 64},
                                    {**body, 'ref': 'other/draft'}, {}, {'request_id': 7}):
                        self.assertEqual(client.post('/owner/recover', headers=headers, json=invalid).status_code, 400)
                    self.assertEqual(len(calls), count)
                    reply[0] = {'ok': True, 'operations': [{'receipt': {'signature': 'synthetic-private-material'}}]}
                    filtered = client.get('/owner/recoverable', headers=headers).json()
                    self.assertFalse(filtered['ok'], 'Nested authority material reached the owner UI')
                    self.assertNotIn('synthetic-private-material', json.dumps(filtered))
                    count = len(calls)
                    ready[0] = False
                    self.assertFalse(client.post('/owner/recover', headers=headers, json=body).json()['ok'])
                    self.assertEqual(len(calls), count)
            finally:
                reset_hermes_home_override(token)

    def test_owner_engine_timeout_is_retryable_without_exposing_request_material(self):
        source = Path(__file__).resolve().parents[1] / 'dashboard/plugin_api.py'
        spec = importlib.util.spec_from_file_location('owner_timeout_fixture', source)
        api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api)
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            with patch.object(api, '_audit_dir', return_value=Path(tmp)), patch.object(api.subprocess, 'run',
                    side_effect=subprocess.TimeoutExpired('fixture-engine', 30)):
                result = api._owner_run('confirm', {'ref': 'run/draft', 'request_id': 'private-fixture-handle'})
            self.assertFalse(result['ok'])
            self.assertTrue(result.get('retryable'), result)
            self.assertNotIn('private-fixture-handle', json.dumps(result))

    def test_panel_rejection_requires_and_forwards_the_displayed_digest(self):
        spec = importlib.util.spec_from_file_location('rejection_route_fixture', Path(__file__).resolve().parents[1] / 'dashboard/plugin_api.py')
        api = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = api
        spec.loader.exec_module(api)
        with patch.object(api, '_candidates_run', return_value=(subprocess.CompletedProcess([], 0, 'Rejected fixture', ''), None)) as run:
            refused = api.candidates_act({'ref': 'run/draft', 'action': 'reject', 'reason': 'Not this version'})
            self.assertFalse(refused['ok'], 'A rejection without the displayed digest reached a mutable candidate')
            run.assert_not_called()
            accepted = api.candidates_act({'ref': 'run/draft', 'action': 'reject', 'reason': 'Not this version', 'review_digest': 'a' * 64})
            self.assertTrue(accepted['ok'], accepted)
            self.assertIn('--expected-review-digest=' + 'a' * 64, run.call_args.args[0])

    def test_unreviewable_candidate_can_be_rejected_only_while_the_engine_refuses_its_review(self):
        # A candidate whose review the engine refuses (stale base, citation mismatch, legacy
        # metadata) has no displayed digest; without this path it could never leave the queue.
        spec = importlib.util.spec_from_file_location('unreviewable_rejection_fixture', Path(__file__).resolve().parents[1] / 'dashboard/plugin_api.py')
        api = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = api
        spec.loader.exec_module(api)
        body = {'ref': 'run/draft', 'action': 'reject', 'reason': 'Legacy metadata', 'unreviewable': True}
        refused_show = subprocess.CompletedProcess([], 1, '!! refused: Required target base hash is missing, malformed or stale', '')
        done = subprocess.CompletedProcess([], 0, 'OK rejected run/draft: Legacy metadata', '')
        with patch.object(api, '_candidates_run', side_effect=[(refused_show, None), (done, None)]) as run:
            accepted = api.candidates_act(body)
            self.assertTrue(accepted['ok'], accepted)
            self.assertEqual([call.args[0] for call in run.call_args_list],
                             [['show', 'run/draft', '--json'], ['reject', 'run/draft', '--reason=Legacy metadata']])
        reviewable = subprocess.CompletedProcess([], 0, '{"ref": "run/draft"}', '')
        with patch.object(api, '_candidates_run', return_value=(reviewable, None)) as run:
            refused = api.candidates_act(body)
            self.assertFalse(refused['ok'], 'A reviewable candidate was rejected without its displayed digest')
            self.assertEqual([call.args[0] for call in run.call_args_list], [['show', 'run/draft', '--json']])
        with patch.object(api, '_candidates_run', return_value=(None, 'engine missing')) as run:
            self.assertFalse(api.candidates_act(body)['ok'])
            self.assertEqual(run.call_count, 1)

    def test_owner_response_schema_rejects_unknown_authority_classes(self):
        spec = importlib.util.spec_from_file_location('owner_schema_fixture', Path(__file__).resolve().parents[1] / 'dashboard/owner_broker.py')
        broker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(broker)
        for payload in ({'ok': True, 'runtime_descriptor': {'key': 'synthetic-unknown-secret'}},
                        {'ok': False, 'reason': {'key': 'synthetic-unknown-secret'}},
                        {'ok': True, 'operations': [{'request_id': 'a' * 64, 'ref': 'run/draft',
                            'kind': 'new', 'target': 'source.md', 'review_digest': 'b' * 64,
                            'state': 'approved', 'key': 'synthetic-unknown-secret'}]}):
            with self.subTest(fields=list(payload)):
                with self.assertRaises(ValueError):
                    broker.checked_result(payload)
        expected = {'ok': True, 'operations': [{'request_id': 'a' * 64, 'ref': 'run/draft',
            'kind': 'new', 'target': 'source.md', 'review_digest': 'b' * 64, 'state': 'approved'}]}
        self.assertEqual(broker.checked_result(expected), expected)

    def test_verified_remote_identity_must_match_configured_owner(self):
        spec = importlib.util.spec_from_file_location('owner_identity_fixture', Path(__file__).resolve().parents[1] / 'dashboard/owner_broker.py')
        broker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(broker)
        from fastapi import FastAPI, HTTPException
        from starlette.requests import Request
        from hermes_cli.dashboard_auth.base import Session
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            (home / 'config.yaml').write_text('{}')
            token = set_hermes_home_override(home)
            try:
                app = FastAPI()
                app.state.auth_required = True
                request = Request({'type': 'http', 'headers': [], 'app': app})
                request.state.session = Session(user_id='owner', email='fixture@example.invalid', display_name='Fixture',
                    org_id='fixture-org', provider='fixture-provider', expires_at=9999999999, access_token='', refresh_token='')
                binding = {'mode': 'interactive_owner', 'home': str(home), 'provider': 'fixture-provider', 'user_id': 'other', 'org_id': 'fixture-org'}
                with self.assertRaises(HTTPException) as denied:
                    broker.owner_principal(request, binding)
                self.assertEqual(denied.exception.status_code, 403)
                binding['user_id'] = 'owner'
                self.assertEqual(len(broker.owner_principal(request, binding)), 64)
                from dataclasses import replace
                request.state.session = replace(request.state.session, access_token='first-remote-session-fixture')
                original_principal = broker.owner_principal(request, binding)
                stable_owner = broker.binding_key(binding)
                request.state.session = replace(request.state.session, access_token='replacement-remote-session-fixture')
                self.assertNotEqual(original_principal, broker.owner_principal(request, binding),
                    'Pending remote confirmations must not transfer to a replacement session')
                self.assertEqual(stable_owner, broker.binding_key(binding),
                    'Already-approved recovery keeps the durable configured-owner binding')
                engine = Path(os.environ['WIKI_ENGINE_TEST_DIR'])
                exercise = (
                    'import sys,json; from pathlib import Path; sys.path.insert(0,sys.argv[1]); '
                    'from owner_decisions import OwnerDecisions,DecisionRefused; '
                    'p=json.loads(sys.stdin.read()); snapshot={"review_digest":"a"*64,"ref":"run/draft"};\n'
                    'with OwnerDecisions(Path(p["data"]),initialize=True) as authority:\n'
                    ' pending=authority.prepare(snapshot,p["first"],owner_key=p["owner"]);\n'
                    ' try: authority.confirm(pending["request_id"],snapshot,p["second"],owner_key=p["owner"])\n'
                    ' except DecisionRefused: pass\n'
                    ' else: raise AssertionError("Replacement session consumed original pending decision")\n'
                    ' original=authority.confirm(pending["request_id"],snapshot,p["first"],owner_key=p["owner"]);\n'
                    ' recovered=authority.recovery_receipt(pending["request_id"],p["owner"]);\n'
                    ' assert recovered==original; print("REMOTE_PENDING_REFUSED_APPROVED_RECOVERY_VERIFIED")\n')
                result = subprocess.run([sys.executable, '-B', '-c', exercise, str(engine)],
                    input=json.dumps({'data': str(home / 'authority'), 'first': original_principal,
                        'second': broker.owner_principal(request, binding), 'owner': stable_owner}),
                    capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('REMOTE_PENDING_REFUSED_APPROVED_RECOVERY_VERIFIED', result.stdout)
                request.state.session = replace(request.state.session, user_id='owner:segment', org_id='org')
                binding.update(user_id='owner:segment', org_id='org')
                first_principal = broker.owner_principal(request, binding)
                request.state.session = replace(request.state.session, user_id='owner', org_id='segment:org')
                binding.update(user_id='owner', org_id='segment:org')
                self.assertNotEqual(first_principal, broker.owner_principal(request, binding), 'Opaque owner fields need unambiguous framing')
                binding['home'] = str(home / 'different-profile')
                with self.assertRaises(HTTPException):
                    broker.owner_principal(request, binding)
                binding['home'] = str(home)
                (home / 'config.yaml').write_text('plugins:\n  isolation: host\n')
                with self.assertRaises(HTTPException) as unsupported:
                    broker.owner_principal(request, binding)
                self.assertEqual(unsupported.exception.status_code, 403)
            finally:
                reset_hermes_home_override(token)


if __name__ == '__main__':
    unittest.main()
