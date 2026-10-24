"""Versioned operation journal; file application has its own recovery boundary."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3


class WorkflowError(RuntimeError):
    pass


class WorkflowStore:
    def __init__(self, path: Path, *, read_only=False):
        self.path = Path(path)
        self.read_only = read_only
        self.db = None

    def __enter__(self):
        if self.read_only:
            try:
                with self.path.open('rb') as journal:
                    header = journal.read(20)
                if header[:16] != b'SQLite format 3\x00' or header[18:20] != b'\x01\x01':
                    raise WorkflowError('Nonmutating journal inspection requires SQLite rollback mode')
                self.db = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)
                version = self.db.execute('PRAGMA user_version').fetchone()[0]
                tables = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if version != 1 or tables != {'operations', 'steps'}:
                    raise WorkflowError('Unknown or invalid workflow schema')
                return self
            except (sqlite3.DatabaseError, WorkflowError, OSError) as exc:
                if self.db is not None:
                    self.db.close()
                raise WorkflowError('Read-only journal unavailable or unsupported') from exc
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=10)
        try:
            self.db.execute('BEGIN IMMEDIATE')
            version = self.db.execute('PRAGMA user_version').fetchone()[0]
            tables = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if version not in (0, 1) or (version == 0 and tables):
                raise WorkflowError('Unknown or newer workflow schema')
            if version == 1 and tables != {'operations', 'steps'}:
                raise WorkflowError('Invalid workflow schema')
            self.db.execute('CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, identity TEXT NOT NULL, state TEXT NOT NULL, result TEXT)')
            self.db.execute('CREATE TABLE IF NOT EXISTS steps (operation_id TEXT NOT NULL REFERENCES operations(id), name TEXT NOT NULL, result TEXT NOT NULL, PRIMARY KEY(operation_id,name))')
            self.db.execute('PRAGMA user_version=1')
            self.db.commit()
        except (sqlite3.DatabaseError, WorkflowError) as exc:
            self.db.rollback()
            self.db.close()
            raise WorkflowError('Workflow journal unreadable or schema unsupported') from exc
        return self

    def __exit__(self, *args):
        self.db.close()

    def record_operation(self, operation: dict) -> dict:
        identity = json.dumps(operation, sort_keys=True, separators=(',', ':'))
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO operations VALUES (?, ?, ?, NULL)',
                            (operation['operation_id'], identity, 'collected'))
            saved = self.db.execute('SELECT identity FROM operations WHERE id=?',
                                    (operation['operation_id'],)).fetchone()[0]
            if saved != identity:
                raise WorkflowError('Operation identity changed')
        return self.get_operation(operation['operation_id'])

    def get_operation(self, operation_id: str) -> dict | None:
        row = self.db.execute('SELECT identity,state,result FROM operations WHERE id=?', (operation_id,)).fetchone()
        return {**json.loads(row[0]), 'state': row[1], 'result': json.loads(row[2]) if row[2] else None} if row else None

    def transition(self, operation_id: str, expected: str, new: str, result: dict | None = None) -> dict:
        allowed = {
            'collected': {'drafted', 'rejected'},
            'drafted': {'awaiting_approval', 'rejected'},
            'awaiting_approval': {'applying', 'rejected'},
            'applying': {'applied', 'recovery_required'},
            'recovery_required': {'applying'},
        }
        operation = self.get_operation(operation_id)
        if operation is not None and operation.get('type') == 'installation':
            allowed = {'collected': {'prepared'}, 'prepared': {'applying'},
                'applying': {'applied', 'recovery_required'}, 'recovery_required': {'applying'}}
        if new not in allowed.get(expected, set()):
            raise WorkflowError('Invalid workflow transition')
        with self.db:
            changed = self.db.execute('UPDATE operations SET state=?,result=? WHERE id=? AND state=?',
                                      (new, json.dumps(result) if result is not None else None, operation_id, expected))
            if changed.rowcount != 1:
                raise WorkflowError('Stale operation state')
        return self.get_operation(operation_id)

    def record_step(self, operation_id: str, step: str, result: dict) -> None:
        encoded = json.dumps(result, sort_keys=True, separators=(',', ':'))
        with self.db:
            if self.get_operation(operation_id) is None:
                raise WorkflowError('Unknown operation')
            self.db.execute('INSERT OR IGNORE INTO steps VALUES (?, ?, ?)', (operation_id, step, encoded))
            saved = self.db.execute('SELECT result FROM steps WHERE operation_id=? AND name=?', (operation_id, step)).fetchone()[0]
            if saved != encoded:
                raise WorkflowError('Step identity changed')

    def steps(self, operation_id: str) -> list[dict]:
        rows = self.db.execute('SELECT name,result FROM steps WHERE operation_id=? ORDER BY rowid', (operation_id,))
        return [{'step': name, 'result': json.loads(result)} for name, result in rows]

