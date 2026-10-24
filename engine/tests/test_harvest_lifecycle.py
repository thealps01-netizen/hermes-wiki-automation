"""Disposable collection/outcome tests never read installed agent histories."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wiki_session_harvest as harvest
from workflow_store import WorkflowStore


class HarvestLifecycleTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.addCleanup(tmp.cleanup)
        self.audit = Path(tmp.name)
        self.run = self.audit / 'inbox/run-one'
        (self.run / 'conversations').mkdir(parents=True)
        (self.run / 'candidates').mkdir()
        (self.run / 'conversations/one.md').write_bytes(b'Owner said something; assistant claims success')
        self.manifest = {'run': 'run-one', 'project_id': 'fixture', 'execution_id': 'execution-one', 'job_id': 'job-one',
            'agents': {'hermes': '1 conversation(s)'}, 'cursors_to_commit': {'hermes': 100},
            'conversations': [{'files': ['conversations/one.md']}], 'committed': False,
            'input_hashes': {'conversations/one.md': hashlib.sha256((self.run / 'conversations/one.md').read_bytes()).hexdigest()}}
        (self.run / 'run.json').write_bytes(json.dumps(self.manifest).encode())
        self.outcome = {'execution_id': 'execution-one', 'job_id': 'job-one', 'status': 'no_candidates',
            'reviewed_inputs': self.manifest['input_hashes'], 'candidate_refs': [], 'missing_evidence': []}

    def finish(self, outcome=None):
        with WorkflowStore(self.audit / 'workflow.sqlite') as store:
            return harvest.finish_run(self.audit, 'run-one', self.outcome if outcome is None else outcome, store)

    def test_drafted_artifacts_are_complete_but_not_published(self):
        from draft_adapter import DraftAdapter
        wiki = self.audit / 'wiki'
        (wiki / '.llm-wiki').mkdir(parents=True)
        (wiki / '.llm-wiki/project.json').write_text('{"id":"fixture"}')
        (wiki / 'raw/sources').mkdir(parents=True)
        (wiki / 'raw/evidence').mkdir(parents=True)
        adapter = DraftAdapter(wiki, self.audit / 'inbox', 'run-one', 'execution-one', 'job-one')
        metadata = {'kind': 'new', 'target': '2026-10-09-harvest-fixture.md', 'summary': 'Fixture decision',
            'why': 'The captured owner request, not an assistant execution claim', 'evidence_ids': []}
        source = '# Fixture\n\n## Decisions\n\n**1. Fixture.**\nEvidence: none (owner-directed).\n'
        ref = adapter.submit('fixture', metadata, source)
        before = {str(path): path.read_bytes() for path in wiki.rglob('*') if path.is_file()}
        outcome = {**self.outcome, 'status': 'drafted', 'candidate_refs': [ref]}
        result = self.finish(outcome)
        self.assertEqual(result['status'], 'drafted')
        self.assertIn(ref + ':source', result['candidate_hashes'])
        self.assertEqual(before, {str(path): path.read_bytes() for path in wiki.rglob('*') if path.is_file()})
        self.assertFalse((self.run / 'candidates/fixture/applied.json').exists())
        self.assertEqual(self.finish(outcome), result)

    def test_malformed_claude_history_is_not_reported_as_an_empty_reader(self):
        claude = self.audit / 'claude'
        (claude / 'project').mkdir(parents=True)
        (claude / 'project/corrupt.jsonl').write_bytes(b'{broken historical message\n')
        with self.assertRaises(harvest.HarvestError):
            list(harvest.read_claude(claude, 0, float('inf')))

    def test_malformed_codex_history_is_not_reported_as_an_empty_reader(self):
        codex = self.audit / 'codex'
        (codex / 'sessions').mkdir(parents=True)
        (codex / 'sessions/corrupt.jsonl').write_bytes(b'{broken historical message\n')
        with self.assertRaises(harvest.HarvestError):
            list(harvest.read_codex(codex, 0, float('inf')))

    def test_antigravity_reader_preserves_utf8_and_refuses_decode_loss(self):
        root = self.audit / 'antigravity'
        log = root / 'brain/utf8-fixture/.system_generated/logs/transcript_full.jsonl'
        log.parent.mkdir(parents=True)
        text = 'Owner decision: caf\u00e9, \u0131, \u4e2d\u6587'
        valid = {'type': 'USER_INPUT', 'content': '<USER_REQUEST>' + text + '</USER_REQUEST>', 'created_at': 100}
        log.write_bytes(json.dumps(valid, ensure_ascii=False).encode('utf-8') + b'\n')
        rows = list(harvest.read_antigravity(root, 0, 1000))
        self.assertEqual(rows[0][2], [(100.0, 'user', text)])
        log.write_bytes(b'{"type":"USER_INPUT","content":"owner \xff bytes","created_at":100}\n')
        with self.assertRaises((UnicodeError, harvest.HarvestError)):
            list(harvest.read_antigravity(root, 0, 1000))

    def collect(self, cfg, roots, readers=None, execution='execution-native'):
        """One host-bound collection; returns (exit code, last JSON line, manifest or None)."""
        import contextlib
        import io
        stream = io.StringIO()
        with patch.object(harvest.wikiconfig, 'load', return_value=cfg), \
                patch.object(harvest.wikiconfig, 'project_root', return_value=self.audit), \
                patch.object(harvest.wikiconfig, 'audit_dir', return_value=self.audit), \
                patch.object(harvest, 'agent_roots', return_value=roots), \
                patch.dict(harvest.READERS, readers or {}), contextlib.redirect_stdout(stream):
            code = harvest.main(['--execution-id', execution, '--job-id', 'job-native'])
        report = json.loads(stream.getvalue().splitlines()[-1])
        run = report.get('run_id')
        manifest = json.loads((self.audit / 'inbox' / run / 'run.json').read_bytes()) if run else None
        return code, report, manifest

    def complete(self, report, manifest, execution='execution-native'):
        outcome = {'execution_id': execution, 'job_id': 'job-native', 'status': 'no_candidates',
            'reviewed_inputs': manifest['input_hashes'], 'candidate_refs': [], 'missing_evidence': []}
        with WorkflowStore(self.audit / 'workflow.sqlite') as store:
            return harvest.finish_run(self.audit, report['run_id'], outcome, store)

    def test_malformed_antigravity_history_waits_alone_and_never_advances_its_cursor(self):
        import time
        root = self.audit / 'antigravity'
        log = root / 'brain/fixture-id/.system_generated/logs/transcript_full.jsonl'
        log.parent.mkdir(parents=True)
        valid = {'type': 'USER_INPUT', 'content': '<USER_REQUEST>Retain this decision</USER_REQUEST>',
            'created_at': time.time() - 7200}
        log.write_bytes(json.dumps(valid).encode() + b'\n{"type":"USER_INPUT","content":"truncated owner decision\n')
        cfg = {'project_id': 'fixture', 'harvest': {'agents': {name: name in ('antigravity', 'hermes') for name in harvest.READERS}}}
        hermes = lambda root, since, until: [('one', 'Fixture', [(until - 10, 'user', 'Hermes owner decision')])]
        code, report, manifest = self.collect(cfg, {'antigravity': root, 'hermes': self.audit}, {'hermes': hermes})
        self.assertEqual(code, 0, 'An unreadable agent stopped the agents that were read')
        self.assertEqual(report['status'], 'partial', 'Truncated history was reported as a complete collection')
        self.assertTrue(report['wakeAgent'])
        self.assertIn('UNREADABLE', manifest['agents']['antigravity'])
        self.assertEqual(manifest['agents']['hermes'], '1 conversation(s)')
        self.assertNotIn('antigravity', manifest['cursors_to_commit'])
        self.assertFalse(any(key.startswith('antigravity:') for key in manifest['done_to_commit']))
        self.complete(report, manifest)
        state = harvest.load_state(self.audit / 'harvest-state.json')
        self.assertIn('hermes', state['cursors'])
        self.assertNotIn('antigravity', state['cursors'], 'Unreadable history advanced its cursor')
        self.assertNotIn('Retain this decision', ''.join(
            (self.audit / 'inbox' / report['run_id'] / name).read_text(encoding='utf-8') for name in manifest['input_hashes']))

    def test_an_agent_that_is_not_installed_is_skipped_and_the_others_complete(self):
        cfg = {'harvest': {'agents': {name: name in ('hermes', 'codex', 'claude') for name in harvest.READERS}}}
        hermes = lambda root, since, until: [('one', 'Fixture', [(until - 10, 'user', 'Hermes owner decision')])]
        absent = self.audit / 'not-installed'
        code, report, manifest = self.collect(cfg, {'hermes': self.audit, 'codex': absent, 'claude': absent / 'projects'},
                                              {'hermes': hermes})
        self.assertEqual(code, 0, 'A missing agent folder stopped the whole harvest')
        self.assertEqual(report['status'], 'collected')
        self.assertTrue(report['wakeAgent'])
        self.assertTrue(manifest['agents']['codex'].startswith('not found'))
        self.assertTrue(manifest['agents']['claude'].startswith('not found'))
        self.assertEqual(set(manifest['cursors_to_commit']), {'hermes'})
        self.assertEqual(self.complete(report, manifest)['status'], 'no_candidates')
        state = harvest.load_state(self.audit / 'harvest-state.json')
        self.assertEqual(set(state['cursors']), {'hermes'})

    def test_last_run_reports_the_newest_host_bound_run_and_its_outcome(self):
        import contextlib
        import io
        def ask(root=None):
            stream = io.StringIO()
            with patch.object(harvest.wikiconfig, 'load', return_value={}), \
                    patch.object(harvest.wikiconfig, 'project_root', return_value=self.audit), \
                    patch.object(harvest.wikiconfig, 'audit_dir', return_value=root or self.audit), contextlib.redirect_stdout(stream):
                code = harvest.main(['--last-run'])
            return code, json.loads(stream.getvalue().splitlines()[-1])
        legacy = self.audit / 'inbox/99999999-legacy'
        legacy.mkdir(parents=True)
        (legacy / 'run.json').write_text('{"run": "99999999-legacy", "committed": false}')
        self.assertEqual(ask(), (0, {'ok': True, 'run': 'run-one', 'execution_id': 'execution-one', 'job_id': 'job-one',
            'created': None, 'committed': False, 'status': None, 'agents': {'hermes': '1 conversation(s)'}}))
        self.finish()
        code, row = ask()
        self.assertEqual((code, row['committed'], row['status']), (0, True, 'no_candidates'))
        before = {str(path): path.read_bytes() for path in self.audit.rglob('*') if path.is_file()}
        broken = self.audit / 'inbox/run-two'
        broken.mkdir()
        (broken / 'run.json').write_bytes(b'{broken')
        code, row = ask()
        self.assertEqual(code, 1)
        self.assertFalse(row['ok'])
        self.assertIn('run-two', row['error'])
        broken.joinpath('run.json').unlink()
        broken.rmdir()
        self.assertEqual(before, {str(path): path.read_bytes() for path in self.audit.rglob('*') if path.is_file()},
                         '--last-run wrote to the data root')
        empty = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.addCleanup(empty.cleanup)
        self.assertEqual(ask(Path(empty.name)), (0, {'ok': True, 'run': None}))

    def test_host_outcome_is_disabled_unless_explicitly_activated(self):
        import io
        wire = json.dumps({'run_id': 'run-one', 'outcome': self.outcome}).encode()
        for flag in (None, False, 'true', 1):
            with self.subTest(flag=flag), patch.object(harvest.wikiconfig, 'load', return_value={
                    'hermes_home': str(self.audit), 'harvest_workflow_enabled': flag}), \
                    patch.object(harvest.wikiconfig, 'project_root', return_value=self.audit), \
                    patch.object(harvest.wikiconfig, 'audit_dir', return_value=self.audit), \
                    patch.object(sys, 'stdin', io.TextIOWrapper(io.BytesIO(wire))):
                self.assertEqual(harvest.main(['--host-outcome', '--home', str(self.audit),
                    '--execution-id', 'execution-one', '--job-id', 'job-one']), 1)
                self.assertFalse((self.audit / 'harvest-state.json').exists())
                self.assertFalse((self.audit / 'workflow.sqlite').exists())

    def test_generated_prompt_uses_only_the_bound_data_contract(self):
        text = (Path(__file__).resolve().parents[1] / 'harvest_prompt.md').read_text(encoding='utf-8')
        self.assertNotIn('--commit', text, 'Prompt still requests an agent-side completion bypass')
        self.assertIn('wiki_draft_read', text)
        self.assertIn('wiki_draft_submit', text)
        self.assertIn('no_candidates', text)

    def test_bound_empty_collection_is_a_durable_domain_input(self):
        import contextlib
        import io
        cfg = {'harvest': {'agents': {name: name == 'hermes' for name in harvest.READERS}}}
        with patch.object(harvest.wikiconfig, 'load', return_value=cfg), \
                patch.object(harvest.wikiconfig, 'project_root', return_value=self.audit), \
                patch.object(harvest.wikiconfig, 'audit_dir', return_value=self.audit), \
                patch.object(harvest, 'agent_roots', return_value={'hermes': self.audit}), \
                patch.dict(harvest.READERS, {'hermes': lambda *args: []}):
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                self.assertEqual(harvest.main(['--execution-id', 'execution-native', '--job-id', 'job-native']), 0)
            report = json.loads(stream.getvalue().splitlines()[-1])
            self.assertIn('run_id', report, 'Empty native collection has no durable domain outcome to finish')
            manifest = json.loads((self.audit / 'inbox' / report['run_id'] / 'run.json').read_bytes())
            self.assertEqual(manifest['conversations'], [])
            self.assertFalse(manifest['committed'])
        self.assertFalse((self.audit / 'harvest-state.json').exists())

    def test_collector_reports_reader_failure_as_partial_not_empty_success(self):
        cfg = {'harvest': {'agents': {name: name == 'hermes' for name in harvest.READERS}}}
        broken = lambda *args: (_ for _ in ()).throw(ValueError('Fixture unreadable'))
        code, report, manifest = self.collect(cfg, {'hermes': self.audit}, {'hermes': broken})
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'partial')
        self.assertFalse(report['wakeAgent'])
        self.assertIn('UNREADABLE', manifest['agents']['hermes'])
        self.assertEqual(manifest['cursors_to_commit'], {})
        self.assertFalse((self.audit / 'harvest-state.json').exists())

    def test_collector_captures_a_unique_host_bound_snapshot(self):
        import contextlib
        import io
        cfg = {'harvest': {'agents': {name: name == 'hermes' for name in harvest.READERS}}}
        reader = lambda root, since, until: [('one', 'Fixture', [(1, 'user', 'Full owner text')])]
        manifests = []
        with patch.object(harvest.wikiconfig, 'load', return_value=cfg), \
                patch.object(harvest.wikiconfig, 'project_root', return_value=self.audit), \
                patch.object(harvest.wikiconfig, 'audit_dir', return_value=self.audit), \
                patch.object(harvest, 'agent_roots', return_value={'hermes': self.audit}), \
                patch.dict(harvest.READERS, {'hermes': reader}):
            for occurrence in range(2):
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    self.assertEqual(harvest.main(['--execution-id', 'execution-native', '--job-id', 'job-native']), 0)
                reply = json.loads(stream.getvalue().splitlines()[-1])
                manifest = json.loads((self.audit / 'inbox' / reply['run_id'] / 'run.json').read_bytes())
                self.assertEqual(manifest['execution_id'], 'execution-native')
                self.assertEqual(manifest['job_id'], 'job-native')
                for name, digest in manifest['input_hashes'].items():
                    self.assertEqual(hashlib.sha256((self.audit / 'inbox' / reply['run_id'] / name).read_bytes()).hexdigest(), digest)
                manifests.append(reply['run_id'])
        self.assertEqual(len(set(manifests)), 2)

    def test_real_process_death_replays_each_cursor_and_manifest_checkpoint(self):
        import candidate_apply
        import shutil
        import subprocess
        points = []
        def make_case(name):
            case = self.audit / name
            shutil.copytree(self.run, case / 'inbox/run-one')
            (case / 'outcome.json').write_bytes(json.dumps(self.outcome).encode())
            return case
        trace = make_case('trace')
        with patch.object(candidate_apply, '_checkpoint', side_effect=points.append), WorkflowStore(trace / 'workflow.sqlite') as store:
            harvest.finish_run(trace, 'run-one', self.outcome, store)
        recovered = 0
        for number, point in enumerate(dict.fromkeys(points)):
            with self.subTest(checkpoint=point):
                case = make_case(f'crash-{number}')
                worker = subprocess.run([sys.executable, str(Path(__file__).with_name('harvest_finish_worker.py')), str(case), point],
                    capture_output=True, timeout=20)
                self.assertEqual(worker.returncode, 91, worker.stderr.decode(errors='replace'))
                with WorkflowStore(case / 'workflow.sqlite') as store:
                    harvest.finish_run(case, 'run-one', self.outcome, store)
                    count = store.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0]
                    self.assertEqual(count, 1)
                    self.assertEqual(harvest.load_state(case / 'harvest-state.json')['cursors']['hermes'], 100)
                    state_bytes = (case / 'harvest-state.json').read_bytes()
                    harvest.finish_run(case, 'run-one', self.outcome, store)
                    self.assertEqual((case / 'harvest-state.json').read_bytes(), state_bytes)
                self.assertTrue(json.loads((case / 'inbox/run-one/run.json').read_bytes())['committed'])
                recovered += 1
        self.assertGreaterEqual(recovered, 6)
        print(f'HARVEST_INTERRUPTION_CASES recovered={recovered}')

    def test_legacy_agent_commit_cannot_mark_processing_complete(self):
        with patch.object(harvest.wikiconfig, 'load', return_value={}), \
                patch.object(harvest.wikiconfig, 'project_root', return_value=self.audit), \
                patch.object(harvest.wikiconfig, 'audit_dir', return_value=self.audit):
            self.assertEqual(harvest.main(['--commit', 'run-one']), 1)
        self.assertTrue(self.run.exists())
        self.assertFalse((self.audit / 'harvest-state.json').exists())
        self.assertFalse(json.loads((self.run / 'run.json').read_bytes())['committed'])

    def test_corrupt_state_is_not_first_run(self):
        path = self.audit / 'harvest-state.json'
        path.write_bytes(b'{broken')
        with self.assertRaises(RuntimeError):
            harvest.load_state(path)
        self.assertEqual(path.read_bytes(), b'{broken')

    def test_no_candidates_is_explicit_completion(self):
        with self.assertRaises(RuntimeError):
            self.finish({'assistant_said': 'success'})
        self.assertFalse((self.audit / 'harvest-state.json').exists())
        result = self.finish()
        self.assertEqual(result['status'], 'no_candidates')
        self.assertEqual(harvest.load_state(self.audit / 'harvest-state.json')['cursors']['hermes'], 100)

    def test_repeated_finish_is_noop_and_old_run_cannot_rewind(self):
        (self.audit / 'harvest-state.json').write_text('{"cursors":{"hermes":200}}')
        first = self.finish()
        path = self.audit / 'harvest-state.json'
        stamp = path.stat().st_mtime_ns
        self.assertEqual(self.finish(), first)
        self.assertEqual(path.stat().st_mtime_ns, stamp)
        self.assertEqual(harvest.load_state(path)['cursors']['hermes'], 200)

    def test_reader_failure_does_not_advance(self):
        for status in ('UNREADABLE (ValueError)', 'not found (fixture)', 'off'):
            with self.subTest(status=status):
                for field, value in (('cursors_to_commit', {'hermes': 100, 'codex': 100}),
                                     ('done_to_commit', {'codex:one': 100})):
                    manifest = {**self.manifest, 'agents': {**self.manifest['agents'], 'codex': status}, field: value}
                    (self.run / 'run.json').write_bytes(json.dumps(manifest).encode())
                    with self.assertRaises(RuntimeError):
                        self.finish()
                    self.assertFalse((self.audit / 'harvest-state.json').exists())
        self.manifest['agents']['codex'] = 'UNREADABLE (ValueError)'
        (self.run / 'run.json').write_bytes(json.dumps(self.manifest).encode())
        self.finish()
        state = harvest.load_state(self.audit / 'harvest-state.json')
        self.assertEqual(state['cursors'], {'hermes': 100})

    def test_incomplete_or_changed_artifacts_cannot_finish(self):
        (self.run / 'conversations/one.md').unlink()
        with self.assertRaises(RuntimeError):
            self.finish()
        self.assertFalse((self.audit / 'harvest-state.json').exists())

    def collect_rounds(self, conversations, budget, rounds):
        """Run collection then a completed outcome `rounds` times; return the conversation text each run saw."""
        import contextlib
        import io
        (self.audit / 'harvest-state.json').write_text('{"cursors":{"hermes":1}}')
        cfg = {'harvest': {'agents': {name: name == 'hermes' for name in harvest.READERS}, 'max_run_chars': budget}}
        reader = lambda root, since, until: [(cid, cid, [m for m in msgs if since < m[0] <= until])
                                             for cid, msgs in conversations
                                             if any(since < m[0] <= until for m in msgs)]
        seen = []
        with patch.object(harvest.wikiconfig, 'load', return_value=cfg), \
                patch.object(harvest.wikiconfig, 'project_root', return_value=self.audit), \
                patch.object(harvest.wikiconfig, 'audit_dir', return_value=self.audit), \
                patch.object(harvest, 'agent_roots', return_value={'hermes': self.audit}), \
                patch.dict(harvest.READERS, {'hermes': reader}):
            for number in range(rounds):
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    code = harvest.main(['--execution-id', f'execution-{number}', '--job-id', 'job-native'])
                reply = json.loads(stream.getvalue().splitlines()[-1])
                if not reply.get('run_id'):
                    self.assertEqual(code, 0)
                    break
                run = self.audit / 'inbox' / reply['run_id']
                manifest = json.loads((run / 'run.json').read_bytes())
                if not manifest['conversations']:
                    break
                read = sum(len((run / name).read_text(encoding='utf-8')) for name in manifest['input_hashes'])
                texts = {row['id']: '\n'.join((run / part).read_text(encoding='utf-8') for part in row['files'])
                         for row in manifest['conversations']}
                seen.append((texts, read))
                outcome = {'execution_id': f'execution-{number}', 'job_id': 'job-native', 'status': 'no_candidates',
                           'reviewed_inputs': manifest['input_hashes'], 'candidate_refs': [], 'missing_evidence': []}
                with WorkflowStore(self.audit / 'workflow.sqlite') as store:
                    harvest.finish_run(self.audit, reply['run_id'], outcome, store)
        return seen

    def test_backlog_is_packed_by_whole_conversation_within_the_run_budget(self):
        index = len(harvest.source_index(self.audit))
        talk = lambda tag, start: [(start + i, 'user', f'{tag} owner message {i} ' + 'x' * 300) for i in range(3)]
        conversations = [('alpha', talk('alpha', 10)), ('beta', talk('beta', 20)), ('gamma', talk('gamma', 30))]
        one = len('\n'.join(harvest.render('alpha', conversations[0][1], 60000)[0]))
        budget = index + 2 * one + 200
        seen = self.collect_rounds(conversations, budget, 4)
        self.assertEqual([sorted(texts) for texts, _ in seen], [['alpha', 'beta'], ['gamma']])
        for texts, read in seen:
            self.assertLessEqual(read, budget)
        for cid, msgs in conversations:
            text = next(texts[cid] for texts, _ in seen if cid in texts)
            for _, _, body in msgs:
                self.assertEqual(text.count(body), 1)

    def test_a_conversation_larger_than_the_budget_is_split_by_time_and_every_message_is_read_once(self):
        index = len(harvest.source_index(self.audit))
        msgs = [(10 + i, 'user', f'long owner message {i} ' + 'y' * 400) for i in range(6)]
        later = [(40, 'user', 'later conversation message')]
        seen = self.collect_rounds([('long', msgs), ('later', later)], index + 1000, 10)
        self.assertGreater(len(seen), 2)
        joined = '\n'.join(text for texts, _ in seen for text in texts.values())
        for _, _, body in msgs + later:
            self.assertEqual(joined.count(body), 1, body[:24])
        order = [cid for texts, _ in seen for cid in texts]
        self.assertEqual(order[-1], 'later')
        self.assertEqual(harvest.load_state(self.audit / 'harvest-state.json').get('done', {}), {})

    def test_user_text_is_not_silently_clipped(self):
        text = 'u' * (harvest.USER_CLIP + 17)
        rendered, clip = harvest.render('Fixture', [(1, 'user', text)], 10000)
        self.assertIn(text, '\n'.join(rendered))


if __name__ == '__main__':
    unittest.main()
