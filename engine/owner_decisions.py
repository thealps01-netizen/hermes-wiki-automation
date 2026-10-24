"""Engine-owned exact-review decision records.

Only the authenticated owner broker may prepare/confirm. Signatures establish broker provenance,
not biometric proof of a click. Draft handlers expose none of this interface or its data directory.
No protection against arbitrary code with the same OS account is claimed.
"""
from __future__ import annotations
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import time


class DecisionRefused(RuntimeError):
    pass


def digest_string(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in '0123456789abcdef' for ch in value)


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def bound_principal(principal, owner_key):
    if owner_key is None:
        return principal
    if not digest_string(owner_key):
        raise DecisionRefused('Verified owner binding is required')
    return canonical({'session': principal, 'owner_key': owner_key}).decode()


class OwnerDecisions:
    def __init__(self, data_root: Path, *, initialize=False, clock=time.time):
        self.path = Path(data_root) / 'owner-decisions.sqlite'
        self.initialize, self.clock = initialize, clock
        self.db = None

    def __enter__(self):
        from workflow_paths import checked_path, PathRefused
        try:
            checked_path(self.path.parent, self.path.name)
        except (PathRefused, OSError) as exc:
            raise DecisionRefused('Linked or unsafe authority path') from exc
        if not self.path.exists() and not self.initialize:
            raise DecisionRefused('Owner authority is not initialized')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=10)
        try:
            self.db.execute('BEGIN IMMEDIATE')
            version = self.db.execute('PRAGMA user_version').fetchone()[0]
            tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if version == 0:
                if tables or not self.initialize:
                    raise DecisionRefused('Unrecognized authority database')
                self.db.execute('CREATE TABLE authority (id TEXT PRIMARY KEY, secret BLOB NOT NULL)')
                self.db.execute('CREATE TABLE decisions (id TEXT PRIMARY KEY, snapshot TEXT NOT NULL, principal TEXT NOT NULL, expires REAL NOT NULL, state TEXT NOT NULL, receipt TEXT, operation_id TEXT)')
                self.db.execute('INSERT INTO authority VALUES (?,?)', (secrets.token_hex(16), secrets.token_bytes(32)))
                self.db.execute('PRAGMA user_version=1')
            elif version != 1 or tables != {'authority', 'decisions'}:
                raise DecisionRefused('Unsupported authority schema')
            rows = self.db.execute('SELECT id,secret FROM authority').fetchall()
            if len(rows) != 1 or not isinstance(rows[0][1], bytes) or len(rows[0][1]) != 32:
                raise DecisionRefused('Invalid owner authority')
            self.issuer, self.key = rows[0]
            self.db.commit()
        except (sqlite3.DatabaseError, DecisionRefused) as exc:
            self.db.rollback()
            self.db.close()
            raise DecisionRefused('Owner authority unreadable or unsupported') from exc
        return self

    def __exit__(self, *args):
        self.db.close()

    def prepare(self, snapshot: dict, principal: str, *, lifetime=300, owner_key=None) -> dict:
        if not principal or not digest_string(snapshot.get('review_digest')):
            raise DecisionRefused('Missing authenticated principal or exact review')
        request_id, expires = secrets.token_hex(32), self.clock() + min(max(lifetime, 1), 300)
        with self.db:
            self.db.execute('INSERT INTO decisions VALUES (?,?,?,?,?,NULL,NULL)',
                            (request_id, canonical(snapshot).decode(), bound_principal(principal, owner_key), expires, 'pending'))
        return {'request_id': request_id, 'review_digest': snapshot['review_digest'], 'expires_at': expires}

    def confirm(self, request_id: str, snapshot: dict, principal: str, *, owner_key=None) -> dict:
        with self.db:
            row = self.db.execute('SELECT snapshot,principal,expires,state FROM decisions WHERE id=?', (request_id,)).fetchone()
            if not row or row[3] != 'pending' or row[0] != canonical(snapshot).decode() or row[1] != bound_principal(principal, owner_key) or row[2] <= self.clock():
                raise DecisionRefused('Unknown, stale, expired, consumed or wrong-session review; review again')
            body = {'schema_version': 1, 'issuer': self.issuer, 'request_id': request_id,
                    'snapshot': snapshot, 'principal': principal, 'expires_at': row[2], 'choice': 'once'}
            if owner_key is not None:
                body['owner_key'] = owner_key
            receipt = {**body, 'signature': hmac.new(self.key, canonical(body), hashlib.sha256).hexdigest()}
            result = self.db.execute('UPDATE decisions SET state=?,receipt=? WHERE id=? AND state=?',
                                    ('approved', canonical(receipt).decode(), request_id, 'pending'))
            if result.rowcount != 1:
                raise DecisionRefused('Review was already decided')
            return receipt

    def verify(self, receipt: dict, snapshot: dict) -> dict:
        if not isinstance(receipt, dict):
            raise DecisionRefused('Owner receipt required')
        body = {k: v for k, v in receipt.items() if k != 'signature'}
        expected = hmac.new(self.key, canonical(body), hashlib.sha256).hexdigest()
        if not digest_string(receipt.get('signature')) or not hmac.compare_digest(receipt['signature'], expected):
            raise DecisionRefused('Invalid owner receipt signature')
        if body.get('issuer') != self.issuer or body.get('choice') != 'once' or body.get('snapshot') != snapshot:
            raise DecisionRefused('Receipt is for a different authority or reviewed operation')
        row = self.db.execute('SELECT state,receipt,expires,operation_id FROM decisions WHERE id=?', (body.get('request_id'),)).fetchone()
        if not row or row[0] not in ('approved', 'consumed') or row[1] != canonical(receipt).decode():
            raise DecisionRefused('Receipt is not an approved broker record')
        if row[0] == 'approved' and row[2] <= self.clock():
            raise DecisionRefused('Owner decision expired')
        return {'review_digest': snapshot['review_digest'], 'state': row[0], 'operation_id': row[3], 'principal': body['principal']}

    def approved_receipt(self, request_id: str, principal: str, ref: str, review_digest: str, *, owner_key=None):
        if not digest_string(request_id):
            raise DecisionRefused('Valid owner request identity is required')
        row = self.db.execute('SELECT snapshot,principal,state,receipt FROM decisions WHERE id=?', (request_id,)).fetchone()
        if not row:
            raise DecisionRefused('Unknown owner request; review again')
        snapshot = json.loads(row[0])
        if row[1] != bound_principal(principal, owner_key) or snapshot.get('ref') != ref or snapshot.get('review_digest') != review_digest:
            raise DecisionRefused('Owner request belongs to a different session, candidate or review')
        if row[2] == 'pending':
            return None
        receipt = json.loads(row[3])
        self.verify(receipt, snapshot)
        return receipt

    def recovery_receipt(self, request_id, owner_key):
        if not digest_string(request_id) or not digest_string(owner_key):
            raise DecisionRefused('Verified owner and valid approved request are required')
        row = self.db.execute('SELECT state,receipt FROM decisions WHERE id=?', (request_id,)).fetchone()
        if not row or row[0] not in ('approved', 'consumed'):
            raise DecisionRefused('Recovery never approves pending or unknown requests; review again')
        receipt = json.loads(row[1])
        if receipt.get('owner_key') != owner_key:
            raise DecisionRefused('Approved request has no matching durable owner binding')
        self.verify(receipt, receipt['snapshot'])
        return receipt

    def consume(self, receipt: dict, snapshot: dict, operation_id: str) -> dict:
        from workflow_paths import identifier, PathRefused
        try:
            identifier(operation_id)
        except PathRefused as exc:
            raise DecisionRefused('Valid operation identity is required') from exc
        self.db.execute('BEGIN IMMEDIATE')
        try:
            record = self.verify(receipt, snapshot)
            if record['state'] == 'consumed' and record['operation_id'] != operation_id:
                raise DecisionRefused('Owner decision already consumed by another operation')
            if record['state'] == 'approved':
                self.db.execute('UPDATE decisions SET state=?,operation_id=? WHERE id=? AND state=?',
                                ('consumed', operation_id, receipt['request_id'], 'approved'))
            self.db.commit()
            return {**record, 'state': 'consumed', 'operation_id': operation_id}
        except BaseException:
            self.db.rollback()
            raise


