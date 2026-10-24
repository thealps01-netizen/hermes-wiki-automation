"""Owner evidence edits at the actual attribution replacement seam remain intact."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evidence_store


class AttributionRaceTests(unittest.TestCase):
    def test_owner_manifest_edit_before_publication_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            root = Path(temp)
            evidence, sources = root / 'raw/evidence', root / 'raw/sources'
            folder = evidence / 'fixture-code'
            folder.mkdir(parents=True)
            sources.mkdir()
            (sources / 'fixture.md').write_bytes(b'# Fixture\nEvidence: fixture-code.\n')
            target = folder / 'manifest.json'
            initial = {'schema': 1, 'evidence_id': 'fixture-code', 'used_by': []}
            target.write_bytes(json.dumps(initial).encode())
            newer = json.dumps({**initial, 'owner_note': 'Edited during attribution'}).encode()
            written = []

            def owner(point):
                if point == 'before-replace:attribution-manifest-fixture-code':
                    reply = subprocess.run([sys.executable, '-B', '-c',
                        'import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(bytes.fromhex(sys.argv[2]))',
                        str(target), newer.hex()], capture_output=True, text=True, timeout=15)
                    self.assertEqual(reply.returncode, 0, reply.stderr)
                    written.append(True)

            with self.assertRaises(RuntimeError):
                evidence_store.sync_used_by(evidence, sources, only={'fixture-code'},
                    staging_root=root / '.llm-wiki/attribution-fixture', checkpoint=owner)
            self.assertEqual(written, [True])
            self.assertTrue(target.exists() and target.read_bytes() == newer
                or any(path.read_bytes() == newer for path in root.rglob('captured.bin')))


    def fixture(self, kind='new', removed=False):
        import test_candidate_apply as fixtures
        value = fixtures.CandidateApplyTests('test_repeated_applied_operation_is_noop')
        value.setUp()
        self.addCleanup(value.doCleanups)
        value.configure_recovery(kind)
        if removed:
            value.remove_candidate_evidence(kind)
        value.authorize()
        return value

    def kill_manifest(self, fixture, phase='after-capture'):
        request = fixture.root / 'worker-request.json'
        request.write_text(json.dumps({'wiki': str(fixture.wiki), 'inbox': str(fixture.inbox),
            'snapshot': fixture.snapshot, 'approval': fixture.approval}), encoding='utf-8')
        worker = Path(__file__).with_name('candidate_apply_worker.py')
        killed = subprocess.run([sys.executable, str(worker), 'attribution-death', str(request), phase],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(killed.returncode, 91, killed.stdout + killed.stderr)
        return Path(killed.stdout.strip())

    def test_unowned_missing_manifest_and_payload_are_refused_without_recreation(self):
        from candidate_apply import apply_candidate, reconcile_operation, ApplyRefused
        from workflow_store import WorkflowStore
        import candidate_apply
        from unittest.mock import patch
        for missing in ('manifest.json', 'payload.txt'):
            with self.subTest(missing=missing):
                fixture = self.fixture()
                def pause(point):
                    if point == 'after-step:source':
                        raise InterruptedError('Pause before attribution has captured any manifest')
                with WorkflowStore(fixture.data / 'workflow.sqlite') as store:
                    with patch.object(candidate_apply, '_checkpoint', pause), self.assertRaises(InterruptedError):
                        apply_candidate(fixture.wiki, fixture.inbox, 'run/draft', fixture.snapshot, fixture.approval, store)
                    operation_id = store.db.execute('SELECT id FROM operations').fetchone()[0]
                    target = fixture.wiki / 'raw/evidence/fixture-code' / missing
                    target.unlink()
                    with self.assertRaises(ApplyRefused):
                        reconcile_operation(fixture.wiki, fixture.inbox, operation_id, store)
                    self.assertFalse(target.exists())
                    self.assertFalse((fixture.candidate / 'applied.json').exists())

    def test_removed_evidence_directory_cannot_disappear_during_owned_capture_gap(self):
        import shutil
        from candidate_apply import reconcile_operation, ApplyRefused
        from workflow_store import WorkflowStore
        fixture = self.fixture('update', removed=True)
        captured = self.kill_manifest(fixture)
        original = captured.read_bytes()
        dest = fixture.wiki / 'raw/evidence/fixture-code'
        shutil.rmtree(dest)
        with WorkflowStore(fixture.data / 'workflow.sqlite') as store:
            operation_id = store.db.execute('SELECT id FROM operations').fetchone()[0]
            with self.assertRaises(ApplyRefused):
                reconcile_operation(fixture.wiki, fixture.inbox, operation_id, store)
            self.assertEqual(store.get_operation(operation_id)['state'], 'recovery_required')
        self.assertFalse(dest.exists())
        self.assertEqual(captured.read_bytes(), original)
        self.assertFalse((fixture.candidate / 'applied.json').exists())

    def test_applied_manifest_capture_handle_drift_is_reported_not_repaired(self):
        from candidate_apply import apply_candidate
        from workflow_store import WorkflowStore
        fixture = self.fixture()
        with WorkflowStore(fixture.data / 'workflow.sqlite') as store:
            result = apply_candidate(fixture.wiki, fixture.inbox, 'run/draft', fixture.snapshot, fixture.approval, store)
            captured = fixture.wiki / f".llm-wiki/evidence-attribution/{result['operation_id']}/fixture-code/captured.bin"
            newer = b'Late owner-held handle writes after operation completed'
            captured.write_bytes(newer)
            again = apply_candidate(fixture.wiki, fixture.inbox, 'run/draft', fixture.snapshot, fixture.approval, store)
            self.assertTrue(again['later_drift'])
            self.assertEqual(captured.read_bytes(), newer)

    def test_expected_hash_binds_parsed_manifest_not_reread_live_metadata(self):
        from unittest.mock import patch
        real_write = evidence_store.write_manifest
        fixture = self.fixture()
        target = fixture.candidate / 'evidence/fixture-code/manifest.json'
        folder = fixture.wiki / 'raw/evidence/fixture-code'
        import shutil
        shutil.copytree(target.parent, folder)
        (fixture.wiki / 'raw/sources/other.md').write_bytes(b'Evidence: fixture-code\n')
        live = folder / 'manifest.json'
        original = live.read_bytes()
        newer = json.dumps({**json.loads(original), 'owner_note': 'Changed before writer is called'}).encode()
        def before_writer(folder, value, **kwargs):
            live.write_bytes(newer)
            return real_write(folder, value, **kwargs)
        with patch.object(evidence_store, 'write_manifest', before_writer), self.assertRaises(RuntimeError):
            evidence_store.sync_used_by(fixture.wiki / 'raw/evidence', fixture.wiki / 'raw/sources',
                                       staging_root=fixture.wiki / '.llm-wiki/hash-fixture')
        self.assertEqual(live.read_bytes(), newer)
        self.assertEqual(next((fixture.wiki / '.llm-wiki/hash-fixture').rglob('captured.bin')).read_bytes(), newer)

    def test_candidate_owner_entry_and_capture_gap_races_preserve_both_objects(self):
        import candidate_apply
        from candidate_apply import apply_candidate, ApplyRefused
        from workflow_store import WorkflowStore
        from unittest.mock import patch
        worker = Path(__file__).with_name('candidate_apply_worker.py')
        real_rename = candidate_apply._rename_no_replace
        for kind in ('new', 'update', 'retire'):
            for race in ('owner-write', 'owner-replace', 'capture-gap'):
                with self.subTest(kind=kind, race=race):
                    fixture = self.fixture(kind)
                    target = fixture.wiki / 'raw/evidence/fixture-code/manifest.json'
                    initial = (fixture.candidate / 'evidence/fixture-code/manifest.json').read_bytes() if kind != 'retire' else target.read_bytes()
                    newer = json.dumps({**json.loads(initial), 'owner_note': race}).encode()
                    raced = []
                    def rename(source, destination):
                        at_boundary = Path(destination) == target if race == 'capture-gap' else Path(source) == target
                        if at_boundary and not raced:
                            reply = subprocess.run([sys.executable, str(worker),
                                'owner-write' if race == 'capture-gap' else race, str(target), newer.hex()],
                                capture_output=True, text=True, timeout=10)
                            self.assertEqual(reply.returncode, 0, reply.stdout + reply.stderr)
                            raced.append(True)
                        return real_rename(source, destination)
                    with WorkflowStore(fixture.data / 'workflow.sqlite') as store:
                        with patch.object(candidate_apply, '_rename_no_replace', rename), self.assertRaises(ApplyRefused):
                            apply_candidate(fixture.wiki, fixture.inbox, 'run/draft', fixture.snapshot, fixture.approval, store)
                        operation_id, state = store.db.execute('SELECT id,state FROM operations').fetchone()
                        self.assertEqual(state, 'recovery_required')
                    self.assertEqual(raced, [True])
                    self.assertEqual(target.read_bytes(), newer)
                    captured = fixture.wiki / f'.llm-wiki/evidence-attribution/{operation_id}/fixture-code/captured.bin'
                    self.assertEqual(captured.read_bytes(), initial if race == 'capture-gap' else newer)
                    self.assertFalse((fixture.candidate / 'applied.json').exists())
                    self.assertEqual({p.name for p in target.parent.iterdir()}, {'manifest.json', 'payload.txt'})

    def test_partial_owner_handle_after_capture_is_retained_without_false_completion(self):
        import candidate_apply
        from candidate_apply import apply_candidate, reconcile_operation, ApplyRefused
        from workflow_store import WorkflowStore
        from unittest.mock import patch
        fixture = self.fixture('retire')
        target = fixture.wiki / 'raw/evidence/fixture-code/manifest.json'
        newer = json.dumps({**json.loads(target.read_bytes()), 'owner_note': 'Owner completes partial stream'}).encode()
        worker = Path(__file__).with_name('candidate_apply_worker.py')
        proc = subprocess.Popen([sys.executable, str(worker), 'owner-held-partial', str(target), newer.hex()],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(proc.stdout.readline().strip(), 'OWNER_OPEN')
            def write_partial(point):
                if point == 'after-capture:attribution-manifest-fixture-code':
                    proc.stdin.write('partial\n')
                    proc.stdin.flush()
                    self.assertEqual(proc.stdout.readline().strip(), 'OWNER_PARTIAL')
            with WorkflowStore(fixture.data / 'workflow.sqlite') as store:
                with patch.object(candidate_apply, '_checkpoint', write_partial), self.assertRaises(ApplyRefused):
                    apply_candidate(fixture.wiki, fixture.inbox, 'run/draft', fixture.snapshot, fixture.approval, store)
                operation_id = store.db.execute('SELECT id FROM operations').fetchone()[0]
                captured = fixture.wiki / f'.llm-wiki/evidence-attribution/{operation_id}/fixture-code/captured.bin'
                partial = newer[:len(newer) // 2]
                self.assertEqual(captured.read_bytes(), partial)
                self.assertEqual(target.read_bytes(), partial)
                output, error = proc.communicate('complete\n', timeout=10)
                self.assertEqual(proc.returncode, 0, output + error)
                self.assertEqual(output.strip(), 'OWNER_WROTE')
                self.assertEqual(captured.read_bytes(), newer)
                self.assertEqual(target.read_bytes(), partial)
                with self.assertRaises(ApplyRefused):
                    reconcile_operation(fixture.wiki, fixture.inbox, operation_id, store)
                self.assertEqual(captured.read_bytes(), newer)
                self.assertEqual(target.read_bytes(), partial)
                self.assertEqual(store.get_operation(operation_id)['state'], 'recovery_required')
            self.assertFalse((fixture.candidate / 'applied.json').exists())
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate(timeout=10)

    def test_capture_gap_restoration_still_refuses_canonical_extras(self):
        from candidate_apply import reconcile_operation, ApplyRefused
        from workflow_store import WorkflowStore
        fixture = self.fixture()
        captured = self.kill_manifest(fixture)
        before = captured.read_bytes()
        extra = fixture.wiki / 'raw/evidence/fixture-code/manifest.json.tmp'
        extra.write_bytes(b'Owner payload, not an operation-private temporary')
        with WorkflowStore(fixture.data / 'workflow.sqlite') as store:
            operation_id = store.db.execute('SELECT id FROM operations').fetchone()[0]
            with self.assertRaisesRegex(ApplyRefused, 'evidence drift'):
                reconcile_operation(fixture.wiki, fixture.inbox, operation_id, store)
            self.assertEqual(store.get_operation(operation_id)['state'], 'recovery_required')
        self.assertEqual(extra.read_bytes(), b'Owner payload, not an operation-private temporary')
        self.assertEqual(captured.read_bytes(), before)
        self.assertEqual(extra.with_name('manifest.json').read_bytes(), before)
        self.assertFalse((fixture.candidate / 'applied.json').exists())

    def test_late_capture_edit_is_checked_before_application_marker(self):
        import candidate_apply
        from candidate_apply import apply_candidate, ApplyRefused
        from workflow_store import WorkflowStore
        from unittest.mock import patch
        fixture = self.fixture()
        newer = b'Owner changed captured manifest after publication, before completion'
        raced = []
        def late(point):
            if point == 'after-write:attribution-fixture-code':
                captured = next((fixture.wiki / '.llm-wiki/evidence-attribution').rglob('captured.bin'))
                captured.write_bytes(newer)
                raced.append(captured)
        with WorkflowStore(fixture.data / 'workflow.sqlite') as store:
            with patch.object(candidate_apply, '_checkpoint', late), self.assertRaises(ApplyRefused):
                apply_candidate(fixture.wiki, fixture.inbox, 'run/draft', fixture.snapshot, fixture.approval, store)
            self.assertEqual(store.db.execute('SELECT state FROM operations').fetchone()[0], 'recovery_required')
        self.assertEqual(len(raced), 1)
        self.assertEqual(raced[0].read_bytes(), newer)
        self.assertFalse((fixture.candidate / 'applied.json').exists())

    def test_capture_gap_owner_partial_json_is_preserved_and_refused(self):
        from candidate_apply import reconcile_operation, ApplyRefused
        from workflow_store import WorkflowStore
        fixture = self.fixture()
        captured = self.kill_manifest(fixture)
        before = captured.read_bytes()
        target = fixture.wiki / 'raw/evidence/fixture-code/manifest.json'
        partial = b'{"owner_note": "Partial independent entry'
        target.write_bytes(partial)
        with WorkflowStore(fixture.data / 'workflow.sqlite') as store:
            operation_id = store.db.execute('SELECT id FROM operations').fetchone()[0]
            with self.assertRaises(ApplyRefused):
                reconcile_operation(fixture.wiki, fixture.inbox, operation_id, store)
            self.assertEqual(store.get_operation(operation_id)['state'], 'recovery_required')
        self.assertEqual(target.read_bytes(), partial)
        self.assertEqual(captured.read_bytes(), before)
        self.assertFalse((fixture.candidate / 'applied.json').exists())

    def test_capture_gap_recovery_requires_exact_journal_owned_capture(self):
        from candidate_apply import reconcile_operation, ApplyRefused
        from workflow_store import WorkflowStore
        for damage in ('missing-binding', 'foreign-operation'):
            with self.subTest(damage=damage):
                fixture = self.fixture('update', removed=True)
                captured = self.kill_manifest(fixture)
                target = fixture.wiki / 'raw/evidence/fixture-code/manifest.json'
                before = captured.read_bytes()
                with WorkflowStore(fixture.data / 'workflow.sqlite') as store:
                    operation_id = store.db.execute('SELECT id FROM operations').fetchone()[0]
                    if damage == 'missing-binding':
                        with store.db:
                            store.db.execute("DELETE FROM steps WHERE operation_id=? AND name='attribution-base:fixture-code'", (operation_id,))
                    else:
                        alien = fixture.wiki / '.llm-wiki/evidence-attribution/another-operation/fixture-code/captured.bin'
                        alien.parent.mkdir(parents=True)
                        captured.rename(alien)
                        captured = alien
                    with self.assertRaises(ApplyRefused):
                        reconcile_operation(fixture.wiki, fixture.inbox, operation_id, store)
                    self.assertEqual(store.get_operation(operation_id)['state'], 'recovery_required')
                self.assertFalse(target.exists())
                self.assertEqual(captured.read_bytes(), before)
                self.assertFalse((fixture.candidate / 'applied.json').exists())

    def test_restored_identical_base_recapture_retains_raced_owner_bytes(self):
        import candidate_apply
        from candidate_apply import publish_file, ApplyRefused
        from unittest.mock import patch
        fixture = self.fixture()
        target = fixture.target
        original = b'Original exact source bytes\n'
        newer = b'Owner races an identical-base recapture\n'
        target.write_bytes(original)
        captured = fixture.wiki / '.llm-wiki/source-recovery/recapture-fixture/captured.bin'
        captured.parent.mkdir(parents=True)
        captured.write_bytes(original)
        worker = Path(__file__).with_name('candidate_apply_worker.py')
        real_rename = candidate_apply._rename_no_replace
        def race(source, destination):
            if Path(source) == target:
                reply = subprocess.run([sys.executable, str(worker), 'owner-write', str(target), newer.hex()],
                                       capture_output=True, text=True, timeout=10)
                self.assertEqual(reply.returncode, 0, reply.stdout + reply.stderr)
            return real_rename(source, destination)
        with patch.object(candidate_apply, '_rename_no_replace', race), self.assertRaises(ApplyRefused):
            publish_file(target, fixture.source, evidence_store.sha256(original), captured)
        self.assertEqual(target.read_bytes(), newer)
        self.assertEqual(captured.read_bytes(), original)
        retained = list(captured.parent.glob('recapture-*/captured.bin'))
        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0].read_bytes(), newer)
        with self.assertRaises(ApplyRefused):
            publish_file(target, fixture.source, evidence_store.sha256(original), captured)
        self.assertEqual(retained[0].read_bytes(), newer)
        self.assertEqual(captured.read_bytes(), original)
        self.assertEqual(target.read_bytes(), newer)

    def test_repeated_native_restoration_and_recapture_deaths_recover_exact_operation(self):
        from candidate_apply import reconcile_operation
        from workflow_store import WorkflowStore
        for kind, removed in (('new', False), ('update', True), ('retire', True)):
            with self.subTest(kind=kind, removed=removed):
                fixture = self.fixture(kind, removed)
                original = (fixture.wiki / 'raw/evidence/fixture-code/manifest.json').read_bytes() if removed else (fixture.candidate / 'evidence/fixture-code/manifest.json').read_bytes()
                phases = ('after-capture', 'before-restore', 'after-restore', 'after-capture', 'before-publish', 'after-publish')
                for phase in phases:
                    self.assertTrue(self.kill_manifest(fixture, phase).is_file())
                    self.assertFalse((fixture.candidate / 'applied.json').exists())
                with WorkflowStore(fixture.data / 'workflow.sqlite') as store:
                    operation_id = store.db.execute('SELECT id FROM operations').fetchone()[0]
                    self.assertEqual(reconcile_operation(fixture.wiki, fixture.inbox, operation_id, store)['state'], 'applied')
                    self.assertFalse(reconcile_operation(fixture.wiki, fixture.inbox, operation_id, store)['later_drift'])
                    self.assertEqual(store.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 1)
                archives = list((fixture.wiki / f'.llm-wiki/evidence-attribution/{operation_id}').rglob('captured.bin'))
                self.assertEqual(len(archives), 4)
                self.assertTrue(all(path.read_bytes() == original for path in archives))
                self.assertEqual({p.name for p in (fixture.wiki / 'raw/evidence/fixture-code').iterdir()}, {'manifest.json', 'payload.txt'})
        print('ATTRIBUTION_REPEAT_NATIVE_DEATHS recovered=18 expected=18 operation_configurations=3')

    def test_standalone_manifest_publication_retains_original_outside_evidence(self):
        fixture = self.fixture()
        import shutil
        folder = fixture.wiki / 'raw/evidence/fixture-code'
        shutil.copytree(fixture.candidate / 'evidence/fixture-code', folder)
        (fixture.wiki / 'raw/sources/fixture.md').write_bytes(b'Evidence: fixture-code\n')
        original = (folder / 'manifest.json').read_bytes()
        self.assertEqual(evidence_store.sync_used_by(folder.parent, fixture.wiki / 'raw/sources'), ['fixture-code'])
        self.assertEqual({p.name for p in folder.iterdir()}, {'manifest.json', 'payload.txt'})
        archive = next((fixture.wiki / 'raw').glob('.evidence-attribution-*/captured.bin'))
        self.assertEqual(archive.read_bytes(), original)
        self.assertEqual(json.loads((folder / 'manifest.json').read_bytes())['used_by'], ['fixture.md'])
        changed, problems = evidence_store.normalise(folder.parent, fixture.wiki / 'raw/sources', False, None)
        self.assertEqual(changed, 1)
        self.assertEqual(problems, [])
        self.assertEqual({p.name for p in folder.iterdir()}, {'manifest.json', 'payload.txt'})
        self.assertEqual(json.loads((folder / 'manifest.json').read_bytes())['schema'], 1)
        self.assertEqual(len(list((fixture.wiki / 'raw').glob('.evidence-attribution-*/captured.bin'))), 2)

    def test_actual_manifest_native_death_matrix_recovers_without_payload_drift(self):
        import test_candidate_apply as fixtures
        from candidate_apply import reconcile_operation
        from workflow_store import WorkflowStore
        worker = Path(__file__).with_name('candidate_apply_worker.py')
        total = 0
        for kind, removed in (('new', False), ('update', False), ('retire', False),
                              ('update', True), ('retire', True)):
            for phase in ('before-fsync', 'after-fsync', 'after-capture', 'before-publish', 'after-publish'):
                with self.subTest(kind=kind, removed=removed, phase=phase):
                    fixture = fixtures.CandidateApplyTests('test_repeated_applied_operation_is_noop')
                    fixture.setUp()
                    try:
                        fixture.configure_recovery(kind)
                        if removed:
                            fixture.remove_candidate_evidence(kind)
                        fixture.authorize()
                        original_manifest = (fixture.wiki / 'raw/evidence/fixture-code/manifest.json').read_bytes() if kind == 'retire' or removed else (fixture.candidate / 'evidence/fixture-code/manifest.json').read_bytes()
                        request = fixture.root / 'worker-request.json'
                        request.write_text(json.dumps({'wiki': str(fixture.wiki), 'inbox': str(fixture.inbox),
                            'snapshot': fixture.snapshot, 'approval': fixture.approval}), encoding='utf-8')
                        killed = subprocess.run([sys.executable, str(worker), 'attribution-death', str(request), phase],
                                                capture_output=True, text=True, timeout=10)
                        self.assertEqual(killed.returncode, 91, killed.stdout + killed.stderr)
                        survivor = Path(killed.stdout.strip())
                        self.assertTrue(survivor.is_file())
                        self.assertFalse((fixture.candidate / 'applied.json').exists())
                        dest = fixture.wiki / 'raw/evidence/fixture-code'
                        self.assertEqual({p.name for p in dest.iterdir()} - {'manifest.json'}, {'payload.txt'})
                        before = fixture.target.stat().st_mtime_ns if fixture.target.exists() else None
                        with WorkflowStore(fixture.data / 'workflow.sqlite') as store:
                            operation_id, state = store.db.execute('SELECT id,state FROM operations').fetchone()
                            self.assertEqual(state, 'applying')
                            self.assertEqual(reconcile_operation(fixture.wiki, fixture.inbox, operation_id, store)['state'], 'applied')
                            again = reconcile_operation(fixture.wiki, fixture.inbox, operation_id, store)
                            self.assertEqual(again['state'], 'applied')
                            self.assertFalse(again['later_drift'], 'Private staging cannot create false evidence drift')
                            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 1)
                        archives = list((fixture.wiki / f'.llm-wiki/evidence-attribution/{operation_id}').rglob('captured.bin'))
                        self.assertGreaterEqual(len(archives), 2 if phase in ('after-capture', 'before-publish') else 1)
                        for retained in archives:
                            self.assertEqual(retained.read_bytes(), original_manifest)
                            self.assertFalse(retained.is_relative_to(dest))
                        self.assertEqual({p.name for p in dest.iterdir()}, {'payload.txt', 'manifest.json'})
                        self.assertEqual(json.loads((dest / 'manifest.json').read_bytes())['used_by'],
                                         [] if kind == 'retire' or removed else [fixture.target.name])
                        if before is not None:
                            self.assertEqual(fixture.target.stat().st_mtime_ns, before)
                        self.assertEqual(fixture.target.exists(), kind != 'retire')
                        if kind != 'retire':
                            self.assertEqual(fixture.target.read_bytes(), fixture.source)
                        total += 1
                    finally:
                        fixture.doCleanups()
        print(f'ATTRIBUTION_NATIVE_DEATH_MATRIX recovered={total} expected=25')


if __name__ == '__main__':
    unittest.main()
