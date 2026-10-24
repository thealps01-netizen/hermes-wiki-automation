"""Recoverable candidate mechanics, not a public activation or owner approval endpoint."""
from contextlib import contextmanager
import errno
import os
from pathlib import Path
import time

from workflow_paths import checked_path, identifier
from owner_decisions import OwnerDecisions, canonical
from wiki_candidates import review_snapshot, load_candidate, cmd_approve, sha, Refused
import contextlib
import hashlib
import io
import json
import tempfile
import shutil
import sys
import evidence_store


def _checkpoint(name):
    return None


def _atomic(path, data, *, checkpoint=None):
    check = _checkpoint if checkpoint is None else checkpoint
    path.parent.mkdir(parents=True, exist_ok=True)
    check(f'before-write:{path.name}')
    fd, name = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            check(f'before-temp:{path.name}')
            handle.write(data)
            handle.flush()
            check(f'after-temp:{path.name}')
            check(f'before-fsync:{path.name}')
            os.fsync(handle.fileno())
            check(f'after-fsync:{path.name}')
        check(f'before-replace:{path.name}')
        os.replace(name, path)
        check(f'after-replace:{path.name}')
    finally:
        if os.path.exists(name):
            os.unlink(name)
    check(f'after-write:{path.name}')


def _rename_no_replace(source, destination):
    """Capture the current directory entry without ever replacing an archive."""
    if os.name == 'nt':
        os.rename(source, destination)  # Windows rename refuses an existing destination.
    elif sys.platform.startswith('linux'):
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        rename = getattr(libc, 'renameat2', None)
        if rename is None:
            raise ApplyRefused('No supported no-overwrite rename; source was not changed')
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1):  # RENAME_NOREPLACE
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), str(source))
    else:
        raise ApplyRefused('No supported no-overwrite rename; source was not changed')


def _source_archive(wiki, operation_id):
    return checked_path(wiki, f'.llm-wiki/source-recovery/{identifier(operation_id)}/captured.bin')


def _check_capture(target, captured, expected):
    if sha(captured) != expected:
        # Restore only into an absent name. Keep the capture even when another owner
        # writer already created the target; neither set of bytes may be discarded.
        try:
            restoration = captured.with_name('restoration.bin')
            _atomic(restoration, captured.read_bytes())
            _rename_no_replace(restoration, target)
        except FileExistsError:
            pass
        except OSError as exc:
            raise ApplyRefused('Source drift retained in source-recovery; restoration unavailable') from exc
        raise ApplyRefused('Target drift preserved in source-recovery; recovery requires review')


def _publish_source(wiki, target, source, snapshot, operation_id):
    """Capture-and-verify, then publish exclusively; never replace/unlink live bytes.

    This is not CAS: an owner handle may still edit the retained capture. It is a
    lossless no-overwrite protocol, with drift requiring review and archives retained.
    """
    captured = _source_archive(wiki, operation_id)
    publish_file(target, source, snapshot['expected_base'], captured)


def _retained_captures(captured):
    yield captured
    for directory in sorted(captured.parent.glob('recapture-*')):
        yield checked_path(captured.parent, f'{directory.name}/captured.bin')


def _retained_capture_drift(captured, expected):
    """Inspect every retained object without restoring or changing owner bytes."""
    drift = False
    for retained in _retained_captures(captured):
        if retained.exists():
            drift |= sha(retained) != expected
    return drift


def _check_retained_captures(captured, expected):
    if _retained_capture_drift(captured, expected):
        raise ApplyRefused('Retained capture drift preserved; recovery requires review')


def _restore_capture_gap(target, captured, expected, *, checkpoint=None):
    check = _checkpoint if checkpoint is None else checkpoint
    for retained in _retained_captures(captured):
        if retained.exists():
            _check_capture(target, retained, expected)
    if not target.exists():
        restoration = checked_path(captured.parent, 'restoration.bin')
        _atomic(restoration, captured.read_bytes(), checkpoint=check)
        try:
            _rename_no_replace(restoration, target)
        except FileExistsError:
            pass  # An independent owner wins the name; validation must see their bytes.


