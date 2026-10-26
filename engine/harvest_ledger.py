"""Per-conversation harvest ledger: one row per conversation (or per new tail of one).

Code writes this ledger, never a model. A row moves pending -> processing -> done | empty | error.
A conversation that grows after `done`/`empty` gets a new row for the new tail only; nothing leaves
`pending` except through its own row, so a failed conversation never forces a whole run to be
collected again. Times are epoch seconds of the conversation's messages; `after` is exclusive and
`through` inclusive. See design section 4.1 and 4.6 (leases, at most 2 paid attempts).

The merger takes items one by one (`merged_items`): a night stopped by its cap or clock keeps the
items it did not reach for the next night, and never offers an item it already drafted again. A row
is marked merged once every one of its items was taken. `meta` keeps the collector's last time.
"""
import hashlib
import json
import sqlite3
import time
from pathlib import Path

LEASE_SECONDS = 15 * 60
MAX_ATTEMPTS = 2
SCHEMA_VERSION = 2
TABLES = {'conversations', 'merged_items', 'meta'}
COLUMNS = ('id', 'agent', 'conversation', 'after', 'through', 'content_hash', 'prompt_version', 'status',
           'attempts', 'last_error', 'next_attempt_at', 'lease_worker', 'lease_started', 'tokens_in',
           'tokens_out', 'cost_usd', 'parts', 'items', 'problems', 'merged', 'created', 'updated')


class LedgerError(RuntimeError):
    pass


def content_hash(parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode('utf-8')).hexdigest()