def _checked_binding(binding, home: Path) -> dict:
    """The owner binding exactly as owner_broker.owner_principal later compares it."""
    if not isinstance(binding, dict) or binding.get('mode') not in ('local_owner', 'interactive_owner'):
        raise DecisionRefused('Owner binding must be local_owner or interactive_owner')
    fields = {'mode', 'home'} | ({'provider', 'user_id', 'org_id'} if binding['mode'] == 'interactive_owner' else set())
    if set(binding) != fields or not isinstance(binding['home'], str) or Path(binding['home']).resolve() != home:
        raise DecisionRefused('Owner binding fields or profile do not match this profile')
    if binding['mode'] == 'interactive_owner' and (
            any(not isinstance(binding[key], str) or not binding[key] for key in ('provider', 'user_id'))
            or not (binding['org_id'] is None or isinstance(binding['org_id'], str))):
        raise DecisionRefused('Interactive owner binding needs the host provider and user identity')
    return dict(binding)


def activate(settings_path: Path, home: Path, payload: dict) -> dict:
    """Explicit owner setup: bind the profile owner, pin the loaded guard code, turn on owner
    publication and native harvest, and create the authority if it is absent. Re-running it after
    a plugin update replaces the pinned code hash and keeps the existing authority."""
    import os
    home = Path(home).resolve()
    if not isinstance(payload, dict) or set(payload) != {'binding', 'loaded_code_hash'}:
        raise DecisionRefused('Activation accepts only the owner binding and the loaded code hash')
    binding = _checked_binding(payload['binding'], home)
    if not digest_string(payload['loaded_code_hash']):
        raise DecisionRefused('Loaded code hash must be a lowercase SHA-256 digest')
    settings_path = Path(settings_path)
    settings = json.loads(settings_path.read_bytes())
    if not isinstance(settings, dict) or not settings.get('hermes_home') or Path(settings['hermes_home']).resolve() != home:
        raise DecisionRefused('Engine settings belong to another profile')
    data = Path(settings.get('audit_dir') or '')
    if not settings.get('audit_dir') or not data.is_dir():
        raise DecisionRefused('Configured engine data root is absent')
    with OwnerDecisions(data, initialize=True):
        pass
    settings.update({'owner_approval_enabled': True, 'owner_publication_enabled': True,
                     'harvest_workflow_enabled': True, 'owner_approval_owner': binding,
                     'owner_approval_runtime': {'loaded_code_hash': payload['loaded_code_hash']}})
    staged = settings_path.with_name(settings_path.name + '.activate.tmp')
    staged.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(staged, settings_path)
    return {'ok': True, 'activated': True}