def publish_file(target, source, expected_base, captured, *, checkpoint=None, boundary='source'):
    """Retain current bytes and publish without replacing independently owned entries."""
    check = _checkpoint if checkpoint is None else checkpoint
    target = checked_path(target.parent, target.name)
    captured = checked_path(captured.parent, captured.name)
    captured.parent.mkdir(parents=True, exist_ok=True)
    staged = captured.with_name('publication.bin')
    if source is not None:
        _atomic(staged, source, checkpoint=check)
    check('before-write:retire' if source is None else f'before-write:{target.name}')
    if source is not None:
        check(f'before-replace:{target.name}')
    try:
        if expected_base is not None:
            for retained in _retained_captures(captured):
                if retained.exists():
                    _check_capture(target, retained, expected_base)
            archive = captured
            if captured.exists() and target.exists():
                if sha(target) != expected_base:
                    raise ApplyRefused('Target drift preserved; existing retained capture cannot authorize replacement')
                # Re-capture identical restored bytes exclusively; the check is not CAS.
                # A writer racing the rename is retained and checked, never overwritten.
                directory = Path(tempfile.mkdtemp(prefix='recapture-', dir=captured.parent))
                archive = checked_path(directory, 'captured.bin')
            if not archive.exists():
                check(f'before-capture:{boundary}')
                _rename_no_replace(target, archive)
                check(f'after-capture:{boundary}')
            _check_capture(target, archive, expected_base)
        if source is not None:
            check(f'before-publish:{boundary}')
            _rename_no_replace(staged, target)  # Exclusive publication, not replace after a pre-read.
            check(f'after-publish:{boundary}')
        for retained in _retained_captures(captured):
            if retained.exists():
                _check_capture(target, retained, expected_base)
    except OSError as exc:
        raise ApplyRefused('Source publication refused; live and captured owner bytes were preserved') from exc
    check('after-write:retire' if source is None else f'after-replace:{target.name}')
    if source is not None:
        check(f'after-write:{target.name}')


def _step(store, operation_id, name, result):
    _checkpoint(f'before-step:{name}')
    store.record_step(operation_id, name, result)
    _checkpoint(f'after-step:{name}')


def _transition(store, operation_id, expected, new):
    _checkpoint(f'before-transition:{new}')
    store.transition(operation_id, expected, new)
    _checkpoint(f'after-transition:{new}')


def _identity(snapshot, approval):
    return hashlib.sha256(canonical({'issuer': approval.get('issuer'), 'request_id': approval.get('request_id'),
                                     'review_digest': snapshot['review_digest']})).hexdigest()


def apply_candidate(wiki, inbox, ref, snapshot, approval, store):
    data = Path(inbox).parent
    if store.path.resolve() != checked_path(data, 'workflow.sqlite').resolve():
        raise ApplyRefused('Workflow journal belongs to another data root')
    operation_id = _identity(snapshot, approval)
    with operation_lock(data):
        existing = store.get_operation(operation_id)
        if existing:
            if existing.get('snapshot') != snapshot or existing.get('approval') != approval or existing.get('ref') != ref:
                raise ApplyRefused('Operation identity changed')
            return _recover(wiki, inbox, operation_id, store)
        if snapshot.get('ref') != ref or review_snapshot(wiki, inbox, ref) != snapshot:
            raise ApplyRefused('Reviewed snapshot changed')
        with OwnerDecisions(data) as authority:
            authority.verify(approval, snapshot)
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_approve(wiki, inbox, ref, True)
        candidate, metadata = load_candidate(inbox, ref)
        staged = checked_path(data, f'operations/{operation_id}/source.md')
        if snapshot['kind'] != 'retire':
            source = (candidate / 'source.md').read_bytes()
            if hashlib.sha256(source).hexdigest() != snapshot['source_hash']:
                raise ApplyRefused('Draft changed during preparation')
            _atomic(staged, source)
        if snapshot['expected_base'] is not None:
            base = checked_path(wiki, f"raw/sources/{snapshot['target']}").read_bytes()
            if hashlib.sha256(base).hexdigest() != snapshot['expected_base']:
                raise ApplyRefused('Target changed during preparation')
            _atomic(staged.with_name('base.md'), base)
        for group, entries in (('evidence', snapshot['evidence']), ('stored_evidence', snapshot['stored_evidence'])):
            for entry in entries:
                origin = checked_path(candidate / 'evidence' if group == 'evidence' else Path(wiki) / 'raw/evidence', entry['path'])
                content = origin.read_bytes()
                if hashlib.sha256(content).hexdigest() != entry['sha256']:
                    raise ApplyRefused('Evidence changed during preparation')
                _atomic(checked_path(data, f"operations/{operation_id}/{group}/{entry['path']}"), content)
        if review_snapshot(wiki, inbox, ref) != snapshot:
            raise ApplyRefused('Review changed while preparation was captured')
        _checkpoint('before-record:operation')
        store.record_operation({'operation_id': operation_id, 'type': 'candidate', 'ref': ref,
                                'snapshot': snapshot, 'approval': approval})
        _checkpoint('after-record:operation')
        return _recover(wiki, inbox, operation_id, store)


