"""Scoped drafting must be enforced by the real host dispatcher, not only schemas."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class DraftDispatchTests(unittest.TestCase):
    def test_draft_context_blocks_alternate_execution_surfaces(self):
        source = Path(__file__).resolve().parents[1] / 'draft_security.py'
        self.assertTrue(source.exists(), 'Missing drafting enforcement adapter')
        spec = importlib.util.spec_from_file_location('wiki_draft_security_test', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        from cron.execution_identity import enter_cron_execution, exit_cron_execution
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            (home / 'config.yaml').write_text('plugins:\n  entries:\n    wiki-automation:\n      settings:\n        draft_job_id: fixture-job\n', encoding='utf-8')
            token = set_hermes_home_override(home)
            import model_tools
            manager = PluginManager()
            manager._discovered = True
            context = PluginContext(PluginManifest(name='wiki-automation', version='0.0.0',
                                                  description='isolated fixture', source='user'), manager)
            try:
                with patch.object(context, 'get_config', side_effect=lambda key, default=None: 'fixture-job' if key == 'draft_job_id' else default):
                    module.register(context)
                with patch('hermes_cli.plugins.get_plugin_manager', return_value=manager):
                    identity = enter_cron_execution({'id': 'fixture-job'}, 'fixture-execution', {})
                    try:
                        for name, arguments in [
                            ('terminal', {'command': 'must never execute'}),
                            ('write_file', {'path': str(home / 'live.md'), 'content': 'denied'}),
                            ('execute_code', {'code': 'raise RuntimeError()'}),
                            ('browser_exec', {'code': 'raise RuntimeError()'}),
                            ('delegate_task', {'tasks': [{'goal': 'must never execute'}]}),
                            ('computer_use', {'action': 'screenshot'}),
                            ('manage_connections', {'action': 'connect', 'connectors': ['gmail']}),
                        ]:
                            with self.subTest(tool=name):
                                response = json.loads(model_tools.handle_function_call(name, arguments,
                                    enabled_tools=['wiki_draft_read', 'wiki_draft_submit'],
                                    enabled_toolsets=['wiki_draft']))
                                self.assertIn('error', response)
                        self.assertFalse((home / 'live.md').exists())
                        self.assertEqual(module.draft_guard(context, tool_name='wiki_draft_read', args={}), None)
                        definitions = model_tools.get_tool_definitions(enabled_toolsets=['wiki_draft'], quiet_mode=True, skip_tool_search_assembly=True)
                        self.assertEqual({entry['function']['name'] for entry in definitions}, {'wiki_draft_read', 'wiki_draft_submit'})
                        described = json.loads(model_tools.handle_function_call('tool_describe', {'names': ['terminal', 'write_file']}, enabled_toolsets=['wiki_draft']))
                        self.assertNotIn('terminal', str(described.get('tools', {})))
                    finally:
                        exit_cron_execution(identity)
                    self.assertEqual(module.draft_guard(context, tool_name='terminal', args={}), None)
            finally:
                manager.unload_plugin('wiki-automation') if 'wiki-automation' in manager._plugins else None
                reset_hermes_home_override(token)

    def test_registered_tool_reads_bound_fixture_through_engine(self):
        import sys
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
        from cron.execution_identity import enter_cron_execution, exit_cron_execution
        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / '__init__.py').exists(), 'Missing native plugin entry point')
        spec = importlib.util.spec_from_file_location('wiki_adapter_fixture', root / '__init__.py', submodule_search_locations=[str(root)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            wiki, data = home / 'wiki', home / 'data'
            (wiki / '.llm-wiki').mkdir(parents=True)
            (wiki / '.llm-wiki/project.json').write_text('{"id":"fixture"}')
            (wiki / 'raw/sources').mkdir(parents=True)
            (wiki / 'raw/evidence').mkdir(parents=True)
            run = data / 'inbox/run'
            (run / 'conversations').mkdir(parents=True)
            (run / 'run.json').write_text(json.dumps({'execution_id': 'execution', 'job_id': 'job', 'project_id': 'fixture'}))
            (run / 'conversations/session.md').write_bytes(b'Owner chose the fixture.\n')
            engine = Path(os.environ['WIKI_ENGINE_TEST_DIR'])
            stage = home / 'engine'
            stage.mkdir()
            for name in ('draft_adapter.py', 'workflow_paths.py', 'wiki_candidates.py', 'wikiconfig.py', 'evidence_store.py',
                         'evidence_requests.py'):
                (stage / name).write_bytes((engine / name).read_bytes())
            (stage / 'settings.json').write_text(json.dumps({'project_root': str(wiki), 'project_id': 'fixture', 'audit_dir': str(data), 'hermes_home': str(home)}))
            (home / 'config.yaml').write_text('plugins:\n  entries:\n    wiki-automation:\n      settings:\n        draft_job_id: job\n')
            token = set_hermes_home_override(home)
            manager = PluginManager()
            manager._discovered = True
            ctx = PluginContext(PluginManifest(name='wiki-automation', version='0.0.0', source='user'), manager)
            identity = enter_cron_execution({'id': 'job'}, 'execution', {})
            try:
                module.register(ctx)
                import model_tools
                with patch.dict(os.environ, {'LLMWIKI_AUDIT_DIR': str(stage)}), patch('hermes_cli.plugins.get_plugin_manager', return_value=manager):
                    result = json.loads(model_tools.handle_function_call('wiki_draft_read', {'run_id': 'run', 'path': 'conversations/session.md'}, enabled_toolsets=['wiki_draft']))
                    self.assertEqual(result.get('text'), 'Owner chose the fixture.\n', result)
                    denied = json.loads(model_tools.handle_function_call('wiki_draft_read', {'run_id': 'run', 'path': '../settings.json'}, enabled_toolsets=['wiki_draft']))
                    self.assertIn('error', denied)
            finally:
                exit_cron_execution(identity)
                reset_hermes_home_override(token)

    def test_owner_readiness_requires_bound_drafting_handlers(self):
        from functools import partial
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
        from cron.jobs import save_jobs
        from tools.registry import registry
        spec = importlib.util.spec_from_file_location('isolated_draft_handler_readiness', Path(__file__).resolve().parents[1] / 'draft_security.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            (home / 'config.yaml').write_text('plugins:\n  entries:\n    wiki-automation:\n      settings:\n        draft_job_id: job\n')
            token = set_hermes_home_override(home)
            manager = PluginManager()
            manager._discovered = True
            ctx = PluginContext(PluginManifest(name='wiki-automation', version='0.0.0', source='user'), manager)
            try:
                with patch('hermes_cli.plugins.get_plugin_manager', return_value=manager):
                    module.register(ctx)
                    save_jobs([{'id': 'job', 'enabled': True, 'enabled_toolsets': ['wiki_draft', 'no_mcp']}])
                    self.assertTrue(module.approval_runtime_ready())
                    entry = registry.get_entry('wiki_draft_submit')
                    registry.deregister('wiki_draft_submit', scope=manager.scope_key)
                    self.assertFalse(module.approval_runtime_ready(), 'A missing submission handler was reported ready')
                    for handler in (lambda args, **kwargs: '{}', partial(module.draft_call, ctx, 'read')):
                        ctx.register_tool(name='wiki_draft_submit', toolset='wiki_draft', schema=entry.schema, handler=handler)
                        self.assertFalse(module.approval_runtime_ready(), 'A foreign or wrong-operation handler was reported ready')
                    ctx.register_tool(name='wiki_draft_submit', toolset='wiki_draft', schema=entry.schema, handler=partial(module.draft_call, ctx, 'submit'))
                    self.assertTrue(module.approval_runtime_ready())
            finally:
                manager.unload()
                reset_hermes_home_override(token)

    def test_owner_readiness_requires_loaded_guard_and_exact_job_tools(self):
        source = Path(__file__).resolve().parents[1] / 'draft_security.py'
        spec = importlib.util.spec_from_file_location('isolated_draft_readiness', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
        from cron.jobs import save_jobs
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            home = Path(temp)
            (home / 'config.yaml').write_text('plugins:\n  entries:\n    wiki-automation:\n      settings:\n        draft_job_id: job\n')
            token = set_hermes_home_override(home)
            manager = PluginManager()
            manager._discovered = True
            ctx = PluginContext(PluginManifest(name='wiki-automation', version='0.0.0', source='user'), manager)
            try:
                with patch('hermes_cli.plugins.get_plugin_manager', return_value=manager):
                    self.assertFalse(module.approval_runtime_ready())
                    module.register(ctx)
                    save_jobs([{'id': 'job', 'enabled': True, 'enabled_toolsets': None}])
                    self.assertFalse(module.approval_runtime_ready())
                    save_jobs([{'id': 'job', 'enabled': True, 'enabled_toolsets': ['wiki_draft']}])
                    self.assertFalse(module.approval_runtime_ready())
                    save_jobs([{'id': 'job', 'enabled': True, 'enabled_toolsets': ['wiki_draft', 'no_mcp']}])
                    self.assertTrue(module.approval_runtime_ready())
                    save_jobs([{'id': 'job', 'enabled': True, 'no_agent': True, 'enabled_toolsets': ['wiki_draft', 'no_mcp']}])
                    self.assertFalse(module.approval_runtime_ready())
                    save_jobs([{'id': 'job', 'enabled': True, 'enabled_toolsets': ['wiki_draft', 'no_mcp', 'terminal']}])
                    self.assertFalse(module.approval_runtime_ready())
            finally:
                reset_hermes_home_override(token)


if __name__ == '__main__':
    unittest.main()
