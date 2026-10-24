"""Actual installer and generated launcher consumers, with real Windows junctions."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

import install
import test_engine_install


class LauncherConfinementTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='consumer-confinement-', dir=os.environ['TMPDIR'])
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.home = self.base / 'home'
        self.home.mkdir()
        self.plan = test_engine_install.EngineInstallTests().prepared(self.home)
        self.code = Path(self.plan['engine_dir'])
        self.data = Path(self.plan['audit_dir'])

    @contextmanager
    def junction(self, link, target):
        if os.name == 'nt':
            reply = subprocess.run([os.environ['COMSPEC'], '/d', '/c', 'mklink', '/J', str(link), str(target)],
                capture_output=True, text=True, check=True)
            self.assertIn('<<===>>', reply.stdout)
            self.assertFalse(link.is_symlink())
            self.assertTrue(link.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        else:
            link.symlink_to(target, target_is_directory=True)
        print(json.dumps({'junction': str(link), 'target': str(target),
            'is_symlink': link.is_symlink(), 'file_attributes': getattr(link.lstat(), 'st_file_attributes', None),
            'python': sys.version, 'os': os.name}))
        try:
            yield link
        finally:
            link.rmdir() if os.name == 'nt' else link.unlink()

    def run_cli(self, *args, script=None, executable=None):
        command = [str(executable or sys.executable), '-B', str(script or self.code / 'install.py'), *map(str, args)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        print(json.dumps({'command': command, 'exit': result.returncode, 'stdout': result.stdout,
            'stderr': result.stderr}, ensure_ascii=True))
        return result

    def preview_args(self, home=None, data=None):
        return ['--hermes-home', str(home or self.home), '--data-root', str(data or self.data),
            '--project-root', self.plan['settings']['project_root'], '--no-cron', '--no-plugin', '--plan-json']

    def assert_cli_refused(self, result):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        refusal = json.loads(result.stdout)
        self.assertEqual(refusal['state'], 'refused')
        self.assertIn('linked', refusal['reason'].lower())

    def test_build_plan_rejects_raw_junction_roots_and_ancestors(self):
        for role, target in (('home', self.home), ('code', self.code), ('data', self.data)):
            for ancestor in (False, True):
                with self.subTest(role=role, ancestor=ancestor):
                    alias = self.base / 'alias'
                    with self.junction(alias, target.parent if ancestor else target):
                        raw = alias / target.name if ancestor else alias
                        cfg = dict(self.plan['settings'])
                        home, code, data = self.home, self.code, self.data
                        if role == 'home':
                            home = raw
                            cfg['hermes_home'] = str(raw)
                        elif role == 'code':
                            code = raw
                        else:
                            data = raw
                            cfg['audit_dir'] = str(raw)
                        with self.assertRaises((ValueError, RuntimeError)) as refusal:
                            install.build_plan(cfg, home, code, data)
                        self.assertIn('linked', str(refusal.exception).lower())
        self.assertFalse((self.home / 'state/wiki-automation/location.json').exists())
        self.assertEqual(install.build_plan(self.plan['settings'], self.home, self.code, self.data), self.plan)

    def test_cli_preview_rejects_raw_roots_before_settings_or_helper_import(self):
        marker = self.base / 'untrusted-helper-imported'
        helper = self.code / 'wikiconfig.py'
        original = helper.read_bytes()
        for role, target in (('home', self.home), ('data', self.data), ('code', self.code)):
            for ancestor in (False, True):
                with self.subTest(role=role, ancestor=ancestor):
                    if role == 'code':
                        helper.write_text('from pathlib import Path\nPath(' + repr(str(marker)) + ').touch()\n')
                    with self.junction(self.base / 'alias', target.parent if ancestor else target) as alias:
                        raw = alias / target.name if ancestor else alias
                        args = self.preview_args(home=raw if role == 'home' else None,
                            data=raw if role == 'data' else None)
                        result = self.run_cli(*args, script=raw / 'install.py' if role == 'code' else None)
                        self.assert_cli_refused(result)
                        self.assertFalse(marker.exists(), 'Imported an untrusted selected-code helper')
                    helper.write_bytes(original)
        self.assertFalse((self.home / 'state').exists())

    def test_cli_apply_rejects_changed_raw_roots_before_any_projection(self):
        artifact = self.base / 'plan.json'
        artifact.write_text(json.dumps(self.plan))
        original_settings = (self.data / 'settings.json').read_bytes()
        for role, target in (('home', self.home), ('code', self.code), ('data', self.data)):
            with self.subTest(role=role):
                moved = self.base / ('moved-' + role)
                shutil.move(target, moved)
                try:
                    with self.junction(target, moved):
                        # Run the trusted repository installer, not code from the redirected root.
                        self.assert_cli_refused(self.run_cli('--apply-plan', artifact,
                            '--expected-digest', self.plan['digest'], script=Path(install.__file__)))
                finally:
                    shutil.move(moved, target)
                self.assertEqual((self.data / 'settings.json').read_bytes(), original_settings)
                self.assertFalse((self.home / 'state').exists())
                self.assertFalse((self.home / 'scripts').exists())

    def test_cli_sensitive_descendants_are_structured_refusals(self):
        for relative in ('scripts', 'state/wiki-automation'):
            with self.subTest(relative=relative):
                link = self.home / relative
                link.parent.mkdir(parents=True, exist_ok=True)
                target = self.base / 'outside'
                target.mkdir(exist_ok=True)
                (target / 'location.json').write_text(json.dumps(self.plan['location']))
                with self.junction(link, target):
                    self.assert_cli_refused(self.run_cli(*self.preview_args()))
                self.assertFalse((target / 'installation.sqlite').exists())
        settings = self.data / 'settings.json'
        alias = self.base / 'settings-hardlink.json'
        os.link(settings, alias)
        try:
            self.assert_cli_refused(self.run_cli(*self.preview_args()))
        finally:
            alias.unlink()
        artifact_dir = self.base / 'artifacts'
        artifact_dir.mkdir()
        artifact = artifact_dir / 'plan.json'
        artifact.write_text(json.dumps(self.plan))
        with self.junction(self.base / 'artifact-alias', artifact_dir) as alias:
            self.assert_cli_refused(self.run_cli('--apply-plan', alias / artifact.name,
                '--expected-digest', self.plan['digest']))

    def sentinel(self, implementation='watchdog.py', status=0):
        marker = self.base / 'executed.json'
        (self.code / implementation).write_text(
            "import json,os,pathlib,sys\npathlib.Path(" + repr(str(marker)) + ").write_text(json.dumps({"
            "'home':os.environ.get('HERMES_HOME'),'settings':os.environ.get('LLMWIKI_SETTINGS'),"
            "'code':os.environ.get('LLMWIKI_AUDIT_DIR'),'cwd':os.getcwd(),'args':sys.argv[1:]}))\n"
            "print('BENIGN_SENTINEL_EXECUTED')\nraise SystemExit(" + repr(status) + ")\n")
        return marker

    def run_launcher(self, launcher=None, executable=None, args=()):
        command = [str(executable or sys.executable), '-B',
            str(launcher or self.home / 'scripts/palantir_wiki_watchdog.py'), *args]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        print(json.dumps({'command': command, 'exit': result.returncode,
            'stdout': result.stdout, 'stderr': result.stderr}))
        return result

    def assert_launcher_refused(self, result, marker):
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertIn('linked', result.stdout.lower())
        self.assertFalse(marker.exists(), 'Redirected consumer executed the sentinel')
        print(json.dumps({'negative_control': str(marker), 'sentinel_exists': marker.exists()}))

    def test_generated_launcher_rejects_redirected_roots_and_descendants(self):
        install.apply_plan(self.plan, self.plan['digest'])
        marker = self.sentinel()
        for role, target in (('code', self.code), ('data', self.data), ('scripts', self.home / 'scripts'),
                ('location', self.home / 'state/wiki-automation'), ('home', self.home)):
            with self.subTest(role=role):
                moved = self.base / ('outside-' + role)
                shutil.move(target, moved)
                try:
                    with self.junction(target, moved):
                        # Positive reproduction setup: old .resolve() adopts this external home.
                        if role == 'scripts':
                            outside_location = self.base / 'state/wiki-automation/location.json'
                            outside_location.parent.mkdir(parents=True, exist_ok=True)
                            outside_location.write_text(json.dumps(self.plan['location']))
                        self.assert_launcher_refused(self.run_launcher(), marker)
                        self.assert_launcher_refused(self.run_launcher(args=['--launcher-check']), marker)
                finally:
                    shutil.move(moved, target)
        for target in (self.data / 'settings.json', self.home / 'state/wiki-automation/location.json',
                self.code / 'watchdog.py', self.code / 'wikiconfig.py'):
            with self.subTest(file=target.name):
                alias = self.base / 'hardlink'
                os.link(target, alias)
                try:
                    args = ['--launcher-check'] if target.name == 'wikiconfig.py' else []
                    self.assert_launcher_refused(self.run_launcher(args=args), marker)
                finally:
                    alias.unlink()
        # Selected interpreter may itself pass through a junction, without symlink privileges.
        with self.junction(self.base / 'python-alias', Path(sys.executable).parent) as alias:
            self.assert_launcher_refused(self.run_launcher(executable=alias / Path(sys.executable).name), marker)
        result = self.run_launcher(args=['forwarded-owner-argument'])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        observed = json.loads(marker.read_bytes())
        self.assertEqual(observed, {'home': str(self.home), 'settings': str(self.data / 'settings.json'),
            'code': str(self.code), 'cwd': str(self.home), 'args': ['forwarded-owner-argument']})

    def test_generated_launcher_preserves_alert_and_real_failure_statuses(self):
        install.apply_plan(self.plan, self.plan['digest'])
        for implementation, launcher, status, expected in (
                ('wiki_autocommit.py', 'palantir_wiki_autocommit.py', 1, 0),
                ('wiki_ingest_watch.py', 'palantir_wiki_ingest_watch.py', 1, 0),
                ('watchdog.py', 'palantir_wiki_watchdog.py', 1, 1),
                ('watchdog.py', 'palantir_wiki_watchdog.py', 2, 2),
                ('wiki_autocommit.py', 'palantir_wiki_autocommit.py', 7, 7)):
            with self.subTest(implementation=implementation, status=status):
                marker = self.sentinel(implementation, status)
                result = self.run_launcher(self.home / 'scripts' / launcher)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                self.assertTrue(marker.exists())
                marker.unlink()

    def test_raw_parent_spelling_cannot_hide_a_junction(self):
        with self.junction(self.base / 'cancelled-alias', self.home) as alias:
            raw = alias / '..' / 'home'
            self.assert_cli_refused(self.run_cli(*self.preview_args(home=raw)))
            self.assert_cli_refused(self.run_cli(*self.preview_args(), script=raw / 'code/install.py'))
            with self.assertRaises((ValueError, RuntimeError)):
                install.build_plan({**self.plan['settings'], 'hermes_home': str(raw)}, raw, self.code, self.data)
        install.apply_plan(self.plan, self.plan['digest'])
        marker = self.sentinel()
        with self.junction(self.base / 'cancelled-alias', self.home) as alias:
            self.assert_launcher_refused(self.run_launcher(alias / '../home/scripts/palantir_wiki_watchdog.py'), marker)

    def test_previous_location_and_configured_profile_aliases_are_not_resolved_away(self):
        location = self.home / 'state/wiki-automation/location.json'
        location.parent.mkdir(parents=True)
        for role, target in (('code', self.code), ('data', self.data), ('home', self.home)):
            with self.subTest(role=role), self.junction(self.base / 'alias', target) as alias:
                record = dict(self.plan['location'])
                cfg = dict(self.plan['settings'])
                if role == 'home':
                    cfg['hermes_home'] = str(alias)
                else:
                    record['engine_dir' if role == 'code' else 'audit_dir'] = str(alias)
                location.write_text(json.dumps(record))
                with self.assertRaises((ValueError, RuntimeError)) as refusal:
                    install.build_plan(cfg, self.home, self.code, self.data)
                self.assertIn('linked', str(refusal.exception).lower())


if __name__ == '__main__':
    unittest.main()
