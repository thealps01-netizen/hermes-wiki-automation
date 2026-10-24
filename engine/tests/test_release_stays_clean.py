"""Engine runs leave the installed release folder exactly as it was installed.

Why: the Wiki Automation panel hashes every file under releases/<engine sha>/ and refuses to work
when one is added ("Installed code release is dirty or lacks verified file identity"). The watchdog
started drift_check.py from the release with a plain `python drift_check.py`; that child imported
wikiconfig and Python wrote __pycache__/wikiconfig.cpython-*.pyc into the release, so one watchdog
run locked the panel. Rule: every Python child an engine script starts runs with -B.
"""
import ast
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ENGINE = Path(__file__).resolve().parents[1]


def python_children_without_no_bytecode_flag() -> list[str]:
    """`[sys.executable, ...]` argument lists in engine code whose next element is not "-B"."""
    found = []
    for path in sorted(ENGINE.glob("*.py")) + sorted((ENGINE / "launchers").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.List) and node.elts and ast.unparse(node.elts[0]) == "sys.executable":
                flag = node.elts[1] if len(node.elts) > 1 else None
                if not (isinstance(flag, ast.Constant) and flag.value == "-B"):
                    found.append(f"{path.name}:{node.lineno}")
    return found


class ReleaseStaysClean(unittest.TestCase):
    def test_every_python_child_runs_without_writing_bytecode(self):
        self.assertEqual(python_children_without_no_bytecode_flag(), [])

    def test_watchdog_drift_check_leaves_release_folder_unchanged(self):
        tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        release = root / "release"
        release.mkdir()
        shipped = ["drift_check.py", "watchdog.py", "wikiconfig.py"]
        for name in shipped:
            shutil.copy2(ENGINE / name, release / name)
        home = root / "home"
        hermes = home / "hermes"
        hermes.mkdir(parents=True)
        (hermes / "config.yaml").write_text("plugins:\n  enabled: []\n", encoding="utf-8")
        (root / "wiki-project" / "wiki").mkdir(parents=True)
        (root / "data").mkdir()
        settings = root / "settings.json"
        settings.write_text(json.dumps({"project_root": str(root / "wiki-project"), "audit_dir": str(root / "data"),
                                        "hermes_home": str(hermes),
                                        "drift": {"expect": {"hermes_plugins_scan_on_install": True}}}),
                                       encoding="utf-8")
        # The scheduler's environment: nothing switches bytecode writing off for the children.
        env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}
        env.update(USERPROFILE=str(home), HOME=str(home), LLMWIKI_SETTINGS=str(settings), PYTHONUTF8="1")
        with patch.dict(os.environ, env, clear=True), patch.dict(sys.modules), \
                patch.object(sys, "path", [str(release), *sys.path]), patch.object(sys, "dont_write_bytecode", True):
            sys.modules.pop("wikiconfig", None)
            spec = importlib.util.spec_from_file_location("release_watchdog", release / "watchdog.py")
            watchdog = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(watchdog)
            watchdog.check_agent_drift()
        self.assertEqual(sorted(p.relative_to(release).as_posix() for p in release.rglob("*")), shipped)


if __name__ == "__main__":
    unittest.main()