def _evidence_groups(snapshot):
    groups = {}
    for group in ('evidence', 'stored_evidence'):
        for entry in snapshot[group]:
            name, relative = entry['path'].split('/', 1)
            identifier(name)
            groups.setdefault(name, {}).setdefault(group, {})[relative] = entry['sha256']
    return groups


def _publish_evidence(wiki, data, operation_id, snapshot, store):
    for name, groups in _evidence_groups(snapshot).items():
        original_group = 'stored_evidence' if 'stored_evidence' in groups else 'evidence'
        original = groups[original_group]
        staged = checked_path(data, f'operations/{operation_id}/{original_group}/{name}')
        for relative, expected in original.items():
            if sha(checked_path(staged, relative)) != expected:
                raise ApplyRefused('Prepared evidence changed')
        dest = checked_path(wiki, f'raw/evidence/{name}')
        if dest.exists():
            actual = {p.relative_to(dest).as_posix(): sha(checked_path(dest, p.relative_to(dest).as_posix()))
                      for p in dest.rglob('*') if p.is_file()}
            if {k: v for k, v in actual.items() if k != 'manifest.json'} != {k: v for k, v in original.items() if k != 'manifest.json'}:
                raise ApplyRefused('Existing evidence drift preserved')
            manifest_path = checked_path(dest, 'manifest.json')
            if not manifest_path.is_file():
                raise ApplyRefused('Existing evidence manifest missing; no owned capture can restore it')
            try:
                live_manifest = json.loads(manifest_path.read_bytes())
            except (OSError, ValueError) as exc:
                raise ApplyRefused('Existing evidence manifest unreadable; owner bytes preserved') from exc
            if not isinstance(live_manifest, dict):
                raise ApplyRefused('Existing evidence manifest is not an object; owner bytes preserved')
            prepared_manifest = json.loads(checked_path(staged, 'manifest.json').read_bytes())
            if {k: v for k, v in live_manifest.items() if k != 'used_by'} != {k: v for k, v in prepared_manifest.items() if k != 'used_by'}:
                raise ApplyRefused('Existing evidence manifest changed')
        else:
            if original_group == 'stored_evidence':
                raise ApplyRefused('Previously stored evidence disappeared')
            temporary = Path(tempfile.mkdtemp(prefix=f'.{name}.', dir=dest.parent))
            try:
                for relative in original:
                    _atomic(checked_path(temporary, relative), checked_path(staged, relative).read_bytes())
                _checkpoint(f'before-write:evidence-{name}')
                os.rename(temporary, dest)
                _checkpoint(f'after-write:evidence-{name}')
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
        _step(store, operation_id, f'evidence:{name}', {'files': original})


