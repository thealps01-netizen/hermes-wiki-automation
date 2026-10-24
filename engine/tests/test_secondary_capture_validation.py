"""Native owner-held recaptures must not disappear from completion validation."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
import candidate_apply as ca
import install
import test_candidate_apply as source_fixtures
import test_engine_install as install_fixtures
from workflow_store import WorkflowStore

# Death follows a real Windows no-overwrite rename, not a fabricated archive.
DEATH_WORKER = r'''
import json, os, pathlib, sys
sys.path[:0] = [sys.argv[1], sys.argv[1] + '/tests']
import candidate_apply as ca
import install
from workflow_store import WorkflowStore
request = json.loads(pathlib.Path(sys.argv[2]).read_bytes())
target, phase = pathlib.Path(sys.argv[3]), sys.argv[4]
real = ca._rename_no_replace
def rename(source, destination):
    result = real(source, destination)
    if ((phase == 'capture' and pathlib.Path(source) == target)
            or (phase == 'publish' and pathlib.Path(destination) == target)):
        os._exit(91)
    return result
ca._rename_no_replace = rename
if 'digest' in request:
    install.apply_plan(request, request['digest'])
else:
    with WorkflowStore(pathlib.Path(request['inbox']).parent / 'workflow.sqlite') as store:
        ca.apply_candidate(pathlib.Path(request['wiki']), pathlib.Path(request['inbox']),
                           'run/draft', request['snapshot'], request['approval'], store)
raise AssertionError('Native death boundary was not reached')
'''


@unittest.skipUnless(os.name == 'nt', 'Requires native Windows FILE_SHARE_DELETE handles')
class SecondaryCaptureValidationTests(unittest.TestCase):
    native_deaths = 0
    held_owner_writes = 0

    @classmethod
    def tearDownClass(cls):
        print(f'SECONDARY_CAPTURE_NATIVE deaths={cls.native_deaths} held_owner_writes={cls.held_owner_writes}')

    def source_fixture(self, kind='update'):
        fixture = source_fixtures.CandidateApplyTests('test_repeated_applied_operation_is_noop')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.configure_recovery(kind)
        fixture.authorize()
        request = fixture.root / 'request.json'
        request.write_bytes(json.dumps({'wiki': str(fixture.wiki), 'inbox': str(fixture.inbox),
            'snapshot': fixture.snapshot, 'approval': fixture.approval}).encode())
        return fixture, request

    def install_fixture(self, key='settings'):
        temporary = tempfile.TemporaryDirectory(dir=os.environ['TMPDIR'])
        self.addCleanup(temporary.cleanup)
        home = Path(temporary.name)
        initial = install_fixtures.EngineInstallTests().prepared(home)
        if key != 'settings':
            location = home / 'state/wiki-automation/location.json'
            location.parent.mkdir(parents=True)
            record = dict(initial['location'])
            if key.startswith('launcher-'):
                name = key.removeprefix('launcher-')
                target = home / 'scripts' / name
                target.parent.mkdir()
                original = b'# Previous owned launcher release\n'
                target.write_bytes(original)
                record['launcher_hashes'] = {**record['launcher_hashes'],
                    name: hashlib.sha256(original).hexdigest()}
            location.write_bytes(json.dumps(record).encode())
        plan = install.build_plan(initial['settings'], home, Path(initial['engine_dir']), Path(initial['audit_dir']))
        target = (Path(plan['audit_dir']) / 'settings.json' if key == 'settings' else
                  home / 'state/wiki-automation/location.json' if key == 'location' else
                  home / 'scripts' / key.removeprefix('launcher-'))
        request = home / 'request.json'
        request.write_bytes(json.dumps(plan).encode())
        return home, plan, target, request

    def death(self, request, target, phase):
        reply = subprocess.run([sys.executable, '-B', '-c', DEATH_WORKER,
            str(ROOT), str(request), str(target), phase], capture_output=True, text=True, timeout=25)
        self.assertEqual(reply.returncode, 91, reply.stdout + reply.stderr)
        type(self).native_deaths += 1

    def owner_write(self, target, content):
        reply = subprocess.run([sys.executable, '-B', str(ROOT / 'tests/candidate_apply_worker.py'),
            'owner-write', str(target), content.hex()], capture_output=True, text=True, timeout=15)
        self.assertEqual(reply.returncode, 0, reply.stdout + reply.stderr)

    def recapture(self, request, target, archive, second_phase='publish'):
        original = target.read_bytes()
        self.death(request, target, 'capture')
        self.assertFalse(target.exists())
        self.owner_write(target, original)
        newer = b'Independent owner retained bytes from FILE_SHARE_DELETE handle\n'
        holder = subprocess.Popen([sys.executable, '-B', str(ROOT / 'tests/candidate_apply_worker.py'),
            'owner-held-write', str(target), newer.hex()], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.close_holder, holder)
        self.assertEqual(holder.stdout.readline().strip(), 'OWNER_OPEN')
        self.death(request, target, second_phase)
        secondary = list(archive.parent.glob('recapture-*/captured.bin'))
        self.assertEqual(len(secondary), 1)
        self.assertEqual(archive.read_bytes(), original)
        self.assertEqual(secondary[0].read_bytes(), original)
        return holder, archive, secondary[0], original, newer

    @staticmethod
    def close_holder(holder):
        if holder.poll() is None:
            holder.kill()
            holder.communicate(timeout=15)

    def release_owner(self, holder, secondary, newer):
        output, error = holder.communicate('write\n', timeout=15)
        self.assertEqual(holder.returncode, 0, output + error)
        self.assertEqual(output.strip(), 'OWNER_WROTE')
        self.assertEqual(secondary.read_bytes(), newer)
        type(self).held_owner_writes += 1

    @staticmethod
    def tree(root):
        return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in root.rglob('*') if p.is_file() and p.suffix not in ('.sqlite', '.sqlite-wal', '.sqlite-shm')}

    def source_recapture(self, kind='update'):
        fixture, request = self.source_fixture(kind)
        operation_id = ca._identity(fixture.snapshot, fixture.approval)
        archive = ca._source_archive(fixture.wiki, operation_id)
        retained = self.recapture(request, fixture.target, archive, 'capture' if kind == 'retire' else 'publish')
        if kind == 'retire':
            self.assertFalse(fixture.target.exists())
        else:
            self.assertEqual(fixture.target.read_bytes(), fixture.source)
        return fixture, operation_id, retained

    def test_source_secondary_drift_before_resume_refuses_and_repeats_without_marker(self):
        self.assert_source_resume_refused('update')

    def test_retirement_secondary_drift_before_resume_refuses_without_marker(self):
        self.assert_source_resume_refused('retire')

    def assert_source_resume_refused(self, kind):
        fixture, operation_id, (holder, archive, secondary, original, newer) = self.source_recapture(kind)
        self.release_owner(holder, secondary, newer)
        before = self.tree(fixture.root)
        with WorkflowStore(fixture.data / 'workflow.sqlite') as store:
            for attempt in range(2):
                with self.subTest(attempt=attempt), self.assertRaises(ca.ApplyRefused):
                    ca.reconcile_operation(fixture.wiki, fixture.inbox, operation_id, store)
                self.assertEqual(store.get_operation(operation_id)['state'], 'recovery_required')
                self.assertNotIn('marker', {step['step'] for step in store.steps(operation_id)})
                self.assertEqual(self.tree(fixture.root), before)
        self.assertFalse((fixture.candidate / 'applied.json').exists())
        self.assertEqual(archive.read_bytes(), original)
        self.assertEqual(secondary.read_bytes(), newer)

    def test_source_applied_secondary_handle_drift_is_readonly_on_repeated_readback(self):
        self.assert_source_readback('update')

    def test_retirement_applied_secondary_handle_drift_is_readonly_on_repeat(self):
        self.assert_source_readback('retire')

    def assert_source_readback(self, kind):
        fixture, operation_id, (holder, archive, secondary, original, newer) = self.source_recapture(kind)
        with WorkflowStore(fixture.data / 'workflow.sqlite') as store:
            result = ca.reconcile_operation(fixture.wiki, fixture.inbox, operation_id, store)
            self.assertFalse(result['later_drift'])
            self.release_owner(holder, secondary, newer)
            before = self.tree(fixture.root)
            operation, steps = store.get_operation(operation_id), store.steps(operation_id)
            for attempt in range(2):
                self.assertTrue(ca.reconcile_operation(fixture.wiki, fixture.inbox, operation_id, store)['later_drift'])
                self.assertEqual(self.tree(fixture.root), before)
                self.assertEqual(store.get_operation(operation_id), operation)
                self.assertEqual(store.steps(operation_id), steps)

    def test_source_secondary_edit_after_attribution_refuses_before_marker(self):
        fixture, operation_id, (holder, archive, secondary, original, newer) = self.source_recapture()
        def late(point):
            if point == 'after-step:attribution':
                self.release_owner(holder, secondary, newer)
        with WorkflowStore(fixture.data / 'workflow.sqlite') as store:
            with patch.object(ca, '_checkpoint', late), self.assertRaises(ca.ApplyRefused):
                ca.reconcile_operation(fixture.wiki, fixture.inbox, operation_id, store)
            self.assertEqual(store.get_operation(operation_id)['state'], 'recovery_required')
        self.assertFalse((fixture.candidate / 'applied.json').exists())
        self.assertEqual(archive.read_bytes(), original)
        self.assertEqual(secondary.read_bytes(), newer)
        self.assertEqual(fixture.target.read_bytes(), fixture.source)

    def test_install_all_secondary_drift_before_resume_refuses_before_completion(self):
        for key in ('settings', 'launcher-_wiki_engine_bootstrap.py', 'location'):
            with self.subTest(key=key):
                home, plan, target, request = self.install_fixture(key)
                archive = target.parent / f".wiki-install-recovery/{plan['digest']}/{key}/captured.bin"
                holder, archive, secondary, original, newer = self.recapture(request, target, archive)
                self.release_owner(holder, secondary, newer)
                before = self.tree(home)
                journal = home / 'state/wiki-automation/installation.sqlite'
                with WorkflowStore(journal, read_only=True) as store:
                    steps = store.steps(plan['digest'])
                for attempt in range(2):
                    with self.assertRaises(ca.ApplyRefused):
                        install.apply_plan(plan, plan['digest'])
                    self.assertEqual(self.tree(home), before)
                    with WorkflowStore(journal, read_only=True) as store:
                        self.assertNotEqual(store.get_operation(plan['digest'])['state'], 'applied')
                        self.assertEqual(store.steps(plan['digest']), steps)
                self.assertEqual(archive.read_bytes(), original)
                self.assertEqual(secondary.read_bytes(), newer)

    def test_install_applied_secondary_handle_drift_is_readonly_on_repeated_readback(self):
        for key in ('settings', 'launcher-_wiki_engine_bootstrap.py', 'location'):
            with self.subTest(key=key):
                home, plan, target, request = self.install_fixture(key)
                archive = target.parent / f".wiki-install-recovery/{plan['digest']}/{key}/captured.bin"
                holder, archive, secondary, original, newer = self.recapture(request, target, archive)
                self.assertTrue(install.apply_plan(plan, plan['digest'])['ok'])
                self.release_owner(holder, secondary, newer)
                before = self.tree(home)
                journal = home / 'state/wiki-automation/installation.sqlite'
                with WorkflowStore(journal, read_only=True) as store:
                    operation, steps = store.get_operation(plan['digest']), store.steps(plan['digest'])
                for attempt in range(2):
                    result = install.apply_plan(plan, plan['digest'])
                    self.assertTrue(result.get('later_drift'), result)
                    self.assertEqual(self.tree(home), before)
                    with WorkflowStore(journal, read_only=True) as store:
                        self.assertEqual(store.get_operation(plan['digest']), operation)
                        self.assertEqual(store.steps(plan['digest']), steps)

    def test_install_earlier_secondary_edit_at_last_projection_refuses_completion(self):
        home, plan, target, request = self.install_fixture()
        archive = target.parent / f".wiki-install-recovery/{plan['digest']}/settings/captured.bin"
        holder, archive, secondary, original, newer = self.recapture(request, target, archive)
        def late(point):
            if point == 'after-write:location.json':
                self.release_owner(holder, secondary, newer)
        with patch.object(ca, '_checkpoint', late), self.assertRaises(ca.ApplyRefused):
            install.apply_plan(plan, plan['digest'])
        with WorkflowStore(home / 'state/wiki-automation/installation.sqlite', read_only=True) as store:
            self.assertNotEqual(store.get_operation(plan['digest'])['state'], 'applied')
        self.assertEqual(archive.read_bytes(), original)
        self.assertEqual(secondary.read_bytes(), newer)


if __name__ == '__main__':
    unittest.main()
