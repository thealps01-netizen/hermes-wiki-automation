/**
 * Shared fixture for the Wiki Watchdog tests — render_check.mjs and preview.mjs use the SAME data.
 *
 * Why a file of its own: with a fixture inside each test, one would be updated and the other
 * forgotten; the render test would then prove one contract while the visual preview showed another.
 *
 * The data mirrors the backend's `/jobs` CONTRACT:
 *   - every row is ONE RUN: `status` and `delivery` are SEPARATE axes (both are carried),
 *   - the status/delivery LABELS arrive from the backend (`status_label` · `delivery_label`),
 *   - `date` (YYYY-MM-DD) is `null` when the stamp cannot be parsed (only "All" shows such a run),
 *   - the body: the list carries a preview only (`body`), the full text comes from `/jobs/run` when
 *     `body_len` is larger; `body_source` is "output" | "error" | "none",
 *   - `registry` is the job list and carries DELETED JOBS too (`live: false`, `name: null`),
 *   - a finding arrives CLASSIFIED (`kind` + `tone` + `title` + `what` + `action`) together with the
 *     checker's own line (`raw`) and the values extracted from it (`data`).
 *
 * There is ONE language (English): the backend's labels are English, and the panel resolves its own
 * text from the application language, so the fixture has no locale parameter at all.
 */
import { fileURLToPath } from 'node:url'

// The hermes home is derived from THIS file's location, never written out for one machine. Inside a
// browser bundle (`import.meta.url` is empty there) the derivation is not available — the preview
// shows no path from this field, so a relative fallback is enough and the bundle still builds.
const HERMES_HOME = (() => {
  try {
    return fileURLToPath(new URL('../../../', import.meta.url)).replace(/\\/g, '/')
  } catch (e) {
    return './'
  }
})()

const isoDay = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

export const TODAY_ISO = isoDay(new Date())
export const OLD_DATE = new Date()
OLD_DATE.setDate(OLD_DATE.getDate() - 20)
export const OLD_ISO = isoDay(OLD_DATE)

const stamp = (iso, hhmmss) => `${iso}T${hhmmss}.123456+03:00`
export const TODAY_AT = stamp(TODAY_ISO, '10:22:56')
export const SECOND_AT = stamp(TODAY_ISO, '09:15:00')
export const OLD_AT = stamp(OLD_ISO, '07:02:58')

// A cycle is two real instants the scheduler reports (last run · next run). Derived from the job's own
// last run so the freshness ring measures a cycle that exists, rather than parsing a cadence string.
const cycleOf = (lastIso, minutes) =>
  new Date(Date.parse(lastIso) + minutes * 60000).toISOString()

/** The silent run's body IS the full body (the panel makes no extra request). Its length is
 *  COMPUTED from the text: a hand-written number one character off would make the panel fetch the
 *  full body for nothing and the render test would (rightly) go red. */
const SILENT_BODY = 'silent (empty output)'

/** ONE case per finding class the backend can emit (`_WD_KINDS`), as the payload carries it: the
 *  class, its extracted `data`, the checker's own line (`raw`) and `en` — the English sentence the
 *  panel must render for that class and that data. The render test reads this table, so the fixture
 *  and the rendered panel can never disagree about what a class is called.
 *
 *  `raw` is DATA (the external checker writes Turkish): it stays beside the English sentence and is
 *  never rewritten. The last case is a REAL `alerts.log` line that matches no pattern: it gets the
 *  neutral label and its raw line, and NO invented translation. */
