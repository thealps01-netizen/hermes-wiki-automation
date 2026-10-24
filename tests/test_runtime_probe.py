"""A verification canary must traverse native dispatch and never execute its real handler."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


class RuntimeProbeTests(unittest.TestCase):
    def test_loaded_guard_blocks_canary_and_missing_guard_is_safe_but_not_ready(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('wiki_probe_fixture', root / '__init__.py', submodule_search_locations=[str(root)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            (home / 'config.yaml').write_text('plugins:\n  entries:\n    wiki-automation:\n      settings:\n        draft_job_id: job\n')
            token = set_hermes_home_override(home)
            manager = PluginManager()
            manager._discovered = True
            ctx = PluginContext(PluginManifest(name='wiki-automation', version='0.0.0', source='user'), manager)
            try:
                module.register(ctx)
                from wiki_probe_fixture import runtime_probe
                with patch('hermes_cli.plugins.get_plugin_manager', return_value=manager):
                    probe = runtime_probe.probe(ctx, 'a' * 64)
                    self.assertTrue(probe['veto_exercised'], probe)
                    self.assertFalse(probe['handler_reached'])
                    self.assertEqual(probe['pid'], os.getpid())
                    self.assertEqual(probe['home'], str(home.resolve()))
                    self.assertEqual(probe['challenge'], 'a' * 64)
                    self.assertTrue(probe['loaded_code_hash'])
                    self.assertTrue(probe['incarnation'])
                    manager._hooks['pre_tool_call'].clear()
                    missing = runtime_probe.probe(ctx, 'b' * 64)
                    self.assertFalse(missing['veto_exercised'], missing)
                    self.assertTrue(missing['handler_reached'])
                    self.assertEqual(missing['incarnation'], probe['incarnation'])
                    self.assertNotEqual(missing['challenge'], probe['challenge'])
                    self.assertEqual((home / 'config.yaml').read_text(), 'plugins:\n  entries:\n    wiki-automation:\n      settings:\n        draft_job_id: job\n')
                    self.assertFalse((home / 'live.md').exists())
            finally:
                reset_hermes_home_override(token)

    def test_owner_runtime_gate_uses_live_control_and_actual_native_veto(self):
        self.exercise_owner_runtime(False)

    def test_schema2_owner_routes_use_selected_code_and_data(self):
        self.exercise_owner_runtime(True)

    def exercise_owner_runtime(self, separated):
        import asyncio
        from concurrent.futures import Future
        import contextvars
        import threading
        from gateway.control_socket import GatewayControlServer
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
        from cron.jobs import save_jobs
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('wiki_runtime_gate_fixture', root / '__init__.py', submodule_search_locations=[str(root)])
        native = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = native
        spec.loader.exec_module(native)
        api_spec = importlib.util.spec_from_file_location('wiki_runtime_gate_api_fixture', root / 'dashboard/plugin_api.py')
        api = importlib.util.module_from_spec(api_spec)
        sys.modules[api_spec.name] = api
        api_spec.loader.exec_module(api)
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            (home / 'config.yaml').write_text('plugins:\n  entries:\n    wiki-automation:\n      settings:\n        draft_job_id: job\n')
            engine = home / 'engine'
            engine.mkdir()
            data = home / 'data'
            data.mkdir()
            for code in Path(os.environ['WIKI_ENGINE_TEST_DIR']).glob('*.py'):
                (engine / code.name).write_bytes(code.read_bytes())
            settings_path = (data if separated else engine) / 'settings.json'
            settings_path.write_text('{}')
            if separated:
                location = home / 'state/wiki-automation/location.json'
                location.parent.mkdir(parents=True)
                location.write_bytes(json.dumps({'schema': 2, 'engine_dir': str(engine), 'audit_dir': str(data)}).encode())
            home_token = set_hermes_home_override(home)
            manager = PluginManager()
            manager._discovered = True
            ctx = PluginContext(PluginManifest(name='wiki-automation', version='0.0.0', source='user'), manager)
            native.register(ctx)
            save_jobs([{'id': 'job', 'enabled': True, 'enabled_toolsets': ['wiki_draft', 'no_mcp']}])
            ready = Future()
            stopper = {}
            peer = {'protocol': 1, 'pid': os.getpid(), 'hermes_home': str(home)}
            async def serve():
                stop = asyncio.Event()
                stopper.update(loop=asyncio.get_running_loop(), stop=stop)
                server = GatewayControlServer(home=home, verb_handlers={'identify': lambda: dict(peer)})
                try:
                    ready.set_result(await server.start())
                    await stop.wait()
                finally:
                    await server.stop()
            copied = contextvars.copy_context()
            thread = threading.Thread(target=lambda: copied.run(asyncio.run, serve()), daemon=True)
            thread.start()
            try:
                self.assertTrue(ready.result(timeout=10), 'Isolated host control socket did not bind')
                with patch.dict(os.environ, {'LLMWIKI_AUDIT_DIR': '' if separated else str(engine), 'LLMWIKI_SETTINGS': ''}), patch('hermes_cli.plugins.get_plugin_manager', return_value=manager):
                    self.assertFalse(api._owner_ready(), 'A disk enable flag or missing release identity cannot authorize')
                    from wiki_runtime_gate_fixture import runtime_probe
                    proof = runtime_probe.probe(ctx, 'c' * 64)
                    settings_path.write_text(json.dumps({'owner_approval_runtime': {'loaded_code_hash': proof['loaded_code_hash']}}))
                    self.assertTrue(api._owner_ready(), 'Same-process native control + exact loaded release + real veto must pass')
                    foreign = {**proof, 'engine_identity': {**proof['engine_identity'], 'engine_dir': str(home / 'foreign-code')}}
                    with patch.object(runtime_probe, 'probe', return_value=foreign):
                        self.assertFalse(api._owner_ready(), 'A native veto for another selected engine cannot authorize publication')
                    # Exercise the mounted, authenticated route with real native veto and engine subprocesses.
                    wiki, data = home / 'wiki', home / 'data'
                    (wiki / '.llm-wiki').mkdir(parents=True)
                    (wiki / '.llm-wiki/project.json').write_text('{"id":"publication-fixture"}')
                    (wiki / 'raw/sources').mkdir(parents=True)
                    (wiki / 'raw/evidence').mkdir()
                    candidate = data / 'inbox/run/candidates/draft'
                    candidate.mkdir(parents=True)
                    (candidate / 'candidate.json').write_text(json.dumps({'kind': 'new', 'target': '2026-10-09-fixture.md',
                        'summary': 'Fixture', 'why': 'Disposable owner flow', 'evidence_ids': []}))
                    source = b'# Fixture\n\n## Decisions\n\n**1. Fixture.**\nEvidence: none (method).\n'
                    (candidate / 'source.md').write_bytes(source)
                    # The owner switches come from the panel's own setup route, not from fixture text.
                    settings_path.write_text(json.dumps({'hermes_home': str(home), 'project_root': str(wiki),
                        'project_id': 'publication-fixture', 'audit_dir': str(data), 'jobs': {'session_harvest': 'job'}}))
                    shown = api.candidates_show('run/draft')
                    self.assertTrue(shown['ok'], shown)
                    from fastapi import FastAPI
                    from fastapi.testclient import TestClient
                    from hermes_cli import web_server
                    app = FastAPI()
                    app.state.auth_required = False
                    app.include_router(api.router, prefix='/api/plugins/wiki-automation')
                    client = TestClient(app)
                    route = '/api/plugins/wiki-automation/owner/decision'
                    body = {'ref': 'run/draft', 'review_digest': shown['review_digest'], 'confirm': False}
                    with patch.object(web_server, '_SESSION_TOKEN', 'isolated-publication-owner-fixture'):
                        headers = {'X-Hermes-Session-Token': 'isolated-publication-owner-fixture'}
                        self.assertEqual(client.post(route, json=body).status_code, 401)
                        setup = '/api/plugins/wiki-automation/owner/activation'
                        before = client.get(setup, headers=headers).json()
                        self.assertEqual((before['ok'], before['active'], before['ready'], before['job']['id']),
                                         (True, False, False, 'job'), before)
                        self.assertFalse(client.post(route, headers=headers, json=body).json().get('needs_confirm'),
                                         'An unconfigured owner was able to prepare a decision')
                        done = client.post(setup, headers=headers, json={'confirm': True, 'plan_digest': before['plan_digest']})
                        self.assertEqual(done.json(), {'ok': True, 'restart_required': True})
                        written = json.loads(settings_path.read_bytes())
                        self.assertEqual((written['owner_approval_owner'], written['owner_approval_runtime']),
                            ({'mode': 'local_owner', 'home': str(home.resolve())}, {'loaded_code_hash': proof['loaded_code_hash']}))
                        self.assertEqual([ctx.get_config(key) for key in ('draft_job_id', 'harvest_workflow_enabled', 'runtime_probe_enabled')],
                                         ['job', True, True])
                        after = client.get(setup, headers=headers).json()
                        self.assertEqual((after['active'], after['ready']), (True, True), after)
                        if separated:
                            original_location = location.read_bytes()
                            real_ready = api._owner_ready
                            def rebind_after_probe():
                                ready_now = real_ready()
                                location.write_bytes(json.dumps({'schema': 2, 'engine_dir': str(home / 'other-code'),
                                    'audit_dir': str(home / 'other-data')}).encode())
                                return ready_now
                            try:
                                with patch.object(api, '_owner_ready', side_effect=rebind_after_probe), patch.object(api, 'resolve_engine_paths', wraps=api.resolve_engine_paths) as resolved:
                                    prepared = client.post(route, headers=headers, json=body).json()
                                    self.assertTrue(prepared.get('needs_confirm'), prepared)
                                    self.assertEqual(resolved.call_count, 1, 'Owner operation re-resolved selection between binding, proof and subprocess')
                            finally:
                                location.write_bytes(original_location)
                        else:
                            prepared = client.post(route, headers=headers, json=body).json()
                        self.assertTrue(prepared.get('needs_confirm'), prepared)
                        target = wiki / 'raw/sources/2026-10-09-fixture.md'
                        self.assertFalse(target.exists())
                        request = {**body, 'confirm': True, 'request_id': prepared['request_id']}
                        applied = client.post(route, headers=headers, json=request).json()
                        self.assertTrue(applied['ok'], applied)
                        self.assertEqual(applied['state'], 'applied')
                        self.assertEqual(target.read_bytes(), source)
                        stamp = target.stat().st_mtime_ns
                        retried = client.post(route, headers=headers, json=request).json()
                        self.assertEqual(retried['operation_id'], applied['operation_id'])
                        self.assertEqual(target.stat().st_mtime_ns, stamp)
                        self.assertTrue({'receipt', 'signature', 'secret'}.isdisjoint(applied))
                        second = data / 'inbox/run/candidates/second'
                        second.mkdir()
                        (second / 'candidate.json').write_text(json.dumps({'kind': 'new', 'target': '2026-10-09-second.md',
                            'summary': 'Second fixture', 'why': 'Session replacement recovery', 'evidence_ids': []}))
                        (second / 'source.md').write_bytes(source)
                        second_shown = api.candidates_show('run/second')
                        second_body = {'ref': 'run/second', 'review_digest': second_shown['review_digest'], 'confirm': False}
                        second_pending = client.post(route, headers=headers, json=second_body).json()
                        (home / 'settings.json').write_bytes(settings_path.read_bytes())
                        real_run = api.subprocess.run
                        def interrupted_engine(command, **kwargs):
                            if any(str(a).endswith('owner_decisions.py') for a in command) and 'confirm' in command:
                                worker = Path(os.environ['WIKI_ENGINE_TEST_DIR']) / 'tests/broker_apply_worker.py'
                                return real_run([sys.executable, '-B', str(worker), str(home), 'after-confirm'], **kwargs)
                            return real_run(command, **kwargs)
                        with patch.object(api.subprocess, 'run', side_effect=interrupted_engine):
                            interrupted = client.post(route, headers=headers,
                                json={**second_body, 'confirm': True, 'request_id': second_pending['request_id']}).json()
                        self.assertFalse(interrupted['ok'], interrupted)
                        second_target = wiki / 'raw/sources/2026-10-09-second.md'
                        self.assertFalse(second_target.exists())
                        with patch.object(web_server, '_SESSION_TOKEN', 'isolated-restarted-publication-owner-fixture'):
                            new_headers = {'X-Hermes-Session-Token': 'isolated-restarted-publication-owner-fixture'}
                            inventory_route = '/api/plugins/wiki-automation/owner/recoverable'
                            recovery_route = '/api/plugins/wiki-automation/owner/recover'
                            available = client.get(inventory_route, headers=new_headers).json()
                            self.assertTrue(available['ok'], available)
                            self.assertEqual([row['ref'] for row in available['operations']], ['run/second'])
                            self.assertTrue({'receipt', 'signature', 'secret', 'owner_key', 'principal'}.isdisjoint(available['operations'][0]))
                            recovered = client.post(recovery_route, headers=new_headers,
                                json={'request_id': second_pending['request_id']}).json()
                            self.assertTrue(recovered['ok'], recovered)
                            self.assertEqual(second_target.read_bytes(), source)
                            self.assertEqual(client.get(inventory_route, headers=new_headers).json()['operations'], [])
                        saved_hooks = list(manager._hooks['pre_tool_call'])
                        manager._hooks['pre_tool_call'].clear()
                        try:
                            refused = client.post(route, headers=headers, json=request).json()
                            self.assertFalse(refused['ok'])
                            self.assertIn('not verified', refused['reason'])
                            self.assertEqual(target.stat().st_mtime_ns, stamp)
                        finally:
                            manager._hooks['pre_tool_call'].extend(saved_hooks)
                    from tools.process_registry import GatewayChildDispatch
                    for mode in ('scoped', 'degraded'):
                        with patch('tools.process_registry.restart_safe_gateway_child_argv', return_value=GatewayChildDispatch(mode, ['fixture-command-never-executed'])):
                            self.assertFalse(api._owner_ready(), f'{mode} external workers must not inherit a parent-process attestation')
                    peer['pid'] = os.getpid() + 1
                    self.assertFalse(api._owner_ready(), 'A split-process cron worker is unverified, not implicitly ready')
                    peer['pid'] = os.getpid()
                    original_config = (home / 'config.yaml').read_bytes()
                    (home / 'config.yaml').write_bytes(b'cron:\n  provider: unsupported-fixture-provider\n' + original_config)
                    self.assertFalse(api._owner_ready(), 'An external provider cannot inherit built-in cron verification')
                    (home / 'config.yaml').write_bytes(original_config)
                    self.assertTrue(api._owner_ready())
                    settings_path.write_text(json.dumps({'owner_approval_runtime': {'loaded_code_hash': '0' * 64}}))
                    self.assertFalse(api._owner_ready(), 'Wrong loaded release must fail')
            finally:
                if stopper:
                    stopper['loop'].call_soon_threadsafe(stopper['stop'].set)
                thread.join(timeout=10)
                self.assertFalse(thread.is_alive(), 'Fixture control server did not stop')
                reset_hermes_home_override(home_token)


if __name__ == '__main__':
    unittest.main()