def broker_command(operation: str, settings: dict, home: Path, payload: dict) -> dict:
    from wiki_candidates import review_snapshot, cmd_approve, Refused
    import wikiconfig
    import contextlib
    import io
    if not settings.get('hermes_home') or Path(settings['hermes_home']).resolve() != Path(home).resolve():
        raise DecisionRefused('Engine authority belongs to another profile')
    if settings.get('owner_approval_enabled') is not True:
        raise DecisionRefused('Owner approval is not activated for this profile')
    data = Path(settings['audit_dir'])
    wiki = wikiconfig.project_root(settings)
    if operation == 'initialize':
        with OwnerDecisions(data, initialize=True):
            pass
        return {'ok': True, 'initialized': True}
    if set(payload) - {'ref', 'review_digest', 'principal', 'request_id', 'owner_key'}:
        raise DecisionRefused('Unsupported owner decision fields')
    principal = payload.get('principal')
    if not digest_string(principal):
        raise DecisionRefused('Host-authenticated principal is required')
    if operation == 'recoverable':
        if settings.get('owner_publication_enabled') is not True or set(payload) != {'principal', 'owner_key'}:
            raise DecisionRefused('Owner recovery is not activated or request fields are unsupported')
        return _recoverable(data, payload['owner_key'])
    if operation == 'recover':
        if settings.get('owner_publication_enabled') is not True or set(payload) != {'principal', 'owner_key', 'request_id'}:
            raise DecisionRefused('Owner recovery is not activated or request fields are unsupported')
        with OwnerDecisions(data) as authority:
            receipt = authority.recovery_receipt(payload['request_id'], payload['owner_key'])
        return _apply_confirmed(wiki, data, receipt)
    if operation == 'confirm' and settings.get('owner_publication_enabled') is True:
        return _publish_confirm(wiki, data, payload)
    snapshot = review_snapshot(wiki, data / 'inbox', payload['ref'])
    if payload.get('review_digest') != snapshot['review_digest']:
        raise DecisionRefused('Displayed content is stale; review again')
    preview = io.StringIO()
    with contextlib.redirect_stdout(preview):
        cmd_approve(wiki, data / 'inbox', payload['ref'], True)
    with OwnerDecisions(data) as store:
        if operation == 'prepare':
            pending = store.prepare(snapshot, principal, owner_key=payload.get('owner_key'))
            return {'ok': False, 'needs_confirm': True, **pending, 'output': preview.getvalue()}
        if operation == 'confirm':
            store.confirm(payload['request_id'], snapshot, principal, owner_key=payload.get('owner_key'))
            return {'ok': False, 'authorized': True, 'request_id': payload['request_id'],
                    'reason': 'Owner decision recorded; publication remains disabled until recoverable application is verified.'}
        raise DecisionRefused('Unsupported owner operation')


