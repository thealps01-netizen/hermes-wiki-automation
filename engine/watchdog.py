"""LLM Wiki watchdog - one status line every run, plus an alert block on findings.

Checks:
  1. purpose.md / schema.md unchanged vs git HEAD, and not reverted to the app's blank template
  2. canonical project identity in .llm-wiki/project.json
  3. no NEW project id registered for the same path in the app's app-state.json
  4. wiki page count did not drop (data-loss signal), compared to the stored baseline
  5. wiki link/index integrity (no unresolvable body links, no index entry without its file, no
     duplicate stems; a page absent from index.md is NOT a finding, see check_integrity)
  6. link form: no path-form wikilinks ([[folder/stem]] creates no app-graph edge; schema says [[page-slug]])
  7. graph isolation, using the app's own rule (linkCount <= 1 over [[wikilinks]] + `related:`,
     query-type nodes excluded; rule shared with app_graph_isolated.py)
  8. evidence store (raw/evidence): sha256 fixity, passages still in the stored files, schema-1
     manifests, used_by equal to the citing sources, no cited id without a folder, and no decision
     that names a pinned version with 'Evidence: none' (also catches sources written by hand)
  9. evidence staleness: passages pinned to an LLM Wiki / Hermes commit that no longer occur at the
     INSTALLED version (an upgrade may have made the decision they back stale)
 10. harvest reader coverage: every Codex session file on disk is one the harvest reader lists, and
     compressed sessions have a decoder (a file form the reader skips is lost without a trace)
 11. engine copies: a script in the automation data folder that differs from the installed engine
     release is an older copy; running it bypasses gates the installed release enforces

Run: python watchdog.py            (one status line + exit 0 when healthy)
     python watchdog.py --selftest (prints a synthetic alert to prove the alert path)

Output contract (what the Hermes cron job records and the panel's Health tab shows):
  healthy  -> single line "✔ ... 0 bulgu | onay bekleyen: N memory / M skill", exit 0
  findings -> "⚠ ... N bulgu | onay bekleyen: ..." + one line per finding + remediation
              commands, exit 1 (exit 1 is the alert signal, not a crash: the cron launcher maps
              it to a delivered message and `hermes cron doctor` keys on it)
The trailing "onay bekleyen" count is the staged-write queue (~/AppData/Local/hermes/pending):
nonzero means Hermes is holding memory/skill writes for approval — review with
/memory pending and /skills pending in the Hermes chat, or approve them in the
desktop "Onaylar" pane.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
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
STATE = AUDIT_DIR / "state.json"
APP_STATE = wikiconfig.app_state(CFG)
# Kimlik beklentisi AYARDAN gelir; boşsa kimlik kontrolü atlanır (başka PC'de kimlik farklıdır).
CANONICAL_ID = CFG.get("project_id")
TEMPLATE_SIZES = {324, 2078}  # app's blank templates for purpose.md / schema.md
DROP_ALERT = int(_GATES.get("page_drop", 3))  # alert when page count falls by this many or more
ISOLATED_ALERT = int(_GATES.get("isolated_alert", 1))  # alert when this many pages are isolated
PENDING_DIR = wikiconfig.hermes_home(CFG) / "pending"


def pending_line() -> str:
    """Staged-write queue (~/AppData/Local/hermes/pending/<subsystem>/*.json), one line for the
    status line: nonzero means Hermes is holding memory/skill writes for approval."""
    n = {sub: len(list((PENDING_DIR / sub).glob("*.json"))) for sub in ("memory", "skills")}
    return f"onay bekleyen: {n['memory']} memory / {n['skills']} skill"

# Wikilinks written inside inline/fenced code are documentation examples, not links.
_CODE_SPAN = re.compile(r"```.*?```|`[^`\n]*`", re.S)


def strip_code(text: str) -> str:
    return _CODE_SPAN.sub(" ", text)

# Windows consoles default to the system codepage (cp1254 here); the alert text contains
# characters it cannot encode, which killed the scheduled run exactly when it had something to
# report. Force UTF-8 on stdout.
for _stream in ("stdout", "stderr"):
    try:
        getattr(sys, _stream).reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

alerts: list[str] = []


def stamp() -> str:
    """Local time for state.json and alerts.log, in the DD.MM.YYYY HH:MM:SS shape the panel parses.

    Taken from Python, never from `cmd /c echo %DATE% %TIME%`: the console prints the weekday in
    the OEM codepage ("Çar" starts with byte 0x80), a UTF-8 reader fails on it and stdout comes
    back as None, so every Wednesday the page-count check crashed and that day's findings never
    reached alerts.log."""
    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")


def git(*args: str) -> str:
    out = subprocess.run(["git", "-C", str(WIKI), *args], capture_output=True, text=True,
                         encoding="utf-8", errors="ignore")
    return out.stdout if out.returncode == 0 else ""


def check_control_files() -> None:
    for name in ("purpose.md", "schema.md"):
        p = WIKI / name
        if not p.exists():
            alerts.append(f"{name} YOK — dosya silinmiş. Geri al: git -C {WIKI} checkout -- {name}")
            continue
        disk = p.read_text(encoding="utf-8", errors="ignore")
        head = git("show", f"HEAD:{name}")
        if head and disk != head:
            alerts.append(f"{name} git'teki sürümden farklı (disk {len(disk)}B / commit {len(head)}B) — "
                          f"app yeniden yazmış olabilir. Farkı gör: git -C {WIKI} diff -- {name}")
        if p.stat().st_size in TEMPLATE_SIZES:
            alerts.append(f'{name} BOŞ ŞABLON boyutunda ({p.stat().st_size}B) — "Create Project" akışı '
                          f"projenin üzerine yazmış olabilir; kimliği (.llm-wiki/project.json) ve git "
                          f"geçmişini kontrol et, gerekirse: git -C {WIKI} checkout -- {name}")


def check_identity() -> None:
    p = WIKI / ".llm-wiki" / "project.json"
    if not p.exists():
        alerts.append(f".llm-wiki/project.json YOK — app yeni bir proje kimliği üretecek (proje yeniden "
                      f"başlar). Geri al: git -C {WIKI} checkout -- .llm-wiki/project.json")
        return
    try:
        pid = json.loads(p.read_text(encoding="utf-8")).get("id", "")
    except Exception as exc:  # noqa: BLE001
        alerts.append(f".llm-wiki/project.json okunamıyor ({exc}) — dosya bozuk; git'ten geri al: "
                      f"git -C {WIKI} checkout -- .llm-wiki/project.json")
        return
    if CANONICAL_ID and pid != CANONICAL_ID:
        # İKİ AYRI DURUM, TEK ALARM DEĞİL: (a) app bu klasörü YENİ kimlikle yeniden kaydetti (Create
        # Project akışı — içerik şablonla ezilmiş olabilir), (b) app bambaşka bir projeyi açık tutuyor.
        # Ayrımı app'in AKTİF proje kimliği verir; ikisi için yapılacak iş farklıdır.
        active = active_project_id()
        if active and active == pid:
            alerts.append(f"APP BU KLASÖRÜ YENİDEN KAYDETTİ: kimlik {pid} (beklenen {CANONICAL_ID}) ve "
                          f"app bu kimliği aktif proje olarak gösteriyor — Create Project akışı çalışmış "
                          f"olabilir; `git -C {WIKI} diff --stat` ile içeriği doğrula, sonra kimliği "
                          f"`git -C {WIKI} checkout -- .llm-wiki/project.json` ile geri al")
        else:
            alerts.append(f"PROJE KİMLİĞİ DEĞİŞMİŞ: {pid} (beklenen {CANONICAL_ID}) — .llm-wiki/project.json'ı "
                          f"git'ten geri al, sonra app'te projeyi kendi listesinden aç")


def check_page_count() -> None:
    pages = [p for p in (WIKI / "wiki").rglob("*.md") if p.name not in ("index.md", "log.md")]
    n = len(pages)
    baseline = None
    if STATE.exists():
        try:
            baseline = json.loads(STATE.read_text(encoding="utf-8")).get("pages")
        except Exception:  # noqa: BLE001
            baseline = None
    if isinstance(baseline, int) and n < baseline - (DROP_ALERT - 1):
        alerts.append(f"sayfa sayısı düştü: {baseline} → {n} (baseline: state.json) — sayfa silinmiş "
                      f"olabilir. Bak: git -C {WIKI} log --oneline -5 -- wiki")
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"pages": n, "checked": stamp()}, indent=1), encoding="utf-8")


def check_integrity() -> None:
    root = WIKI / "wiki"
    pages = [p for p in root.rglob("*.md") if p.name not in ("index.md", "log.md")]
    stems: dict[str, list[str]] = {}
    for p in pages:
        stems.setdefault(p.stem, []).append(p.relative_to(root).as_posix())
    dups = {k: v for k, v in stems.items() if len(v) > 1}
    if dups:
        alerts.append(f"AYNI İSİMLİ İKİ SAYFA (stem çakışması): {dups} — [[link]] hedefi belirsiz kalır, "
                      f"app graph'ı kenar kuramaz. Birini diğerine birleştir")

    broken: dict[str, int] = {}
    for p in pages:
        body = strip_code(re.sub(r"^---.*?---", "", p.read_text(encoding="utf-8", errors="ignore"),
                                 count=1, flags=re.S))
        for m in re.findall(r"\[\[([^\]]+)\]\]", body):
            t = m.split("|")[0].split("#")[0].strip().removesuffix(".md")
            if t and t.replace("\\", "/").split("/")[-1] not in stems:
                broken[t] = broken.get(t, 0) + 1
    if broken:
        alerts.append(f"var olmayan sayfalara giden linkler: {broken} — hedef sayfayı oluştur ya da "
                      f"linki düzelt (kod bloğu içindeki örnekler sayılmaz)")

    idx = root / "index.md"
    if idx.exists():
        ilinks = {m.split("|")[0].split("#")[0].strip().removesuffix(".md")
                  for m in re.findall(r"\[\[([^\]]+)\]\]",
                                      strip_code(idx.read_text(encoding="utf-8", errors="ignore")))}
        files = {p.relative_to(root).with_suffix("").as_posix() for p in pages}
        stale = [l for l in ilinks if l not in files and l.split("/")[-1] not in stems]
        # No "page missing from the index" check: since LLM Wiki v0.6.12 index.md is not a full
        # catalogue. The app appends each written page to a bounded "## Recently Updated" section
        # capped at 200 entries (src/lib/ingest.ts updateBoundedRecentIndexSection, slice(0, 200)
        # at 48fd970e), because index.md is sent verbatim in every ingest prompt (issue #706).
        # A wiki above 200 pages therefore always has unlisted pages; findability is measured by
        # the graph-isolation check instead.
        if stale:
            alerts.append(f"index'te kayıtlı ama dosyası yok ({len(stale)}): {stale[:5]} — app index'i "
                          f"dosya adından üretir; sayfa adı değişmiş olabilir")


def check_unsplit_ingest() -> None:
    """A page body holding `---FILE: <path>---` blocks is an ingest whose multi-page answer was never
    split: the pages inside were not created, so every link to them dangles and a hub among them
    goes missing. Fix by re-ingesting the source (confirm the pages then exist), never by
    repointing the dangling links. Code spans are ignored, so documented examples do not count."""
    root = WIKI / "wiki"
    marker = re.compile(r"^---FILE:\s*\S+?---\s*$", re.M)
    hits = []
    for p in sorted(root.rglob("*.md")):
        if marker.search(strip_code(p.read_text(encoding="utf-8", errors="ignore"))):
            hits.append(p.relative_to(root).as_posix())
    if hits:
        alerts.append(f"bölünmemiş ingest çıktısı ({len(hits)} sayfa): {hits[:6]} — gövdedeki "
                      f"'---FILE:' bloklarının sayfaları hiç yazılmadı; o kaynağı yeniden ingest et, "
                      f"kırık linkleri başka sayfalara yönlendirme")


def check_graph_isolation() -> None:
    """The app's isolated-page insight (linkCount <= 1, overview/index/log excluded, query pages not
    in the graph). The rule itself lives in app_graph_isolated.isolated_pages(): since LLM Wiki
    v0.6.12 a frontmatter `related:` entry is an edge too, not only a [[wikilink]]."""
    from app_graph_isolated import isolated_pages

    _, _, isolated = isolated_pages(WIKI / "wiki")
    if len(isolated) >= ISOLATED_ALERT:
        shown = ", ".join(f"{i} (deg {d})" for i, d, _, _ in isolated[:5])
        more = f" and {len(isolated) - 5} more" if len(isolated) > 5 else ""
        alerts.append(f"{len(isolated)} sayfa app-graph'ta izole (derece ≤1): {shown}{more} — bu "
                      f"sayfanın `related:` alanına veya gövdesine var olan bir komşu sayfayı ekle "
                      f"(yalnızca stem biçimi: [[sayfa-slug]]); ilişkisi yoksa sayfanın gerekliliğini "
                      f"gözden geçir")


def check_mcp_access() -> None:
    """MCP data tools are gated by the app's own switch. With it off every tool except `status`
    returns "LLM Wiki MCP access is disabled", while MCP clients still report Connected - a silent
    failure mode. Cheap file check: the app persists the same flag as apiConfig.mcpEnabled."""
    if not APP_STATE.exists():
        return
    try:
        cfg = json.loads(APP_STATE.read_text(encoding="utf-8")).get("apiConfig") or {}
    except Exception:  # noqa: BLE001
        return
    if cfg.get("mcpEnabled") is False:
        alerts.append('Uygulamada "Enable MCP access" KAPALI — MCP araçları "MCP access is disabled" '
                      'döndürür, buna rağmen istemciler "Connected" görünür. Aç: Settings → API + MCP '
                      '→ Enable MCP access → Save')


def active_project_id() -> str | None:
    """App'in AKTİF proje kimliği (yerel API). App kapalıysa None — yanlış alarm üretilmez."""
    try:
        import urllib.request
        base = str(CFG.get("api_base") or "http://127.0.0.1:19828").rstrip("/")
        with urllib.request.urlopen(f"{base}/api/v1/projects", timeout=5) as r:
            payload = json.loads(r.read().decode("utf-8", "ignore"))
    except Exception:  # noqa: BLE001  (app kapalı olabilir)
        return None
    return ((payload.get("currentProject") or {}).get("id")) or payload.get("currentProjectId")


def check_active_project() -> None:
    """The app reports its active project id over the local API. Per-project settings (output
    language, source watching / auto-ingest) are keyed by that id, and several stale ids exist for
    the same path, so an active id other than the canonical one silently changes behaviour.

    Kimlik beklentisi (`project_id`) tanımlı değilse karşılaştırılacak bir şey yoktur: kontrol
    atlanır. Başka bir PC'ye taşınan kurulumda kimlik farklı olacağı için yanlış alarm üretilmez."""
    if not CANONICAL_ID:
        return
    try:
        import urllib.request
        with urllib.request.urlopen(f"{str(CFG.get('api_base') or 'http://127.0.0.1:19828').rstrip('/')}"
                                   "/api/v1/projects", timeout=5) as r:
            payload = json.loads(r.read().decode("utf-8", "ignore"))
    except Exception:  # noqa: BLE001  (app closed is normal)
        return
    current = ((payload.get("currentProject") or {}).get("id")) or payload.get("currentProjectId")
    if not current or current == CANONICAL_ID:
        return
    # An id mismatch alone is cosmetic (same folder). What actually changes behaviour is the
    # per-project settings the app reads from the active id: output language and source watching.
    try:
        app = json.loads(APP_STATE.read_text(encoding="utf-8")) if APP_STATE.exists() else {}
    except Exception:  # noqa: BLE001
        app = {}
    lang = (app.get("projectOutputLanguages") or {}).get(current)
    if lang and str(lang).lower() != "english":
        alerts.append(f"app'in AKTİF proje kimliği {current} (beklenen {CANONICAL_ID}) ve bu kimliğin "
                      f"çıktı dili '{lang}' — üretilen sayfalar bu dilde yazılır. App'te projeyi doğru "
                      f"kimlikle aç ya da dil ayarını English yap")
    # Source watching / auto-ingest is a normal feature of this setup (sources are dropped into
    # raw/sources on purpose) and the folder is identical, so an id mismatch alone is not alerted.


def check_backup_freshness() -> None:
    """The mirrors are only as fresh as the last successful push (the post-commit hook does it).
    Compare HEAD against each remote-tracking ref: commits that never reached a mirror are the
    one failure mode a 'backup exists' claim can hide."""
    for remote in wikiconfig.mirror_remotes(CFG, WIKI):
        out = git("rev-list", "--count", f"{remote}/main..HEAD")
        if out.strip().isdigit() and int(out.strip()) > 0:
            alerts.append(f"{out.strip()} commit '{remote}' mirror'una gitmemiş — yedek eksik. Çalıştır: "
                          f"git -C {WIKI} push {remote} HEAD:refs/heads/main")


BACKLOG_HOURS = float(_GATES.get("uncommitted_hours", 26))


def autocommit_last_output() -> str:
    """Last line the auto-commit job wrote; its alerts reach only this file (delivery is local)."""
    job = (CFG.get("jobs") or {}).get("autocommit")
    if not job:
        return "auto-commit görevi ayarlarda yok"
    runs = sorted((wikiconfig.hermes_home(CFG) / "cron" / "output" / str(job)).glob("*.md"))
    if not runs:
        return "auto-commit hiç çalışmamış"
    lines = [l.strip() for l in runs[-1].read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    return f"{runs[-1].stem}: {lines[-1][:220] if lines else '(boş)'}"


def check_commit_backlog() -> None:
    """Wiki changes waiting longer than a day mean the daily auto-commit is not committing, for any
    reason: a refused hook, a lock, a crash. Its own refusals stay in a local file nobody reads."""
    paths = ("wiki", "raw/sources", "raw/evidence", ".llm-wiki/project.json")
    rows = [l for l in git("status", "--porcelain", "-uall", "--", *paths).splitlines() if l.strip()]
    if not rows:
        return
    ages = []
    for row in rows:
        target = WIKI / row[3:].strip().strip('"').split(" -> ")[-1]
        try:
            ages.append(target.stat().st_mtime)
        except OSError:
            continue
    if not ages:
        return
    hours = (datetime.now().timestamp() - min(ages)) / 3600
    if hours >= BACKLOG_HOURS:
        alerts.append(f"{len(rows)} wiki değişikliği {hours:.0f} saattir commit edilmedi — otomatik commit "
                      f"kaydetmiyor. Son otomatik commit çıktısı: {autocommit_last_output()}")


def drift_script() -> Path:
    """The drift checker shipped with this engine release, never an older copy elsewhere."""
    return Path(__file__).resolve().parent / "drift_check.py"


def check_agent_drift() -> None:
    """Agent-setup drift: broken skill references, and
    pinned config values (Hermes model routing / plugin scanning, Codex Headroom routing,
    wiki repo protection). Copies of one skill in several agents are not compared (retired by
    the owner). Runs the shared drift checker and surfaces its report. It describes one
    installation's own agent setup, so it runs only where settings declare `drift.expect`."""
    if not (CFG.get("drift") or {}).get("expect"):
        return
    script = drift_script()
    if not script.exists():
        return
    out = subprocess.run([sys.executable, "-B", str(script)], capture_output=True, text=True,
                         encoding="utf-8", errors="ignore")
    if out.returncode != 0 and "== SONUÇ ==" not in (out.stdout or ""):
        # The checker died before its verdict: say so, with its last error line. "No details"
        # here hid a crash for days (drift_check could not parse config.yaml without PyYAML).
        err = [l.strip() for l in (out.stderr or "").splitlines() if l.strip()]
        alerts.append(f"drift_check ÇÖKTÜ (çıkış {out.returncode}): {err[-1] if err else 'çıktı yok'} — "
                      f"denetleyicinin hatası; ajan kurulumları hakkında bilgi vermez. Ayrıntı: "
                      f"python {script}")
        return
    if out.returncode != 0:
        # Only the "== SONUÇ ==" block lists deviations. Earlier sections print a "->" explanation
        # under each intentional difference, and a plain startswith("-") scan mistakes that line
        # for drift - it reported the KASITLI llm-wiki split as a finding.
        tail = (out.stdout or "").split("== SONUÇ ==")[-1]
        lines = [l.strip().lstrip("-").strip() for l in tail.splitlines() if l.strip().startswith("-")]
        alerts.append("ajan kurulumları farklı: " + ("; ".join(lines[:4]) or "drift_check ayrıntı vermedi")
                      + " — kopyaları hizala ya da farkı kasıtlı olarak kaydet")


def check_evidence_store() -> None:
    """raw/evidence fixity and consistency (evidence_store.verify): stored files still match their
    sha256, passages still occur in them, manifests are schema 1, used_by equals the sources that
    cite a folder, and no source cites an id without a folder. Read-only."""
    import evidence_store
    probs = evidence_store.verify(WIKI / "raw" / "evidence", WIKI / "raw" / "sources")
    for p in sorted((WIKI / "raw" / "sources").glob("*.md")):
        for d in evidence_store.version_claims_without_evidence(p.read_text(encoding="utf-8"), ""):
            probs.append(f"{p.name}: {d} names a pinned version but has 'Evidence: none' "
                         f"(capture the code/doc with evidence_capture.py and cite its id)")
    if probs:
        alerts.append(f"kanıt deposu ({len(probs)} sorun): {probs[:3]} — ayrıntı ve düzeltme: "
                      f"python {ENGINE_DIR / 'evidence_capture.py'} --verify")


def check_evidence_staleness() -> None:
    """Decisions pinned to an LLM Wiki or Hermes version whose evidence passages no longer occur in
    the INSTALLED version: the decision may be stale after an upgrade. Compares stored passages
    with the upstream file at the installed commit; results are cached per installed commit, so a
    day without an upgrade costs nothing. The app not running only skips LLM Wiki for the day."""
    import evidence_store
    cache_p = AUDIT_DIR / "evidence-recheck-cache.json"
    cache = json.loads(cache_p.read_text(encoding="utf-8")) if cache_p.exists() else {}
    inst = evidence_store.installed_commits(CFG, wikiconfig.hermes_home(CFG))
    found = evidence_store.recheck(WIKI / "raw" / "evidence", inst, wikiconfig.hermes_home(CFG), cache)
    cache_p.write_text(json.dumps(cache, indent=1) + "\n", encoding="utf-8")
    if found:
        alerts.append(f"sürüm değişti, {len(found)} kanıt artık kurulu sürümle uyuşmuyor: {found[:2]} — "
                      f"bu kaynaklardaki kararları yeni sürüme göre gözden geçir (kaynağı düzelt, "
                      f"kanıtı yeni commit ile yeniden yakala); liste: python "
                      f"{ENGINE_DIR / 'evidence_capture.py'} --recheck")


def check_harvest_coverage() -> None:
    """Codex stores older rollouts zstd-compressed (`*.jsonl.zst`). The harvest reader once globbed
    `*.jsonl` only and skipped 264 sessions with no error. Compare the reader's own file list with
    the folder so any file form it does not read becomes a finding."""
    import importlib.util
    import wiki_session_harvest as harvest
    root = harvest.agent_roots(CFG)["codex"]
    folders = [root / sub for sub in ("sessions", "archived_sessions") if (root / sub).is_dir()]
    if not folders:
        return
    listed = set(harvest.codex_session_files(root))
    on_disk = {f for folder in folders for f in folder.rglob("rollout-*") if f.is_file()}
    missed = sorted(on_disk - listed)
    if missed:
        kinds = sorted({"".join(f.suffixes) or f.name for f in missed})
        alerts.append(f"harvest {len(missed)} Codex oturumunu okumuyor (dosya türü: {kinds}) — "
                      f"wiki_session_harvest.codex_session_files bu türü de listelemeli")
    compressed = [f for f in listed if f.name.endswith(".zst")]
    if compressed and not zstd_available():
        alerts.append(f"{len(compressed)} sıkıştırılmış Codex oturumu var ama bu Python'da zstd çözücü yok "
                      f"({sys.version.split()[0]}; 3.14+ gerekir) — harvest bu oturumlarda durur")


def zstd_available() -> bool:
    """Python 3.14+ ships compression.zstd. Before 3.14 the parent package is missing too, and
    find_spec on a submodule of a missing package raises instead of returning None."""
    import importlib.util
    try:
        return importlib.util.find_spec("compression.zstd") is not None
    except ModuleNotFoundError:
        return False


def installed_engine_dir() -> Path | None:
    """The engine release the panel installed, as recorded by the installer."""
    loc = wikiconfig.hermes_home(CFG) / "state" / "wiki-automation" / "location.json"
    if not loc.exists():
        return None
    raw = json.loads(loc.read_text(encoding="utf-8")).get("engine_dir")
    return Path(raw) if raw and Path(raw).is_dir() else None


def check_engine_copies() -> None:
    """The automation data folder is also a Git checkout of the engine, and agents were told to run
    scripts from it. When it lags the installed release, its scripts lack gates the release
    enforces: an older wiki_candidates.py applied a candidate the installed one refuses to apply
    from the command line. Any script there that differs from the release is a finding."""
    engine = installed_engine_dir()
    if engine is None or engine.resolve() == AUDIT_DIR.resolve():
        return
    stale = sorted(f.name for f in AUDIT_DIR.glob("*.py")
                   if (engine / f.name).is_file() and f.read_bytes() != (engine / f.name).read_bytes())
    if stale:
        alerts.append(f"veri klasöründe kurulu sürümden farklı {len(stale)} motor betiği: {stale} — "
                      f"eski kopya onay kapılarını atlayabilir; betikleri kurulu sürümden çalıştır: "
                      f"{engine}")


def main() -> int:
    if "--selftest" in sys.argv:
        assert "[[x]]" not in strip_code("`[[x]]`") and "[[y]]" in strip_code("see [[y]] here")
        assert "[[z]]" not in strip_code("```\n[[z]]\n```")
        assert re.search(r"^---FILE:\s*\S+?---\s*$", "x\n---FILE: wiki/a.md---\ny", re.M)
        assert not re.search(r"^---FILE:\s*\S+?---\s*$", strip_code("`---FILE: wiki/a.md---`"), re.M)
        print("[watchdog selftest] uyarı yolu çalışıyor: purpose.md için sahte şablon-boyutu bulgusu "
              "(exit 1 beklenir)")
        return 1
    for fn in (check_control_files, check_identity, check_page_count,
               check_integrity, check_unsplit_ingest, check_graph_isolation, check_mcp_access,
               check_active_project,
               check_backup_freshness,
               check_commit_backlog,
               check_agent_drift,
               check_evidence_store,
               check_evidence_staleness,
               check_harvest_coverage,
               check_engine_copies):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            alerts.append(f"{fn.__name__} ÇÖKTÜ: {exc} — bu denetleyicinin hatası; wiki'de bir şeyin "
                          f"bozuk olduğunu göstermez")
    status = f"{len(alerts)} bulgu | {pending_line()}"
    if alerts:
        try:  # append-only history: LAST-ALERT.txt is cleared when healthy, this is not
            AUDIT_DIR.mkdir(parents=True, exist_ok=True)
            with (AUDIT_DIR / "alerts.log").open("a", encoding="utf-8") as fh:
                fh.write(f"[{stamp()}]\n" + "\n".join(f"- {a}" for a in alerts) + "\n")
        except Exception:  # noqa: BLE001
            pass
        print(f"⚠ Wiki watchdog — {status}\n"
              + "\n".join(f"- {a}" for a in alerts)
              + f"\n\nBulgu geçmişi: {AUDIT_DIR / 'alerts.log'}\n"
                f"Git durumu:   git -C {WIKI} status --short\n"
                f"Tam denetim:  python {ENGINE_DIR / 'wiki_audit.py'}")
        return 1
    print(f"✔ Wiki watchdog — {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
