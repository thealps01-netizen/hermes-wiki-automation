"""Probe-only local IPC; tests never enable or contact the live profile."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest


class RuntimeChannelTests(unittest.TestCase):
    def test_native_registration_is_opt_in_and_host_unload_stops_it(self):
        from unittest.mock import patch
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
        from cron.jobs import save_jobs
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('wiki_native_channel_fixture', root / '__init__.py', submodule_search_locations=[str(root)])
        native = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = native
        spec.loader.exec_module(native)
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            config = home / 'config.yaml'
            prefix = 'plugins:\n  entries:\n    wiki-automation:\n      settings:\n        draft_job_id: fixture-job\n'
            config.write_text(prefix)
            token = set_hermes_home_override(home)
            manager = PluginManager()
            manager._discovered = True
            ctx = PluginContext(PluginManifest(name='wiki-automation', version='0.0.0', source='user'), manager)
            try:
                with patch('hermes_cli.plugins.get_plugin_manager', return_value=manager):
                    native.register(ctx)
                    descriptor = home / 'cache/wiki-automation/runtime' / f'{os.getpid()}.json'
                    self.assertFalse(descriptor.exists(), 'A default registration started a listener')
                    manager.unload()
                    config.write_text(prefix + '        runtime_probe_enabled: true\n')
                    save_jobs([{'id': 'fixture-job', 'enabled': True, 'enabled_toolsets': ['wiki_draft', 'no_mcp']}])
                    manager._discovered = True
                    native.register(ctx)
                    self.assertTrue(descriptor.exists(), 'Explicitly opted-in native registration did not start the channel')
                    from wiki_native_channel_fixture import runtime_channel, runtime_probe
                    proof = runtime_channel.query_peer(home, os.getpid(), runtime_probe._LOADED_CODE_HASH, 'fixture-job')
                    self.assertTrue(proof['veto_exercised'])
                    self.assertFalse(proof['handler_reached'])
                    self.assertTrue(manager.unload())
                    self.assertFalse(descriptor.exists(), 'Host unload left a live descriptor')
                    with self.assertRaises(runtime_channel.ProbeRefused):
                        runtime_channel.query_peer(home, os.getpid(), runtime_probe._LOADED_CODE_HASH, 'fixture-job')
                    manager._discovered = True
                    ctx._abandon_load()
                    late = None
                    try:
                        with self.assertLogs('hermes_cli.plugins', level='WARNING'):
                            with self.assertRaises(runtime_channel.ProbeRefused):
                                late = runtime_channel.register(ctx)
                    finally:
                        if late is not None:
                            late.close()
                    self.assertFalse(descriptor.exists(), 'An abandoned host load left an unowned listener')
            finally:
                manager.unload()
                reset_hermes_home_override(token)

    def test_separate_native_peer_is_challenged_before_owner_readiness(self):
        import json
        import subprocess
        from unittest.mock import patch
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
        from cron.jobs import save_jobs
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('wiki_split_channel_fixture', root / '__init__.py', submodule_search_locations=[str(root)])
        native = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = native
        spec.loader.exec_module(native)
        api_spec = importlib.util.spec_from_file_location('wiki_split_channel_api', root / 'dashboard/plugin_api.py')
        api = importlib.util.module_from_spec(api_spec)
        sys.modules[api_spec.name] = api
        api_spec.loader.exec_module(api)
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            (home / 'config.yaml').write_text('plugins:\n  entries:\n    wiki-automation:\n      settings:\n        draft_job_id: fixture-job\n        runtime_probe_enabled: true\n')
            engine = home / 'engine'
            engine.mkdir()
            for code in Path(os.environ['WIKI_ENGINE_TEST_DIR']).glob('*.py'):
                (engine / code.name).write_bytes(code.read_bytes())
            token = set_hermes_home_override(home)
            manager = PluginManager()
            manager._discovered = True
            ctx = PluginContext(PluginManifest(name='wiki-automation', version='0.0.0', source='user'), manager)
            peer = None
            try:
                with patch('hermes_cli.plugins.get_plugin_manager', return_value=manager), patch.dict(os.environ, {'LLMWIKI_AUDIT_DIR': str(engine)}):
                    save_jobs([{'id': 'fixture-job', 'enabled': True, 'enabled_toolsets': ['wiki_draft', 'no_mcp']}])
                    native.register(ctx)
                    from wiki_split_channel_fixture import runtime_probe, runtime_channel
                    (engine / 'settings.json').write_text(json.dumps({'owner_approval_runtime': {'loaded_code_hash': runtime_probe._LOADED_CODE_HASH}}))
                    peer = subprocess.Popen([sys.executable, str(root / 'tests/runtime_channel_peer.py'), str(home)], stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    announcement = json.loads(peer.stdout.readline())
                    self.assertNotEqual(announcement['pid'], os.getpid())
                    self.assertEqual(announcement['loaded_code_hash'], runtime_probe._LOADED_CODE_HASH)
                    self.assertTrue(announcement['native_dispatch_initialized'], 'The peer advertised readiness before native dispatch initialization')
                    self.assertTrue(api._owner_ready(), 'The first owner probe could not verify the loaded peer')
                    import time
                    started = time.monotonic()
                    proof = runtime_channel.query_peer(home, announcement['pid'], runtime_probe._LOADED_CODE_HASH, 'fixture-job', timeout=3)
                    print(f'NATIVE_PEER_COLD_PROBE_SECONDS {time.monotonic() - started:.4f}')
                    self.assertEqual(proof['incarnation'], announcement['incarnation'])
                    self.assertTrue(proof['veto_exercised'])
                    self.assertTrue(api._owner_ready(), 'A real, separately loaded guarded gateway could not be verified')
                    peer.stdin.write('drop-guard\n')
                    peer.stdin.flush()
                    self.assertEqual(json.loads(peer.stdout.readline())['ack'], 'drop-guard')
                    self.assertFalse(api._owner_ready(), 'A stale earlier peer proof hid a removed guard')
                    peer.stdin.write('stop\n')
                    peer.stdin.flush()
                    output, error = peer.communicate(timeout=15)
                    self.assertEqual(peer.returncode, 0, output + error)
                    self.assertFalse(api._owner_ready(), 'A dead peer was reported as ready')
                    self.assertFalse((home / 'cache/wiki-automation/runtime' / f"{announcement['pid']}.json").exists())
                    foreign_settings = home / 'foreign-settings.json'
                    foreign_settings.write_bytes((engine / 'settings.json').read_bytes())
                    peer = subprocess.Popen([sys.executable, str(root / 'tests/runtime_channel_peer.py'), str(home)], stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                        env={**os.environ, 'LLMWIKI_SETTINGS': str(foreign_settings)})
                    announcement = json.loads(peer.stdout.readline())
                    self.assertFalse(api._owner_ready(), 'An authenticated native peer selecting other settings was reported ready')
                    peer.stdin.write('stop\n')
                    peer.stdin.flush()
                    output, error = peer.communicate(timeout=15)
                    self.assertEqual(peer.returncode, 0, output + error)
            finally:
                if peer is not None and peer.poll() is None:
                    peer.kill()
                    peer.communicate(timeout=10)
                manager.unload()
                reset_hermes_home_override(token)

    def test_expired_response_is_rejected(self):
        import time
        from types import SimpleNamespace
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('wiki_expired_channel_fixture', root / 'runtime_channel.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        offset = [0]
        module.time = SimpleNamespace(time=lambda: time.time() + offset[0])
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            def late_proof(ctx, challenge):
                offset[0] = 4
                return {'challenge': challenge, 'pid': os.getpid(), 'home': str(home.resolve()), 'job_id': 'fixture-job',
                        'loaded_code_hash': 'a' * 64, 'incarnation': 'late-fixture', 'veto_exercised': True, 'handler_reached': False}
            channel = module.ProbeChannel(home, None, late_proof, lambda: True)
            try:
                with self.assertRaises(module.ProbeRefused):
                    module.query_peer(home, os.getpid(), 'a' * 64, 'fixture-job')
            finally:
                channel.close()

    def test_unknown_proof_schema_is_refused(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('wiki_schema_channel_fixture', root / 'runtime_channel.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            def wrong_schema(ctx, challenge):
                return {'schema_version': 2, 'challenge': challenge, 'pid': os.getpid(), 'home': str(home.resolve()),
                    'job_id': 'fixture-job', 'loaded_code_hash': 'a' * 64, 'incarnation': 'schema-fixture',
                    'veto_exercised': True, 'handler_reached': False}
            channel = module.ProbeChannel(home, None, wrong_schema, lambda: True)
            try:
                with self.assertRaises(module.ProbeRefused):
                    module.query_peer(home, os.getpid(), 'a' * 64, 'fixture-job')
            finally:
                channel.close()

    def test_real_host_discovery_registers_and_unloads_opted_in_package(self):
        import json
        import shutil
        import subprocess
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from cron.jobs import save_jobs
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            package = home / 'plugins/wiki-automation'
            package.mkdir(parents=True)
            for name in ('__init__.py', 'draft_security.py', 'runtime_probe.py', 'runtime_channel.py', 'harvest_runtime.py', 'engine_paths.py', 'plugin.yaml'):
                shutil.copy2(root / name, package / name)
            (home / 'config.yaml').write_text('plugins:\n  enabled: [wiki-automation]\n  entries:\n    wiki-automation:\n      settings:\n        draft_job_id: fixture-job\n        runtime_probe_enabled: true\n')
            token = set_hermes_home_override(home)
            try:
                save_jobs([{'id': 'fixture-job', 'enabled': True, 'enabled_toolsets': ['wiki_draft', 'no_mcp']}])
            finally:
                reset_hermes_home_override(token)
            proc = subprocess.run([sys.executable, str(root / 'tests/runtime_channel_peer.py'), str(home), '--discover'],
                                  input='stop\n', capture_output=True, text=True, timeout=20)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            announcement = json.loads(proc.stdout.splitlines()[0])
            self.assertEqual(announcement['load_mode'], 'host-discovery')
            self.assertEqual(Path(announcement['native_source_root']).resolve(), package.resolve())
            self.assertTrue(announcement['native_dispatch_initialized'])
            self.assertFalse((home / 'cache/wiki-automation/runtime' / f"{announcement['pid']}.json").exists())

    def test_handler_failure_does_not_silently_kill_listener(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('wiki_error_channel_fixture', root / 'runtime_channel.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            def prove(ctx, challenge):
                return {'schema_version': 1, 'challenge': challenge, 'pid': os.getpid(), 'home': str(home.resolve()),
                    'job_id': 'fixture-job', 'loaded_code_hash': 'a' * 64, 'incarnation': 'error-fixture',
                    'veto_exercised': True, 'handler_reached': False}
            failure = [RuntimeError]
            def broken_ready():
                raise failure[0]('Synthetic transient native callback failure')
            channel = module.ProbeChannel(home, None, prove, broken_ready)
            try:
                for kind in (RuntimeError, TypeError, ValueError, OSError):
                    failure[0] = kind
                    with self.assertLogs(module.__name__, level='WARNING') as logs:
                        with self.assertRaises(module.ProbeRefused):
                            module.query_peer(home, os.getpid(), 'a' * 64, 'fixture-job', timeout=0.2)
                    self.assertIn(kind.__name__, logs.output[0])
                    self.assertNotIn('Synthetic transient', logs.output[0], 'The channel logged callback data instead of a safe exception type')
                channel.ready = lambda: True
                self.assertTrue(module.query_peer(home, os.getpid(), 'a' * 64, 'fixture-job', timeout=0.2)['veto_exercised'])
            finally:
                channel.close()

    def test_authenticated_channel_reports_loaded_peer_and_closes(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('wiki_channel_fixture', root / 'runtime_channel.py')
        channel_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(channel_module)
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            token = set_hermes_home_override(home)
            class Context:
                def get_config(self, name, default=None):
                    return 'fixture-job' if name == 'draft_job_id' else default
            ctx = Context()
            calls = []
            def prove(context, challenge):
                calls.append(challenge)
                return {'schema_version': 1, 'challenge': challenge, 'pid': os.getpid(),
                    'incarnation': 'fixture-incarnation', 'loaded_code_hash': 'a' * 64, 'home': str(home.resolve()),
                    'job_id': 'fixture-job', 'veto_exercised': True, 'handler_reached': False}
            try:
                channel = channel_module.ProbeChannel(home, ctx, prove, lambda: True)
                try:
                    proof = channel_module.query_peer(home, os.getpid(), 'a' * 64, 'fixture-job')
                    self.assertEqual(proof['pid'], os.getpid())
                    self.assertTrue(proof['veto_exercised'])
                    self.assertEqual(len(calls), 1)
                    with self.assertRaises(channel_module.ProbeRefused):
                        channel_module.query_peer(home, os.getpid(), 'a' * 64, 'fixture-job', challenge=proof['challenge'])
                    self.assertEqual(len(calls), 1, 'A replay invoked the peer guard again')
                    with self.assertRaises(channel_module.ProbeRefused):
                        channel_module.query_peer(home, os.getpid(), 'b' * 64, 'fixture-job')
                    import json
                    import socket
                    import struct
                    import time
                    key = channel.key
                    port = channel.listener.getsockname()[1]
                    invalid = [
                        {'operation': 'approve', 'challenge': 'c' * 64, 'expires_at': time.time() + 3},
                        {'operation': 'publish', 'challenge': 'd' * 64, 'expires_at': time.time() + 3},
                        {'operation': 'probe', 'challenge': 'e' * 64, 'expires_at': time.time() - 1},
                    ]
                    before = len(calls)
                    for request in invalid:
                        with socket.create_connection(('127.0.0.1', port), timeout=1) as client:
                            channel_module._send(client, channel_module._sign(request, key))
                            with self.assertRaises((channel_module.ProbeRefused, OSError)):
                                channel_module._receive(client)
                    with socket.create_connection(('127.0.0.1', port), timeout=1) as client:
                        request = {'operation': 'probe', 'challenge': 'f' * 64, 'expires_at': time.time() + 3}
                        channel_module._send(client, channel_module._sign(request, b'wrong-authentication-material'))
                        with self.assertRaises((channel_module.ProbeRefused, OSError)):
                            channel_module._receive(client)
                    with socket.create_connection(('127.0.0.1', port), timeout=1) as client:
                        client.sendall(struct.pack('!I', 8193))
                        with self.assertRaises((channel_module.ProbeRefused, OSError)):
                            channel_module._receive(client)
                    self.assertEqual(len(calls), before, 'A forbidden request reached the native probe callback')
                    proof = channel_module.query_peer(home, os.getpid(), 'a' * 64, 'fixture-job')
                    self.assertTrue(proof['veto_exercised'], 'Invalid requests silently killed the listener')
                    with self.assertRaises(channel_module.ProbeRefused):
                        channel_module.query_peer(home, os.getpid(), 'a' * 64, 'wrong-job')
                    descriptor = json.loads(channel.path.read_bytes())
                    descriptor['pid'] += 1
                    channel.path.write_text(json.dumps(descriptor))
                    with self.assertRaises(channel_module.ProbeRefused):
                        channel_module.query_peer(home, os.getpid(), 'a' * 64, 'fixture-job')
                    channel.path.write_bytes(channel.saved)
                    outside = home / 'outside-runtime-descriptor.json'
                    outside.write_bytes(channel.saved)
                    channel.path.unlink()
                    os.link(outside, channel.path)
                    with self.assertRaises(channel_module.ProbeRefused):
                        channel_module.query_peer(home, os.getpid(), 'a' * 64, 'fixture-job')
                    self.assertEqual(outside.read_bytes(), channel.saved)
                    channel.path.unlink()
                    channel.path.write_bytes(channel.saved)
                    if os.name == 'nt':
                        import subprocess
                        runtime_dir = channel.path.parent
                        outside_dir = home / 'outside-runtime-directory'
                        runtime_dir.rename(outside_dir)
                        linked = False
                        try:
                            made = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(runtime_dir), str(outside_dir)], capture_output=True, text=True, timeout=10)
                            self.assertEqual(made.returncode, 0, made.stdout + made.stderr)
                            linked = True
                            with self.assertRaises(channel_module.ProbeRefused):
                                channel_module.query_peer(home, os.getpid(), 'a' * 64, 'fixture-job')
                            self.assertEqual((outside_dir / channel.path.name).read_bytes(), channel.saved)
                        finally:
                            if linked:
                                os.rmdir(runtime_dir)
                            outside_dir.rename(runtime_dir)
                finally:
                    channel.close()
                self.assertFalse(channel.thread.is_alive())
                self.assertFalse(channel.path.exists())
                with self.assertRaises(channel_module.ProbeRefused):
                    channel_module.query_peer(home, os.getpid(), 'a' * 64, 'fixture-job')
            finally:
                reset_hermes_home_override(token)


if __name__ == '__main__':
    unittest.main()