export const FINDING_CASES = [
  {
    kind: 'not_indexed', n: 2, tone: 'neutral', title: 'Page outside the index (retired check)', retired: true,
    what: '2 page(s) were reported outside index.md by a check the engine no longer runs: LLM Wiki v0.6.12 '
      + 'keeps index.md as a bounded Recently Updated list of 200 entries.',
    action: 'Nothing to do: this line is history from before the check was retired.',
    en: 'Retired check: 2 pages were reported outside index.md. The engine no longer runs this check, since '
      + 'LLM Wiki v0.6.12 keeps index.md as a bounded list of the 200 most recently updated pages.',
    raw: "index'te hiç görünmeyen sayfa (2): ['dead-cells', 'overview'] — app'te projeyi açıp yeniden tarat",
    data: { n: '2' }
  },
  {
    kind: 'wikilink', n: 3, tone: 'warn', title: 'Path-form link',
    what: '3 link(s) are written as paths ([[a/b]]); the app graph cannot see them as edges.',
    action: 'Rewrite them as [[page-name]].',
    en: '3 links are written as a path ([[a/b]]), so the app graph draws no edge — write it as [[page-name]].',
    raw: "path-form wikilinks (3): {'concepts/abap-bot-fleet': 2, 'entities/abap-bot-fleet': 1} — "
      + "[[klasor/sayfa]] yerine [[sayfa-adı]] yaz",
    data: { n: '3' }
  },
  {
    kind: 'dup', n: null, tone: 'bad', title: 'Two pages with one name',
    what: 'Two pages share the same name; [[link]] targets become ambiguous and the app graph cannot draw an edge.',
    action: 'Merge one into the other; keep a single page.',
    en: 'Two pages share one name — the [[link]] target is ambiguous and the app graph draws no edge.',
    raw: "AYNI İSİMLİ İKİ SAYFA (stem çakışması): {'abap-bot-fleet': "
      + "['concepts/abap-bot-fleet.md', 'entities/abap-bot-fleet.md']} — [[link]] hedefi belirsiz kalır",
    data: {}
  },
  {
    kind: 'drift', n: null, tone: 'warn', title: 'Agent setup drift',
    what: 'The Hermes, Codex and Claude setups differ (skill content or plugin version).',
    action: 'Sync the difference or note that it is intentional.',
    en: 'The Hermes, Codex and Claude setups differ — sync the difference or record it as intentional.',
    raw: 'ajan kurulumları farklı: bileşen eksik: ponytail -> codex; codex: ponytail kurulu ama hiç '
      + 'hook kayıtlı değil — kopyaları hizala ya da farkı kasıtlı olarak kaydet',
    data: {}
  },
  {
    kind: 'mirror', n: 3, tone: 'warn', title: 'Backup mirror behind',
    what: "The local repo is 3 commit(s) ahead of the 'onedrive' mirror; the backup is stale.",
    action: 'Run the backup (git command below).',
    en: "3 commits never reached the 'onedrive' mirror — run the backup.",
    raw: "3 commit 'onedrive' mirror'una gitmemiş — yedeği çalıştır",
    data: { n: '3', remote: 'onedrive' }
  },
  {
    kind: 'identity', n: null, tone: 'bad', title: 'Project id mismatch',
    what: "The app's active project id differs from the canonical id; per-project settings are read from the active one.",
    action: "Open the project from the app's own list; clean the stale id.",
    en: "The app's ACTIVE project id changed: abc123 (expected def456).",
    raw: "app'in AKTİF proje kimliği abc123 (beklenen def456) — App'te projeyi aç, eski kimliği temizle",
    data: { id: 'abc123', expected: 'def456' }
  },
  {
    kind: 'unresolvable', n: null, tone: 'bad', title: 'Unresolvable link',
    what: 'A body link points at a target that does not exist in the files.',
    action: 'Create the target page or fix the link.',
    en: 'A body link points at a page that does not exist — create the target page or fix the link.',
    raw: "var olmayan sayfalara giden linkler: {'dead-cells': 1, 'incremental-source-update': 1} — "
      + 'hedef sayfayı oluştur ya da linki düzelt (kod bloğu içindeki örnekler sayılmaz)',
    data: {}
  },
  {
    kind: 'isolated', n: 24, tone: 'warn', title: 'Page alone in the graph',
    what: '24 page(s) have no links at all (graph degree 0); they sit alone in the app graph.',
    action: 'Link those pages, or archive them if unneeded.',
    en: '24 pages have no links at all (graph degree ≤ 1), so nothing in the app graph points to them.',
    raw: "24 sayfa app-graph'ta izole (derece ≤1): bot-chat-growth (deg 1), cache-safe-prompt-section "
      + "(deg 1) and 22 more — bu sayfalara hub'dan veya komşu sayfadan stem-form [[link]] ekle",
    data: { n: '24' }
  },
  {
    kind: 'pages_down', n: 204, tone: 'bad', title: 'Page count dropped',
    what: 'Page count dropped 204 → 200; a page may have been deleted.',
    action: 'Check the deleted pages (baseline: state.json).',
    en: 'Page count dropped: 204 → 200.',
    raw: 'sayfa sayısı düştü: 204 → 200 (baseline: state.json) — sayfa silinmiş olabilir. '
      + 'Bak: git -C C:/wiki log --oneline -5 -- wiki',
    data: { before: '204', after: '200' }
  },
  {
    kind: 'crash', n: null, tone: 'bad', title: 'Checker crashed',
    what: 'The check_links checker errored: detail line',
    action: 'A checker bug — it does not mean the wiki is broken; fix the code.',
    en: "The check_links checker crashed: KeyError('/wiki/x').",
    raw: "check_links ÇÖKTÜ: KeyError('/wiki/x') — bu denetleyicinin hatası",
    data: { fn: 'check_links', error: "KeyError('/wiki/x')" }
  },
  {
    kind: 'evidence_store', n: 2, tone: 'bad', title: 'Evidence store problem',
    what: '2 problem(s) in the evidence store: a stored file no longer matches its sha256, a passage is gone, '
      + 'a manifest or used_by list is off, or a source names a pinned version with no evidence.',
    action: 'Run evidence_capture.py --verify in the engine folder for the detail and the fix.',
    en: '2 problems in the evidence store — run evidence_capture.py --verify in the engine folder.',
    raw: "kanıt deposu (2 sorun): ['a.md: sha256 mismatch'] — ayrıntı ve düzeltme: "
      + 'python C:/audit/evidence_capture.py --verify',
    data: { n: '2' }
  },
  {
    kind: 'evidence_stale', n: 3, tone: 'warn', title: 'Evidence out of date',
    what: '3 evidence passage(s) no longer occur in the installed LLM Wiki or Hermes version; the decisions '
      + 'pinned to them may be stale after an upgrade.',
    action: 'Run evidence_capture.py --recheck in the engine folder, review those decisions and recapture the '
      + 'evidence at the new commit.',
    en: '3 evidence passages no longer match the installed LLM Wiki or Hermes version — run '
      + 'evidence_capture.py --recheck.',
    raw: "sürüm değişti, 3 kanıt artık kurulu sürümle uyuşmuyor: ['ev-1', 'ev-2'] — liste: "
      + 'python C:/audit/evidence_capture.py --recheck',
    data: { n: '3' }
  },
  {
    kind: "control_missing", n: null, tone: "bad", title: "Control file missing",
    what: "purpose.md is missing from the wiki folder; the file was deleted.",
    action: "Restore the file from git (the command is in the line as written).",
    en: "purpose.md is missing from the wiki folder — restore it from git.",
    raw: "purpose.md YOK — dosya silinmiş. Geri al: git -C C:/wiki checkout -- purpose.md",
    data: { name: "purpose.md" }
  },
  {
    kind: "control_changed", n: null, tone: "warn", title: "Control file changed",
    what: "schema.md differs from its version in git; the app may have rewritten it.",
    action: "Compare it with git diff in the wiki folder and keep the right version.",
    en: "schema.md differs from its version in git — the app may have rewritten it; compare the two.",
    raw: "schema.md git'teki sürümden farklı (disk 2410B / commit 2078B) — app yeniden yazmış olabilir. Farkı gör: git -C C:/wiki diff -- schema.md",
    data: { name: "schema.md" }
  },
  {
    kind: "control_template", n: null, tone: "bad", title: "Control file reset to a template",
    what: "purpose.md has the size of the app's blank template; the Create Project flow may have written over the project.",
    action: "Check .llm-wiki/project.json and the git history; restore the file from git if needed.",
    en: "purpose.md has the size of the app's blank template — the Create Project flow may have written over the project.",
    raw: "purpose.md BOŞ ŞABLON boyutunda (324B) — \"Create Project\" akışı projenin üzerine yazmış olabilir; kimliği (.llm-wiki/project.json) ve git geçmişini kontrol et",
    data: { name: "purpose.md" }
  },
  {
    kind: "project_file_missing", n: null, tone: "bad", title: "Project file missing",
    what: ".llm-wiki/project.json is missing; the app will make a new project id and the project starts over.",
    action: "Restore .llm-wiki/project.json from git.",
    en: ".llm-wiki/project.json is missing — the app will start the project over with a new id; restore the file from git.",
    raw: ".llm-wiki/project.json YOK — app yeni bir proje kimliği üretecek (proje yeniden başlar). Geri al: git -C C:/wiki checkout -- .llm-wiki/project.json",
    data: {}
  },
  {
    kind: "project_file_unreadable", n: null, tone: "bad", title: "Project file unreadable",
    what: ".llm-wiki/project.json cannot be read; the file is damaged.",
    action: "Restore .llm-wiki/project.json from git.",
    en: ".llm-wiki/project.json cannot be read — the file is damaged; restore it from git.",
    raw: ".llm-wiki/project.json okunamıyor (Expecting value: line 1 column 1 (char 0)) — dosya bozuk; git'ten geri al",
    data: {}
  },
  {
    kind: "project_reregistered", n: null, tone: "bad", title: "Folder registered again",
    what: "The app registered this folder again under a new project id and shows that id as the active project.",
    action: "Check the content with git diff --stat, then restore .llm-wiki/project.json from git.",
    en: "The app registered this folder again: id 7f0a2c (expected 9c1b4d) — check the content, then restore .llm-wiki/project.json from git.",
    raw: "APP BU KLASÖRÜ YENİDEN KAYDETTİ: kimlik 7f0a2c (beklenen 9c1b4d) ve app bu kimliği aktif proje olarak gösteriyor — Create Project akışı çalışmış olabilir",
    data: { id: "7f0a2c", expected: "9c1b4d" }
  },
  {
    kind: "index_stale", n: 2, tone: "warn", title: "Index lists a missing page",
    what: "2 page(s) are listed in index.md but have no file; a page may have been renamed.",
    action: "Check whether those pages were renamed; the app builds index.md from file names.",
    en: "2 pages are listed in index.md but have no file — the page may have been renamed.",
    raw: "index'te kayıtlı ama dosyası yok (2): ['concepts/incremental-source-update'] — app index'i dosya adından üretir; sayfa adı değişmiş olabilir",
    data: { n: "2" }
  },
  {
    kind: "unsplit_ingest", n: 4, tone: "bad", title: "Unsplit ingest output",
    what: "4 page(s) hold an unsplit ingest output: the pages in their ---FILE: blocks were never written.",
    action: "Ingest that source again; do not point the broken links at other pages.",
    en: "4 pages hold an unsplit ingest output — the pages in its ---FILE: blocks were never written; ingest that source again.",
    raw: "bölünmemiş ingest çıktısı (4 sayfa): ['sources/hermes-release.md'] — gövdedeki '---FILE:' bloklarının sayfaları hiç yazılmadı; kaynağı yeniden ingest et",
    data: { n: "4" }
  },
  {
    kind: "mcp_off", n: null, tone: "warn", title: "MCP access is off",
    what: "\"Enable MCP access\" is off in the app; MCP tools answer \"MCP access is disabled\" although clients show Connected.",
    action: "Turn it on: Settings → API + MCP → Enable MCP access → Save.",
    en: "\"Enable MCP access\" is off in the app — MCP tools refuse although clients show Connected; turn it on in Settings → API + MCP.",
    raw: "Uygulamada \"Enable MCP access\" KAPALI — MCP araçları \"MCP access is disabled\" döndürür; Settings → API + MCP",
    data: {}
  },
  {
    kind: "commit_backlog", n: 12, tone: "warn", title: "Changes not committed",
    what: "12 wiki change(s) have not been committed for 30 hours; the automatic commit is not saving them.",
    action: "Check the Saving job (wiki auto-commit) and its last output.",
    en: "12 wiki changes have not been committed for 30 hours — the automatic commit is not saving.",
    raw: "12 wiki değişikliği 30 saattir commit edilmedi — otomatik commit kaydetmiyor. Son otomatik commit çıktısı: nothing to commit",
    data: { n: "12", hours: "30" }
  },
  {
    kind: "drift_crash", n: null, tone: "bad", title: "Setup check crashed",
    what: "drift_check crashed; it says nothing about the agent setups.",
    action: "A checker bug, not a setup difference; run drift_check.py for the detail.",
    en: "The agent-setup check crashed — a checker bug; it says nothing about the setups.",
    raw: "drift_check ÇÖKTÜ (çıkış 1): ModuleNotFoundError: No module named 'tomllib' — denetleyicinin hatası; ajan kurulumları hakkında bilgi vermez",
    data: {}
  },
  {
    kind: "harvest_unread", n: 3, tone: "warn", title: "Codex sessions not read",
    what: "The harvest does not read 3 Codex session(s) of a file type it does not list.",
    action: "Add that file type to wiki_session_harvest.codex_session_files.",
    en: "The harvest does not read 3 Codex sessions — their file type is not in its list.",
    raw: "harvest 3 Codex oturumunu okumuyor (dosya türü: .jsonl.zst) — wiki_session_harvest.codex_session_files bu türü de listelemeli",
    data: { n: "3" }
  },
  {
    kind: "harvest_zstd", n: 5, tone: "warn", title: "Compressed sessions unreadable",
    what: "5 compressed Codex session(s) exist, but this Python has no zstd decoder (3.14 or later is needed).",
    action: "Run the harvest on Python 3.14 or later; until then it stops on these sessions.",
    en: "5 compressed Codex sessions cannot be read: this Python has no zstd decoder (3.14 or later is needed).",
    raw: "5 sıkıştırılmış Codex oturumu var ama bu Python'da zstd çözücü yok (3.11.9; 3.14+ gerekir) — harvest bu oturumlarda durur",
    data: { n: "5" }
  },
  {
    kind: "engine_copies", n: 2, tone: "warn", title: "Old engine copies",
    what: "2 engine script(s) in the data folder differ from the installed version; an old copy can bypass the approval gates.",
    action: "Run the scripts from the installed engine folder, not from the data folder.",
    en: "2 engine scripts in the data folder differ from the installed version — an old copy can bypass the approval gates.",
    raw: "veri klasöründe kurulu sürümden farklı 2 motor betiği: ['watchdog.py', 'drift_check.py'] — eski kopya onay kapılarını atlayabilir",
    data: { n: "2" }
  },
  {
    kind: 'other', n: null, tone: 'warn', title: 'Other finding',
    what: 'A watchdog finding that matches no known pattern; the detail is below.',
    action: 'Act on the message in the detail line.',
    en: 'Unrecognized finding — no pattern matched; the checker line is shown as written.',
    raw: "denetim satırı tanınmadı (7): ['x'] — bu biçim hiçbir kurala uymuyor",
    data: {}
  }
]

