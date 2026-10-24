"""Recovery mechanics use disposable projects; no live entry point is enabled."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class OperationLockTests(unittest.TestCase):
    def test_two_processes_serialize_and_process_death_releases_lock(self):
        from candidate_apply import operation_lock, ApplyRefused
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as tmp:
            root = Path(tmp)
            worker = Path(__file__).with_name('candidate_apply_worker.py')
            with operation_lock(root):
                denied = subprocess.run([sys.executable, str(worker), 'lock', str(root)], capture_output=True, text=True, timeout=10)
                self.assertEqual(denied.returncode, 2, denied.stdout + denied.stderr)
                self.assertIn('Operation lock is busy', denied.stdout)
            proc = subprocess.Popen([sys.executable, str(worker), 'hold-lock', str(root)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertEqual(proc.stdout.readline().strip(), 'LOCKED')
                with self.assertRaises(ApplyRefused):
                    with operation_lock(root, timeout=0):
                        self.fail('Two independent processes acquired the same lock')
            finally:
                proc.kill()
                proc.communicate(timeout=10)
            with operation_lock(root, timeout=0):
                self.assertTrue((root / 'operation.lock').is_file())


class CandidateApplyTests(unittest.TestCase):
    def setUp(self):
        import json
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.wiki, self.data = self.root / 'wiki', self.root / 'data'
        self.inbox = self.data / 'inbox'
        (self.wiki / '.llm-wiki').mkdir(parents=True)
        (self.wiki / '.llm-wiki/project.json').write_bytes(b'{"id":"recovery-fixture"}')
        (self.wiki / 'raw/sources').mkdir(parents=True)
        (self.wiki / 'raw/evidence').mkdir()
        self.candidate = self.inbox / 'run/candidates/draft'
        self.candidate.mkdir(parents=True)
        self.target = self.wiki / 'raw/sources/2026-10-08-fixture.md'
        self.metadata = {'kind': 'new', 'target': self.target.name, 'summary': 'Fixture', 'why': 'Test', 'evidence_ids': []}
        (self.candidate / 'candidate.json').write_text(json.dumps(self.metadata), encoding='utf-8')
        self.source = b'# Recovery fixture\n\n## Decisions\n\n**1. Fixture.**\nEvidence: none (method).\n'
        (self.candidate / 'source.md').write_bytes(self.source)

    def authorize(self):
        from owner_decisions import OwnerDecisions
        from wiki_candidates import review_snapshot
        self.snapshot = review_snapshot(self.wiki, self.inbox, 'run/draft')
        with OwnerDecisions(self.data, initialize=True) as authority:
            request = authority.prepare(self.snapshot, 'fixture-owner')
            self.approval = authority.confirm(request['request_id'], self.snapshot, 'fixture-owner')

    def configure_recovery(self, kind):
        import hashlib
        import json
        evidence = self.candidate / 'evidence/fixture-code'
        evidence.mkdir(parents=True)
        payload = b'Exact stored evidence'
        (evidence / 'payload.txt').write_bytes(payload)
        (evidence / 'manifest.json').write_text(json.dumps({'schema': 1, 'evidence_id': 'fixture-code', 'used_by': [],
            'files': {'payload.txt': {'sha256': hashlib.sha256(payload).hexdigest()}}}), encoding='utf-8')
        self.metadata.update(kind=kind, evidence_ids=['fixture-code'])
        self.source = self.source.replace(b'none (method)', b'fixture-code')
        (self.candidate / 'source.md').write_bytes(self.source)
        if kind != 'new':
            original = self.source.replace(b'Recovery fixture', b'Original fixture')
            self.target.write_bytes(original)
            self.metadata['base_sha256'] = hashlib.sha256(original).hexdigest()
        if kind == 'retire':
            import shutil
            shutil.copytree(evidence, self.wiki / 'raw/evidence/fixture-code')
            (self.candidate / 'source.md').unlink()
            manifest = self.wiki / 'raw/evidence/fixture-code/manifest.json'
            value = json.loads(manifest.read_bytes())
            value['used_by'] = [self.target.name]
            manifest.write_text(json.dumps(value), encoding='utf-8')
        (self.candidate / 'candidate.json').write_text(json.dumps(self.metadata), encoding='utf-8')

    def remove_candidate_evidence(self, kind):
        import json
        import shutil
        if kind == 'update':
            shutil.copytree(self.candidate / 'evidence/fixture-code', self.wiki / 'raw/evidence/fixture-code')
            manifest = self.wiki / 'raw/evidence/fixture-code/manifest.json'
            value = json.loads(manifest.read_bytes())
            value['used_by'] = [self.target.name]
            manifest.write_text(json.dumps(value), encoding='utf-8')
            self.source = self.source.replace(b'fixture-code', b'none (method)')
            (self.candidate / 'source.md').write_bytes(self.source)
        self.metadata['evidence_ids'] = []
        shutil.rmtree(self.candidate / 'evidence')
        (self.candidate / 'candidate.json').write_text(json.dumps(self.metadata), encoding='utf-8')

    def test_actual_inner_manifest_publication_death_reconciles(self):
        import json
        from candidate_apply import reconcile_operation
        from workflow_store import WorkflowStore
        self.configure_recovery('new')
        self.authorize()
        request = self.root / 'worker-request.json'
        request.write_text(json.dumps({'wiki': str(self.wiki), 'inbox': str(self.inbox),
            'snapshot': self.snapshot, 'approval': self.approval}), encoding='utf-8')
        worker = Path(__file__).with_name('candidate_apply_worker.py')
        killed = subprocess.run([sys.executable, str(worker), 'attribution-death', str(request)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(killed.returncode, 91, killed.stdout + killed.stderr)
        temporary = Path(killed.stdout.strip())
        self.assertTrue(temporary.is_file(), 'Actual staged manifest must survive abrupt process death')
        self.assertEqual(json.loads(temporary.read_bytes())['used_by'], [self.target.name])
        dest = self.wiki / 'raw/evidence/fixture-code'
        self.assertFalse((dest / 'manifest.json').exists(), 'Native capture gap is observable')
        self.assertEqual(json.loads(temporary.with_name('captured.bin').read_bytes())['used_by'], [])
        self.assertEqual(self.target.read_bytes(), self.source)
        self.assertFalse((self.candidate / 'applied.json').exists())
        stamp = self.target.stat().st_mtime_ns
        with WorkflowStore(self.data / 'workflow.sqlite') as store:
            operation_id, state = store.db.execute('SELECT id,state FROM operations').fetchone()
            self.assertEqual(state, 'applying')
            self.assertEqual(reconcile_operation(self.wiki, self.inbox, operation_id, store)['state'], 'applied')
            self.assertEqual(reconcile_operation(self.wiki, self.inbox, operation_id, store)['state'], 'applied')
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 1)
        self.assertFalse(temporary.is_relative_to(dest), 'Operation staging cannot contaminate canonical evidence')
        self.assertFalse(temporary.exists())
        self.assertEqual({p.name for p in dest.iterdir()}, {'payload.txt', 'manifest.json'})
        self.assertEqual(json.loads((dest / 'manifest.json').read_bytes())['used_by'], [self.target.name])
        self.assertEqual(self.target.stat().st_mtime_ns, stamp)
        self.assertTrue((self.candidate / 'applied.json').exists())
        print('RR-LOGIC-3 actual os._exit(91) before no-overwrite publication after fsync; exact operation reconciled twice')

    def test_unbound_actual_existing_evidence_citation_refused_before_approval(self):
        import json
        import shutil
        from wiki_candidates import review_snapshot, Refused, cmd_approve
        for kind in ('new', 'update'):
            with self.subTest(kind=kind):
                fixture = CandidateApplyTests('test_repeated_applied_operation_is_noop')
                fixture.setUp()
                try:
                    fixture.configure_recovery(kind)
                    shutil.move(fixture.candidate / 'evidence/fixture-code', fixture.wiki / 'raw/evidence/fixture-code')
                    shutil.rmtree(fixture.candidate / 'evidence')
                    fixture.metadata['evidence_ids'] = []
                    (fixture.candidate / 'candidate.json').write_text(json.dumps(fixture.metadata), encoding='utf-8')
                    before = {p.relative_to(fixture.root).as_posix(): p.read_bytes()
                              for p in fixture.root.rglob('*') if p.is_file()}
                    with self.assertRaisesRegex(Refused, 'citations.*evidence_ids'):
                        review_snapshot(fixture.wiki, fixture.inbox, 'run/draft')
                    with self.assertRaisesRegex(Refused, 'citations.*evidence_ids'):
                        cmd_approve(fixture.wiki, fixture.inbox, 'run/draft', True)
                    self.assertEqual(before, {p.relative_to(fixture.root).as_posix(): p.read_bytes()
                                              for p in fixture.root.rglob('*') if p.is_file()})
                    self.assertFalse((fixture.data / 'owner-decisions.sqlite').exists())
                    self.assertFalse((fixture.data / 'workflow.sqlite').exists())
                finally:
                    fixture.doCleanups()
        print('RR-LOGIC-4 new/update actual retained citation with empty metadata refused before approval')

    def test_cited_evidence_requires_bound_manifest_before_approval(self):
        import json
        import shutil
        from wiki_candidates import review_snapshot, Refused
        self.configure_recovery('new')
        shutil.rmtree(self.candidate / 'evidence')
        with self.assertRaisesRegex(Refused, 'evidence.*manifest'):
            review_snapshot(self.wiki, self.inbox, 'run/draft')
        dest = self.wiki / 'raw/evidence/fixture-code'
        dest.mkdir()
        (dest / 'payload.txt').write_bytes(b'Not enough without a bound manifest')
        with self.assertRaisesRegex(Refused, 'evidence.*manifest'):
            review_snapshot(self.wiki, self.inbox, 'run/draft')
        self.assertFalse((self.data / 'workflow.sqlite').exists())

    def test_none_evidence_annotation_is_not_a_citation(self):
        from wiki_candidates import review_snapshot
        self.source = self.source.replace(b'none (method)', b'none (owner-directed method)')
        (self.candidate / 'source.md').write_bytes(self.source)
        snapshot = review_snapshot(self.wiki, self.inbox, 'run/draft')
        self.assertEqual(snapshot['evidence'], [])
        self.assertEqual(snapshot['stored_evidence'], [])

    def test_cited_evidence_manifest_identity_must_support_attribution(self):
        import json
        from wiki_candidates import review_snapshot, Refused
        self.configure_recovery('new')
        path = self.candidate / 'evidence/fixture-code/manifest.json'
        original = json.loads(path.read_bytes())
        for changed in ({**original, 'schema': 0}, {**original, 'evidence_id': 'other-code'}):
            with self.subTest(manifest=changed):
                path.write_text(json.dumps(changed), encoding='utf-8')
                with self.assertRaisesRegex(Refused, 'evidence.*manifest'):
                    review_snapshot(self.wiki, self.inbox, 'run/draft')
        self.assertFalse((self.data / 'workflow.sqlite').exists())

    def test_none_prefixed_evidence_id_is_still_a_citation(self):
        from wiki_candidates import validate_source_citations
        validate_source_citations('Evidence: none-code\n', ['none-code'])

    def test_reviewed_retained_citations_are_bound_and_attributed(self):
        import json
        import shutil
        from candidate_apply import apply_candidate
        from workflow_store import WorkflowStore
        for kind in ('new', 'update'):
            for style in ('line', 'table'):
                with self.subTest(kind=kind, style=style):
                    fixture = CandidateApplyTests('test_repeated_applied_operation_is_noop')
                    fixture.setUp()
                    try:
                        fixture.configure_recovery(kind)
                        shutil.move(fixture.candidate / 'evidence/fixture-code', fixture.wiki / 'raw/evidence/fixture-code')
                        shutil.rmtree(fixture.candidate / 'evidence')
                        if style == 'table':
                            fixture.source = fixture.source.replace(b'Evidence: fixture-code', b'Evidence: none (method)')
                            fixture.source += b'\n## Evidence\n\n| ID | Support |\n| --- | --- |\n| `fixture-code` | Fixture |\n'
                            (fixture.candidate / 'source.md').write_bytes(fixture.source)
                        fixture.authorize()
                        self.assertEqual(fixture.snapshot['evidence'], [])
                        self.assertEqual({entry['path'] for entry in fixture.snapshot['stored_evidence']},
                                         {'fixture-code/manifest.json', 'fixture-code/payload.txt'})
                        with WorkflowStore(fixture.data / 'workflow.sqlite') as store:
                            result = apply_candidate(fixture.wiki, fixture.inbox, 'run/draft', fixture.snapshot, fixture.approval, store)
                        self.assertEqual(result['state'], 'applied')
                        self.assertEqual(fixture.target.read_bytes(), fixture.source)
                        self.assertEqual(json.loads((fixture.wiki / 'raw/evidence/fixture-code/manifest.json').read_bytes())['used_by'], [fixture.target.name])
                    finally:
                        fixture.doCleanups()

    def test_citation_metadata_mismatch_and_missing_ids_are_refused(self):
        import json
        from wiki_candidates import review_snapshot, Refused
        self.configure_recovery('new')
        for ids in (None, [], ['other-code'], ['fixture-code', 'unused-code'], ['fixture-code', 'fixture-code'], [{}]):
            with self.subTest(ids=ids):
                metadata = {**self.metadata, 'evidence_ids': ids}
                if ids is None:
                    metadata.pop('evidence_ids')
                (self.candidate / 'candidate.json').write_text(json.dumps(metadata), encoding='utf-8')
                with self.assertRaises(Refused):
                    review_snapshot(self.wiki, self.inbox, 'run/draft')
        self.metadata['evidence_ids'] = []
        (self.candidate / 'candidate.json').write_text(json.dumps(self.metadata), encoding='utf-8')
        for row in ('fixture-code', 'unknown-code', '../fixture-code'):
            with self.subTest(table_id=row):
                text = self.source.replace(b'Evidence: fixture-code', b'Evidence: none (method)')
                text += f'\n## Evidence\n\n| ID | Support |\n| --- | --- |\n| {row} | Fixture |\n'.encode()
                (self.candidate / 'source.md').write_bytes(text)
                with self.assertRaises(Refused):
                    review_snapshot(self.wiki, self.inbox, 'run/draft')
        self.assertFalse((self.data / 'workflow.sqlite').exists())

    def test_recovery_never_ignores_arbitrary_canonical_evidence_extras(self):
        from candidate_apply import apply_candidate, reconcile_operation, ApplyRefused
        from workflow_store import WorkflowStore
        from unittest.mock import patch
        import candidate_apply
        self.configure_recovery('new')
        self.authorize()
        def stop(point):
            if point == 'after-step:source':
                raise InterruptedError('Pause after source publication')
        with WorkflowStore(self.data / 'workflow.sqlite') as store:
            with patch.object(candidate_apply, '_checkpoint', stop), self.assertRaises(InterruptedError):
                apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot, self.approval, store)
            operation_id = store.db.execute('SELECT id FROM operations').fetchone()[0]
            for name in ('manifest.json.tmp', 'arbitrary.bin'):
                with self.subTest(extra=name):
                    extra = self.wiki / 'raw/evidence/fixture-code' / name
                    content = b'Independent canonical payload; never ignore or delete'
                    extra.write_bytes(content)
                    with self.assertRaisesRegex(ApplyRefused, 'evidence drift'):
                        reconcile_operation(self.wiki, self.inbox, operation_id, store)
                    self.assertEqual(extra.read_bytes(), content)
                    self.assertEqual(self.target.read_bytes(), self.source)
                    self.assertFalse((self.candidate / 'applied.json').exists())
                    self.assertEqual(store.get_operation(operation_id)['state'], 'recovery_required')
                    extra.unlink()  # Fixture owner deliberately removes the extra before next case.
            self.assertEqual(reconcile_operation(self.wiki, self.inbox, operation_id, store)['state'], 'applied')

    def test_prepared_legacy_unbound_citation_refuses_resume_without_expansion(self):
        import json
        import shutil
        import candidate_apply
        import wiki_candidates
        from candidate_apply import apply_candidate, reconcile_operation, ApplyRefused
        from workflow_store import WorkflowStore
        from unittest.mock import patch
        self.configure_recovery('new')
        shutil.move(self.candidate / 'evidence/fixture-code', self.wiki / 'raw/evidence/fixture-code')
        shutil.rmtree(self.candidate / 'evidence')
        self.metadata['evidence_ids'] = []
        (self.candidate / 'candidate.json').write_text(json.dumps(self.metadata), encoding='utf-8')
        def stop(point):
            if point == 'after-step:source':
                raise InterruptedError('Predecessor prepared and published the unbound citation')
        with WorkflowStore(self.data / 'workflow.sqlite') as store:
            # Recreate a real signed operation admitted by the predecessor validator.
            with patch.object(wiki_candidates, 'validate_source_citations', return_value=None):
                self.authorize()
                with patch.object(candidate_apply, '_checkpoint', stop), self.assertRaises(InterruptedError):
                    apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot, self.approval, store)
            operation_id = store.db.execute('SELECT id FROM operations').fetchone()[0]
            with self.assertRaisesRegex(ApplyRefused, 'citations.*evidence_ids'):
                reconcile_operation(self.wiki, self.inbox, operation_id, store)
            self.assertEqual(store.get_operation(operation_id)['state'], 'recovery_required')
            self.assertEqual(store.get_operation(operation_id)['snapshot'], self.snapshot)
            self.assertEqual(self.snapshot['evidence'], [])
            self.assertEqual(self.snapshot['stored_evidence'], [])
            self.assertEqual(self.target.read_bytes(), self.source)
            self.assertFalse((self.candidate / 'applied.json').exists())
            self.assertEqual(json.loads((self.wiki / 'raw/evidence/fixture-code/manifest.json').read_bytes())['used_by'], [])

    def test_evidence_removal_crash_matrix_reconciles(self):
        for kind in ('update', 'retire'):
            fixture = CandidateApplyTests('test_repeated_applied_operation_is_noop')
            fixture.setUp()
            try:
                fixture.configure_recovery(kind)
                fixture.remove_candidate_evidence(kind)
                fixture.assert_interruption_recovery(kind, remove_evidence=True)
            finally:
                fixture.doCleanups()

    def test_failure_at_every_step_reconciles(self):
        for kind in ('new', 'update', 'retire'):
            fixture = CandidateApplyTests('test_repeated_applied_operation_is_noop')
            fixture.setUp()
            try:
                fixture.configure_recovery(kind)
                fixture.assert_interruption_recovery(kind)
            finally:
                fixture.doCleanups()

    def assert_interruption_recovery(self, kind, remove_evidence=False):
        import json
        from candidate_apply import apply_candidate
        from workflow_store import WorkflowStore
        from unittest.mock import patch
        import candidate_apply
        self.authorize()
        trace = []
        with WorkflowStore(self.data / 'workflow.sqlite') as store, patch.object(candidate_apply, '_checkpoint', trace.append):
            apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot, self.approval, store)
        self.assertIn('before-record:operation', trace)
        self.assertIn('after-consume:authority', trace)
        self.assertIn('before-transition:applied', trace)
        for mutation in ('before-temp', 'after-temp', 'before-fsync', 'after-fsync', 'before-replace', 'after-replace'):
            self.assertIn(f'{mutation}:attribution-manifest-fixture-code', trace)
        prepared_name = 'source.md' if kind != 'retire' else 'base.md' if remove_evidence else 'manifest.json'
        self.assertIn(f'after-temp:{prepared_name}', trace)
        self.assertIn(f'before-replace:{prepared_name}', trace)
        worker = Path(__file__).with_name('candidate_apply_worker.py')
        for index, point in enumerate(trace):
            with self.subTest(point=point):
                fixture = CandidateApplyTests('test_repeated_applied_operation_is_noop')
                fixture.setUp()
                try:
                    fixture.configure_recovery(kind)
                    if remove_evidence:
                        fixture.remove_candidate_evidence(kind)
                    fixture.authorize()
                    request = fixture.root / 'worker-request.json'
                    request.write_text(json.dumps({'wiki': str(fixture.wiki), 'inbox': str(fixture.inbox),
                        'snapshot': fixture.snapshot, 'approval': fixture.approval}), encoding='utf-8')
                    killed = subprocess.run([sys.executable, str(worker), 'apply', str(request), str(index)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(killed.returncode, 91, killed.stdout + killed.stderr)
                    stamp = fixture.target.stat().st_mtime_ns if fixture.target.exists() and fixture.target.read_bytes() == fixture.source else None
                    recovered = subprocess.run([sys.executable, str(worker), 'apply', str(request)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
                    if kind == 'retire':
                        self.assertFalse(fixture.target.exists())
                    else:
                        self.assertEqual(fixture.target.read_bytes(), fixture.source)
                    manifest = json.loads((fixture.wiki / 'raw/evidence/fixture-code/manifest.json').read_bytes())
                    self.assertEqual(manifest['used_by'], [] if kind == 'retire' or remove_evidence else [fixture.target.name])
                    if stamp is not None:
                        self.assertEqual(fixture.target.stat().st_mtime_ns, stamp, 'Recovery rewrote already published bytes')
                    with WorkflowStore(fixture.data / 'workflow.sqlite') as store:
                        rows = store.db.execute('SELECT id,state FROM operations').fetchall()
                        self.assertEqual(len(rows), 1)
                        self.assertEqual(rows[0][1], 'applied')
                finally:
                    fixture.doCleanups()
        print(f'INTERRUPTION_MATRIX kind={kind} remove_evidence={remove_evidence} recovered={len(trace)} checkpoints={len(trace)}')

    def test_update_and_retire_preserve_expected_version(self):
        import hashlib
        import json
        from candidate_apply import apply_candidate
        from workflow_store import WorkflowStore
        for kind in ('update', 'retire'):
            with self.subTest(kind=kind):
                fixture = CandidateApplyTests('test_repeated_applied_operation_is_noop')
                fixture.setUp()
                try:
                    original = b'# Previously reviewed source\n'
                    fixture.target.write_bytes(original)
                    fixture.metadata.update(kind=kind, base_sha256=hashlib.sha256(original).hexdigest())
                    (fixture.candidate / 'candidate.json').write_text(json.dumps(fixture.metadata), encoding='utf-8')
                    if kind == 'retire':
                        (fixture.candidate / 'source.md').unlink()
                    fixture.authorize()
                    with WorkflowStore(fixture.data / 'workflow.sqlite') as store:
                        result = apply_candidate(fixture.wiki, fixture.inbox, 'run/draft', fixture.snapshot, fixture.approval, store)
                        self.assertEqual(result['state'], 'applied')
                        if kind == 'retire':
                            self.assertFalse(fixture.target.exists())
                        else:
                            self.assertEqual(fixture.target.read_bytes(), fixture.source)
                        self.assertEqual((fixture.data / 'operations' / result['operation_id'] / 'base.md').read_bytes(), original)
                        self.assertEqual(apply_candidate(fixture.wiki, fixture.inbox, 'run/draft', fixture.snapshot, fixture.approval, store)['operation_id'], result['operation_id'])
                finally:
                    fixture.doCleanups()

    def test_external_drift_preserved(self):
        from candidate_apply import apply_candidate, ApplyRefused
        from workflow_store import WorkflowStore
        import candidate_apply
        from unittest.mock import patch
        self.authorize()
        with WorkflowStore(self.data / 'workflow.sqlite') as store:
            def stop_after_source(point):
                if point == 'after-step:source':
                    raise InterruptedError('Simulated interruption after journaled source')
            with patch.object(candidate_apply, '_checkpoint', stop_after_source):
                with self.assertRaises(InterruptedError):
                    apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot, self.approval, store)
            self.target.unlink()
            with self.assertRaises(ApplyRefused):
                apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot, self.approval, store)
            self.assertFalse(self.target.exists(), 'Deleted source was recreated over an external decision')
            operation = store.db.execute('SELECT id,state FROM operations').fetchone()
            self.assertEqual(operation[1], 'recovery_required')
            self.target.write_bytes(b'Independent newer content')
            with self.assertRaises(ApplyRefused):
                apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot, self.approval, store)
            self.assertEqual(self.target.read_bytes(), b'Independent newer content')

    def test_evidence_is_prepared_before_source_and_attribution_is_reconciled(self):
        import hashlib
        import json
        from candidate_apply import apply_candidate
        from workflow_store import WorkflowStore
        from unittest.mock import patch
        import candidate_apply
        evidence = self.candidate / 'evidence/fixture-code'
        evidence.mkdir(parents=True)
        payload = b'Exact stored evidence'
        (evidence / 'payload.txt').write_bytes(payload)
        (evidence / 'manifest.json').write_text(json.dumps({'schema': 1, 'evidence_id': 'fixture-code', 'used_by': [],
            'files': {'payload.txt': {'sha256': hashlib.sha256(payload).hexdigest()}}}), encoding='utf-8')
        self.metadata['evidence_ids'] = ['fixture-code']
        (self.candidate / 'candidate.json').write_text(json.dumps(self.metadata), encoding='utf-8')
        self.source = self.source.replace(b'none (method)', b'fixture-code')
        (self.candidate / 'source.md').write_bytes(self.source)
        self.authorize()
        def observe(point):
            if point == f'before-write:{self.target.name}':
                self.assertEqual((self.wiki / 'raw/evidence/fixture-code/payload.txt').read_bytes(), payload)
        with WorkflowStore(self.data / 'workflow.sqlite') as store, patch.object(candidate_apply, '_checkpoint', observe):
            result = apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot, self.approval, store)
            manifest = self.wiki / 'raw/evidence/fixture-code/manifest.json'
            self.assertEqual(json.loads(manifest.read_bytes())['used_by'], [self.target.name])
            stamp = manifest.stat().st_mtime_ns
            self.assertEqual(apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot, self.approval, store)['operation_id'], result['operation_id'])
            self.assertEqual(manifest.stat().st_mtime_ns, stamp)

    def test_recovery_rejects_changed_candidate_inputs(self):
        from candidate_apply import apply_candidate, ApplyRefused
        from workflow_store import WorkflowStore
        import candidate_apply
        from unittest.mock import patch
        self.authorize()
        with WorkflowStore(self.data / 'workflow.sqlite') as store:
            def stop_before_consume(point):
                if point == 'before-consume:authority':
                    raise InterruptedError('Simulated interruption before consuming authorization')
            with patch.object(candidate_apply, '_checkpoint', stop_before_consume):
                with self.assertRaises(InterruptedError):
                    apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot, self.approval, store)
            (self.candidate / 'source.md').write_bytes(b'# Independent changed draft\n')
            with self.assertRaises(ApplyRefused):
                apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot, self.approval, store)
            self.assertFalse(self.target.exists())

    def test_missing_or_forged_authority_never_publishes(self):
        from candidate_apply import apply_candidate
        from workflow_store import WorkflowStore
        from owner_decisions import DecisionRefused
        self.authorize()
        forged = {**self.approval, 'signature': '0' * 64}
        with WorkflowStore(self.data / 'workflow.sqlite') as store:
            with self.assertRaises(DecisionRefused):
                apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot, forged, store)
            self.assertFalse(self.target.exists())
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 0)

    def test_owner_creation_in_capture_gap_is_never_replaced(self):
        import candidate_apply
        from candidate_apply import apply_candidate, ApplyRefused
        from workflow_store import WorkflowStore
        from unittest.mock import patch
        self.configure_recovery('update')
        original = self.target.read_bytes()
        self.authorize()
        newer = b'Owner independently recreated the target during capture gap\n'
        worker = Path(__file__).with_name('candidate_apply_worker.py')
        real_rename = candidate_apply._rename_no_replace
        def race(source, destination):
            if destination == self.target:
                written = subprocess.run([sys.executable, str(worker), 'owner-write', str(self.target), newer.hex()],
                                         capture_output=True, text=True, timeout=10)
                self.assertEqual(written.returncode, 0, written.stdout + written.stderr)
            return real_rename(source, destination)
        with WorkflowStore(self.data / 'workflow.sqlite') as store:
            with patch.object(candidate_apply, '_rename_no_replace', race), self.assertRaises(ApplyRefused):
                apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot, self.approval, store)
            operation_id, state = store.db.execute('SELECT id,state FROM operations').fetchone()
            self.assertEqual(state, 'recovery_required')
            self.assertEqual(self.target.read_bytes(), newer)
            self.assertEqual(candidate_apply._source_archive(self.wiki, operation_id).read_bytes(), original)
            self.assertFalse((self.candidate / 'applied.json').exists())

    def test_applied_capture_drift_is_reported_without_repair(self):
        import candidate_apply
        from candidate_apply import apply_candidate
        from workflow_store import WorkflowStore
        self.configure_recovery('retire')
        self.authorize()
        with WorkflowStore(self.data / 'workflow.sqlite') as store:
            result = apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot, self.approval, store)
            archive = candidate_apply._source_archive(self.wiki, result['operation_id'])
            newer = b'Late owner edit through a captured handle\n'
            archive.write_bytes(newer)
            again = apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot, self.approval, store)
            self.assertTrue(again['later_drift'])
            self.assertEqual(archive.read_bytes(), newer)
            self.assertFalse(self.target.exists())

    def test_open_owner_handle_edit_survives_capture(self):
        import candidate_apply
        from candidate_apply import apply_candidate, ApplyRefused
        from workflow_store import WorkflowStore
        from unittest.mock import patch
        worker = Path(__file__).with_name('candidate_apply_worker.py')
        for kind in ('update', 'retire'):
            with self.subTest(kind=kind):
                fixture = CandidateApplyTests('test_repeated_applied_operation_is_noop')
                fixture.setUp()
                proc = None
                try:
                    fixture.configure_recovery(kind)
                    fixture.authorize()
                    newer = b'Owner held handle edits the retained object after capture\n'
                    proc = subprocess.Popen([sys.executable, str(worker), 'owner-held-write', str(fixture.target), newer.hex()],
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    self.assertEqual(proc.stdout.readline().strip(), 'OWNER_OPEN')
                    def owner_write(point):
                        if point == 'after-capture:source':
                            output, error = proc.communicate('write\n', timeout=10)
                            self.assertEqual(proc.returncode, 0, output + error)
                            self.assertEqual(output.strip(), 'OWNER_WROTE')
                    with WorkflowStore(fixture.data / 'workflow.sqlite') as store:
                        with patch.object(candidate_apply, '_checkpoint', owner_write), self.assertRaises(ApplyRefused):
                            apply_candidate(fixture.wiki, fixture.inbox, 'run/draft', fixture.snapshot, fixture.approval, store)
                        operation_id, state = store.db.execute('SELECT id,state FROM operations').fetchone()
                        self.assertEqual(state, 'recovery_required')
                        self.assertEqual(candidate_apply._source_archive(fixture.wiki, operation_id).read_bytes(), newer)
                        self.assertEqual(fixture.target.read_bytes(), newer)
                        self.assertFalse((fixture.candidate / 'applied.json').exists())
                finally:
                    if proc is not None and proc.poll() is None:
                        proc.kill()
                        proc.communicate(timeout=10)
                    fixture.doCleanups()

    def test_independent_owner_writer_at_os_rename_boundary_is_preserved(self):
        import candidate_apply
        from candidate_apply import apply_candidate, ApplyRefused
        from workflow_store import WorkflowStore
        from unittest.mock import patch
        worker = Path(__file__).with_name('candidate_apply_worker.py')
        real_rename = candidate_apply._rename_no_replace
        for kind in ('new', 'update', 'retire'):
            for mode in ('owner-write', 'owner-replace'):
                with self.subTest(kind=kind, mode=mode):
                    fixture = CandidateApplyTests('test_repeated_applied_operation_is_noop')
                    fixture.setUp()
                    try:
                        fixture.configure_recovery(kind)
                        fixture.authorize()
                        newer = b'Independent process changed the entry at the OS boundary\n'
                        raced = []
                        def race(source, destination):
                            at_boundary = destination == fixture.target if kind == 'new' else source == fixture.target
                            if at_boundary and not raced:
                                written = subprocess.run([sys.executable, str(worker), mode, str(fixture.target), newer.hex()],
                                                         capture_output=True, text=True, timeout=10)
                                self.assertEqual(written.returncode, 0, written.stdout + written.stderr)
                                self.assertEqual(written.stdout.strip(), 'OWNER_WROTE')
                                raced.append(True)
                            return real_rename(source, destination)
                        with WorkflowStore(fixture.data / 'workflow.sqlite') as store:
                            with patch.object(candidate_apply, '_rename_no_replace', race), self.assertRaises(ApplyRefused):
                                apply_candidate(fixture.wiki, fixture.inbox, 'run/draft', fixture.snapshot, fixture.approval, store)
                            self.assertEqual(raced, [True])
                            self.assertEqual(fixture.target.read_bytes(), newer)
                            operation_id, state = store.db.execute('SELECT id,state FROM operations').fetchone()
                            self.assertEqual(state, 'recovery_required')
                            if kind != 'new':
                                self.assertEqual(candidate_apply._source_archive(fixture.wiki, operation_id).read_bytes(), newer)
                            self.assertFalse((fixture.candidate / 'applied.json').exists())
                    finally:
                        fixture.doCleanups()

    def test_source_mutation_boundary_preserves_concurrent_owner_bytes(self):
        import candidate_apply
        from candidate_apply import apply_candidate, ApplyRefused
        from workflow_store import WorkflowStore
        from unittest.mock import patch
        for kind in ('new', 'update', 'retire'):
            with self.subTest(kind=kind):
                fixture = CandidateApplyTests('test_repeated_applied_operation_is_noop')
                fixture.setUp()
                try:
                    fixture.configure_recovery(kind)
                    fixture.authorize()
                    newer = b'Independent owner bytes at the mutation boundary\n'
                    boundary = 'before-write:retire' if kind == 'retire' else f'before-replace:{fixture.target.name}'
                    raced = []
                    def owner_write(point):
                        if point == boundary:
                            fixture.target.write_bytes(newer)
                            raced.append(point)
                    with WorkflowStore(fixture.data / 'workflow.sqlite') as store:
                        with patch.object(candidate_apply, '_checkpoint', owner_write), self.assertRaises(ApplyRefused):
                            apply_candidate(fixture.wiki, fixture.inbox, 'run/draft', fixture.snapshot, fixture.approval, store)
                        self.assertEqual(raced, [boundary])
                        self.assertEqual(fixture.target.read_bytes(), newer)
                        self.assertEqual(store.db.execute('SELECT state FROM operations').fetchone()[0], 'recovery_required')
                        self.assertFalse((fixture.candidate / 'applied.json').exists())
                        with self.assertRaises(ApplyRefused):
                            apply_candidate(fixture.wiki, fixture.inbox, 'run/draft', fixture.snapshot, fixture.approval, store)
                        self.assertEqual(fixture.target.read_bytes(), newer)
                finally:
                    fixture.doCleanups()

    def test_retirement_without_new_evidence_removes_obsolete_attribution(self):
        import json
        import shutil
        from candidate_apply import apply_candidate
        from workflow_store import WorkflowStore
        self.configure_recovery('retire')
        self.metadata['evidence_ids'] = []
        shutil.rmtree(self.candidate / 'evidence')
        (self.candidate / 'candidate.json').write_text(json.dumps(self.metadata), encoding='utf-8')
        self.authorize()
        with WorkflowStore(self.data / 'workflow.sqlite') as store:
            self.assertEqual(apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot,
                                             self.approval, store)['state'], 'applied')
        self.assertFalse(self.target.exists())
        self.assertEqual(json.loads((self.wiki / 'raw/evidence/fixture-code/manifest.json').read_bytes())['used_by'], [])

    def test_cli_rejection_binds_valid_digest_and_retries_moved_candidate(self):
        import contextlib
        import io
        import wiki_candidates
        from candidate_apply import reject_candidate, ApplyRefused
        from workflow_store import WorkflowStore
        from unittest.mock import patch
        digest = wiki_candidates.review_snapshot(self.wiki, self.inbox, 'run/draft')['review_digest']
        arguments = ['reject', 'run/draft', '--reason', 'Unsupported source', '--expected-review-digest', digest]
        with patch.object(wiki_candidates, 'paths', return_value=(self.wiki, self.inbox)), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(wiki_candidates.main(arguments), 0)
        with WorkflowStore(self.data / 'workflow.sqlite', read_only=True) as store:
            operation_id = store.db.execute('SELECT id FROM operations').fetchone()[0]
            self.assertEqual(store.get_operation(operation_id)['review_digest'], digest)
        destination = self.inbox / 'rejected/run-draft'
        before = {p.relative_to(destination).as_posix(): p.read_bytes() for p in destination.rglob('*') if p.is_file()}
        result = reject_candidate(self.inbox, 'run/draft', 'Unsupported source', wiki=self.wiki, expected_review_digest=digest)
        self.assertEqual(result['operation_id'], operation_id)
        with self.assertRaises(ApplyRefused):
            reject_candidate(self.inbox, 'run/draft', 'Unsupported source', wiki=self.wiki, expected_review_digest='0' * 64)
        self.assertEqual(before, {p.relative_to(destination).as_posix(): p.read_bytes() for p in destination.rglob('*') if p.is_file()})

    def test_rejection_digest_is_rechecked_inside_engine_lock(self):
        import contextlib
        import candidate_apply
        from candidate_apply import reject_candidate, ApplyRefused
        from wiki_candidates import review_snapshot
        from unittest.mock import patch
        digest = review_snapshot(self.wiki, self.inbox, 'run/draft')['review_digest']
        real_lock = candidate_apply.operation_lock
        @contextlib.contextmanager
        def concurrent_edit(data):
            with real_lock(data):
                (self.candidate / 'source.md').write_bytes(b'# Changed while lock was being acquired\n')
                yield
        with patch.object(candidate_apply, 'operation_lock', concurrent_edit):
            with self.assertRaises(ApplyRefused):
                reject_candidate(self.inbox, 'run/draft', 'Unsupported source', wiki=self.wiki,
                                 expected_review_digest=digest)
        self.assertTrue(self.candidate.exists())
        self.assertFalse((self.candidate / 'rejected.json').exists())
        self.assertFalse((self.inbox / 'rejected/run-draft').exists())
        self.assertFalse((self.data / 'workflow.sqlite').exists())

    def test_rejection_cannot_move_unfinished_application_inputs(self):
        from candidate_apply import apply_candidate, reject_candidate, reconcile_operation, ApplyRefused
        from workflow_store import WorkflowStore
        import candidate_apply
        from unittest.mock import patch
        self.authorize()
        def interrupt(point):
            if point == 'after-step:source':
                raise InterruptedError('Interrupted source publication')
        with WorkflowStore(self.data / 'workflow.sqlite') as store:
            with patch.object(candidate_apply, '_checkpoint', interrupt), self.assertRaises(InterruptedError):
                apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot, self.approval, store)
            operation_id = store.db.execute("SELECT id FROM operations WHERE state='applying'").fetchone()[0]
        before = {p.relative_to(self.candidate).as_posix(): p.read_bytes()
                  for p in self.candidate.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(ApplyRefused, 'application'):
            reject_candidate(self.inbox, 'run/draft', 'Owner rejects still-pending candidate')
        self.assertEqual(before, {p.relative_to(self.candidate).as_posix(): p.read_bytes()
                                 for p in self.candidate.rglob('*') if p.is_file()})
        self.assertFalse((self.inbox / 'rejected/run-draft').exists())
        with WorkflowStore(self.data / 'workflow.sqlite') as store:
            self.assertEqual(reconcile_operation(self.wiki, self.inbox, operation_id, store)['state'], 'applied')
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 1)

    def test_reject_preserves_recoverable_reason(self):
        import json
        from candidate_apply import reject_candidate
        import candidate_apply
        from unittest.mock import patch
        reason = 'Owner rejected unsupported claims'
        def stop_before_move(point):
            if point == 'before-write:reject-move':
                raise InterruptedError('Simulated interruption before candidate move')
        with patch.object(candidate_apply, '_checkpoint', stop_before_move):
            with self.assertRaises(InterruptedError):
                reject_candidate(self.inbox, 'run/draft', reason)
        self.assertEqual(json.loads((self.candidate / 'rejected.json').read_bytes())['reason'], reason)
        result = reject_candidate(self.inbox, 'run/draft', reason)
        self.assertEqual(result['state'], 'rejected')
        self.assertFalse(self.candidate.exists())
        dest = self.inbox / 'rejected/run-draft'
        before = {p.relative_to(dest).as_posix(): p.read_bytes() for p in dest.rglob('*') if p.is_file()}
        self.assertEqual(reject_candidate(self.inbox, 'run/draft', reason)['operation_id'], result['operation_id'])
        self.assertEqual(before, {p.relative_to(dest).as_posix(): p.read_bytes() for p in dest.rglob('*') if p.is_file()})

    def test_legacy_marker_conflict_is_ambiguous(self):
        import json
        from candidate_apply import reconcile_legacy
        from workflow_store import WorkflowStore
        marker = self.candidate / 'applied.json'
        marker.write_text(json.dumps({'kind': 'new', 'target': self.target.name}), encoding='utf-8')
        self.target.write_bytes(b'Independent source, not the proposed bytes')
        with WorkflowStore(self.data / 'workflow.sqlite') as store:
            before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
            rows = reconcile_legacy(self.wiki, self.inbox, store)
            self.assertEqual(rows[0]['status'], 'ambiguous')
            self.assertEqual(before, {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
            self.target.write_bytes(self.source)
            rows = reconcile_legacy(self.wiki, self.inbox, store)
            self.assertEqual(rows[0]['status'], 'verified')
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 0)
            rows = reconcile_legacy(self.wiki, self.inbox, store, import_verified=True)
            self.assertEqual(rows[0]['status'], 'imported')
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 1)
            self.assertEqual(self.target.read_bytes(), self.source)

    def test_applied_evidence_drift_is_reported_without_repair(self):
        from candidate_apply import apply_candidate
        from workflow_store import WorkflowStore
        self.configure_recovery('new')
        self.authorize()
        with WorkflowStore(self.data / 'workflow.sqlite') as store:
            apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot, self.approval, store)
            payload = self.wiki / 'raw/evidence/fixture-code/payload.txt'
            payload.write_bytes(b'Independent evidence change')
            result = apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot, self.approval, store)
            self.assertTrue(result['later_drift'])
            self.assertEqual(payload.read_bytes(), b'Independent evidence change')

    def test_journal_must_belong_to_the_selected_data_root(self):
        from candidate_apply import apply_candidate, ApplyRefused
        from workflow_store import WorkflowStore
        self.authorize()
        with WorkflowStore(self.root / 'other-data/workflow.sqlite') as store:
            with self.assertRaises(ApplyRefused):
                apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot, self.approval, store)
        self.assertFalse(self.target.exists())

    def test_public_rejection_uses_durable_reason_path(self):
        import wiki_candidates
        import candidate_apply
        from unittest.mock import patch
        def stop_before_move(point):
            if point == 'before-write:reject-move':
                raise InterruptedError('Simulated interruption at public rejection')
        with patch.object(candidate_apply, '_checkpoint', stop_before_move):
            with self.assertRaises(InterruptedError):
                wiki_candidates.cmd_reject(self.inbox, 'run/draft', 'Unsupported source')
        self.assertTrue((self.candidate / 'rejected.json').exists())
        self.assertTrue(self.candidate.exists())
        self.assertEqual(wiki_candidates.cmd_reject(self.inbox, 'run/draft', 'Unsupported source'), 0)

    def test_public_recovery_preview_is_read_only(self):
        import contextlib
        import io
        import json
        import wiki_candidates
        from candidate_apply import apply_candidate
        from workflow_store import WorkflowStore
        self.authorize()
        with WorkflowStore(self.data / 'workflow.sqlite') as store:
            result = apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot, self.approval, store)
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(wiki_candidates.cmd_recover(self.wiki, self.inbox, result['operation_id'], True), 0)
        response = json.loads(output.getvalue())
        self.assertEqual(response['state'], 'applied')
        self.assertNotIn('approval', response)
        self.assertEqual(before, {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        with self.assertRaises(wiki_candidates.Refused):
            wiki_candidates.cmd_recover(self.wiki, self.inbox, result['operation_id'], False)

    def test_cli_reconciliation_does_not_initialize_missing_journal(self):
        import contextlib
        import io
        import json
        import wiki_candidates
        from unittest.mock import patch
        (self.candidate / 'applied.json').write_text(json.dumps({'kind': 'new', 'target': self.target.name}), encoding='utf-8')
        self.target.write_bytes(self.source)
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch.object(wiki_candidates, 'paths', return_value=(self.wiki, self.inbox)), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(wiki_candidates.main(['reconcile', '--dry-run']), 0)
        self.assertEqual(json.loads(output.getvalue())[0]['status'], 'verified')
        self.assertFalse((self.data / 'workflow.sqlite').exists())
        self.assertEqual(before, {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_recovery_requires_prepared_authorized_operation(self):
        from candidate_apply import reconcile_operation, ApplyRefused
        from workflow_store import WorkflowStore
        with WorkflowStore(self.data / 'workflow.sqlite') as store:
            store.record_operation({'operation_id': 'legacy-record', 'type': 'legacy-import'})
            for operation_id in ('missing', 'legacy-record', '../escape'):
                with self.subTest(operation_id=operation_id), self.assertRaises(ApplyRefused):
                    reconcile_operation(self.wiki, self.inbox, operation_id, store)
        self.assertFalse(self.target.exists())

    def test_legacy_invalid_candidate_is_reported_not_silently_skipped(self):
        import json
        from candidate_apply import reconcile_legacy
        self.metadata['kind'] = 'unsupported'
        (self.candidate / 'candidate.json').write_text(json.dumps(self.metadata), encoding='utf-8')
        (self.candidate / 'applied.json').write_bytes(b'{}')
        rows = reconcile_legacy(self.wiki, self.inbox, None)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'ambiguous')
        self.assertIn('unknown kind', rows[0]['reason'])

    def test_two_processes_share_one_application(self):
        import json
        from workflow_store import WorkflowStore
        self.authorize()
        request = self.root / 'worker-request.json'
        request.write_text(json.dumps({'wiki': str(self.wiki), 'inbox': str(self.inbox), 'snapshot': self.snapshot,
                                      'approval': self.approval}), encoding='utf-8')
        worker = Path(__file__).with_name('candidate_apply_worker.py')
        processes = [subprocess.Popen([sys.executable, str(worker), 'apply', str(request)], stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True) for _ in range(2)]
        results = []
        try:
            for proc in processes:
                output, error = proc.communicate(timeout=20)
                self.assertEqual(proc.returncode, 0, output + error)
                results.append(json.loads(output))
        finally:
            for proc in processes:
                if proc.poll() is None:
                    proc.kill()
                    proc.communicate(timeout=10)
        self.assertEqual(results[0]['operation_id'], results[1]['operation_id'])
        self.assertEqual(self.target.read_bytes(), self.source)
        with WorkflowStore(self.data / 'workflow.sqlite', read_only=True) as store:
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 1)
            self.assertEqual(store.get_operation(results[0]['operation_id'])['state'], 'applied')

    def test_repeated_applied_operation_is_noop(self):
        from candidate_apply import apply_candidate
        from workflow_store import WorkflowStore
        self.authorize()
        with WorkflowStore(self.data / 'workflow.sqlite') as store:
            result = apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot, self.approval, store)
            self.assertEqual(result['state'], 'applied')
            self.assertEqual(self.target.read_bytes(), self.source)
            marker = (self.candidate / 'applied.json').read_bytes()
            stamp = self.target.stat().st_mtime_ns
            again = apply_candidate(self.wiki, self.inbox, 'run/draft', self.snapshot, self.approval, store)
            self.assertEqual(again['operation_id'], result['operation_id'])
            self.assertEqual(self.target.stat().st_mtime_ns, stamp)
            self.assertEqual((self.candidate / 'applied.json').read_bytes(), marker)


class CorrectionTests(unittest.TestCase):
    """A harvest that resubmits a corrected 'new' draft for the same file."""

    def setUp(self):
        import json
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.wiki, self.data = root / 'wiki', root / 'data'
        self.inbox = self.data / 'inbox'
        (self.wiki / '.llm-wiki').mkdir(parents=True)
        (self.wiki / '.llm-wiki/project.json').write_bytes(b'{"id":"correction-fixture"}')
        (self.wiki / 'raw/sources').mkdir(parents=True)
        (self.wiki / 'raw/evidence').mkdir()
        self.target = self.wiki / 'raw/sources/2026-10-16-fixture.md'
        self.first = self.draft('first', b'# Fixture\n\n## Decisions\n\n**1. Kept pinned.**\nEvidence: none (owner).\n')
        self.second = self.draft('first-v2', b'# Fixture\n\n## Decisions\n\n**1. Not decided yet.**\nEvidence: none (owner).\n')

    def draft(self, name, body):
        import json
        c = self.inbox / 'run' / 'candidates' / name
        c.mkdir(parents=True)
        (c / 'candidate.json').write_text(json.dumps({'kind': 'new', 'target': self.target.name, 'summary': name,
                                                      'why': 'Test', 'evidence_ids': []}), encoding='utf-8')
        (c / 'source.md').write_bytes(body)
        stamp = 1_700_000_000_000_000_000 + len(list(self.inbox.glob('run/candidates/*'))) * 1_000_000_000
        os.utime(c / 'candidate.json', ns=(stamp, stamp))
        return c

    def apply(self, name):
        from candidate_apply import apply_candidate
        from owner_decisions import OwnerDecisions
        from wiki_candidates import review_snapshot
        from workflow_store import WorkflowStore
        snapshot = review_snapshot(self.wiki, self.inbox, f'run/{name}')
        with OwnerDecisions(self.data, initialize=True) as authority:
            request = authority.prepare(snapshot, 'fixture-owner')
            approval = authority.confirm(request['request_id'], snapshot, 'fixture-owner')
        with WorkflowStore(self.data / 'workflow.sqlite') as store:
            return snapshot, apply_candidate(self.wiki, self.inbox, f'run/{name}', snapshot, approval, store)

    def listed(self):
        import contextlib
        import io
        import json
        import wiki_candidates
        out = io.StringIO()
        with unittest.mock.patch.object(wiki_candidates.wikiconfig, 'project_root', return_value=self.wiki), \
                unittest.mock.patch.object(wiki_candidates.wikiconfig, 'load', return_value={}), \
                contextlib.redirect_stdout(out):
            wiki_candidates.cmd_list(self.inbox, True)
        return {row['ref']: row for row in json.loads(out.getvalue())}

    def test_older_pending_draft_is_marked_superseded(self):
        rows = self.listed()
        self.assertEqual(rows['run/first'].get('superseded_by'), 'run/first-v2')
        self.assertNotIn('superseded_by', rows['run/first-v2'])

    def test_newer_draft_corrects_the_approved_one(self):
        self.apply('first')
        rows = self.listed()
        self.assertEqual(rows['run/first-v2'].get('corrects'), 'run/first')
        snapshot, result = self.apply('first-v2')
        self.assertEqual(result['state'], 'applied')
        self.assertEqual(snapshot['corrects'], 'run/first')
        self.assertEqual(self.target.read_bytes(), (self.second / 'source.md').read_bytes())

    def test_older_draft_cannot_replace_the_newer_approved_one(self):
        from wiki_candidates import Refused, review_snapshot
        self.apply('first-v2')
        with self.assertRaisesRegex(Refused, 'newer draft of this source .run/first-v2. is already approved'):
            review_snapshot(self.wiki, self.inbox, 'run/first')
        self.assertIn('older', self.listed()['run/first']['blocked'])

    def test_file_edited_after_approval_is_not_overwritten(self):
        from wiki_candidates import Refused, review_snapshot
        self.apply('first')
        self.target.write_bytes(self.target.read_bytes() + b'Owner edit.\n')
        with self.assertRaisesRegex(Refused, 'not the unchanged file an earlier approved draft wrote'):
            review_snapshot(self.wiki, self.inbox, 'run/first-v2')

    def test_identical_resubmission_is_a_duplicate(self):
        from wiki_candidates import Refused, review_snapshot
        self.apply('first')
        (self.second / 'source.md').write_bytes((self.first / 'source.md').read_bytes())
        with self.assertRaisesRegex(Refused, 'identical'):
            review_snapshot(self.wiki, self.inbox, 'run/first-v2')

    def test_plain_new_snapshot_has_no_correction_field(self):
        from wiki_candidates import review_snapshot
        self.assertNotIn('corrects', review_snapshot(self.wiki, self.inbox, 'run/first'))


if __name__ == '__main__':
    unittest.main()
