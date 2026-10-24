"""LLM Wiki - source delivery watchdog (did the watcher actually ingest what we dropped?).

WHY THIS EXISTS
  A source file written into raw/sources/ is ingested by the app's own source watcher. Nothing in
  that path reports failure: if the app was not running, the watch was toggled off, the extension
  was not in includeExtensions, or the write landed while the watcher was starting, the source just
  sits on disk with no pages and no error anywhere. That silent class is what this check closes.
  The matching integrator check (app never commits) lives in wiki_autocommit.py.

WHAT ONE RUN CHECKS (read-only except the deliberate rescan escalation)
  1. NAME   - every raw/sources/*.md has an entry in .llm-wiki/ingest-cache.json
  2. HASH   - the cache's recorded hash equals sha256 of the file's current bytes
              (verified 2026-09-17: the cache stores sha256 over the file bytes, 59/59 matched)
  3. MIRROR - the cache's provenance page wiki/sources/<name> for that source still exists.
              Check 3 deliberately does NOT walk every path in the cache's filesWritten list: that
              list is history, not a live inventory (the app deletes pages on purpose when a source
              is removed, agents delete them during dedup cleanup). Walking it fired 6 false alerts
              on 2026-09-17 for pages removed by deliberate cleanup commits, so this scanner checks
              the one page that must always survive. All 59 sources have theirs.

ESCALATION LADDER (a finding is not an alert until it survives the ladder)
  younger than INFLIGHT_MIN        -> in-flight, silent, not recorded
  older, first seen               -> recorded in ingest-watch-state.json, still silent
  older than RESCAN_AFTER_MIN      -> one POST .../sources/rescan (the documented recovery trigger)
  older than ESCALATE_MIN          -> alert line, exit 1 (the run shows red until it clears)

PROJECT ID IS RESOLVED AT RUN TIME from GET /api/v1/projects, never read from
  .llm-wiki/project.json: the app's HTTP API knows only its runtime-active id. Verified 2026-09-17:
  POST /projects/<canonical id>/sources/rescan -> 404 {"error":"Unknown project"}, while the
  runtime-active id returned 200. Hardcoding the canonical id would have shipped a dead escalation path.

OUTPUT CONTRACT (Hermes cron, no_agent -> stdout delivered verbatim)
  clean     -> no output, exit 0
  findings  -> "!!" lines with age, action taken and the checks to run, exit 1
  API down  -> "!!" line naming the app as the suspect, exit 1 (cannot verify != verified clean)

Run: python wiki_ingest_watch.py [--selftest]
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Script klasörü sys.path'e ÖNCE eklenir: cron giriş noktası bu dosyayı `runpy.run_path` ile koşar
# ve o yolda script'in kendi klasörü path'e girmez (`python script.py` ile girer). Sıra önemli —
# import satırı bunun ALTINDA olmalı, yoksa cron koşusunda ModuleNotFoundError alınır (yaşandı).
sys.path.insert(0, str(Path(__file__).resolve().parent))

import wikiconfig  # tek ayar kaynağı (settings.json) — makineye özel yol KODDA YOK

try:
    CFG = wikiconfig.load()
    WIKI = wikiconfig.project_root(CFG)          # seçili proje kökü; ayarsızsa ALARM
except wikiconfig.ConfigError as exc:
    print(f"!! ayar sorunu: {exc}")
    print(f"   düzeltme: {wikiconfig.settings_path()} içindeki 'project_root' alanını doldur")
    raise SystemExit(1)

AUDIT_DIR = wikiconfig.audit_dir(CFG)
# Scripts run from the installed engine release; the data folder holds state, never engine code.
ENGINE_DIR = Path(__file__).resolve().parent
_GATES = CFG.get("gates") or {}
RAW = WIKI / "raw" / "sources"
CACHE = WIKI / ".llm-wiki" / "ingest-cache.json"
STATE = AUDIT_DIR / "ingest-watch-state.json"
LOCK = AUDIT_DIR / "ingest-watch.lock"

API = f"{str(CFG.get('api_base') or 'http://127.0.0.1:19828').rstrip('/')}/api/v1"
PROJECT_PATH = str(WIKI)

INFLIGHT_MIN = int(_GATES.get("inflight_minutes", 10))
RESCAN_AFTER_MIN = int(_GATES.get("rescan_after_minutes", 20))
ESCALATE_MIN = int(_GATES.get("escalate_minutes", 45))
LOCK_MAX_MIN = int(_GATES.get("lock_max_minutes", 20))

for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def api(method: str, path: str, timeout: int = 15):
    req = urllib.request.Request(f"{API}{path}", method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def active_project_id() -> str | None:
    data = api("GET", "/projects")
    projects = data.get("projects", data if isinstance(data, list) else [])
    for p in projects:
        if str(p.get("path", "")).replace("\\", "/").lower() == PROJECT_PATH.lower() and p.get("current"):
            return p.get("id")
    for p in projects:
        if str(p.get("path", "")).replace("\\", "/").lower() == PROJECT_PATH.lower():
            return p.get("id")
    return None


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def findings() -> list[dict]:
    out: list[dict] = []
    cache = read_json(CACHE, {}).get("entries", {})
    if not isinstance(cache, dict):
        return out
    for src in sorted(RAW.glob("*.md")):
        age_min = (time.time() - src.stat().st_mtime) / 60.0
        entry = cache.get(src.name)
        if entry is None:
            if age_min >= INFLIGHT_MIN:
                out.append({"name": src.name, "kind": "missing",
                            "detail": f"no ingest-cache entry {age_min:.0f} min after the file landed"})
            continue
        want = entry.get("hash")
        got = sha256(src)
        if want and want != got:
            if age_min >= INFLIGHT_MIN:
                out.append({"name": src.name, "kind": "drift",
                            "detail": f"source changed after ingest (cache {want[:10]} != disk {got[:10]})"})
        mirror = f"wiki/sources/{src.name}"
        wrote = set(entry.get("filesWritten") or [])
        if mirror not in wrote or not (WIKI / mirror).exists():
            out.append({"name": src.name, "kind": "no-mirror",
                        "detail": f"no wiki/sources provenance page - {mirror} missing"})
    return out


def take_lock() -> bool:
    if LOCK.exists() and (time.time() - LOCK.stat().st_mtime) / 60.0 < LOCK_MAX_MIN:
        return False
    LOCK.write_text(str(time.time()), encoding="utf-8")
    return True


def main() -> int:
    selftest = "--selftest" in sys.argv

    if not CACHE.exists():
        print(f"!! wiki ingest watch: {CACHE} not found - is this a LLM Wiki project?")
        return 1

    if selftest:
        print("!! wiki ingest watch: SELFTEST - synthetic finding, no API call, no state written")
        print("   - synthetic-source.md  missing  probe of the alert path (nothing is wrong)")
        return 1

    if not take_lock():
        return 0

    try:
        try:
            pid = active_project_id()
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print(f"!! wiki ingest watch: app API unreachable at {API} ({exc.__class__.__name__}) - "
                  f"cannot verify source delivery; is llm-wiki.exe running?")
            return 1

        state = read_json(STATE, {})
        found = findings()
        now = time.time()
        alerts: list[str] = []
        rescanned: list[str] = []

        keep: dict[str, dict] = {}
        for f in found:
            name = f["name"]
            rec = state.get(name) if state.get(name, {}).get("kind") == f["kind"] else None
            first = rec.get("first_seen") if rec else now
            age_min = (now - first) / 60.0
            rec = {"kind": f["kind"], "detail": f["detail"], "first_seen": first,
                   "rescanned": bool(rec.get("rescanned")) if rec else False}
            if age_min >= RESCAN_AFTER_MIN and not rec["rescanned"] and pid:
                try:
                    api("POST", f"/projects/{pid}/sources/rescan")
                    rec["rescanned"] = True
                    rescanned.append(name)
                except (urllib.error.URLError, OSError, ValueError):
                    pass
            if age_min >= ESCALATE_MIN:
                alerts.append(f"{f['detail']} (first seen {age_min:.0f} min ago"
                              f"{', rescan sent' if rec['rescanned'] else ''})")
            keep[name] = rec
        write_json(STATE, keep)

        if not alerts:
            return 0
        print(f"!! wiki ingest watch: {len(alerts)} source(s) not properly ingested")
        for a in alerts:
            print(f"   - {a}")
        if rescanned:
            print(f"   rescan requested for: {', '.join(rescanned)}")
        print(f"   app running? Source Watch enabled? extension in includeExtensions? "
              f"then: python {ENGINE_DIR / 'wiki_audit.py'} {WIKI}")
        return 1
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