class Ledger:
    def __init__(self, path, clock=time.time):
        self.path = Path(path)
        self.clock = clock
        self.db = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            self.db.execute('BEGIN IMMEDIATE')
            version = self.db.execute('PRAGMA user_version').fetchone()[0]
            tables = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if (version, tables) not in ((0, set()), (1, {'conversations'}), (SCHEMA_VERSION, TABLES)):
                raise LedgerError('The harvest ledger has an unknown schema; it was left untouched')
            self.db.execute(
                'CREATE TABLE IF NOT EXISTS conversations (id INTEGER PRIMARY KEY, agent TEXT NOT NULL,'
                ' conversation TEXT NOT NULL, after REAL, through REAL NOT NULL, content_hash TEXT NOT NULL,'
                ' prompt_version TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,'
                ' last_error TEXT, next_attempt_at REAL, lease_worker TEXT, lease_started REAL,'
                ' tokens_in INTEGER NOT NULL DEFAULT 0, tokens_out INTEGER NOT NULL DEFAULT 0,'
                ' cost_usd REAL NOT NULL DEFAULT 0, parts TEXT NOT NULL, items TEXT, problems TEXT, merged TEXT,'
                ' created REAL NOT NULL, updated REAL NOT NULL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS merged_items (row_id INTEGER NOT NULL, item INTEGER NOT NULL,'
                            ' night TEXT NOT NULL, PRIMARY KEY (row_id, item))')
            self.db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            self.db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
            self.db.execute('COMMIT')
        except (sqlite3.DatabaseError, LedgerError) as exc:
            if self.db.in_transaction:
                self.db.execute('ROLLBACK')
            self.db.close()
            if isinstance(exc, LedgerError):
                raise
            raise LedgerError('The harvest ledger is unreadable') from exc
        return self

    def __exit__(self, *args):
        self.db.close()

    def _write(self, work):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            result = work()
            self.db.execute('COMMIT')
            return result
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def _row(self, values):
        row = dict(zip(COLUMNS, values))
        for field in ('parts', 'items', 'problems'):
            row[field] = json.loads(row[field]) if row[field] is not None else None
        return row

    def _latest(self, agent, conversation):
        values = self.db.execute(f'SELECT {",".join(COLUMNS)} FROM conversations WHERE agent=? AND conversation=?'
                                 ' ORDER BY id DESC LIMIT 1', (agent, conversation)).fetchone()
        return self._row(values) if values else None

    def tail_start(self, agent, conversation):
        """Time after which the conversation's messages are not yet in any row; None = from the start."""
        latest = self._latest(agent, conversation)
        if latest is None:
            return None
        return latest['through'] if latest['status'] in ('done', 'empty') else latest['after']

    def offer(self, agent, conversation, after, through, parts, prompt_version):
        """Queue the rendered messages in (after, through] as `parts`, the exact text the extractor reads.
        Returns queued | updated | nothing_new | busy | blocked."""
        digest = content_hash(parts)
        stored = json.dumps(parts, ensure_ascii=False)

        def work():
            now = self.clock()
            latest = self._latest(agent, conversation)
            if latest and latest['status'] == 'processing':
                return 'busy'
            if latest and latest['status'] == 'error':
                return 'blocked'
            if latest and latest['status'] == 'pending':
                if after != latest['after']:
                    raise LedgerError('A pending row was offered from a different start')
                if (through, digest) == (latest['through'], latest['content_hash']):
                    return 'nothing_new'
                self.db.execute('UPDATE conversations SET through=?, content_hash=?, parts=?, prompt_version=?,'
                                ' updated=? WHERE id=?', (through, digest, stored, prompt_version, now, latest['id']))
                return 'updated'
            start = latest['through'] if latest else None
            if after != start:
                raise LedgerError('A tail must start where the last finished row ended')
            if latest and through <= start:
                return 'nothing_new'
            self.db.execute('INSERT INTO conversations (agent, conversation, after, through, content_hash, parts,'
                            ' prompt_version, status, created, updated) VALUES (?,?,?,?,?,?,?,?,?,?)',
                            (agent, conversation, after, through, digest, stored, prompt_version, 'pending', now, now))
            return 'queued'
        return self._write(work)

    def claim(self, worker):
        """Lease the oldest due pending row to `worker` and count a paid attempt; None when nothing is due."""
        def work():
            now = self.clock()
            expired = now - LEASE_SECONDS
            self.db.execute("UPDATE conversations SET status='error', last_error=?, lease_worker=NULL,"
                            " lease_started=NULL, updated=? WHERE status='processing' AND lease_started<?"
                            " AND attempts>=?", (f'lease expired after {MAX_ATTEMPTS} attempts', now, expired,
                                                  MAX_ATTEMPTS))
            self.db.execute("UPDATE conversations SET status='pending', last_error='lease expired',"
                            " lease_worker=NULL, lease_started=NULL, updated=? WHERE status='processing'"
                            " AND lease_started<?", (now, expired))
            found = self.db.execute("SELECT id FROM conversations WHERE status='pending' AND"
                                    " (next_attempt_at IS NULL OR next_attempt_at<=?) ORDER BY id LIMIT 1",
                                    (now,)).fetchone()
            if not found:
                return None
            self.db.execute("UPDATE conversations SET status='processing', lease_worker=?, lease_started=?,"
                            " attempts=attempts+1, next_attempt_at=NULL, updated=? WHERE id=?",
                            (worker, now, now, found[0]))
            return self._by_id(found[0])
        return self._write(work)

    def _by_id(self, row_id):
        values = self.db.execute(f'SELECT {",".join(COLUMNS)} FROM conversations WHERE id=?', (row_id,)).fetchone()
        if not values:
            raise LedgerError(f'No ledger row {row_id}')
        return self._row(values)

    def _held(self, row_id, worker):
        row = self._by_id(row_id)
        if row['status'] != 'processing' or row['lease_worker'] != worker:
            raise LedgerError(f'Row {row_id} is not leased to {worker}')
        return row

    def finish(self, row_id, worker, items, problems, cost_usd=0.0, tokens_in=0, tokens_out=0):
        def work():
            self._held(row_id, worker)
            self.db.execute('UPDATE conversations SET status=?, items=?, problems=?, lease_worker=NULL,'
                            ' lease_started=NULL, cost_usd=cost_usd+?, tokens_in=tokens_in+?,'
                            ' tokens_out=tokens_out+?, updated=? WHERE id=?',
                            ('done' if items else 'empty', json.dumps(items, ensure_ascii=False),
                             json.dumps(problems, ensure_ascii=False), cost_usd or 0.0, tokens_in or 0,
                             tokens_out or 0, self.clock(), row_id))
        self._write(work)

    def fail(self, row_id, worker, error, retry_at=None, cost_usd=0.0, tokens_in=0, tokens_out=0):
        """Record a failed attempt; it waits for `retry_at` unless it was the last allowed attempt."""
        def work():
            row = self._held(row_id, worker)
            again = retry_at is not None and row['attempts'] < MAX_ATTEMPTS
            self.db.execute('UPDATE conversations SET status=?, last_error=?, next_attempt_at=?,'
                            ' lease_worker=NULL, lease_started=NULL, cost_usd=cost_usd+?, tokens_in=tokens_in+?,'
                            ' tokens_out=tokens_out+?, updated=? WHERE id=?',
                            ('pending' if again else 'error', str(error), retry_at if again else None,
                             cost_usd or 0.0, tokens_in or 0, tokens_out or 0, self.clock(), row_id))
        self._write(work)

    def retry(self, row_id):
        """Owner action: give an `error` row a fresh pair of attempts; its earlier cost stays counted."""
        def work():
            if self._by_id(row_id)['status'] != 'error':
                raise LedgerError(f'Row {row_id} is not in error')
            self.db.execute("UPDATE conversations SET status='pending', attempts=0, next_attempt_at=NULL,"
                            " updated=? WHERE id=?", (self.clock(), row_id))
        self._write(work)

    def unmerged(self):
        """Finished rows (done or empty) the merger has not taken yet, oldest first."""
        values = self.db.execute(f'SELECT {",".join(COLUMNS)} FROM conversations WHERE status IN (\'done\', \'empty\')'
                                 ' AND merged IS NULL ORDER BY id').fetchall()
        return [self._row(v) for v in values]

    def mark_merged(self, row_ids, night):
        """Record that `night`'s merger took these finished rows; any other row refuses the whole batch."""
        def work():
            for row_id in row_ids:
                row = self._by_id(row_id)
                if row['status'] not in ('done', 'empty') or row['merged'] is not None:
                    raise LedgerError(f'Row {row_id} is not a finished, unmerged row')
                self.db.execute('UPDATE conversations SET merged=?, updated=? WHERE id=?', (night, self.clock(), row_id))
        self._write(work)

    def merged_items(self):
        """{(row id, item index)} the merger already took."""
        return {tuple(pair) for pair in self.db.execute('SELECT row_id, item FROM merged_items')}

    def mark_items_merged(self, pairs, night):
        """Record that `night` took these (row id, item index) pairs; a row whose items are all taken is
        marked merged. An item already taken, out of range or of an unfinished row refuses the batch."""
        def work():
            touched = set()
            for row_id, index in pairs:
                row = self._by_id(row_id)
                if (row['status'] not in ('done', 'empty') or row['merged'] is not None
                        or not 0 <= index < len(row['items'] or [])):
                    raise LedgerError(f'Item {index} of row {row_id} is not an item of a finished, unmerged row')
                try:
                    self.db.execute('INSERT INTO merged_items (row_id, item, night) VALUES (?, ?, ?)', (row_id, index, night))
                except sqlite3.IntegrityError as exc:
                    raise LedgerError(f'Item {index} of row {row_id} was already merged') from exc
                touched.add(row_id)
            for row_id in touched:
                taken = self.db.execute('SELECT COUNT(*) FROM merged_items WHERE row_id=?', (row_id,)).fetchone()[0]
                if taken == len(self._by_id(row_id)['items'] or []):
                    self.db.execute('UPDATE conversations SET merged=?, updated=? WHERE id=?', (night, self.clock(), row_id))
        self._write(work)

    def get_meta(self, key):
        row = self.db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def set_meta(self, key, value):
        self._write(lambda: self.db.execute('INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE'
                                            ' SET value=excluded.value', (key, json.dumps(value))))

    def rows(self, status=None):
        query = f'SELECT {",".join(COLUMNS)} FROM conversations'
        values = self.db.execute(query + (' WHERE status=? ORDER BY id' if status else ' ORDER BY id'),
                                 (status,) if status else ()).fetchall()
        return [self._row(v) for v in values]

    def summary(self):
        counts = dict(self.db.execute('SELECT status, COUNT(*) FROM conversations GROUP BY status ORDER BY status'))
        cost = self.db.execute('SELECT COALESCE(SUM(cost_usd), 0) FROM conversations').fetchone()[0]
        return {'counts': counts, 'cost_usd': cost}