def _recoverable(data, owner_key):
    import contextlib
    from candidate_apply import _identity
    from workflow_paths import checked_path
    from workflow_store import WorkflowStore
    if not digest_string(owner_key):
        raise DecisionRefused('Verified owner binding is required')
    with contextlib.ExitStack() as stack:
        authority = stack.enter_context(OwnerDecisions(data))
        path = checked_path(data, 'workflow.sqlite')
        journal = stack.enter_context(WorkflowStore(path, read_only=True)) if path.exists() else None
        operations = []
        for request_id, state, raw, expires in authority.db.execute(
                'SELECT id,state,receipt,expires FROM decisions WHERE state IN (?,?)', ('approved', 'consumed')):
            receipt = json.loads(raw)
            if receipt.get('owner_key') != owner_key or state == 'approved' and expires <= authority.clock():
                continue
            authority.verify(receipt, receipt['snapshot'])
            snapshot = receipt['snapshot']
            saved = journal.get_operation(_identity(snapshot, receipt)) if journal else None
            if saved and saved['state'] == 'applied':
                continue
            operations.append({'request_id': request_id, 'ref': snapshot['ref'], 'kind': snapshot['kind'],
                'target': snapshot['target'], 'review_digest': snapshot['review_digest'],
                'state': saved['state'] if saved else 'approved'})
        return {'ok': True, 'operations': operations}


def _publish_confirm(wiki, data, payload):
    from wiki_candidates import review_snapshot
    with OwnerDecisions(data) as authority:
        receipt = authority.approved_receipt(payload['request_id'], payload['principal'], payload['ref'], payload['review_digest'], owner_key=payload.get('owner_key'))
        if receipt is None:
            snapshot = review_snapshot(wiki, data / 'inbox', payload['ref'])
            if snapshot['review_digest'] != payload['review_digest']:
                raise DecisionRefused('Displayed content is stale; review again')
            receipt = authority.confirm(payload['request_id'], snapshot, payload['principal'], owner_key=payload.get('owner_key'))
        else:
            snapshot = receipt['snapshot']
    return _apply_confirmed(wiki, data, receipt)


def _apply_confirmed(wiki, data, receipt):
    snapshot = receipt['snapshot']
    from candidate_apply import apply_candidate
    from workflow_store import WorkflowStore
    from workflow_paths import checked_path
    with WorkflowStore(checked_path(data, 'workflow.sqlite')) as journal:
        result = apply_candidate(wiki, data / 'inbox', snapshot['ref'], snapshot, receipt, journal)
    response = {'ok': not result['later_drift'], 'authorized': True, 'request_id': receipt['request_id'], **result}
    if result['later_drift']:
        response['reason'] = 'The previously applied result has changed; newer content was preserved, not repaired.'
    return response


def main(argv=None) -> int:
    import argparse
    import sys
    import wikiconfig
    from wiki_candidates import Refused
    from candidate_apply import ApplyRefused
    from workflow_store import WorkflowError
    parser = argparse.ArgumentParser(description='Engine-owned owner authority; callable only through the trusted broker or explicit setup')
    parser.add_argument('operation', choices=('activate', 'initialize', 'prepare', 'confirm', 'recover', 'recoverable'))
    parser.add_argument('--home', required=True)
    parser.add_argument('--settings', required=True)
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise DecisionRefused('Owner request too large')
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise DecisionRefused('Owner request must be an object')
        settings = json.loads(Path(args.settings).read_bytes())
        if args.operation == 'activate':
            result = activate(Path(args.settings), Path(args.home), payload)
        else:
            result = broker_command(args.operation, settings, Path(args.home), payload)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (DecisionRefused, ApplyRefused, WorkflowError, Refused, wikiconfig.ConfigError, OSError, ValueError, KeyError, TypeError, sqlite3.DatabaseError) as exc:
        print(json.dumps({'ok': False, 'reason': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

