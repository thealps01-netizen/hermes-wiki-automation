"""Watchdog timestamps and the agent-drift wrapper, in disposable folders only.

Why: the watchdog stamped state.json and alerts.log with `cmd /c echo %DATE% %TIME%`. On a Turkish
Windows the console prints the weekday in the OEM codepage ("Çar" -> byte 0x80), the scheduler's
Python decodes it as UTF-8, the reader thread dies and stdout comes back as None: every Wednesday
check_page_count crashed and that day's findings never reached alerts.log. And when drift_check.py
itself crashed, the watchdog reported "drift_check ayrıntı vermedi" instead of the crash.
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

# The panel's parser for alerts.log headers and state.json "checked" (dashboard/plugin_api.py).
PANEL_TIME = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})\D+(\d{1,2}):(\d{2}):(\d{2})")


def undecodable_console(*args, **kwargs):
    """What subprocess.run returns when its reader thread hit a UnicodeDecodeError."""
    return subprocess.CompletedProcess(args[0] if args else kwargs.get("args"), 0, stdout=None, stderr=None)


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.wiki = root / "wiki-project"
        (self.wiki / "wiki" / "concepts").mkdir(parents=True)
        (self.wiki / "wiki" / "concepts" / "a.md").write_text("# A\n", encoding="utf-8")
        self.audit = root / "data"
        self.audit.mkdir()
        self.hermes = root / "hermes"
        self.hermes.mkdir()
        settings = root / "settings.json"
        settings.write_text(json.dumps({"project_root": str(self.wiki), "audit_dir": str(self.audit),
                                        "hermes_home": str(self.hermes)}), encoding="utf-8")
        environment = patch.dict(os.environ, {"LLMWIKI_SETTINGS": str(settings)})
        environment.start()
        self.addCleanup(environment.stop)
        spec = importlib.util.spec_from_file_location("isolated_watchdog", ENGINE / "watchdog.py")
        self.wd = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.wd)
        self.wd.alerts.clear()

    def test_page_count_survives_undecodable_console_date(self):
        with patch.object(self.wd.subprocess, "run", side_effect=undecodable_console):
            self.wd.check_page_count()
        self.assertEqual(self.wd.alerts, [])
        state = json.loads((self.audit / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["pages"], 1)
        self.assertRegex(state["checked"], PANEL_TIME)

    def test_findings_reach_alerts_log_when_console_date_undecodable(self):
        def finding():
            self.wd.alerts.append("fixture finding")

        names = [n for n in dir(self.wd) if n.startswith("check_")]
        with patch.object(self.wd.subprocess, "run", side_effect=undecodable_console), \
                patch.multiple(self.wd, **{n: (lambda: None) for n in names if n != "check_page_count"}), \
                patch.object(self.wd, "check_page_count", finding):
            self.assertEqual(self.wd.main(), 1)
        log = (self.audit / "alerts.log").read_text(encoding="utf-8")
        header = log.splitlines()[0]
        self.assertTrue(header.startswith("[") and header.endswith("]"), header)
        self.assertRegex(header, PANEL_TIME)
        self.assertIn("- fixture finding", log)

    def test_drift_checker_crash_is_reported_as_a_crash(self):
        (self.audit / "drift_check.py").write_text("raise ValueError('fixture crash')\n", encoding="utf-8")
        script = Path(self.wd.__file__).resolve().parent / "drift_check.py"
        self.wd.CFG["drift"] = {"expect": {"hermes_plugins_scan_on_install": True}}
        with patch.object(self.wd, "drift_script", lambda: self.audit / "drift_check.py"):
            self.wd.check_agent_drift()
        self.assertEqual(len(self.wd.alerts), 1)
        self.assertIn("ValueError: fixture crash", self.wd.alerts[0])
        self.assertNotIn("ayrıntı vermedi", self.wd.alerts[0])
        self.assertTrue(script.exists())

    def test_agent_drift_runs_the_engine_copy(self):
        self.assertEqual(self.wd.drift_script(), ENGINE / "drift_check.py")


    def make_codex(self, *names):
        codex = self.audit.parent / "codex"
        for name in names:
            f = codex / "sessions" / "2026" / "09" / "01" / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"")
        return codex

    def test_compressed_codex_sessions_are_listed_by_the_reader(self):
        codex = self.make_codex("rollout-a.jsonl", "rollout-b.jsonl.zst")
        with patch.dict(os.environ, {"CODEX_HOME": str(codex)}), \
                patch.object(self.wd, "zstd_available", return_value=True):
            self.wd.check_harvest_coverage()
        self.assertEqual(self.wd.alerts, [])

    def test_missing_zstd_decoder_is_a_finding_not_a_crash(self):
        codex = self.make_codex("rollout-a.jsonl", "rollout-b.jsonl.zst")
        with patch.dict(os.environ, {"CODEX_HOME": str(codex)}), \
                patch("importlib.util.find_spec", side_effect=ModuleNotFoundError("compression")):
            self.wd.check_harvest_coverage()
        self.assertEqual(len(self.wd.alerts), 1)
        self.assertIn("zstd", self.wd.alerts[0])

    def test_codex_file_form_the_reader_skips_is_a_finding(self):
        codex = self.make_codex("rollout-a.jsonl", "rollout-c.jsonl.gz")
        with patch.dict(os.environ, {"CODEX_HOME": str(codex)}):
            self.wd.check_harvest_coverage()
        self.assertEqual(len(self.wd.alerts), 1)
        self.assertIn("1 Codex", self.wd.alerts[0])

    def install_engine(self, files):
        engine = self.audit.parent / "release"
        engine.mkdir()
        for name, body in files.items():
            (engine / name).write_text(body, encoding="utf-8")
        loc = self.hermes / "state" / "wiki-automation" / "location.json"
        loc.parent.mkdir(parents=True)
        loc.write_text(json.dumps({"engine_dir": str(engine)}), encoding="utf-8")

    def test_older_engine_copy_in_data_folder_is_a_finding(self):
        self.install_engine({"wiki_candidates.py": "new", "watchdog.py": "same"})
        (self.audit / "wiki_candidates.py").write_text("old", encoding="utf-8")
        (self.audit / "watchdog.py").write_text("same", encoding="utf-8")
        (self.audit / "local_tool.py").write_text("not an engine file", encoding="utf-8")
        self.wd.check_engine_copies()
        self.assertEqual(len(self.wd.alerts), 1)
        self.assertIn("['wiki_candidates.py']", self.wd.alerts[0])

    def test_matching_engine_copies_are_silent(self):
        self.install_engine({"watchdog.py": "same"})
        (self.audit / "watchdog.py").write_text("same", encoding="utf-8")
        self.wd.check_engine_copies()
        self.assertEqual(self.wd.alerts, [])

    def test_uncommitted_wiki_changes_older_than_a_day_are_a_finding(self):
        subprocess.run(["git", "-C", str(self.wiki), "init", "-q"], check=True)
        page = self.wiki / "wiki" / "concepts" / "a.md"
        old = __import__("time").time() - 30 * 3600
        os.utime(page, (old, old))
        out = self.hermes / "cron" / "output" / "job-ac"
        out.mkdir(parents=True)
        (out / "2026-10-16_09-27-36.md").write_text("# Cron Job\n\n!! auto-commit blocked: fixture\n", encoding="utf-8")
        self.wd.CFG["jobs"] = {"autocommit": "job-ac"}
        self.wd.check_commit_backlog()
        self.assertEqual(len(self.wd.alerts), 1)
        self.assertIn("commit edilmedi", self.wd.alerts[0])
        self.assertIn("!! auto-commit blocked: fixture", self.wd.alerts[0])

    def test_fresh_uncommitted_changes_are_not_a_finding(self):
        subprocess.run(["git", "-C", str(self.wiki), "init", "-q"], check=True)
        self.wd.check_commit_backlog()
        self.assertEqual(self.wd.alerts, [])

if __name__ == "__main__":
    unittest.main()