// The trend: 24 hourly buckets over the 7-day window plus the window BEFORE it, built from the same
// runs the payload carries (the backend computes it the same way). The previous window is what a delta
// compares against, so it is stated here rather than derived from the current window.
const BUCKET_H = 24
const WINDOW_H = 24 * 7

function trendFrom(runs) {
  const now = Date.now() / 1000
  const buckets = []
  for (let i = 0; i < 24; i += 1) {
    buckets.push({
      iso: new Date((now - (24 - i) * BUCKET_H * 3600) * 1000).toISOString(),
      runs: 0, failed: 0, silent: 0, delivered: 0
    })
  }
  const prev = { runs: 3, failed: 0, silent: 2, delivered: 1 }
  const perJob = {}
  const slotOf = ts => {
    const age = (now - ts) / 3600
    return Math.min(23, Math.max(0, 23 - Math.floor(age / BUCKET_H)))
  }
  runs.forEach(run => {
    const ts = run.at ? Date.parse(run.at) / 1000 : null
    if (ts === null || (now - ts) / 3600 >= WINDOW_H) return
    const failed = run.status === 'failed' ? 1 : 0
    const silent = run.delivery === 'suppressed' ? 1 : 0
    const delivered = run.delivery === 'delivered' ? 1 : 0
    for (const slots of [buckets, (perJob[run.job_id] = perJob[run.job_id] || buckets.map(b => ({ ...b, runs: 0, failed: 0, silent: 0, delivered: 0 })))]) {
      const slot = slots[slotOf(ts)]
      slot.runs += 1
      slot.failed += failed
      slot.silent += silent
      slot.delivered += delivered
    }
  })
  return { bucket_hours: BUCKET_H, buckets, prev, prev_basis: `${WINDOW_H}h`, per_job: perJob }
}

