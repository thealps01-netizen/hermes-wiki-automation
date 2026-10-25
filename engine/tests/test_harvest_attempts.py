"""Why a harvest run stopped and what it cost are recorded per run, using disposable fixtures only."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wiki_session_harvest as harvest
from workflow_store import WorkflowStore

SESSION_COLUMNS = ('id TEXT, model TEXT, started_at REAL, ended_at REAL, end_reason TEXT, input_tokens INTEGER, '
                   'output_tokens INTEGER, cache_read_tokens INTEGER, cache_write_tokens INTEGER, '
                   'estimated_cost_usd REAL, actual_cost_usd REAL, cost_status TEXT')


class HarvestAttemptTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.addCleanup(tmp.cleanup)
        self.audit = Path(tmp.name)
        self.home = self.audit / 'home'
        self.home.mkdir()
        self.run = self.audit / 'inbox/run-one'
        (self.run / 'conversations').mkdir(parents=True)
        (self.run / 'candidates').mkdir()
        (self.run / 'conversations/one.md').write_bytes(b'Owner chose the fixture.')
        self.manifest = {'run': 'run-one', 'execution_id': 'execution-one', 'job_id': 'job-one', 'created': '2026-10-25T21:30:00',
            'agents': {'hermes': '1 conversation(s)'}, 'cursors_to_commit': {'hermes': 100},
            'conversations': [{'files': ['conversations/one.md']}], 'committed': False,
            'input_hashes': {'conversations/one.md': hashlib.sha256(b'Owner chose the fixture.').hexdigest()}}
        (self.run / 'run.json').write_bytes(json.dumps(self.manifest).encode())
        self.cfg = {'hermes_home': str(self.home), 'harvest_workflow_enabled': True}

    def main(self, argv, body=None, cfg=None):
        stream = io.StringIO()
        stdin = io.TextIOWrapper(io.BytesIO(json.dumps(body).encode())) if body is not None else sys.stdin
        with patch.object(harvest.wikiconfig, 'load', return_value=self.cfg if cfg is None else cfg), \
                patch.object(harvest.wikiconfig, 'project_root', return_value=self.audit), \
                patch.object(harvest.wikiconfig, 'audit_dir', return_value=self.audit), \
                patch.object(sys, 'stdin', stdin), contextlib.redirect_stdout(stream):
            code = harvest.main(argv)
        return code, json.loads(stream.getvalue().splitlines()[-1])

    def record(self, event, execution='execution-one', run='run-one', cfg=None):
        return self.main(['--record-attempt', '--home', str(self.home), '--execution-id', execution, '--job-id', 'job-one'],
                         {'run_id': run, 'event': event}, cfg)

    def last(self):
        code, row = self.main(['--last-run'])
        self.assertEqual(code, 0)
        return row

    def sessions(self, *rows):
        db = sqlite3.connect(self.home / 'state.db')
        db.execute(f'CREATE TABLE IF NOT EXISTS sessions ({SESSION_COLUMNS})')
        db.executemany('INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', rows)
        db.commit()
        db.close()

    END = {'stage': 'end', 'session_id': 'session-one', 'completed': False, 'failed': True, 'interrupted': False,
           'turn_exit_reason': 'provider_error', 'model': 'fixture-model',
           'stop': {'code': 'turn_failed', 'detail': 'The drafting turn failed (exit reason: provider_error).'}}

    def test_the_reason_a_run_stopped_is_reported_with_the_run(self):
        self.assertEqual(self.record({'stage': 'start', 'session_id': 'session-one'}), (0, {'ok': True}))
        self.assertEqual(self.record(self.END), (0, {'ok': True}))
        row = self.last()
        self.assertEqual(row['session_id'], 'session-one')
        self.assertEqual(row['stop_reason'], self.END['stop'])
        self.assertFalse(row['committed'])

    def test_usage_and_cost_come_from_the_drafting_session(self):
        self.sessions(('session-one', 'fixture-model', 1.0, 2.0, 'cron_complete', 30, 35011, 1309893, 0, 0.9451643, None, 'estimated'))
        self.record({'stage': 'start', 'session_id': 'session-one'})
        self.assertEqual(self.last()['usage'], {'model': 'fixture-model', 'ended': True, 'end_reason': 'cron_complete',
            'input_tokens': 30, 'output_tokens': 35011, 'cache_read_tokens': 1309893, 'cache_write_tokens': 0,
            'cost_usd': 0.9451643, 'cost_status': 'estimated'})

    def test_a_session_that_ended_without_reporting_back_is_named(self):
        self.sessions(('session-one', 'fixture-model', 1.0, 2.0, 'cron_timeout', 1, 1, 0, 0, 0.01, None, 'estimated'))
        self.record({'stage': 'start', 'session_id': 'session-one'})
        reason = self.last()['stop_reason']
        self.assertEqual(reason['code'], 'no_end_event')
        self.assertIn('cron_timeout', reason['detail'])

    def test_a_session_still_running_has_no_stop_reason(self):
        self.sessions(('session-one', 'fixture-model', 1.0, None, None, 1, 1, 0, 0, None, None, None))
        self.record({'stage': 'start', 'session_id': 'session-one'})
        row = self.last()
        self.assertIsNone(row['stop_reason'])
        self.assertFalse(row['usage']['ended'])

    def test_a_run_from_before_recording_says_so(self):
        row = self.last()
        self.assertEqual(row['stop_reason']['code'], 'not_recorded')
        self.assertIsNone(row['usage'])

    def test_a_committed_run_has_no_stop_reason(self):
        self.record({'stage': 'start', 'session_id': 'session-one'})
        self.record({**self.END, 'completed': True, 'failed': False, 'turn_exit_reason': 'completed', 'stop': None})
        with WorkflowStore(self.audit / 'workflow.sqlite') as store:
            harvest.finish_run(self.audit, 'run-one', {'execution_id': 'execution-one', 'job_id': 'job-one',
                'status': 'no_candidates', 'reviewed_inputs': self.manifest['input_hashes'], 'candidate_refs': [],
                'missing_evidence': []}, store)
        row = self.last()
        self.assertTrue(row['committed'])
        self.assertIsNone(row['stop_reason'])

    def test_missing_cost_store_is_reported_not_guessed(self):
        self.record({'stage': 'start', 'session_id': 'session-one'})
        self.assertIn('error', self.last()['usage'])

    def test_recording_is_bound_to_the_run_and_never_touches_its_inputs(self):
        before = (self.run / 'run.json').read_bytes()
        self.assertEqual(self.record({'stage': 'start', 'session_id': 'session-one'}, execution='other')[0], 1)
        self.assertEqual(self.record({'stage': 'start', 'session_id': 'session-one'}, run='../escape')[0], 1)
        self.assertEqual(self.record({'stage': 'start', 'session_id': 'session-one'},
                                     cfg={**self.cfg, 'harvest_workflow_enabled': False})[0], 1)
        self.assertEqual(self.record({'stage': 'end', 'session_id': 'session-one', 'stop': {'code': 'x'}})[0], 1)
        self.assertEqual(self.record({'stage': 'start', 'session_id': 'session-one', 'extra': 1})[0], 1)
        self.assertFalse((self.run / 'attempt.json').exists())
        self.record({'stage': 'start', 'session_id': 'session-one'})
        self.assertEqual((self.run / 'run.json').read_bytes(), before)
        self.assertEqual(self.record({'stage': 'start', 'session_id': 'session-two'})[0], 1,
                         'a run was rebound to a second drafting session')

    def test_the_runs_report_lists_every_run_newest_first(self):
        older = self.audit / 'inbox/run-older'
        older.mkdir()
        (older / 'run.json').write_bytes(json.dumps({**self.manifest, 'run': 'run-older', 'execution_id': 'execution-zero'}).encode())
        self.record({'stage': 'start', 'session_id': 'session-one'})
        self.record(self.END)
        code, rows = self.main(['--runs', '--json'])
        self.assertEqual(code, 0)
        self.assertEqual([row['run'] for row in rows['runs']], ['run-one', 'run-older'])
        self.assertEqual(rows['runs'][0]['stop_reason']['code'], 'turn_failed')
        self.assertEqual(rows['runs'][0]['conversations'], 1)


if __name__ == '__main__':
    unittest.main()