def _attribution_groups(wiki, snapshot, operation_id, store):
    evidence_root = checked_path(wiki, 'raw/evidence')
    groups = set(_evidence_groups(snapshot))
    if snapshot['expected_base'] is not None:
        base = checked_path(store.path.parent, f'operations/{identifier(operation_id)}/base.md')
        if sha(base) != snapshot['expected_base']:
            raise ApplyRefused('Prepared base changed')
        lines, table = evidence_store._evidence_texts(base.read_text(encoding='utf-8'))
        known = evidence_store.folders(evidence_root)
        bound = {step['step'].split(':', 1)[1] for step in store.steps(operation_id)
                 if step['step'].startswith('attribution-base:')}
        groups.update(token for token in evidence_store.cited_ids(lines + table)
                      if token in known or token in bound)
    return groups


def _restore_attribution_gaps(wiki, snapshot, operation_id, store):
    steps = {step['step']: step['result'] for step in store.steps(operation_id)}
    for name in sorted(_attribution_groups(wiki, snapshot, operation_id, store)):
        target = checked_path(wiki, f'raw/evidence/{name}/manifest.json')
        captured = checked_path(wiki, f'.llm-wiki/evidence-attribution/{identifier(operation_id)}/{name}/captured.bin')
        binding = steps.get(f'attribution-base:{name}')
        if binding is not None and not target.exists() and not captured.exists():
            raise ApplyRefused('Missing evidence manifest has no exact operation-owned retained capture')
        if captured.exists():
            if binding is None:
                raise ApplyRefused('Attribution capture has no operation-owned before-image binding')
            if not target.parent.is_dir():
                raise ApplyRefused('Existing evidence directory disappeared; retained manifest is not a payload backup')
            _restore_capture_gap(target, captured, binding['sha256'])


def _sync_attribution(wiki, snapshot, operation_id, store):
    evidence_root = checked_path(wiki, 'raw/evidence')
    sources = checked_path(wiki, 'raw/sources')
    for p in [*evidence_root.rglob('*'), *sources.glob('*.md')]:
        checked_path(wiki, p.relative_to(wiki).as_posix())
    groups = _attribution_groups(wiki, snapshot, operation_id, store)
    bindings = {step['step']: step['result'] for step in store.steps(operation_id)}
    def bind_base(name, expected):
        step = f'attribution-base:{name}'
        result = {'sha256': expected}
        if step in bindings and bindings[step] != result:
            raise ApplyRefused('Attribution manifest changed from operation-owned before-image')
        _step(store, operation_id, step, result)
    for name in sorted(groups):
        _checkpoint(f'before-write:attribution-{name}')
        staging = checked_path(wiki, f'.llm-wiki/evidence-attribution/{identifier(operation_id)}')
        evidence_store.sync_used_by(evidence_root, sources, only={name},
                                   staging_root=staging, checkpoint=_checkpoint, bind_base=bind_base)
        _checkpoint(f'after-write:attribution-{name}')
    _step(store, operation_id, 'attribution', {'evidence_ids': sorted(groups)})


def _recover(wiki, inbox, operation_id, store):
    try:
        return _resume(wiki, inbox, operation_id, store)
    except ApplyRefused as exc:
        operation = store.get_operation(operation_id)
        if operation['state'] == 'applying':
            store.transition(operation_id, 'applying', 'recovery_required', {'reason': str(exc)})
        raise


