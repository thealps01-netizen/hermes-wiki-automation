"""Safe staging and mirror verification use disposable local Git repositories only."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class AutocommitTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.wiki = self.root / 'wiki-project'
        self.wiki.mkdir()
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Isolated Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        for name in ('wiki', 'raw/sources', 'raw/evidence', '.llm-wiki'):
            (self.wiki / name).mkdir(parents=True, exist_ok=True)
        (self.wiki / '.llm-wiki/project.json').write_text('{"id":"fixture"}')
        (self.wiki / 'wiki/page.md').write_bytes(b'# Initial\n')
        (self.wiki / 'user.txt').write_bytes(b'Initial user work\n')
        self.git('add', '.')
        self.git('commit', '-m', 'Fixture baseline')
        self.audit = self.root / 'data'
        self.audit.mkdir()
        settings = self.root / 'settings.json'
        settings.write_bytes(json.dumps({'project_root': str(self.wiki), 'project_id': 'fixture', 'audit_dir': str(self.audit)}).encode())
        environment = patch.dict(os.environ, {'LLMWIKI_SETTINGS': str(settings)})
        environment.start()
        self.addCleanup(environment.stop)
        spec = importlib.util.spec_from_file_location('isolated_autocommit', Path(__file__).resolve().parents[1] / 'wiki_autocommit.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.module.REMOTES = ()

    def git(self, *args):
        proc = subprocess.run(['git', '-C', str(self.wiki), *args], capture_output=True, timeout=15)
        if proc.returncode:
            raise AssertionError(proc.stderr.decode(errors='replace'))
        return proc.stdout

    def test_unrelated_partial_staging_preserved(self):
        (self.wiki / 'user.txt').write_bytes(b'Staged owner work\n')
        self.git('add', 'user.txt')
        (self.wiki / 'user.txt').write_bytes(b'Staged plus unstaged owner work\n')
        (self.wiki / 'wiki/page.md').write_bytes(b'# New page\n')
        index, head = self.git('diff', '--cached', '--binary'), self.git('rev-parse', 'HEAD')
        sha, message = self.module.app_commit(self.module.page_files())
        self.assertEqual(sha, '')
        self.assertIn('staged', message.lower())
        self.assertEqual(self.git('diff', '--cached', '--binary'), index)
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)

    def test_refused_hook_preserves_index_without_cleanup(self):
        (self.wiki / 'wiki/page.md').write_bytes(b'# New page\n')
        hooks = self.wiki / '.git/hooks'
        (hooks / 'pre-commit').write_bytes(b'#!/bin/sh\nexit 1\n')
        index = self.git('diff', '--cached', '--binary')
        sha, message = self.module.app_commit(self.module.page_files())
        self.assertEqual(sha, '')
        self.assertEqual(self.git('diff', '--cached', '--binary'), index)
        self.assertEqual((self.wiki / 'wiki/page.md').read_bytes(), b'# New page\n')

    def test_index_mutating_precommit_hook_is_refused_before_any_commit(self):
        (self.wiki / 'wiki/page.md').write_bytes(b'# New page\n')
        (self.wiki / '.git/hooks/pre-commit').write_bytes(
            b'#!/bin/sh\nprintf "Owner work\\n" > concurrent.txt\ngit add concurrent.txt\nexit 0\n')
        head = self.git('rev-parse', 'HEAD')
        sha, message = self.module.app_commit(self.module.page_files())
        self.assertEqual(sha, '', 'An index-mutating precommit hook ran during automatic commit')
        self.assertIn('hook', message.lower())
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        self.assertEqual(self.git('diff', '--cached', '--name-only'), b'')
        self.assertFalse((self.wiki / 'concurrent.txt').exists())

    def test_scoped_commit_includes_both_sides_of_a_rename(self):
        renamed = self.wiki / 'wiki/[draft] page.md'
        (self.wiki / 'wiki/page.md').rename(renamed)
        sha, message = self.module.app_commit(self.module.page_files())
        self.assertTrue(sha, message)
        self.assertEqual(self.git('ls-tree', '-r', '--name-only', 'HEAD', '--', 'wiki').splitlines(),
            [b'wiki/[draft] page.md'])
        self.assertEqual(self.git('show', 'HEAD:wiki/[draft] page.md'), b'# Initial\n')
        self.assertEqual(self.git('diff', '--cached', '--name-only'), b'')

    def test_successful_commit_rejects_concurrent_native_staging_without_losing_work(self):
        (self.wiki / 'wiki/page.md').write_bytes(b'# New page\n')
        owner_staged = b'Private owner work, not ready for backup\n'
        owner_worktree = b'Private staged plus unstaged owner work\n'
        original_git = self.module.git
        rejected = []
        def concurrent_writer(*args, **kwargs):
            if args[0] == 'commit':
                (self.wiki / 'user.txt').write_bytes(owner_staged)
                proc = subprocess.run(['git', '-C', str(self.wiki), 'add', 'user.txt'],
                    capture_output=True, timeout=15)
                rejected.append(proc.returncode)
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn(b'index.lock', proc.stderr)
                (self.wiki / 'user.txt').write_bytes(owner_worktree)
            return original_git(*args, **kwargs)
        with patch.object(self.module, 'git', side_effect=concurrent_writer):
            sha, message = self.module.app_commit(self.module.page_files())
        self.assertTrue(sha, message)
        self.assertEqual(self.git('show', '--pretty=format:', '--name-only', 'HEAD').splitlines(),
            [b'wiki/page.md'])
        self.assertEqual(self.git('show', 'HEAD:user.txt'), b'Initial user work\n')
        self.assertEqual(len(rejected), 1)
        self.assertEqual(self.git('show', ':user.txt'), b'Initial user work\n')
        self.assertEqual((self.wiki / 'user.txt').read_bytes(), owner_worktree)
        self.assertEqual(self.git('diff', '--cached', '--name-only'), b'')
        (self.wiki / 'user.txt').write_bytes(owner_staged)
        self.git('add', 'user.txt')  # Accepted after native lock release.
        (self.wiki / 'user.txt').write_bytes(owner_worktree)
        self.assertEqual(self.git('show', ':user.txt'), owner_staged)
        self.assertEqual(self.git('diff', '--cached', '--name-only'), b'user.txt\n')

    def test_failed_commit_rejects_concurrent_native_staging_without_losing_work(self):
        (self.wiki / 'wiki/page.md').write_bytes(b'# New page\n')
        original_git = self.module.git
        rejected = []
        def concurrent_writer(*args, **kwargs):
            if args[0] == 'commit':
                (self.wiki / 'concurrent.txt').write_bytes(b'Owner work\n')
                proc = subprocess.run(['git', '-C', str(self.wiki), 'add', 'concurrent.txt'],
                    capture_output=True, timeout=15)
                rejected.append(proc.returncode)
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn(b'index.lock', proc.stderr)
                self.git('config', 'user.name', '')
            return original_git(*args, **kwargs)
        with patch.object(self.module, 'git', side_effect=concurrent_writer):
            sha, message = self.module.app_commit(self.module.page_files())
        self.assertEqual(sha, '')
        self.assertEqual(len(rejected), 1)
        self.assertEqual(self.git('diff', '--cached', '--name-only'), b'')
        self.assertEqual((self.wiki / 'concurrent.txt').read_bytes(), b'Owner work\n')
        self.assertIn('recovery', message.lower())
        self.git('add', 'concurrent.txt')
        self.assertEqual(self.git('show', ':concurrent.txt'), b'Owner work\n')

    def test_selected_partial_staging_is_not_published_from_worktree(self):
        target = self.wiki / 'wiki/page.md'
        engine = b'# Engine snapshot\n'
        owner = b'# Owner selected hunk\n'
        private = b'# Owner selected hunk plus UNSTAGED private draft\n'
        target.write_bytes(engine)
        original_git = self.module.git
        accepted = []
        def concurrent_writer(*args, **kwargs):
            if args[0] == 'commit':
                target.write_bytes(owner)
                result = subprocess.run(['git', '-C', str(self.wiki), 'add', '--', 'wiki/page.md'],
                    capture_output=True, timeout=15)
                accepted.append(result.returncode == 0)
                if result.returncode:
                    self.assertIn(b'index.lock', result.stderr)
                target.write_bytes(private)
            return original_git(*args, **kwargs)
        with patch.object(self.module, 'git', side_effect=concurrent_writer):
            sha, message = self.module.app_commit(self.module.page_files())
        self.assertTrue(sha, message)
        self.assertEqual(self.git('show', 'HEAD:wiki/page.md'), engine)
        self.assertEqual(self.git('show', ':wiki/page.md'), owner if accepted[0] else engine)
        self.assertEqual(target.read_bytes(), private)

    def test_failed_cleanup_never_discards_selected_owner_staging(self):
        target = self.wiki / 'wiki/page.md'
        engine = b'# Engine snapshot\n'
        owner = b'# Owner selected hunk\n'
        private = b'# Owner selected hunk plus UNSTAGED private draft\n'
        baseline = self.git('rev-parse', 'HEAD')
        original_git = self.module.git
        for seam in ('before-attempt-snapshot', 'after-cleanup-comparison'):
            with self.subTest(seam=seam):
                self.git('read-tree', 'HEAD')
                target.write_bytes(engine)
                self.git('config', 'user.name', '')  # Native commit failure, not a mock failure.
                reads = []
                accepted = []
                def stage_owner():
                    target.write_bytes(owner)
                    proc = subprocess.run(['git', '-C', str(self.wiki), 'add', '--', 'wiki/page.md'],
                        capture_output=True, timeout=15)
                    accepted.append(proc.returncode == 0)
                    if proc.returncode:
                        self.assertIn(b'index.lock', proc.stderr)
                    target.write_bytes(private)
                def concurrent_writer(*args, **kwargs):
                    if args == ('diff', '--cached', '--binary'):
                        reads.append(True)
                        if seam == 'before-attempt-snapshot' and len(reads) == 1:
                            stage_owner()
                        result = original_git(*args, **kwargs)
                        if seam == 'after-cleanup-comparison' and len(reads) == 2:
                            stage_owner()
                        return result
                    if args[0] == 'commit' and not reads:
                        stage_owner()  # New protocol has no destructive-cleanup comparison seam.
                    return original_git(*args, **kwargs)
                with patch.object(self.module, 'git', side_effect=concurrent_writer):
                    sha, message = self.module.app_commit(self.module.page_files())
                self.assertEqual(sha, '')
                self.assertEqual(self.git('rev-parse', 'HEAD'), baseline)
                self.assertEqual(self.git('show', ':wiki/page.md'), owner if accepted[0] else b'# Initial\n')
                self.assertEqual(target.read_bytes(), private)

    def test_native_failure_never_changes_shared_index_bytes(self):
        target = self.wiki / 'wiki/page.md'
        target.write_bytes(b'# Engine snapshot\n')
        index = self.wiki / '.git/index'
        before = index.read_bytes()
        head = self.git('rev-parse', 'HEAD')
        self.git('config', 'user.name', '')
        sha, message = self.module.app_commit(self.module.page_files())
        self.assertEqual(sha, '', message)
        self.assertIn('failed', message)
        self.assertEqual(index.read_bytes(), before)
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        self.assertFalse((self.wiki / '.git/index.lock').exists())
        self.assertEqual(target.read_bytes(), b'# Engine snapshot\n')

    def test_postcommit_hook_runs_and_retains_its_accepted_private_staging(self):
        target = self.wiki / 'wiki/page.md'
        engine = b'# Engine snapshot\n'
        target.write_bytes(engine)
        hook = self.wiki / '.git/hooks/post-commit'
        hook.write_bytes(b'#!/bin/sh\nprintf "Private owner draft\\n" > wiki/page.md\ngit add -- wiki/page.md\n')
        hook.chmod(0o755)
        sha, message = self.module.app_commit(self.module.page_files())
        self.assertTrue(sha, message)
        self.assertEqual(self.git('show', 'HEAD:wiki/page.md'), engine)
        # The hook's native Git writes its inherited private index, not the locked
        # shared index. Its accepted staging must survive publication too.
        self.assertEqual(self.git('show', ':wiki/page.md'), b'Private owner draft\n')
        self.assertEqual(self.git('diff', '--cached', '--name-only'), b'wiki/page.md\n')
        self.assertEqual(target.read_bytes(), b'Private owner draft\n')
        self.assertEqual(hook.read_bytes(), b'#!/bin/sh\nprintf "Private owner draft\\n" > wiki/page.md\ngit add -- wiki/page.md\n')

    def test_failed_index_publication_retains_accepted_hook_staging_for_recovery(self):
        target = self.wiki / 'wiki/page.md'
        target.write_bytes(b'# Engine snapshot\n')
        hook = self.wiki / '.git/hooks/post-commit'
        hook.write_bytes(b'#!/bin/sh\nprintf "Hook staged owner work\\n" > user.txt\ngit add -- user.txt\n')
        hook.chmod(0o755)
        original_index = (self.wiki / '.git/index').read_bytes()
        with patch.object(self.module.os, 'replace', side_effect=PermissionError('fixture publication denied')):
            sha, message = self.module.app_commit(self.module.page_files())
        self.assertEqual(sha, '')
        self.assertIn('recovery', message)
        self.assertEqual(self.git('show', 'HEAD:wiki/page.md'), b'# Engine snapshot\n')
        self.assertEqual((self.wiki / '.git/index').read_bytes(), original_index)
        snapshots = list((self.wiki / '.git').glob('wiki-commit-*/index'))
        self.assertEqual(len(snapshots), 1, 'Accepted hook staging must remain recoverable')
        env = {**os.environ, 'GIT_INDEX_FILE': str(snapshots[0])}
        proc = subprocess.run(['git', '-C', str(self.wiki), 'show', ':user.txt'],
            env=env, capture_output=True, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, b'Hook staged owner work\n')
        lock = self.wiki / '.git/index.lock'
        before_lock = lock.read_bytes()
        self.assertTrue(before_lock)
        sha, message = self.module.app_commit(self.module.page_files())
        self.assertEqual(sha, '')
        self.assertIn('index.lock', message)
        self.assertEqual(lock.read_bytes(), before_lock)

    def test_native_lock_preserves_preexisting_lock_and_partial_staging(self):
        target = self.wiki / 'wiki/page.md'
        target.write_bytes(b'# Staged owner hunk\n')
        self.git('add', '--', 'wiki/page.md')
        target.write_bytes(b'# Staged owner hunk plus private draft\n')
        index = self.wiki / '.git/index'
        lock = self.wiki / '.git/index.lock'
        lock.write_bytes(b'Existing native writer lock, not engine-owned\n')
        before_index, before_lock = index.read_bytes(), lock.read_bytes()
        head = self.git('rev-parse', 'HEAD')
        sha, message = self.module.app_commit(self.module.page_files())
        self.assertEqual(sha, '')
        self.assertIn('index.lock', message)
        self.assertEqual(index.read_bytes(), before_index)
        self.assertEqual(lock.read_bytes(), before_lock)
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        self.assertEqual(target.read_bytes(), b'# Staged owner hunk plus private draft\n')

    def test_accepted_owner_staging_before_lock_is_preserved_inside_and_outside_scope(self):
        original_git = self.module.git
        baseline = self.git('rev-parse', 'HEAD')
        for name in ('wiki/page.md', 'user.txt'):
            with self.subTest(path=name):
                self.git('read-tree', 'HEAD')
                target = self.wiki / name
                (self.wiki / 'wiki/page.md').write_bytes(b'# Engine snapshot\n')
                accepted = []
                def concurrent_writer(*args, **kwargs):
                    result = original_git(*args, **kwargs)
                    if args == ('rev-parse', '--path-format=absolute', '--git-path', 'index'):
                        target.write_bytes(b'Owner selected hunk\n')
                        self.git('add', '--', name)
                        target.write_bytes(b'Owner selected plus UNSTAGED draft\n')
                        accepted.append((self.wiki / '.git/index').read_bytes())
                    return result
                with patch.object(self.module, 'git', side_effect=concurrent_writer):
                    sha, message = self.module.app_commit(self.module.page_files())
                self.assertEqual(sha, '')
                self.assertIn('staged', message)
                self.assertEqual(self.git('rev-parse', 'HEAD'), baseline)
                self.assertEqual((self.wiki / '.git/index').read_bytes(), accepted[0])
                self.assertEqual(self.git('show', ':' + name), b'Owner selected hunk\n')
                self.assertEqual(target.read_bytes(), b'Owner selected plus UNSTAGED draft\n')

    def test_worktree_only_edits_after_capture_do_not_enter_commit(self):
        target = self.wiki / 'wiki/page.md'
        target.write_bytes(b'# Engine snapshot\n')
        original_git = self.module.git
        calls = []
        def edit_after_capture(*args, **kwargs):
            result = original_git(*args, **kwargs)
            calls.append((args, kwargs.get('index_file')))
            if args[0] == 'add':
                target.write_bytes(b'# UNSTAGED owner private draft\n')
                (self.wiki / 'user.txt').write_bytes(b'Outside private draft\n')
            return result
        with patch.object(self.module, 'git', side_effect=edit_after_capture):
            sha, message = self.module.app_commit(self.module.page_files())
        self.assertTrue(sha, message)
        self.assertEqual(self.git('show', 'HEAD:wiki/page.md'), b'# Engine snapshot\n')
        self.assertEqual(self.git('show', ':wiki/page.md'), b'# Engine snapshot\n')
        self.assertEqual(target.read_bytes(), b'# UNSTAGED owner private draft\n')
        self.assertEqual(self.git('show', 'HEAD:user.txt'), b'Initial user work\n')
        self.assertEqual((self.wiki / 'user.txt').read_bytes(), b'Outside private draft\n')
        self.assertEqual(self.git('diff', '--cached', '--name-only'), b'')
        for args, index_file in calls:
            self.assertNotEqual(args[0], 'reset')
            if args[0] in ('add', 'commit'):
                self.assertIsNotNone(index_file)
            if args[0] == 'commit':
                self.assertNotIn('--only', args)
                self.assertNotIn('--no-verify', args)
                self.assertNotIn('--no-gpg-sign', args)

    def test_signing_failure_respects_existing_policy_and_preserves_index(self):
        (self.wiki / 'wiki/page.md').write_bytes(b'# Engine snapshot\n')
        self.git('config', 'commit.gpgsign', 'true')
        self.git('config', 'gpg.program', str(self.root / 'nonexistent-fixture-signer'))
        index = (self.wiki / '.git/index').read_bytes()
        head = self.git('rev-parse', 'HEAD')
        sha, message = self.module.app_commit(self.module.page_files())
        self.assertEqual(sha, '')
        self.assertIn('failed', message)
        self.assertEqual((self.wiki / '.git/index').read_bytes(), index)
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        self.assertEqual(self.git('config', 'commit.gpgsign').strip(), b'true')
        self.assertFalse((self.wiki / '.git/index.lock').exists())

    def test_real_process_death_preserves_native_index_and_owner_bytes(self):
        # Each subprocess actually exits 91 without finally/atexit cleanup. Native
        # Git runs normally; wrappers schedule death at real filesystem/Git seams.
        worker = r'''
import importlib.util, json, os, pathlib, subprocess, sys
source, root, mode = sys.argv[1:]
spec = importlib.util.spec_from_file_location('death_autocommit', source)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
root = pathlib.Path(root)
proof = root / 'death-proof.json'
lock_path = m.WIKI / '.git/index.lock'
def die():
    attempts = []
    for name in ('wiki/page.md', 'user.txt'):
        target = m.WIKI / name
        target.write_bytes(b'Owner selected hunk\n')
        p = subprocess.run(['git', '-C', str(m.WIKI), 'add', '--', name], capture_output=True, timeout=15)
        attempts.append({'path': name, 'exit': p.returncode, 'stderr': p.stderr.decode(errors='replace')})
        target.write_bytes(b'Owner selected plus UNSTAGED draft\n')
    proof.write_text(json.dumps({'mode': mode, 'attempts': attempts}), encoding='utf-8')
    os._exit(91)
old_git = m.git
def git(*args, **kwargs):
    if mode == 'before-commit' and args[0] == 'commit':
        die()
    p = old_git(*args, **kwargs)
    if mode == 'before-lock' and args == ('rev-parse', '--path-format=absolute', '--git-path', 'index'):
        die()
    if mode == 'after-capture' and args[0] == 'add':
        assert p.returncode == 0, p.stderr
        die()
    if mode == 'after-commit' and args[0] == 'commit':
        assert p.returncode == 0, p.stderr
        die()
    return p
m.git = git
old_copy = m.shutil.copyfile
def copy(*args, **kwargs):
    p = old_copy(*args, **kwargs)
    if mode == 'after-lock':
        die()
    return p
m.shutil.copyfile = copy
old_replace = m.os.replace
def replace(src, dst):
    if pathlib.Path(src) == lock_path and mode == 'before-replace':
        die()
    result = old_replace(src, dst)
    if pathlib.Path(src) == lock_path and mode == 'after-replace':
        die()
    return result
m.os.replace = replace
old_open = pathlib.Path.open
class InterruptedLock:
    def __init__(self, stream): self.stream = stream
    def write(self, data):
        self.stream.write(data[:len(data)//2])
        self.stream.flush()
        die()
    def __getattr__(self, name): return getattr(self.stream, name)
def open_path(path, *args, **kwargs):
    stream = old_open(path, *args, **kwargs)
    if mode == 'during-lock-write' and path == lock_path and args == ('xb',):
        return InterruptedLock(stream)
    return stream
pathlib.Path.open = open_path
m.app_commit(m.page_files())
raise AssertionError('Death seam was not reached: ' + mode)
'''
        modes = ('before-lock', 'after-lock', 'after-capture', 'before-commit',
            'after-commit', 'during-lock-write', 'before-replace', 'after-replace')
        for mode in modes:
            with self.subTest(mode=mode):
                fixture = AutocommitTests()
                fixture.setUp()
                try:
                    target = fixture.wiki / 'wiki/page.md'
                    target.write_bytes(b'# Engine snapshot\n')
                    shared = fixture.wiki / '.git/index'
                    before = shared.read_bytes()
                    baseline = fixture.git('rev-parse', 'HEAD')
                    proc = subprocess.run([sys.executable, '-B', '-c', worker,
                        str(Path(__file__).resolve().parents[1] / 'wiki_autocommit.py'),
                        str(fixture.root), mode], capture_output=True, timeout=30)
                    self.assertEqual(proc.returncode, 91, proc.stdout + proc.stderr)
                    proof = json.loads((fixture.root / 'death-proof.json').read_text(encoding='utf-8'))
                    unlocked = mode in ('before-lock', 'after-replace')
                    for attempt in proof['attempts']:
                        if unlocked:
                            self.assertEqual(attempt['exit'], 0, attempt)
                            self.assertEqual(fixture.git('show', ':' + attempt['path']), b'Owner selected hunk\n')
                        else:
                            self.assertNotEqual(attempt['exit'], 0, attempt)
                            self.assertIn('index.lock', attempt['stderr'])
                            self.assertEqual(shared.read_bytes(), before)
                        self.assertEqual((fixture.wiki / attempt['path']).read_bytes(),
                            b'Owner selected plus UNSTAGED draft\n')
                    committed = mode in ('after-commit', 'during-lock-write', 'before-replace', 'after-replace')
                    if committed:
                        self.assertNotEqual(fixture.git('rev-parse', 'HEAD'), baseline)
                        self.assertEqual(fixture.git('show', 'HEAD:wiki/page.md'), b'# Engine snapshot\n')
                        self.assertEqual(fixture.git('show', 'HEAD:user.txt'), b'Initial user work\n')
                    else:
                        self.assertEqual(fixture.git('rev-parse', 'HEAD'), baseline)
                    lock = fixture.wiki / '.git/index.lock'
                    self.assertEqual(lock.exists(), not unlocked)
                    if lock.exists():
                        before_lock, before_retry = lock.read_bytes(), shared.read_bytes()
                        snapshots = list((fixture.wiki / '.git').glob('wiki-commit-*/index'))
                        self.assertEqual(len(snapshots), 1)
                        env = {**os.environ, 'GIT_INDEX_FILE': str(snapshots[0])}
                        saved = subprocess.run(['git', '-C', str(fixture.wiki), 'show', ':wiki/page.md'],
                            env=env, capture_output=True, timeout=15)
                        self.assertEqual(saved.returncode, 0, saved.stderr)
                        expected = b'# Initial\n' if mode == 'after-lock' else b'# Engine snapshot\n'
                        self.assertEqual(saved.stdout, expected)
                        sha, message = fixture.module.app_commit(fixture.module.page_files())
                        self.assertEqual(sha, '')
                        self.assertIn('index.lock', message)
                        self.assertEqual(lock.read_bytes(), before_lock)
                        self.assertEqual(shared.read_bytes(), before_retry)
                finally:
                    fixture.doCleanups()

    def test_postcommit_head_change_requires_recovery_without_shared_publication(self):
        (self.wiki / 'wiki/page.md').write_bytes(b'# Engine snapshot\n')
        before = (self.wiki / '.git/index').read_bytes()
        hook = self.wiki / '.git/hooks/post-commit'
        hook.write_bytes(b'#!/bin/sh\ngit update-ref HEAD HEAD^\n')
        hook.chmod(0o755)
        sha, message = self.module.app_commit(self.module.page_files())
        self.assertEqual(sha, '', 'Changed HEAD must not be reported as the captured commit')
        self.assertIn('recovery', message)
        self.assertEqual((self.wiki / '.git/index').read_bytes(), before)
        self.assertTrue((self.wiki / '.git/index.lock').exists())
        snapshots = list((self.wiki / '.git').glob('wiki-commit-*/index'))
        self.assertEqual(len(snapshots), 1)

    def test_capture_io_failure_reports_no_retained_snapshot_and_preserves_index(self):
        (self.wiki / 'wiki/page.md').write_bytes(b'# Engine snapshot\n')
        before = (self.wiki / '.git/index').read_bytes()
        with patch.object(self.module.shutil, 'copyfile', side_effect=PermissionError('fixture capture denied')):
            sha, message = self.module.app_commit(self.module.page_files())
        self.assertEqual(sha, '')
        self.assertNotIn('snapshot retained', message)
        self.assertEqual((self.wiki / '.git/index').read_bytes(), before)
        self.assertFalse((self.wiki / '.git/index.lock').exists())
        self.assertEqual(list((self.wiki / '.git').glob('wiki-commit-*')), [])

    def test_failed_push_is_retried_without_a_new_commit(self):
        remote = self.root / 'remote.git'
        subprocess.run(['git', 'init', '--bare', str(remote)], capture_output=True, check=True, timeout=15)
        self.git('remote', 'add', 'fixture', str(remote))
        self.git('push', 'fixture', 'HEAD:refs/heads/main')
        self.module.REMOTES = ('fixture',)
        (remote / 'hooks/pre-receive').write_bytes(b'#!/bin/sh\nexit 1\n')
        (self.wiki / 'wiki/page.md').write_bytes(b'# Committed, not pushed\n')
        self.git('add', 'wiki/page.md')
        self.git('commit', '-m', 'Fixture unpushed change')
        head = self.git('rev-parse', 'HEAD')
        result = self.module.retry_mirrors()
        self.assertEqual(result['fixture']['state'], 'behind')
        self.assertIn('error', result['fixture'])
        (remote / 'hooks/pre-receive').unlink()
        with patch.object(sys, 'argv', ['wiki_autocommit.py', '--force']):
            self.assertEqual(self.module.main(), 0)
        self.assertEqual(self.module.mirror_state()['fixture']['state'], 'fresh')
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)

    def test_main_does_not_commit_while_an_application_holds_the_lock(self):
        from candidate_apply import operation_lock
        (self.wiki / 'wiki/page.md').write_bytes(b'# Still applying\n')
        head = self.git('rev-parse', 'HEAD')
        with operation_lock(self.audit), patch.object(sys, 'argv', ['wiki_autocommit.py', '--force']):
            self.assertEqual(self.module.main(), 1)
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        self.assertEqual(self.git('diff', '--cached', '--name-only'), b'')

    def test_busy_apply_blocks_commit(self):
        from workflow_store import WorkflowStore
        with WorkflowStore(self.audit / 'workflow.sqlite') as store:
            store.record_operation({'operation_id': 'fixture-operation'})
            for old, new in (('collected', 'drafted'), ('drafted', 'awaiting_approval'), ('awaiting_approval', 'applying')):
                store.transition('fixture-operation', old, new)
        (self.wiki / 'wiki/page.md').write_bytes(b'# Changed\n')
        head = self.git('rev-parse', 'HEAD')
        sha, message = self.module.app_commit(self.module.page_files())
        self.assertEqual(sha, '')
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        self.assertEqual(self.git('diff', '--cached', '--name-only'), b'')

    def test_unreachable_remote_is_unknown(self):
        self.git('remote', 'add', 'fixture', str(self.root / 'missing.git'))
        self.git('update-ref', 'refs/remotes/fixture/main', self.git('rev-parse', 'HEAD').decode().strip())
        self.module.REMOTES = ('fixture',)
        status = self.module.mirror_state()['fixture']
        self.assertIsInstance(status, dict, 'Mirror status trusts a tracking ref instead of checking actual remote')
        self.assertEqual(status['state'], 'unknown')


    def install_engine_hook(self):
        hooks = self.wiki / '.githooks'
        hooks.mkdir()
        (hooks / 'pre-commit').write_bytes(self.module.ENGINE_HOOK.read_bytes())
        self.git('config', 'core.hooksPath', '.githooks')

    def test_engine_own_precommit_hook_runs_and_commits(self):
        self.install_engine_hook()
        (self.wiki / 'wiki/other.md').write_bytes(b'# Other\n')
        (self.wiki / 'wiki/page.md').write_bytes(b'# New page\nSee [[concepts/other]].\n')
        head = self.git('rev-parse', 'HEAD')
        sha, message = self.module.app_commit(self.module.page_files())
        self.assertTrue(sha, message)
        self.assertNotEqual(self.git('rev-parse', 'HEAD'), head)
        committed = self.git('show', 'HEAD:wiki/page.md')
        self.assertIn(b'[[other]]', committed, 'the hook did not normalize link form before the commit')
        self.assertEqual(self.git('status', '--porcelain', '--', 'wiki'), b'')
        self.assertEqual(self.git('diff', '--cached', '--name-only'), b'')

    def test_engine_own_precommit_hook_leaves_no_bytecode_in_the_release(self):
        # The installed release is verified file by file; a __pycache__ the hook's Python writes into
        # it made the panel refuse the release as dirty (2026-10-19).
        release = self.root / 'release'
        (release / 'wiki-hooks').mkdir(parents=True)
        source = Path(__file__).resolve().parents[1]
        for name in ('fix_link_form.py', 'wikiconfig.py', 'wiki-hooks/pre-commit'):
            (release / name).write_bytes((source / name).read_bytes())
        self.module.ENGINE_HOOK = release / 'wiki-hooks/pre-commit'
        self.install_engine_hook()
        (self.wiki / 'wiki/other.md').write_bytes(b'# Other\n')
        (self.wiki / 'wiki/page.md').write_bytes(b'# New page\nSee [[concepts/other]].\n')
        environment = {key: value for key, value in os.environ.items() if key != 'PYTHONDONTWRITEBYTECODE'}
        with patch.dict(os.environ, environment, clear=True):
            sha, message = self.module.app_commit(self.module.page_files())
        self.assertTrue(sha, message)
        self.assertIn(b'[[other]]', self.git('show', 'HEAD:wiki/page.md'), 'the hook did not run from the release copy')
        self.assertEqual(sorted(path.relative_to(release).as_posix() for path in release.rglob('*') if path.is_file()),
            ['fix_link_form.py', 'wiki-hooks/pre-commit', 'wikiconfig.py'], 'the hook wrote files into the engine release')

    def test_modified_engine_hook_is_still_refused(self):
        self.install_engine_hook()
        hook = self.wiki / '.githooks/pre-commit'
        hook.write_bytes(hook.read_bytes() + b'\ngit add -A\n')
        (self.wiki / 'wiki/page.md').write_bytes(b'# New page\n')
        head = self.git('rev-parse', 'HEAD')
        sha, message = self.module.app_commit(self.module.page_files())
        self.assertEqual(sha, '')
        self.assertIn('not the engine', message)
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)

    def test_foreign_commit_msg_hook_is_refused_next_to_the_engine_hook(self):
        self.install_engine_hook()
        (self.wiki / '.githooks/commit-msg').write_bytes(b'#!/bin/sh\nexit 0\n')
        (self.wiki / 'wiki/page.md').write_bytes(b'# New page\n')
        head = self.git('rev-parse', 'HEAD')
        sha, message = self.module.app_commit(self.module.page_files())
        self.assertEqual(sha, '')
        self.assertIn('commit-msg', message)
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)

if __name__ == '__main__':
    unittest.main()
