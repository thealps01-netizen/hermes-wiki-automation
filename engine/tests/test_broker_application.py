"""Disposable broker publication fixtures are not live activation or physical-click proof."""
import json
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_candidate_apply as fixtures
from owner_decisions import broker_command
from wiki_candidates import review_snapshot


class BrokerApplicationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CandidateApplyTests('test_repeated_applied_operation_is_noop')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.settings = {'hermes_home': str(f.root), 'project_root': str(f.wiki),
                         'project_id': 'recovery-fixture', 'audit_dir': str(f.data),
                         'owner_approval_enabled': True, 'owner_publication_enabled': True}
        broker_command('initialize', self.settings, f.root, {})

    def prepare(self):
        f = self.fixture
        self.body = {'ref': 'run/draft', 'review_digest': review_snapshot(f.wiki, f.inbox, 'run/draft')['review_digest'],
                     'principal': 'a' * 64}
        pending = broker_command('prepare', self.settings, f.root, self.body)
        self.assertTrue(pending['needs_confirm'])
        return {**self.body, 'request_id': pending['request_id']}

    def test_recovery_rejects_changed_inputs_and_forged_owner_binding(self):
        import subprocess
        from owner_decisions import DecisionRefused, OwnerDecisions
        from candidate_apply import ApplyRefused
        f = self.fixture
        body = {**self.body_for_current_review(), 'owner_key': 'e' * 64}
        pending = broker_command('prepare', self.settings, f.root, body)
        request = {**body, 'request_id': pending['request_id']}
        (f.root / 'settings.json').write_bytes(json.dumps(self.settings).encode())
        stopped = subprocess.run([sys.executable, '-B', str(Path(__file__).with_name('broker_apply_worker.py')), str(f.root), 'after-confirm'],
            input=json.dumps(request), capture_output=True, text=True, timeout=15)
        self.assertEqual(stopped.returncode, 91, stopped.stdout + stopped.stderr)
        recovery = {'principal': 'b' * 64, 'owner_key': 'e' * 64, 'request_id': pending['request_id']}
        with self.assertRaises(DecisionRefused):
            broker_command('recover', self.settings, f.root, {**recovery, 'owner_key': 'f' * 64})
        (f.candidate / 'source.md').write_bytes(f.source + b'\nUnapproved changes\n')
        with self.assertRaises(ApplyRefused):
            broker_command('recover', self.settings, f.root, recovery)
        with OwnerDecisions(f.data) as authority:
            receipt = json.loads(authority.db.execute('SELECT receipt FROM decisions WHERE id=?', (pending['request_id'],)).fetchone()[0])
            receipt['owner_key'] = 'f' * 64
            with authority.db:
                authority.db.execute('UPDATE decisions SET receipt=? WHERE id=?', (json.dumps(receipt), pending['request_id']))
        with self.assertRaises(DecisionRefused):
            broker_command('recover', self.settings, f.root, {**recovery, 'owner_key': 'f' * 64})
        self.assertFalse(f.target.exists())
        self.assertFalse((f.candidate / 'applied.json').exists())

    def test_recoverable_list_exposes_only_same_owner_unfinished_approvals(self):
        f = self.fixture
        body = {**self.body_for_current_review(), 'owner_key': 'e' * 64}
        pending = broker_command('prepare', self.settings, f.root, body)
        lookup = {'principal': 'b' * 64, 'owner_key': 'e' * 64}
        self.assertEqual(broker_command('recoverable', self.settings, f.root, lookup)['operations'], [])
        self.settings['owner_publication_enabled'] = False
        broker_command('confirm', self.settings, f.root, {**body, 'request_id': pending['request_id']})
        self.settings['owner_publication_enabled'] = True
        rows = broker_command('recoverable', self.settings, f.root, lookup)['operations']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['request_id'], pending['request_id'])
        self.assertEqual(rows[0]['ref'], 'run/draft')
        self.assertEqual(rows[0]['state'], 'approved')
        self.assertTrue({'receipt', 'signature', 'secret', 'owner_key', 'principal'}.isdisjoint(rows[0]))
        self.assertEqual(broker_command('recoverable', self.settings, f.root, {**lookup, 'owner_key': 'f' * 64})['operations'], [])
        broker_command('recover', self.settings, f.root, {**lookup, 'request_id': pending['request_id']})
        self.assertEqual(broker_command('recoverable', self.settings, f.root, lookup)['operations'], [])

    def test_recovery_never_approves_pending_or_unbound_legacy_decisions(self):
        from owner_decisions import DecisionRefused
        f = self.fixture
        body = {**self.body_for_current_review(), 'owner_key': 'e' * 64}
        pending = broker_command('prepare', self.settings, f.root, body)
        recovery = {'principal': 'b' * 64, 'owner_key': 'e' * 64, 'request_id': pending['request_id']}
        with self.assertRaises(DecisionRefused):
            broker_command('recover', self.settings, f.root, recovery)
        self.settings['owner_publication_enabled'] = False
        legacy = self.prepare()
        broker_command('confirm', self.settings, f.root, legacy)
        self.settings['owner_publication_enabled'] = True
        with self.assertRaises(DecisionRefused):
            broker_command('recover', self.settings, f.root, {**recovery, 'request_id': legacy['request_id']})
        self.assertFalse(f.target.exists())
        self.assertFalse((f.data / 'workflow.sqlite').exists())

    def test_new_verified_owner_session_can_resume_only_its_approved_request(self):
        import subprocess
        f = self.fixture
        body = {**self.body_for_current_review(), 'owner_key': 'e' * 64}
        pending = broker_command('prepare', self.settings, f.root, body)
        request = {**body, 'request_id': pending['request_id']}
        (f.root / 'settings.json').write_bytes(json.dumps(self.settings).encode())
        argv = [sys.executable, '-B', str(Path(__file__).with_name('broker_apply_worker.py')), str(f.root), 'after-confirm']
        stopped = subprocess.run(argv, input=json.dumps(request), capture_output=True, text=True, timeout=15)
        self.assertEqual(stopped.returncode, 91, stopped.stdout + stopped.stderr)
        resumed = broker_command('recover', self.settings, f.root,
            {'principal': 'b' * 64, 'owner_key': 'e' * 64, 'request_id': pending['request_id']})
        self.assertTrue(resumed['ok'], resumed)
        self.assertEqual(f.target.read_bytes(), f.source)
        self.assertTrue({'receipt', 'signature', 'secret', 'owner_key'}.isdisjoint(resumed))

    def body_for_current_review(self):
        f = self.fixture
        return {'ref': 'run/draft', 'review_digest': review_snapshot(f.wiki, f.inbox, 'run/draft')['review_digest'],
                'principal': 'a' * 64}

    def test_applied_drift_is_explained_and_never_repaired(self):
        f = self.fixture
        request = self.prepare()
        first = broker_command('confirm', self.settings, f.root, request)
        f.target.write_bytes(b'Owner edited the published result')
        stamp = f.target.stat().st_mtime_ns
        result = broker_command('confirm', self.settings, f.root, request)
        self.assertFalse(result['ok'])
        self.assertTrue(result['later_drift'])
        self.assertEqual(result['operation_id'], first['operation_id'])
        self.assertIn('changed', result.get('reason', '').lower())
        self.assertEqual(f.target.read_bytes(), b'Owner edited the published result')
        self.assertEqual(f.target.stat().st_mtime_ns, stamp)

    def test_disabled_publication_never_writes_even_with_a_confirmation(self):
        f = self.fixture
        request = self.prepare()
        for flag in (None, False, 'true', 1):
            with self.subTest(flag=flag):
                case = BrokerApplicationTests('test_same_confirmed_update_retry_is_a_noop')
                case.setUp()
                try:
                    request = case.prepare()
                    case.settings['owner_publication_enabled'] = flag
                    result = broker_command('confirm', case.settings, case.fixture.root, request)
                    self.assertFalse(result['ok'])
                    self.assertFalse(case.fixture.target.exists())
                    self.assertFalse((case.fixture.data / 'workflow.sqlite').exists())
                finally:
                    case.doCleanups()

    def test_wrong_session_or_review_cannot_resume_a_confirmed_operation(self):
        import owner_decisions
        f = self.fixture
        request = self.prepare()
        result = broker_command('confirm', self.settings, f.root, request)
        stamp = f.target.stat().st_mtime_ns
        for change in ({'principal': 'b' * 64}, {'review_digest': 'c' * 64}, {'ref': 'other/draft'}, {'request_id': 'd' * 64}):
            with self.subTest(change=change), self.assertRaises(owner_decisions.DecisionRefused):
                broker_command('confirm', self.settings, f.root, {**request, **change})
        self.assertEqual(f.target.read_bytes(), f.source)
        self.assertEqual(f.target.stat().st_mtime_ns, stamp)

    def test_conflicting_target_returns_a_structured_refusal_without_overwrite(self):
        import subprocess
        f = self.fixture
        f.configure_recovery('update')
        request = self.prepare()
        (f.root / 'settings.json').write_bytes(json.dumps(self.settings).encode())
        argv = [sys.executable, '-B', str(Path(__file__).with_name('broker_apply_worker.py')), str(f.root)]
        stopped = subprocess.run([*argv, 'after-consume:authority'], input=json.dumps(request), capture_output=True, text=True, timeout=15)
        self.assertEqual(stopped.returncode, 91, stopped.stdout + stopped.stderr)
        independent = b'Independent owner changes must survive'
        f.target.write_bytes(independent)
        denied = subprocess.run(argv, input=json.dumps(request), capture_output=True, text=True, timeout=15)
        self.assertEqual(denied.returncode, 1, denied.stdout + denied.stderr)
        self.assertTrue(denied.stdout.strip(), 'The broker crashed instead of returning a structured refusal')
        result = json.loads(denied.stdout)
        self.assertFalse(result['ok'])
        self.assertIn('drift', result['reason'].lower())
        self.assertEqual(denied.stderr, '')
        self.assertEqual(f.target.read_bytes(), independent)
        self.assertFalse((f.candidate / 'applied.json').exists())

    def test_process_interruption_resumes_from_the_same_owner_request(self):
        import subprocess
        from workflow_store import WorkflowStore
        count = 0
        for kind in ('new', 'update', 'retire'):
            for point in ('after-confirm', 'before-consume:authority', 'after-consume:authority',
                          'after-write:retire' if kind == 'retire' else 'after-write:2026-10-08-fixture.md',
                          'after-write:applied.json', 'before-transition:applied', 'after-transition:applied'):
                with self.subTest(kind=kind, point=point):
                    case = BrokerApplicationTests('test_same_confirmed_update_retry_is_a_noop')
                    case.setUp()
                    try:
                        f = case.fixture
                        f.configure_recovery(kind)
                        request = case.prepare()
                        (f.root / 'settings.json').write_bytes(json.dumps(case.settings).encode())
                        argv = [sys.executable, '-B', str(Path(__file__).with_name('broker_apply_worker.py')), str(f.root)]
                        stopped = subprocess.run([*argv, point], input=json.dumps(request), capture_output=True, text=True, timeout=15)
                        self.assertEqual(stopped.returncode, 91, stopped.stdout + stopped.stderr)
                        finished = subprocess.run(argv, input=json.dumps(request), capture_output=True, text=True, timeout=15)
                        self.assertEqual(finished.returncode, 0, finished.stdout + finished.stderr)
                        result = json.loads(finished.stdout)
                        self.assertTrue(result['ok'], result)
                        self.assertTrue({'receipt', 'secret', 'signature'}.isdisjoint(result))
                        if kind == 'retire':
                            self.assertFalse(f.target.exists())
                        else:
                            self.assertEqual(f.target.read_bytes(), f.source)
                        with WorkflowStore(f.data / 'workflow.sqlite', read_only=True) as journal:
                            rows = journal.db.execute('SELECT id,state FROM operations').fetchall()
                            self.assertEqual(rows, [(result['operation_id'], 'applied')])
                        stamp = f.target.stat().st_mtime_ns if f.target.exists() else None
                        again = subprocess.run(argv, input=json.dumps(request), capture_output=True, text=True, timeout=15)
                        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
                        self.assertEqual(json.loads(again.stdout)['operation_id'], result['operation_id'])
                        self.assertEqual(f.target.stat().st_mtime_ns if f.target.exists() else None, stamp)
                        count += 1
                    finally:
                        case.doCleanups()
        print(f'BROKER_INTERRUPTION_CASES recovered={count}')

    def test_same_confirmed_update_retry_is_a_noop(self):
        f = self.fixture
        f.configure_recovery('update')
        request = self.prepare()
        first = broker_command('confirm', self.settings, f.root, request)
        stamp = f.target.stat().st_mtime_ns
        retried = broker_command('confirm', self.settings, f.root, request)
        self.assertEqual(first['operation_id'], retried['operation_id'])
        self.assertTrue(retried['ok'], retried)
        self.assertEqual(f.target.stat().st_mtime_ns, stamp)

    def test_explicitly_enabled_owner_confirmation_publishes_exact_bytes(self):
        f = self.fixture
        request = self.prepare()
        self.assertFalse(f.target.exists(), 'Preparation wrote a source before confirmation')
        result = broker_command('confirm', self.settings, f.root, request)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['state'], 'applied')
        self.assertEqual(f.target.read_bytes(), f.source)
        self.assertEqual(json.loads((f.candidate / 'applied.json').read_bytes())['operation_id'], result['operation_id'])
        self.assertTrue({'receipt', 'secret', 'signature'}.isdisjoint(result))


if __name__ == '__main__':
    unittest.main()