def _resume(wiki, inbox, operation_id, store):
    operation = store.get_operation(operation_id)
    snapshot, approval = operation['snapshot'], operation['approval']
    data = Path(inbox).parent
    if snapshot['project_root'] != str(Path(wiki).resolve()) or sha(checked_path(wiki, '.llm-wiki/project.json')) != snapshot['project_hash']:
        raise ApplyRefused('Project identity changed')
    target = checked_path(wiki, f"raw/sources/{snapshot['target']}")
    actual = sha(target) if target.exists() else None
    desired = None if snapshot['kind'] == 'retire' else snapshot['source_hash']
    if operation['state'] == 'applied':
        drift = actual != desired
        captured = _source_archive(wiki, operation_id)
        drift |= _retained_capture_drift(captured, snapshot['expected_base'])
        for name, groups in _evidence_groups(snapshot).items():
            original = groups.get('stored_evidence', groups.get('evidence', {}))
            dest = checked_path(wiki, f'raw/evidence/{name}')
            payload = {p.relative_to(dest).as_posix(): sha(checked_path(dest, p.relative_to(dest).as_posix()))
                       for p in dest.rglob('*') if p.is_file() and p.name != 'manifest.json'}
            drift |= payload != {k: v for k, v in original.items() if k != 'manifest.json'}
        for step in store.steps(operation_id):
            if step['step'].startswith('attribution-base:'):
                name = identifier(step['step'].split(':', 1)[1])
                archive = checked_path(wiki, f'.llm-wiki/evidence-attribution/{identifier(operation_id)}/{name}/captured.bin')
                for retained in _retained_captures(archive):
                    if retained.exists():
                        drift |= sha(retained) != step['result']['sha256']
        return {'operation_id': operation_id, 'state': 'applied', 'later_drift': drift}
    candidate, metadata = load_candidate(inbox, operation['ref'])
    observed_source = sha(candidate / 'source.md') if (candidate / 'source.md').is_file() else None
    observed_evidence = [{'path': p.relative_to(candidate / 'evidence').as_posix(), 'sha256': sha(p)}
                         for p in sorted((candidate / 'evidence').rglob('*')) if p.is_file()]
    if sha(candidate / 'candidate.json') != snapshot['metadata_hash'] or observed_source != snapshot['source_hash'] or observed_evidence != snapshot['evidence']:
        raise ApplyRefused('Reviewed candidate inputs changed; review again')
    source = None
    if snapshot['kind'] != 'retire':
        source = checked_path(data, f'operations/{identifier(operation_id)}/source.md').read_bytes()
        if hashlib.sha256(source).hexdigest() != desired:
            raise ApplyRefused('Prepared source changed')
        from wiki_candidates import validate_source_citations
        try:
            validate_source_citations(source.decode('utf-8'), metadata.get('evidence_ids', []))
        except Refused as exc:
            raise ApplyRefused(str(exc)) from exc
    if operation['state'] in ('collected', 'drafted'):
        if review_snapshot(wiki, inbox, operation['ref']) != snapshot:
            raise ApplyRefused('Reviewed snapshot changed before authorization consumption')
        if operation['state'] == 'collected':
            _transition(store, operation_id, 'collected', 'drafted')
        _transition(store, operation_id, 'drafted', 'awaiting_approval')
        operation = store.get_operation(operation_id)
    _checkpoint('before-consume:authority')
    with OwnerDecisions(data) as authority:
        authority.consume(approval, snapshot, operation_id)
    _checkpoint('after-consume:authority')
    _step(store, operation_id, 'authority', {'request_id': approval['request_id']})
    if operation['state'] == 'awaiting_approval':
        _transition(store, operation_id, 'awaiting_approval', 'applying')
    recorded = {step['step'] for step in store.steps(operation_id)}
    captured = _source_archive(wiki, operation_id)
    _check_retained_captures(captured, snapshot['expected_base'])
    capture_gap = actual is None and captured.exists() and snapshot['expected_base'] is not None and 'source' not in recorded
    if (actual not in (snapshot['expected_base'], desired) and not capture_gap) or ('source' in recorded and actual != desired):
        raise ApplyRefused('Target drift preserved; recovery requires review')
    if operation['state'] == 'recovery_required':
        _transition(store, operation_id, 'recovery_required', 'applying')
    _restore_attribution_gaps(wiki, snapshot, operation_id, store)
    _publish_evidence(wiki, data, operation_id, snapshot, store)
    if actual != desired:
        _publish_source(wiki, target, source, snapshot, operation_id)
    if (sha(target) if target.exists() else None) != desired:
        raise ApplyRefused('Source publication could not be verified')
    _step(store, operation_id, 'source', {'sha256': desired})
    _sync_attribution(wiki, snapshot, operation_id, store)
    _check_retained_captures(captured, snapshot['expected_base'])
    for step in store.steps(operation_id):
        if step['step'].startswith('attribution-base:'):
            name = identifier(step['step'].split(':', 1)[1])
            live = checked_path(wiki, f'raw/evidence/{name}/manifest.json')
            archive = checked_path(wiki, f'.llm-wiki/evidence-attribution/{identifier(operation_id)}/{name}/captured.bin')
            for retained in _retained_captures(archive):
                if retained.exists():
                    _check_capture(live, retained, step['result']['sha256'])
    candidate, _ = load_candidate(inbox, operation['ref'])
    marker = canonical({'operation_id': operation_id, 'kind': snapshot['kind'], 'target': snapshot['target'],
                        'review_digest': snapshot['review_digest'], 'source_hash': snapshot['source_hash']}) + b'\n'
    marker_path = checked_path(inbox, f"{operation['ref'].split('/')[0]}/candidates/{operation['ref'].split('/')[1]}/applied.json")
    if marker_path.exists():
        if marker_path.read_bytes() != marker:
            raise ApplyRefused('Conflicting application marker')
    else:
        _atomic(marker_path, marker)
    _step(store, operation_id, 'marker', {'sha256': hashlib.sha256(marker).hexdigest()})
    _transition(store, operation_id, 'applying', 'applied')
    return {'operation_id': operation_id, 'state': 'applied', 'later_drift': False}


