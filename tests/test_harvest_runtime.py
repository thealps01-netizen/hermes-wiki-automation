"""Native host lifecycle, real bounded reads and real engine subprocesses in a disposable profile."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch


class HarvestRuntimeTests(unittest.TestCase):
    def test_native_completed_turn_only_finishes_after_all_captured_inputs_were_read(self):
        self.exercise_native_harvest(False)

    def test_schema2_native_harvest_uses_separate_code_data_and_captured_settings(self):
        self.exercise_native_harvest(True)

    def test_completion_lists_the_accepted_submissions_not_the_model_claim(self):
        self.exercise_native_harvest(False, drafted=True)

    def exercise_native_harvest(self, separated, drafted=False):
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
        from cron.execution_identity import enter_cron_execution, exit_cron_execution
        from cron.jobs import save_jobs
        root = Path(__file__).resolve().parents[1]
        engine_source = Path(os.environ['WIKI_ENGINE_TEST_DIR'])
        spec = importlib.util.spec_from_file_location('wiki_harvest_native_fixture', root / '__init__.py', submodule_search_locations=[str(root)])
        native = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = native
        spec.loader.exec_module(native)
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            engine, data, wiki = home / 'engine', home / 'data', home / 'wiki'
            engine.mkdir()
            data.mkdir()
            (wiki / '.llm-wiki').mkdir(parents=True)
            (wiki / '.llm-wiki/project.json').write_text('{"id":"fixture"}')
            (wiki / 'raw/sources').mkdir(parents=True)
            (wiki / 'raw/evidence').mkdir(parents=True)
            for source in engine_source.glob('*.py'):
                shutil.copy2(source, engine / source.name)
            settings_file = (data if separated else engine) / 'settings.json'
            settings_file.write_bytes(json.dumps({'project_root': str(wiki), 'project_id': 'fixture', 'audit_dir': str(data), 'hermes_home': str(home), 'harvest_workflow_enabled': True,
                'harvest': {'agents': {'hermes': False, 'codex': True, 'claude': False, 'antigravity': False}}}).encode())
            if separated:
                location = home / 'state/wiki-automation/location.json'
                location.parent.mkdir(parents=True)
                location.write_bytes(json.dumps({'schema': 2, 'engine_dir': str(engine), 'audit_dir': str(data)}).encode())
            (home / 'config.yaml').write_text('plugins:\n  entries:\n    wiki-automation:\n      settings:\n        draft_job_id: fixture-job\n        harvest_workflow_enabled: true\n')
            codex = home / 'codex'
            (codex / 'sessions').mkdir(parents=True)
            record = {'type': 'response_item', 'timestamp': (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                'payload': {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': 'Owner selected this isolated fixture; no invented success.'}]}}
            (codex / 'sessions/fixture.jsonl').write_bytes(json.dumps(record).encode() + b'\n')
            home_token = set_hermes_home_override(home)
            manager = PluginManager()
            manager._discovered = True
            ctx = PluginContext(PluginManifest(name='wiki-automation', version='0.0.0', source='user'), manager)
            execution_token = None
            try:
                job = {'id': 'fixture-job', 'enabled': True, 'enabled_toolsets': ['wiki_draft', 'no_mcp']}
                save_jobs([job])
                with patch.dict(os.environ, {'LLMWIKI_AUDIT_DIR': '' if separated else str(engine), 'LLMWIKI_SETTINGS': '', 'CODEX_HOME': str(codex)}), \
                        patch('hermes_cli.plugins.get_plugin_manager', return_value=manager):
                    native.register(ctx)
                    execution_token = enter_cron_execution(job, 'fixture-execution', {'source': 'builtin'})
                    original_settings = settings_file.read_bytes()
                    foreign = json.loads(original_settings)
                    foreign['hermes_home'] = str(home / 'foreign-profile')
                    settings_file.write_bytes(json.dumps(foreign).encode())
                    manager.invoke_hook('on_session_start', session_id='fixture-session')
                    self.assertFalse((data / 'inbox').exists(), 'A foreign profile was collected before owner binding was checked')
                    settings_file.write_bytes(original_settings)
                    disabled = json.loads(original_settings)
                    disabled['harvest_workflow_enabled'] = False
                    settings_file.write_bytes(json.dumps(disabled).encode())
                    manager.invoke_hook('on_session_start', session_id='fixture-session')
                    self.assertFalse((data / 'inbox').exists(), 'Host collection ignored the selected engine activation gate')
                    settings_file.write_bytes(original_settings)
                    manager.invoke_hook('on_session_start', session_id='fixture-session')
                    runs = list((data / 'inbox').glob('*/run.json')) if (data / 'inbox').exists() else []
                    self.assertEqual(len(runs), 1, 'Configured native lifecycle never collected a bound run')
                    manifest = json.loads(runs[0].read_bytes())
                    self.assertEqual(manifest['execution_id'], 'fixture-execution')
                    self.assertEqual(manifest['job_id'], 'fixture-job')
                    manager.invoke_hook('on_session_start', session_id='fixture-session')
                    self.assertEqual(len(list((data / 'inbox').glob('*/run.json'))), 1,
                        'Repeated native start replaced the bound collection within one execution')
                    manager.invoke_hook('post_llm_call', session_id='fixture-session', assistant_response=json.dumps({
                        'status': 'no_candidates', 'candidate_refs': [], 'missing_evidence': []}))
                    manager.invoke_hook('on_session_end', session_id='fixture-session', completed=True, failed=False, interrupted=False)
                    self.assertFalse((data / 'harvest-state.json').exists(), 'An unread input was silently marked processed')
                    attempt = runs[0].parent / 'attempt.json'
                    def stop_code():
                        return json.loads(attempt.read_bytes())['end']['stop']['code']
                    self.assertEqual(json.loads(attempt.read_bytes())['start']['session_id'], 'fixture-session')
                    self.assertEqual(stop_code(), 'unread_input', 'An unread input stopped the run without saying so')
                    from wiki_harvest_native_fixture.draft_security import draft_call
                    changed_name = list(manifest['input_hashes'])[-1]
                    changed_file = runs[0].parent / changed_name
                    original_input = changed_file.read_bytes()
                    for name in manifest['input_hashes']:
                        if name == changed_name:
                            changed_file.write_bytes(b'Temporary text not in the captured input snapshot')
                        result = json.loads(draft_call(ctx, 'read', {'run_id': manifest['run'], 'path': name}))
                        if name == changed_name:
                            self.assertIn('error', result, 'Noncaptured content was returned to the drafting model')
                            self.assertNotIn('text', result)
                            changed_file.write_bytes(original_input)
                        else:
                            self.assertNotIn('error', result)
                            self.assertFalse(result['truncated'])
                    manager.invoke_hook('on_session_end', session_id='fixture-session', completed=True, failed=False, interrupted=False)
                    self.assertFalse((data / 'harvest-state.json').exists(), 'A restored file disguised a read of noncaptured input bytes')
                    with patch.dict(os.environ, {'LLMWIKI_SETTINGS': str(home / 'unselected-missing-settings.json')}):
                        captured_read = json.loads(draft_call(ctx, 'read', {'run_id': manifest['run'], 'path': changed_name}))
                        self.assertNotIn('error', captured_read, 'Bound native drafting re-resolved settings after collection')
                    accepted = []
                    if drafted:
                        # One submission the engine accepts and one it refuses; the model's final list then
                        # names only the refused one, so the outcome can only be right if it comes from the host.
                        source = '# Fixture decision\n\n## Decisions\n\n- The owner kept the isolated fixture.\n'
                        reply = json.loads(draft_call(ctx, 'submit', {'run_id': manifest['run'], 'name': 'fixture-decision',
                            'metadata': {'kind': 'new', 'target': '2026-01-01-fixture-decision.md', 'summary': 'Fixture decision',
                                'why': 'Exercises host-recorded completion', 'evidence_ids': []}, 'source': source}))
                        self.assertNotIn('error', reply, 'A valid fixture candidate was refused')
                        accepted.append(reply['ref'])
                        refused = json.loads(draft_call(ctx, 'submit', {'run_id': manifest['run'], 'name': 'refused-decision',
                            'metadata': {'kind': 'new', 'target': 'not-a-source-name', 'summary': 'x', 'why': 'x', 'evidence_ids': []},
                            'source': source}))
                        self.assertIn('error', refused, 'An invalid candidate was accepted')
                    # The misspelled key repeats the 2026-10-19 drafting reply that left a finished run uncommitted.
                    wire = {'status': 'no_candidates', 'candret_refs': None,
                        'candidate_refs': [manifest['run'] + '/refused-decision'] if drafted else [],
                        'missing_evidence': ['No execution evidence was supplied.', 7],
                        'owner_report': 'Yeni aday yok; sağlanmayan çalıştırma kanıtı başarı diye yazılmadı.'}
                    rendered = manager.invoke_hook('transform_llm_output', session_id='fixture-session', response_text=json.dumps(wire))
                    rendered = next((value for value in rendered if isinstance(value, str)), None)
                    self.assertEqual(rendered, wire['owner_report'], 'Native data outcome leaked as a machine-only owner notification')
                    manager.invoke_hook('post_llm_call', session_id='fixture-session', assistant_response=rendered)
                    manager.invoke_hook('on_session_end', session_id='fixture-session', completed=False, failed=True, interrupted=False,
                                        turn_exit_reason='provider_error')
                    self.assertFalse((data / 'harvest-state.json').exists(), 'Scheduler failure was interpreted as domain completion')
                    self.assertEqual(stop_code(), 'turn_failed')
                    self.assertIn('provider_error', json.loads(attempt.read_bytes())['end']['stop']['detail'])
                    with patch.dict(os.environ, {'LLMWIKI_SETTINGS': str(home / 'unselected-missing-settings.json')}):
                        manager.invoke_hook('on_session_end', session_id='fixture-session', completed=True, failed=False, interrupted=False)
                    committed = json.loads(runs[0].read_bytes())
                    self.assertTrue(committed['committed'], 'A fully read run was not committed: a reply field or the candidate list decided completion')
                    self.assertEqual(committed['outcome']['candidate_refs'], accepted,
                        'Completion followed the model list instead of the submissions the engine accepted')
                    self.assertEqual(committed['outcome']['status'], 'drafted' if drafted else 'no_candidates')
                    self.assertEqual(committed['outcome']['missing_evidence'], ['No execution evidence was supplied.'])
                    self.assertIsNone(json.loads(attempt.read_bytes())['end']['stop'], 'A finished run kept a stop reason')
                    self.assertEqual(json.loads(runs[0].read_bytes())['input_hashes'], manifest['input_hashes'])
                    state = (data / 'harvest-state.json').read_bytes()
                    manager.invoke_hook('on_session_end', session_id='fixture-session', completed=True, failed=False, interrupted=False)
                    self.assertEqual((data / 'harvest-state.json').read_bytes(), state)
                    self.assertEqual(list((wiki / 'raw/sources').iterdir()), [])
            finally:
                exit_cron_execution(execution_token)
                reset_hermes_home_override(home_token)


if __name__ == '__main__':
    unittest.main()
