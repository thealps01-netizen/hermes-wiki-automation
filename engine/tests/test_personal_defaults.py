"""Nothing from the original author's own setup is built into the engine.

Why: the engine was written on one PC and carried that PC's choices as code: auto-commit and the
watchdog checked two git remotes named `onedrive` and `github`, so every other installation reported
a missing mirror every day; the watchdog compared that PC's agent setup (skills, plugins, Codex
routing) on every machine; the morning report was always written in Turkish; built-in job ids and the
wiki's own name appeared in defaults and in printed lines; and a dated installation report shipped that
PC's user name, home folder, wiki folder and project id. Each test below fails on that behaviour.
"""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))

import wikiconfig  # noqa: E402

LAUNCHER_PREFIX = "palantir_wiki_"   # installed cron entry-point names; renaming them is a migration
AUTHORS_WIKI = LAUNCHER_PREFIX.split("_")[0]
USER_HOME_PATH = re.compile(r"(?i)(?:\b[a-z]:[\\/]+|/[a-z]/|(?<![\w.])/)users[\\/]+[a-z][\w-]*")


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                          check=True, timeout=30).stdout.strip()


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.wiki = self.root / "wiki-project"
        (self.wiki / "wiki" / "concepts").mkdir(parents=True)
        (self.wiki / "wiki" / "concepts" / "a.md").write_text("# A\n", encoding="utf-8")
        git(self.wiki, "init", "-q", "-b", "main")
        git(self.wiki, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
        git(self.wiki, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")
        self.audit = self.root / "data"
        self.audit.mkdir()
        self.hermes = self.root / "hermes"
        self.hermes.mkdir()
        self.settings_file = self.root / "settings.json"
        self.write_settings({})
        environment = patch.dict(os.environ, {"LLMWIKI_SETTINGS": str(self.settings_file)})
        environment.start()
        self.addCleanup(environment.stop)

    def write_settings(self, extra: dict):
        self.settings_file.write_text(json.dumps({"project_root": str(self.wiki), "audit_dir": str(self.audit),
                                                  "hermes_home": str(self.hermes), **extra}), encoding="utf-8")

    def add_remote(self, name: str, pushed: bool = True) -> Path:
        bare = self.root / f"{name}.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, timeout=30)
        git(self.wiki, "remote", "add", name, str(bare))
        if pushed:
            git(self.wiki, "push", "-q", name, "HEAD:refs/heads/main")
            git(self.wiki, "fetch", "-q", name)
        return bare

    def load(self, name: str):
        spec = importlib.util.spec_from_file_location(f"isolated_{name}", ENGINE / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class MirrorRemotes(Fixture):
    def test_unset_mirrors_means_every_remote_of_the_wiki_repo(self):
        self.add_remote("backup")
        self.add_remote("offsite")
        self.assertEqual(wikiconfig.mirror_remotes(wikiconfig.load(), self.wiki), ["backup", "offsite"])

    def test_listed_mirrors_are_used_as_given(self):
        self.add_remote("backup")
        self.add_remote("offsite")
        self.write_settings({"mirrors": ["offsite"]})
        self.assertEqual(wikiconfig.mirror_remotes(wikiconfig.load(), self.wiki), ["offsite"])

    def test_empty_list_turns_the_mirror_check_off(self):
        self.add_remote("backup")
        self.write_settings({"mirrors": []})
        self.assertEqual(wikiconfig.mirror_remotes(wikiconfig.load(), self.wiki), [])

    def test_a_wiki_without_remotes_has_no_mirrors(self):
        self.assertEqual(wikiconfig.mirror_remotes(wikiconfig.load(), self.wiki), [])

    def test_autocommit_checks_the_wikis_own_remotes(self):
        self.add_remote("backup")
        self.assertEqual(tuple(self.load("wiki_autocommit").REMOTES), ("backup",))

    def test_watchdog_reports_a_behind_mirror_under_its_own_name(self):
        self.add_remote("backup")
        (self.wiki / "wiki" / "concepts" / "b.md").write_text("# B\n", encoding="utf-8")
        git(self.wiki, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
        git(self.wiki, "-c", "user.name=t", "-c", "user.email=t@t",
            "commit", "-q", "-m", "not pushed")
        wd = self.load("watchdog")
        wd.alerts.clear()
        wd.check_backup_freshness()
        self.assertEqual(len(wd.alerts), 1, wd.alerts)
        self.assertIn("'backup'", wd.alerts[0])

    def test_watchdog_is_silent_without_mirrors(self):
        wd = self.load("watchdog")
        wd.alerts.clear()
        wd.check_backup_freshness()
        self.assertEqual(wd.alerts, [])


class AgentDriftIsOptIn(Fixture):
    def crashing_checker(self) -> Path:
        script = self.audit / "drift_check.py"
        script.write_text("raise ValueError('fixture crash')\n", encoding="utf-8")
        return script

    def test_no_drift_expectations_means_the_check_does_not_run(self):
        wd = self.load("watchdog")
        wd.alerts.clear()
        script = self.crashing_checker()
        with patch.object(wd, "drift_script", lambda: script):
            wd.check_agent_drift()
        self.assertEqual(wd.alerts, [])

    def test_declared_drift_expectations_run_the_check(self):
        self.write_settings({"drift": {"expect": {"hermes_plugins_scan_on_install": True}}})
        wd = self.load("watchdog")
        wd.alerts.clear()
        script = self.crashing_checker()
        with patch.object(wd, "drift_script", lambda: script):
            wd.check_agent_drift()
        self.assertEqual(len(wd.alerts), 1)
        self.assertIn("fixture crash", wd.alerts[0])


class NoAuthorSetupInDefaults(unittest.TestCase):
    def test_no_job_ids_are_built_in(self):
        self.assertEqual(wikiconfig.DEFAULTS["jobs"], {})

    def test_report_language_is_not_fixed(self):
        prompt = (ENGINE / "harvest_prompt.md").read_text(encoding="utf-8")
        self.assertNotIn("Turkish", prompt)
        self.assertIn("language the owner writes in", prompt)

    def test_shipped_files_do_not_name_the_authors_wiki_or_home(self):
        found = []
        for path in sorted(ENGINE.rglob("*")):
            rel = path.relative_to(ENGINE)
            if not path.is_file() or "__pycache__" in rel.parts or any(p.startswith(".") for p in rel.parts[:-1]):
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if AUTHORS_WIKI in line.replace(LAUNCHER_PREFIX, "").lower() or USER_HOME_PATH.search(line):
                    found.append(f"{rel.as_posix()}:{number}")
        self.assertEqual(found, [])

    def test_home_path_rule_catches_a_real_user_folder(self):
        self.assertTrue(USER_HOME_PATH.search("C:" + r"\Users\someone\.llmwiki-audit"))
        self.assertTrue(USER_HOME_PATH.search("/c/" + "Users/someone/AppData"))
        self.assertFalse(USER_HOME_PATH.search("$HOME is /c/Users/...; hand it C:/Users/..."))


if __name__ == "__main__":
    unittest.main()
