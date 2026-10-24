"""Cron entry point for the wiki source-delivery watch.

The canonical script lives in the automation folder (`~/.llmwiki-audit`, or the `audit_dir` named in
its `settings.json`) - Hermes cron only
accepts a script inside its own scripts directory, so this file is a thin launcher and carries no
check logic of its own. What it does own is the EXIT CONTRACT.

Exit contract (see cron_exit):
  watch 0 (every source ingested)     -> cron 0, silent (empty stdout delivers nothing)
  watch 1 (finding / API unreachable) -> cron 0, stdout is a "!!" block = the message itself
  anything else                       -> passed through = a genuinely failed run

Why 1 maps to 0: the canonical script uses exit 1 as its ALERT signal, but Hermes cron reads ANY
non-zero exit as a failed job, so an alert would arrive framed as "script failed" instead of as the
message it already is. Real crashes (exit 2+, or an unexpected exception) still fail loudly.
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


TARGET = audit_root() / "wiki_ingest_watch.py"


def cron_exit(code: object) -> int:
    """Map the ingest-watch exit code onto cron's: 0 and 1 both mean "deliver stdout", else fail."""
    if code is None or code == 0 or code == 1:
        return 0
    return code if isinstance(code, int) else 1


if "--launcher-selftest" in sys.argv:
    assert cron_exit(0) == 0 and cron_exit(None) == 0
    assert cron_exit(1) == 0, "alerts must not look like a failed job"
    assert cron_exit(2) == 2 and cron_exit("boom") == 1, "real failures must still fail"
    print("[launcher selftest] exit contract holds")
    raise SystemExit(0)

if not TARGET.exists():
    print(f"ingest-watch script not found: {TARGET}")
    raise SystemExit(2)
sys.argv[0] = str(TARGET)
try:
    runpy.run_path(str(TARGET), run_name="__main__")
    raise SystemExit(cron_exit(0))
except SystemExit as exc:
    raise SystemExit(cron_exit(exc.code))
