"""Durability tests use disposable SQLite files, never the active wiki."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class StoreTests(unittest.TestCase):
    def test_reopen_preserves_operation(self):
        import workflow_store
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as temp:
            path = Path(temp) / 'workflow.sqlite'
            operation = dict(operation_id='op-1', project_root='fixture', project_id='fixture',
                             ref='run/candidate', kind='new', target='fixture.md',
                             review_digest='a' * 64, expected_base=None)
            with workflow_store.WorkflowStore(path) as store:
                saved = store.record_operation(operation)
            with workflow_store.WorkflowStore(path) as store:
                self.assertEqual(store.get_operation('op-1'), saved)
                self.assertEqual(saved['state'], 'collected')

    def test_conflicting_identity_refused(self):
        import workflow_store
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as temp:
            with workflow_store.WorkflowStore(Path(temp) / 'db') as store:
                original = dict(operation_id='one', target='one.md')
                store.record_operation(original)
                self.assertEqual(store.record_operation(original), store.get_operation('one'))
                with self.assertRaises(workflow_store.WorkflowError):
                    store.record_operation(dict(operation_id='one', target='two.md'))
                self.assertEqual(store.get_operation('one')['target'], 'one.md')
                self.assertEqual(store.db.execute('SELECT count(*) FROM operations').fetchone()[0], 1)

    def test_compare_and_set_refuses_stale_state(self):
        import workflow_store
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as temp:
            with workflow_store.WorkflowStore(Path(temp) / 'db') as store:
                store.record_operation(dict(operation_id='one'))
                store.transition('one', 'collected', 'drafted')
                with self.assertRaises(workflow_store.WorkflowError):
                    store.transition('one', 'collected', 'rejected')
                with self.assertRaises(workflow_store.WorkflowError):
                    store.transition('one', 'drafted', 'applied')
                self.assertEqual(store.get_operation('one')['state'], 'drafted')
                store.transition('one', 'drafted', 'awaiting_approval')
                store.transition('one', 'awaiting_approval', 'applying')
                store.record_step('one', 'source', {'hash': 'a'})
                store.record_step('one', 'source', {'hash': 'a'})
                with self.assertRaises(workflow_store.WorkflowError):
                    store.record_step('one', 'source', {'hash': 'b'})
                self.assertEqual(store.steps('one'), [{'step': 'source', 'result': {'hash': 'a'}}])
                store.transition('one', 'applying', 'applied', {'ok': True})
                self.assertEqual(store.get_operation('one')['result'], {'ok': True})

    def test_corrupt_or_newer_schema_refused(self):
        import workflow_store
        import sqlite3
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as temp:
            for bad in ('corrupt', 'newer', 'unversioned'):
                path = Path(temp) / bad
                if bad == 'corrupt':
                    path.write_bytes(b'not a SQLite database')
                else:
                    db = sqlite3.connect(path)
                    try:
                        with db:
                            db.execute('CREATE TABLE unrelated (value TEXT)')
                            if bad == 'newer':
                                db.execute('PRAGMA user_version=2')
                    finally:
                        db.close()
                before = path.read_bytes()
                with self.subTest(bad=bad), self.assertRaises(workflow_store.WorkflowError):
                    with workflow_store.WorkflowStore(path):
                        pass
                self.assertEqual(path.read_bytes(), before)

    def test_read_only_journal_does_not_create_or_mutate_files(self):
        import sqlite3
        import workflow_store
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as temp:
            root = Path(temp)
            missing = root / 'missing/workflow.sqlite'
            with self.assertRaises(workflow_store.WorkflowError):
                with workflow_store.WorkflowStore(missing, read_only=True):
                    pass
            self.assertFalse(missing.parent.exists())
            path = root / 'workflow.sqlite'
            with workflow_store.WorkflowStore(path) as store:
                store.record_operation({'operation_id': 'read-fixture'})
            before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
            with workflow_store.WorkflowStore(path, read_only=True) as store:
                self.assertEqual(store.get_operation('read-fixture')['state'], 'collected')
                with self.assertRaises(sqlite3.DatabaseError):
                    store.record_operation({'operation_id': 'denied-write'})
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()})

    def test_live_wal_is_refused_before_sqlite_open_and_keeps_pending_records(self):
        import sqlite3
        from unittest.mock import patch
        import workflow_store
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            path = Path(temp) / 'workflow.sqlite'
            with workflow_store.WorkflowStore(path) as store:
                store.record_operation({'operation_id': 'original'})
            db = sqlite3.connect(path)
            try:
                self.assertEqual(db.execute('PRAGMA journal_mode=WAL').fetchone(), ('wal',))
                db.execute('PRAGMA wal_autocheckpoint=0')
                db.execute("INSERT INTO operations VALUES ('pending', '{\"operation_id\":\"pending\"}', 'applying', NULL)")
                db.commit()
                root = path.parent
                before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir() if p.is_file()}
                with patch.object(workflow_store.sqlite3, 'connect') as opened:
                    with self.assertRaises(workflow_store.WorkflowError):
                        with workflow_store.WorkflowStore(path, read_only=True):
                            pass
                    opened.assert_not_called()
                self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns)
                                          for p in root.iterdir() if p.is_file()})
                self.assertEqual(db.execute("SELECT state FROM operations WHERE id='pending'").fetchone(), ('applying',))
            finally:
                db.close()

    def test_idempotent_record(self):
        import workflow_store
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            with workflow_store.WorkflowStore(Path(temp) / 'db') as store:
                operation = dict(operation_id='same', target='same.md')
                first = store.record_operation(operation)
                self.assertEqual(first, store.record_operation(operation))
                self.assertEqual(store.db.execute('SELECT count(*) FROM operations').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
