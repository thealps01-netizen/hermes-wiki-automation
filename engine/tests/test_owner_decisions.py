"""Authorization fixtures do not assert that a real person clicked a live UI."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class OwnerDecisionTests(unittest.TestCase):
    def test_bound_receipt_survives_reopen_and_can_be_consumed_once(self):
        import owner_decisions
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            data = Path(tmp)
            snapshot = {'project_id': 'fixture', 'project_root': 'fixture-root', 'ref': 'run/draft',
                        'target': 'fixture.md', 'kind': 'new', 'review_digest': 'a' * 64}
            with owner_decisions.OwnerDecisions(data, initialize=True) as store:
                pending = store.prepare(snapshot, 'authenticated-fixture-session')
                receipt = store.confirm(pending['request_id'], snapshot, 'authenticated-fixture-session')
                self.assertNotIn('issuer_key', str(receipt))
            with owner_decisions.OwnerDecisions(data, initialize=True) as store:
                self.assertEqual(store.verify(receipt, snapshot)['review_digest'], snapshot['review_digest'])
                self.assertEqual(store.consume(receipt, snapshot, 'operation-1')['operation_id'], 'operation-1')
                with self.assertRaises(owner_decisions.DecisionRefused):
                    store.consume(receipt, snapshot, 'operation-2')

    def test_linked_authority_is_refused_without_mutation(self):
        import owner_decisions
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            root = Path(tmp)
            data = root / 'inbox'
            data.mkdir()
            outside_root = root / 'outside'
            with owner_decisions.OwnerDecisions(outside_root, initialize=True):
                pass
            outside = outside_root / 'owner-decisions.sqlite'
            path = data / 'owner-decisions.sqlite'
            try:
                path.symlink_to(outside)
            except OSError:
                os.link(outside, path)
            before = outside.read_bytes()
            with self.assertRaises(owner_decisions.DecisionRefused):
                with owner_decisions.OwnerDecisions(data, initialize=True):
                    pass
            self.assertEqual(outside.read_bytes(), before)

    def test_same_receipt_retry_is_same_operation(self):
        import owner_decisions
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            snapshot = {'review_digest': 'a' * 64}
            with owner_decisions.OwnerDecisions(Path(tmp), initialize=True) as store:
                pending = store.prepare(snapshot, 'fixture-session')
                receipt = store.confirm(pending['request_id'], snapshot, 'fixture-session')
                first = store.consume(receipt, snapshot, 'one')
                self.assertEqual(first, store.consume(receipt, snapshot, 'one'))

    def test_missing_authority_does_not_initialize_on_verification(self):
        import owner_decisions
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            data = Path(tmp) / 'missing'
            with self.assertRaises(owner_decisions.DecisionRefused):
                with owner_decisions.OwnerDecisions(data):
                    pass
            self.assertFalse(data.exists())

    def test_stale_forged_wrong_session_and_expired_are_denied(self):
        import owner_decisions
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            now = [1000]
            snapshot = {'review_digest': 'a' * 64}
            with owner_decisions.OwnerDecisions(Path(tmp), initialize=True, clock=lambda: now[0]) as store:
                pending = store.prepare(snapshot, 'fixture-session', lifetime=10)
                with self.assertRaises(owner_decisions.DecisionRefused):
                    store.confirm(pending['request_id'], snapshot, 'other-session')
                with self.assertRaises(owner_decisions.DecisionRefused):
                    store.confirm(pending['request_id'], {'review_digest': 'b' * 64}, 'fixture-session')
                receipt = store.confirm(pending['request_id'], snapshot, 'fixture-session')
                with self.assertRaises(owner_decisions.DecisionRefused):
                    store.verify({**receipt, 'signature': '0' * 64}, snapshot)
                with self.assertRaises(owner_decisions.DecisionRefused):
                    store.verify(receipt, {'review_digest': 'b' * 64})
                now[0] += 11
                with self.assertRaises(owner_decisions.DecisionRefused):
                    store.consume(receipt, snapshot, 'new-operation')
                self.assertEqual(store.db.execute('SELECT state FROM decisions').fetchone()[0], 'approved')

    def test_empty_operation_cannot_consume_owner_decision(self):
        import owner_decisions
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            snapshot = {'review_digest': 'a' * 64}
            with owner_decisions.OwnerDecisions(Path(tmp), initialize=True) as store:
                pending = store.prepare(snapshot, 'fixture-session')
                receipt = store.confirm(pending['request_id'], snapshot, 'fixture-session')
                with self.assertRaises(owner_decisions.DecisionRefused):
                    store.consume(receipt, snapshot, '')
                self.assertEqual(store.verify(receipt, snapshot)['state'], 'approved')

    def test_two_processes_cannot_consume_for_different_operations(self):
        import owner_decisions
        import json
        import subprocess
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            data = Path(tmp)
            snapshot = {'review_digest': 'a' * 64}
            with owner_decisions.OwnerDecisions(data, initialize=True) as store:
                pending = store.prepare(snapshot, 'fixture-session')
                receipt = store.confirm(pending['request_id'], snapshot, 'fixture-session')
            fixture = data / 'test-receipt.json'
            fixture.write_text(json.dumps({'snapshot': snapshot, 'receipt': receipt}), encoding='utf-8')
            worker = Path(__file__).with_name('owner_consume_worker.py')
            def consume(operation):
                return subprocess.run([sys.executable, str(worker), str(data), str(fixture), operation],
                                      capture_output=True, text=True, timeout=15)
            with ThreadPoolExecutor(max_workers=2) as pool:
                outputs = list(pool.map(consume, ['one', 'two']))
            self.assertEqual(sorted(p.returncode for p in outputs), [0, 2], '\n'.join(p.stdout + p.stderr for p in outputs))
            with owner_decisions.OwnerDecisions(data) as store:
                record = store.verify(receipt, snapshot)
                self.assertEqual(record['state'], 'consumed')
                self.assertIn(record['operation_id'], ('one', 'two'))

    def test_malformed_receipt_is_a_refusal_not_an_unhandled_error(self):
        import owner_decisions
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            snapshot = {'review_digest': 'a' * 64}
            with owner_decisions.OwnerDecisions(Path(tmp), initialize=True) as store:
                for malformed in ({}, {'signature': '\u00e7'}, {'signature': None}, {'signature': 7}):
                    with self.subTest(receipt=malformed), self.assertRaises(owner_decisions.DecisionRefused):
                        store.verify(malformed, snapshot)
                with self.assertRaises(owner_decisions.DecisionRefused):
                    store.prepare({'review_digest': 'g' * 64}, 'fixture-session')

    def test_broker_setup_requires_explicit_activation_and_profile_ownership(self):
        import owner_decisions
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home = Path(tmp)
            data = home / 'authority-not-created'
            settings = {'hermes_home': str(home), 'audit_dir': str(data)}
            with self.assertRaises(owner_decisions.DecisionRefused):
                owner_decisions.broker_command('initialize', settings, home, {})
            settings['owner_approval_enabled'] = True
            with self.assertRaises(owner_decisions.DecisionRefused):
                owner_decisions.broker_command('initialize', settings, home / 'different-profile', {})
            self.assertFalse(data.exists())

    def test_activation_binds_the_profile_owner_and_initializes_authority_once(self):
        # The one owner-setup step: the panel derives the binding from the host session and the
        # hash from its loaded guard code; the engine validates both and writes every switch.
        import json
        import owner_decisions
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
            home, data, wiki = Path(tmp) / 'home', Path(tmp) / 'data', Path(tmp) / 'wiki'
            home.mkdir()
            data.mkdir()
            (wiki / '.llm-wiki').mkdir(parents=True)
            (wiki / '.llm-wiki/project.json').write_text('{"id":"activation-fixture"}')
            settings_path = Path(tmp) / 'settings.json'
            original = {'hermes_home': str(home), 'audit_dir': str(data), 'project_root': str(wiki),
                        'project_id': 'activation-fixture', 'jobs': {'harvest_night': 'job'},
                        # Left behind by 2.13.2 and earlier; activation drops them.
                        'harvest_workflow_enabled': True, 'owner_approval_runtime': {'loaded_code_hash': 'b' * 64}}
            settings_path.write_text(json.dumps(original), encoding='utf-8')
            local = {'mode': 'local_owner', 'home': str(home)}
            payload = {'binding': local}
            refused = (
                {**payload, 'extra': True},
                {**payload, 'loaded_code_hash': 'b' * 64},
                {**payload, 'binding': {**local, 'home': str(Path(tmp) / 'other')}},
                {**payload, 'binding': {**local, 'provider': 'x'}},
                {**payload, 'binding': {'mode': 'interactive_owner', 'home': str(home), 'provider': 'p',
                                        'user_id': '', 'org_id': None}},
                {**payload, 'binding': {'mode': 'administrator', 'home': str(home)}},
            )
            for bad in refused:
                with self.subTest(bad=bad), self.assertRaises(owner_decisions.DecisionRefused):
                    owner_decisions.activate(settings_path, home, bad)
            with self.assertRaises(owner_decisions.DecisionRefused):
                owner_decisions.activate(settings_path, Path(tmp) / 'other-profile', payload)
            self.assertEqual(json.loads(settings_path.read_text(encoding='utf-8')), original)
            self.assertFalse((data / 'owner-decisions.sqlite').exists())

            self.assertEqual(owner_decisions.activate(settings_path, home, payload), {'ok': True, 'activated': True})
            saved = json.loads(settings_path.read_text(encoding='utf-8'))
            expected = {key: value for key, value in original.items()
                        if key not in ('harvest_workflow_enabled', 'owner_approval_runtime')}
            self.assertEqual(saved, {**expected, 'owner_approval_enabled': True, 'owner_publication_enabled': True,
                'owner_approval_owner': local})
            with owner_decisions.OwnerDecisions(data) as store:
                issuer = store.issuer
            # Re-activation for another owner replaces the binding and keeps the authority.
            remote = {'mode': 'interactive_owner', 'home': str(home), 'provider': 'p', 'user_id': 'u', 'org_id': None}
            owner_decisions.activate(settings_path, home, {'binding': remote})
            saved = json.loads(settings_path.read_text(encoding='utf-8'))
            self.assertEqual(saved['owner_approval_owner'], remote)
            self.assertNotIn('owner_approval_runtime', saved)
            with owner_decisions.OwnerDecisions(data) as store:
                self.assertEqual(store.issuer, issuer)
            self.assertEqual(owner_decisions.broker_command('recoverable', saved, home,
                {'principal': 'd' * 64, 'owner_key': 'e' * 64}), {'ok': True, 'operations': []})


if __name__ == '__main__':
    unittest.main()