def reconcile_operation(wiki, inbox, operation_id, store):
    from workflow_paths import PathRefused
    try:
        identifier(operation_id)
    except PathRefused as exc:
        raise ApplyRefused('Valid operation identity is required') from exc
    data = Path(inbox).parent
    if store.path.resolve() != checked_path(data, 'workflow.sqlite').resolve():
        raise ApplyRefused('Workflow journal belongs to another data root')
    with operation_lock(data):
        operation = store.get_operation(operation_id)
        if not operation or operation.get('type') != 'candidate' or not isinstance(operation.get('approval'), dict):
            raise ApplyRefused('Recovery requires a prepared owner-authorized candidate operation')
        if _identity(operation['snapshot'], operation['approval']) != operation_id:
            raise ApplyRefused('Prepared operation identity changed')
        return _recover(wiki, inbox, operation_id, store)


def reject_candidate(inbox, ref, reason, *, wiki=None, expected_review_digest=None):
    from workflow_store import WorkflowStore
    if not isinstance(reason, str) or not reason.strip():
        raise ApplyRefused('A nonempty rejection reason is required')
    parts = ref.split('/')
    if len(parts) != 2:
        raise ApplyRefused('Candidate reference requires run/name')
    run, name = map(identifier, parts)
    data = Path(inbox).parent
    with operation_lock(data):
        journal = checked_path(data, 'workflow.sqlite')
        if journal.exists():
            with WorkflowStore(journal, read_only=True) as store:
                prepared = store.db.execute(
                    "SELECT id FROM operations WHERE json_extract(identity, '$.type')='candidate' "
                    "AND json_extract(identity, '$.ref')=?", (ref,)).fetchone()
                if prepared:
                    raise ApplyRefused('Prepared application owns these inputs; reconcile it instead of rejecting')
        candidate = checked_path(inbox, f'{run}/candidates/{name}')
        destination = checked_path(inbox, f'rejected/{run}-{name}')
        if candidate.exists() and destination.exists():
            raise ApplyRefused('Rejected destination already exists; neither copy was changed')
        folder = candidate if candidate.exists() else destination
        if not folder.is_dir():
            raise ApplyRefused('Candidate and rejected copy are both missing')
        if expected_review_digest is not None and candidate.exists():
            if wiki is None or review_snapshot(Path(wiki), Path(inbox), ref)['review_digest'] != expected_review_digest:
                raise ApplyRefused('Reviewed rejection snapshot changed; review again')
        metadata_path = checked_path(folder, 'candidate.json')
        identity = {'type': 'rejection', 'ref': ref, 'reason': reason, 'metadata_hash': sha(metadata_path)}
        if expected_review_digest is not None:
            identity['review_digest'] = expected_review_digest
        operation_id = hashlib.sha256(canonical(identity)).hexdigest()
        record = {**identity, 'operation_id': operation_id}
        marker = canonical({'operation_id': operation_id, 'ref': ref, 'reason': reason}) + b'\n'
        reason_path = checked_path(folder, 'rejected.json')
        if reason_path.exists() and reason_path.read_bytes() != marker:
            raise ApplyRefused('Existing rejection decision differs')
        with WorkflowStore(checked_path(data, 'workflow.sqlite')) as store:
            if not candidate.exists() and store.get_operation(operation_id) is None:
                raise ApplyRefused('Moved candidate has no durable rejection record')
            store.record_operation(record)
            if not reason_path.exists():
                _atomic(reason_path, marker)
            if store.get_operation(operation_id)['state'] == 'collected':
                _transition(store, operation_id, 'collected', 'rejected')
            if candidate.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                _checkpoint('before-write:reject-move')
                os.rename(candidate, destination)
                _checkpoint('after-write:reject-move')
            _step(store, operation_id, 'rejection', {'reason': reason, 'destination': destination.name})
        return {'operation_id': operation_id, 'state': 'rejected'}