// Five runs covering five distinct states: the alarm (failed + delivered, with findings) · a silent
// normal run · a run of a deleted job with no body · a running run (the absence of both status and
// delivery) · and one whose stamp cannot be parsed. The ORDER is the backend's: newest first, and a
// row without a date last (SQLite `order by claimed_at desc` puts NULLs last).
const RUN_DEFS = [
  {
    id: 'run-watchdog-1', job_id: '23b87c7253d4', job_name: 'Watch Dog', job_live: true,
    at: TODAY_AT, scheduled_at: stamp(TODAY_ISO, '08:34:00'), finished_at: stamp(TODAY_ISO, '10:22:58'),
    status: 'failed', delivery: 'delivered', duration_ms: 1500, lateness_s: 6499.2,
    silent: false, body: '⚠ Wiki watchdog — 2 finding(s) | awaiting approval: 0 memory / 0 skill',
    body_len: 2400, body_source: 'output',
    findings: FINDING_CASES, findings_count: FINDING_CASES.length
  },
  {
    id: 'run-fleet-1', job_id: '2821e5b08d06', job_name: 'Fleet Watch', job_live: true,
    at: SECOND_AT, scheduled_at: stamp(TODAY_ISO, '09:14:00'), finished_at: stamp(TODAY_ISO, '09:15:00'),
    status: 'completed', delivery: 'suppressed', duration_ms: 285, lateness_s: 60.0,
    silent: true, body: SILENT_BODY, body_len: SILENT_BODY.length, body_source: 'output',
    findings: [], findings_count: 0
  },
  {
    id: 'run-fleet-2', job_id: '2821e5b08d06', job_name: 'Fleet Watch', job_live: true,
    at: stamp(TODAY_ISO, '09:04:00'), scheduled_at: stamp(TODAY_ISO, '09:03:00'),
    finished_at: stamp(TODAY_ISO, '09:04:01'),
    status: 'completed', delivery: 'suppressed', duration_ms: 900, lateness_s: 60.0,
    silent: true, body: SILENT_BODY, body_len: SILENT_BODY.length, body_source: 'output',
    findings: [], findings_count: 0
  },
  {
    id: 'run-gone-1', job_id: '2e8b8d50566d', job_name: null, job_live: false,
    at: OLD_AT, scheduled_at: stamp(OLD_ISO, '06:00:00'), finished_at: null,
    status: 'completed', delivery: 'suppressed', duration_ms: null, lateness_s: null,
    silent: true, body: '', body_len: 0, body_source: 'none',
    findings: [], findings_count: 0
  },
  {
    id: 'run-running-1', job_id: '5d27193a92a0', job_name: 'Wiki Ingest Watch', job_live: true,
    at: null, scheduled_at: null, finished_at: null,
    status: 'running', delivery: 'none', duration_ms: null, lateness_s: null,
    silent: false, body: '', body_len: 0, body_source: 'none',
    findings: [], findings_count: 0
  }
]

