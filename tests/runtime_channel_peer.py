"""Disposable native peer plus the real host control server, without a cron/model run."""
import asyncio
from concurrent.futures import Future
import contextvars
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
from unittest.mock import patch

from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
from gateway.control_socket import GatewayControlServer

home = Path(sys.argv[1])
root = Path(__file__).resolve().parents[1]
token = set_hermes_home_override(home)
spec = importlib.util.spec_from_file_location('wiki_peer_channel_fixture', root / '__init__.py', submodule_search_locations=[str(root)])
native = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = native
spec.loader.exec_module(native)
manager = PluginManager()
manager._discovered = True
ctx = PluginContext(PluginManifest(name='wiki-automation', version='0.0.0', source='user'), manager)
ready = Future()
stopper = {}

async def serve_control():
    stop = asyncio.Event()
    stopper.update(loop=asyncio.get_running_loop(), stop=stop)
    server = GatewayControlServer(home=home, verb_handlers={'identify': lambda: {'protocol': 1, 'pid': os.getpid(), 'hermes_home': str(home)}})
    try:
        ready.set_result(await server.start())
        await stop.wait()
    finally:
        await server.stop()

with patch('hermes_cli.plugins.get_plugin_manager', return_value=manager):
    try:
        if '--discover' in sys.argv[2:]:
            manager._discovered = False
            manager.discover_and_load()
            guards = [callback for callback in manager._hooks.get('pre_tool_call', [])
                      if getattr(getattr(callback, 'func', None), '__name__', None) == 'draft_guard']
            if len(guards) != 1:
                raise RuntimeError('Real host discovery did not load exactly one drafting guard')
            package = guards[0].func.__globals__['__package__']
            runtime_probe = sys.modules[package + '.runtime_probe']
            load_mode = 'host-discovery'
        else:
            native.register(ctx)
            runtime_probe = sys.modules['wiki_peer_channel_fixture.runtime_probe']
            load_mode = 'direct-fixture-registration'
        copied = contextvars.copy_context()
        thread = threading.Thread(target=lambda: copied.run(asyncio.run, serve_control()), daemon=True)
        thread.start()
        if not ready.result(timeout=10):
            raise RuntimeError('Disposable host control socket did not bind')
        print(json.dumps({'pid': os.getpid(), 'loaded_code_hash': runtime_probe._LOADED_CODE_HASH,
                          'incarnation': runtime_probe._INCARNATION, 'load_mode': load_mode,
                          'native_source_root': str(Path(runtime_probe.__file__).parent),
                          'native_dispatch_initialized': 'model_tools' in sys.modules}), flush=True)
        for line in sys.stdin:
            command = line.strip()
            if command == 'stop':
                break
            if command == 'drop-guard':
                manager._hooks['pre_tool_call'].clear()
            print(json.dumps({'ack': command}), flush=True)
    finally:
        manager.unload()
        if stopper:
            stopper['loop'].call_soon_threadsafe(stopper['stop'].set)
            thread.join(timeout=10)
        reset_hermes_home_override(token)