def reconcile_legacy(wiki, inbox, store, import_verified=False):
    rows = []
    for marker_path in sorted(Path(inbox).glob('*/candidates/*/applied.json')):
        ref = f'{marker_path.parent.parent.parent.name}/{marker_path.parent.name}'
        row = {'ref': ref, 'status': 'ambiguous'}
        try:
            candidate, metadata = load_candidate(inbox, ref)
            marker = json.loads(checked_path(candidate, 'applied.json').read_bytes())
            target = checked_path(wiki, f"raw/sources/{metadata['target']}")
            if marker.get('kind') != metadata['kind'] or marker.get('target') != metadata['target']:
                raise ApplyRefused('Marker does not describe this candidate')
            if metadata['kind'] == 'retire':
                raise ApplyRefused('Absence plus a legacy marker does not prove retirement')
            source = checked_path(candidate, 'source.md')
            if not target.is_file() or sha(target) != sha(source):
                raise ApplyRefused('Current source disagrees with the marked candidate')
            for name in metadata.get('evidence_ids', []):
                dest = checked_path(wiki, f'raw/evidence/{identifier(name)}')
                if not dest.is_dir() or not (dest / 'manifest.json').is_file():
                    raise ApplyRefused('Legacy evidence is incomplete')
                original = candidate / 'evidence' / name
                if original.is_dir():
                    for p in [*original.rglob('*'), *dest.rglob('*')]:
                        checked_path(original if p.is_relative_to(original) else dest, p.relative_to(original if p.is_relative_to(original) else dest).as_posix())
                    from wiki_candidates import same_evidence
                    if not same_evidence(original, dest):
                        raise ApplyRefused('Legacy evidence payload disagrees')
                manifest = json.loads(checked_path(dest, 'manifest.json').read_bytes())
                cites, _ = evidence_store.citations(wiki / 'raw/sources', {name})
                if manifest.get('used_by') != sorted(cites.get(name, set())):
                    raise ApplyRefused('Legacy attribution disagrees with source citations')
            row['status'] = 'verified'
            if import_verified:
                identity = {'type': 'legacy-import', 'ref': ref, 'source_hash': sha(target), 'marker_hash': sha(marker_path)}
                operation_id = hashlib.sha256(canonical(identity)).hexdigest()
                operation = store.record_operation({**identity, 'operation_id': operation_id})
                for expected, new in [('collected', 'drafted'), ('drafted', 'awaiting_approval'), ('awaiting_approval', 'applying'), ('applying', 'applied')]:
                    if operation['state'] == expected:
                        operation = store.transition(operation_id, expected, new, {'verification': 'legacy content agreement only, not owner authorization'})
                row.update(status='imported', operation_id=operation_id)
        except (OSError, ValueError, RuntimeError, Refused) as exc:
            row['reason'] = str(exc)
        rows.append(row)
    return rows


class ApplyRefused(RuntimeError):
    pass


@contextmanager
def operation_lock(data_root: Path, *, timeout=10):
    path = checked_path(data_root, 'operation.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        if path.stat().st_size == 0:
            handle.write(b'\0')
            handle.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                handle.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                if time.monotonic() >= deadline:
                    raise ApplyRefused('Operation lock is busy; the existing owner was not disturbed') from exc
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