const REGISTRY = [
  {
    id: '2821e5b08d06', name: 'Fleet Watch', live: true, schedule: 'every 10m',
    script: 'fleet_watch.py', mode: 'script', deliver: 'bot-chat:sap_orkestrator', state: 'scheduled',
    enabled: true, last_status: 'ok', last_error: null, last_run_at: TODAY_AT,
    next_run_at: cycleOf(TODAY_AT, 60), runs: 2, failed: 0, silent: 2, delivered: 0, findings: 0,
    last_at: TODAY_AT
  },
  {
    id: '23b87c7253d4', name: 'Watch Dog', live: true, schedule: 'every day at 9am',
    script: 'palwiki_watchdog.py', mode: 'script', deliver: 'ntfy', state: 'scheduled',
    enabled: true, last_status: 'ok', last_error: null, last_run_at: TODAY_AT,
    next_run_at: cycleOf(TODAY_AT, 30), runs: 1, failed: 1, silent: 0, delivered: 1, findings: 2,
    last_at: TODAY_AT
  },
  {
    id: '5d27193a92a0', name: 'Wiki Ingest Watch', live: true, schedule: 'every 30m',
    script: 'palwiki_ingest_watch.py', mode: 'script', deliver: 'ntfy', state: 'scheduled',
    enabled: true, last_status: 'ok', last_error: null, last_run_at: null,
    next_run_at: null, runs: 1, failed: 0, silent: 0, delivered: 0, findings: 0, last_at: null
  },
  {
    id: '2e8b8d50566d', name: null, live: false, schedule: null, script: null, mode: null,
    deliver: null, state: null, enabled: false, last_status: null, last_error: null,
    last_run_at: null, next_run_at: null, runs: 1, failed: 0, silent: 1, delivered: 0,
    findings: 0, last_at: OLD_AT
  }
]

