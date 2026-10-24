"""Cron entry point for the Wiki Session Harvest (pre-run script of an agent job).

The canonical script lives in the automation folder (`~/.llmwiki-audit`, or the `audit_dir` named in
its `settings.json`). Hermes cron only accepts a script inside its own scripts directory, so this
file is a thin launcher and carries no logic of its own.

Contract: the harvest script's last stdout line is the cron gate, `{"wakeAgent": false}` when
nothing new was said (the job then costs nothing) or `{"wakeAgent": true, "context": {...}}` with
the run folder for the drafting agent. Exit 1 (settings missing) still prints a gate that keeps the
agent asleep; anything else is a real failure and passes through.
"""
import json, os, pathlib, runpy, sys


def audit_root() -> pathlib.Path:
    env = os.environ.get("LLMWIKI_AUDIT_DIR")
    if env:
        return pathlib.Path(env)
    home_dir = pathlib.Path.home() / ".llmwiki-audit"
    cfg_file = home_dir / "settings.json"
    if cfg_file.exists():
        try:
            raw = json.loads(cfg_file.read_text(encoding="utf-8")).get("audit_dir")
            if raw and pathlib.Path(raw).is_dir():
                return pathlib.Path(raw)
        except (OSError, ValueError):
            pass
    return home_dir


TARGET = audit_root() / "wiki_session_harvest.py"

if not TARGET.exists():
    print(f"session-harvest script not found: {TARGET}")
    print(json.dumps({"wakeAgent": False}))
    raise SystemExit(2)
sys.argv[0] = str(TARGET)
try:
    runpy.run_path(str(TARGET), run_name="__main__")
    raise SystemExit(0)
except SystemExit as exc:
    raise SystemExit(0 if exc.code in (None, 0, 1) else exc.code)
