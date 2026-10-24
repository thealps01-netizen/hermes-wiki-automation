"""drift_check.py when the running Python has no PyYAML, in a disposable home only.

Why: the Hermes scheduler runs engine scripts with Hermes' bundled interpreter, which has no
PyYAML. drift_check then parsed config.yaml as JSON, crashed before its "== SONUÇ ==" block, and the
watchdog could only say "drift_check ayrıntı vermedi" every day.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ENGINE = Path(__file__).resolve().parents[1]
NO_YAML = ("import runpy, sys; sys.modules['yaml'] = None; sys.argv = [sys.argv[1]]; "
           "runpy.run_path(sys.argv[0], run_name='__main__')")


class DriftCheckWithoutYaml(unittest.TestCase):
    def run_check(self, hermes_python: bool, prepare=None, drift=None) -> subprocess.CompletedProcess:
        tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(tmp.cleanup)
        home = Path(tmp.name)
        hermes = home / "hermes"
        hermes.mkdir()
        (hermes / "config.yaml").write_text("plugins:\n  enabled:\n  - honey\n", encoding="utf-8")
        if prepare:
            prepare(home, hermes)
        settings = home / "settings.json"
        conf = {"hermes_home": str(hermes), "audit_dir": str(home)}
        if drift is not None:
            conf["drift"] = drift
        settings.write_text(json.dumps(conf), encoding="utf-8")
        env = {**os.environ, "USERPROFILE": str(home), "HOME": str(home), "LLMWIKI_SETTINGS": str(settings),
               "PYTHONUTF8": "1"}
        # Stand-in for Hermes' own interpreter: this test's Python, which must have PyYAML.
        env["DRIFT_CHECK_YAML_PYTHON"] = sys.executable if hermes_python else str(home / "absent-python")
        return subprocess.run([sys.executable, "-c", NO_YAML, str(ENGINE / "drift_check.py")],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
                              timeout=120)

    def test_reports_unreadable_config_instead_of_crashing(self):
        out = self.run_check(hermes_python=False)
        self.assertNotIn("Traceback", out.stderr)
        self.assertIn("== SONUÇ ==", out.stdout)
        result = out.stdout.split("== SONUÇ ==")[-1]
        self.assertIn("PyYAML", result)
        # Checks that need the config are skipped, not reported as missing components.
        self.assertNotIn("honey -> hermes", result)
        self.assertNotIn("llm-wiki -> hermes", result)

    @unittest.skipUnless(importlib.util.find_spec("yaml"), "needs a Python with PyYAML as the stand-in")
    def test_reads_config_through_hermes_python(self):
        out = self.run_check(hermes_python=True)
        self.assertNotIn("Traceback", out.stderr)
        result = out.stdout.split("== SONUÇ ==")[-1]
        self.assertNotIn("PyYAML", result)
        self.assertNotIn("okunamadı", result)


def _skill(folder: Path, body: str) -> None:
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        "---\nname: demo-skill\nauthor: Example Owner\n---\n\n" + body + "\n", encoding="utf-8")


class SkillCopiesAreNotCompared(unittest.TestCase):
    """The owner retired the skill-copy comparison: copies of one skill in several agents may differ.

    Why: the comparison raised a finding every time a Hermes skill was edited, and the copies in the
    other agents are no longer kept in step. Broken references inside a single copy are still a finding.
    """

    run_check = DriftCheckWithoutYaml.run_check

    def test_different_copies_are_not_a_finding(self):
        def prepare(home: Path, hermes: Path) -> None:
            _skill(hermes / "skills" / "demo-skill", "Hermes wording.")
            _skill(home / ".claude" / "skills" / "demo-skill", "Claude wording.")
        out = self.run_check(hermes_python=False, prepare=prepare)
        self.assertNotIn("Traceback", out.stderr)
        result = out.stdout.split("== SONUÇ ==")[-1]
        self.assertNotIn("skill içeriği farklı", result)
        self.assertNotIn("demo-skill", result)

    def test_missing_reference_in_one_copy_is_still_a_finding(self):
        def prepare(home: Path, hermes: Path) -> None:
            _skill(hermes / "skills" / "demo-skill", "Details: [notes](references/notes.md)")
        out = self.run_check(hermes_python=False, prepare=prepare)
        result = out.stdout.split("== SONUÇ ==")[-1]
        self.assertIn("eksik referans: demo-skill", result)


@unittest.skipUnless(importlib.util.find_spec("yaml"), "needs a Python with PyYAML as the stand-in")
class RemovedAgentsAreNotExpected(unittest.TestCase):
    """`drift.agents` names the agent setups that exist; a tool left out of it is not expected.

    Why: the owner removed Claude Code and the Codex CLI (2026-10-16), and the hard-coded targets kept
    reporting honey, serena, llm-wiki-mcp and two skills as missing in tools that no longer exist.
    """

    run_check = DriftCheckWithoutYaml.run_check

    def result(self, drift=None) -> str:
        out = self.run_check(hermes_python=True, drift=drift)
        self.assertNotIn("Traceback", out.stderr)
        return out.stdout.split("== SONUÇ ==")[-1]

    def test_removed_tools_raise_no_finding(self):
        result = self.result({"agents": ["hermes", "antigravity"]})
        for tool in ("codex", "claude"):
            self.assertNotIn(f"-> {tool}", result)

    def test_listed_agent_is_still_checked(self):
        # The disposable Hermes enables honey but has no plugins/honey folder: still a finding.
        result = self.result({"agents": ["hermes", "antigravity"]})
        self.assertIn("bileşen eksik: honey -> hermes", result)

    def test_without_the_setting_every_agent_is_expected(self):
        result = self.result()
        self.assertIn("bileşen eksik: honey -> claude", result)
        self.assertIn("skill eksik: llm-wiki -> codex", result)


if __name__ == "__main__":
    unittest.main()
