"""install.py's panel step: panels are pinned Git installs at the commit panels.json names.

Run: python tests/test_install_panels.py   (stdlib only; no Hermes, no network, no real Hermes home)
The hermes CLI is replaced by a stub that records its arguments and writes the install record the way
`hermes plugins install --ref` does, so each case checks what the installer decides, not Hermes.
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import install  # noqa: E402

REPO = "owner/panel-repo"
PIN = "a" * 40
OTHER = "b" * 40


class PanelStep(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        (self.home / "plugins").mkdir()
        self.calls = []
        self.exit_code = 0
        install.report.clear()
        install.PANELS = {"demo": {"repo": REPO, "commit": PIN}}
        install.hermes_cli = self.fake_cli

    def tearDown(self):
        self.tmp.cleanup()

    def fake_cli(self, args):
        self.calls.append(args)
        if self.exit_code == 0:
            ref = args[args.index("--ref") + 1]
            self.write_record({"demo": {"pinned": True, "revision": ref, "source": REPO}})
            (self.home / "plugins" / "demo").mkdir(exist_ok=True)
        return self.exit_code, "" if self.exit_code == 0 else "clone failed"

    def write_record(self, record):
        (self.home / "plugins" / ".install-metadata.json").write_text(json.dumps(record), encoding="utf-8")

    def panel_dir(self):
        d = self.home / "plugins" / "demo"
        d.mkdir()
        return d

    def results(self):
        return [(status.strip(), text) for status, text in install.report]

    def test_missing_panel_is_installed_pinned(self):
        install.install_panels(self.home, dry=False)
        self.assertEqual(self.calls, [["plugins", "install", REPO, "--ref", PIN, "--enable"]])
        self.assertEqual(self.results()[0][0], "OK")

    def test_dry_run_names_the_command_and_calls_nothing(self):
        install.install_panels(self.home, dry=True)
        self.assertEqual(self.calls, [])
        self.assertIn(f"--ref {PIN}", self.results()[0][1])

    def test_panel_pinned_at_the_engine_commit_is_left_alone(self):
        self.panel_dir()
        self.write_record({"demo": {"pinned": True, "revision": PIN}})
        install.install_panels(self.home, dry=False, force=True)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.results()[0][0], "OK")

    def test_panel_pinned_elsewhere_is_reported_not_moved(self):
        self.panel_dir()
        self.write_record({"demo": {"pinned": True, "revision": OTHER}})
        install.install_panels(self.home, dry=False)
        self.assertEqual(self.calls, [])
        self.assertIn(OTHER[:8], self.results()[0][1])
        self.assertIn("--force", self.results()[0][1])

    def test_force_moves_a_present_panel_to_the_engine_commit(self):
        self.panel_dir()
        install.install_panels(self.home, dry=False, force=True)
        self.assertEqual(self.calls, [["plugins", "install", REPO, "--ref", PIN, "--enable", "--force"]])
        self.assertEqual(self.results()[0][0], "OK")

    def test_force_never_replaces_uncommitted_work(self):
        d = self.panel_dir()
        subprocess.run(["git", "init", "-q", str(d)], check=True)
        (d / "plugin.yaml").write_text("name: demo\n", encoding="utf-8")
        install.install_panels(self.home, dry=False, force=True)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.results()[0][0], "EKSİK")

    def test_a_failed_install_is_a_failure(self):
        self.exit_code = 1
        install.install_panels(self.home, dry=False)
        self.assertEqual(self.results()[0][0], "EKSİK")
        self.assertIn("clone failed", self.results()[0][1])


class PanelsFile(unittest.TestCase):
    def test_every_panel_names_a_repo_and_a_full_commit(self):
        panels = json.loads((ROOT / "panels.json").read_text(encoding="utf-8"))["panels"]
        self.assertTrue(panels)
        for name, pin in panels.items():
            self.assertRegex(pin["repo"], r"^[\w.-]+/[\w.-]+$", name)
            self.assertTrue(re.fullmatch(r"[0-9a-f]{40}", pin["commit"]), name)

    def test_the_engine_keeps_no_panel_copy(self):
        self.assertFalse((ROOT / "plugin").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
