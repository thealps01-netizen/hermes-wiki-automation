"""Cron entry point. The canonical watchdog and the other audit scripts live in the automation folder
(`~/.llmwiki-audit`, or the `audit_dir` named in its `settings.json`; no path is baked into code) —
Hermes cron only accepts a script inside its own scripts dir,
so this file is a thin launcher and carries no audit logic of its own. The one thing it does own
is the EXIT CONTRACT: it adapts the watchdog's signal convention to Hermes cron's.

Exit contract (see cron_exit):
  watchdog 0 (healthy)  -> cron 0, silent
  watchdog 1 (findings) -> cron 0, findings already on stdout = the delivered message
  anything else         -> passed through = a genuinely failed run

Why: the canonical watchdog uses exit 1 as its ALERT signal (that is what the Windows Task
Scheduler fires on), but Hermes cron reads ANY non-zero exit as a failed job. So every run that
found something arrived framed as "script failed" instead of as the message it already was.
"""
import json, os, pathlib, runpy, sys


def audit_root() -> pathlib.Path:
    """Otomasyon klasörünü BUL — kod içinde makineye özel mutlak yol yoktur.

    Sıra: `LLMWIKI_AUDIT_DIR` (taşıma provası) → kullanıcı evindeki `~/.llmwiki-audit` →
    oradaki `settings.json` içindeki `audit_dir`. Klasör başka bir PC'de başka bir kullanıcı
    altında olsa da bulunur; hedef bulunamazsa launcher açıkça hata verir."""
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


TARGET = audit_root() / "watchdog.py"


def cron_exit(code: object) -> int:
    """Map the watchdog's exit code onto cron's: 0 and 1 both mean "deliver stdout", else fail."""
    if code is None or code == 0 or code == 1:
        return 0
    return code if isinstance(code, int) else 1


if "--launcher-selftest" in sys.argv:
    assert cron_exit(0) == 0 and cron_exit(None) == 0
    assert cron_exit(1) == 0, "findings must not look like a failed job"
    assert cron_exit(2) == 2 and cron_exit("boom") == 1, "real failures must still fail"
    print("[launcher selftest] exit contract holds")
    raise SystemExit(0)

if not TARGET.exists():
    print(f"watchdog not found: {TARGET}")
    raise SystemExit(2)
sys.argv[0] = str(TARGET)
try:
    runpy.run_path(str(TARGET), run_name="__main__")
    raise SystemExit(cron_exit(0))
except SystemExit as exc:
    raise SystemExit(cron_exit(exc.code))