const LABELS = {
  completed: 'completed',
  failed: 'failed',
  running: 'running',
  delivered: 'delivered',
  suppressed: 'silent (no output)',
  none: 'no delivery record',
  output: 'run output',
  error: 'recorded error',
  'none-src': 'no body record (the output file was never written or has been removed)'
}

/** Builds the payload the way the backend does: labels from the message table, `date`, registry. */
export function fixture() {
  return {
    generatedAt: `${TODAY_ISO}T10:30:00+03:00`,
    window: '7d',
    since: null,
    truncated: false,
    cap: 3000,
    cron_dir: `${HERMES_HOME}cron`,
    registry: REGISTRY,
    totals: {
      runs: RUN_DEFS.length, failed: 1, silent: 3, delivered: 1, findings: 1,
      jobs: REGISTRY.length, deleted_jobs: 1
    },
    trend: trendFrom(RUN_DEFS),
    runs: RUN_DEFS.map(run => ({
      ...run,
      date: run.at ? run.at.slice(0, 10) : null,
      // The backend sends `at_ts` (the claimed instant as a number) and the panel positions every
      // timeline bar from it: a fixture that left it null silently pushed the panel into its empty
      // branch, so the timeline lock had nothing to measure.
      at_ts: run.at ? Date.parse(run.at) / 1000 : null,
      status_label: LABELS[run.status],
      delivery_label: LABELS[run.delivery],
      body_label: LABELS[run.body_source === 'none' ? 'none-src' : run.body_source],
      findings: run.findings.map(f => ({
        kind: f.kind, n: f.n, tone: f.tone,
        title: f.title, what: f.what, action: f.action, detail: f.detail,
        raw: f.raw, data: f.data
      }))
    }))
  }
}
