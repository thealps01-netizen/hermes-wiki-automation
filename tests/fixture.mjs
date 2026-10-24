/**
 * Wiki Automation panel — SHARED test data (render_check.mjs and preview.mjs use the same data).
 *
 * The contracts are locked here:
 *   * `/automation` → the settings file, the root VERIFICATION (`project.ok`) and the script list come
 *     from the BACKEND. (The Task Scheduler flag is gone with 2.1.0: the engine has no Windows task.)
 *   * `/runs` → a run list per job; status and delivery are SEPARATE fields; a deleted job is `live:false`.
 *   * Labels arrive from the backend ALREADY RESOLVED (`status_label`, `delivery_label`) — the panel
 *     prints them as they arrive and never re-translates them. There is one language: English.
 *   * Timestamps are built RELATIVE to today: one run is today's (prints the time only), one is on an
 *     older day (prints `DD.MM HH:mm`). A fixture pinned to a fixed date silently turned the day rule
 *     into a failure the next day.
 */

const pad = value => String(value).padStart(2, '0')

/** A timestamp `offsetDays` back, at `time`, together with the stamp the panel must print for it. */
function dayAt(offsetDays, time) {
  const when = new Date()
  when.setDate(when.getDate() - offsetDays)
  const date = `${when.getFullYear()}-${pad(when.getMonth() + 1)}-${pad(when.getDate())}`
  return {
    at: `${date}T${time}+03:00`,
    stamp: offsetDays === 0 ? time : `${pad(when.getDate())}.${pad(when.getMonth() + 1)} ${time.slice(0, 5)}`
  }
}

const TODAY_NEWEST = dayAt(0, '17:30:28')
const TODAY_SECOND = dayAt(0, '17:00:27')
const TODAY_THIRD = dayAt(0, '16:00:27')
const OLDER_DAY = dayAt(3, '20:33:42')

/** What the run table must print, newest first: three same-day runs then the older day. */
export const RUN_STAMPS = [TODAY_NEWEST.stamp, TODAY_SECOND.stamp, TODAY_THIRD.stamp, OLDER_DAY.stamp]

/** Install state: one script is deliberately MISSING (install.py) → the panel writes "3 of 4".
 *  The job counter that used to be printed here is gone with the install row: the Scheduled jobs
 *  card owns the job facts now (`jobsState()` / `jobsView()` at the end of this file). */
export function automation() {
  return {
    audit_dir: '/srv/audit',
    available: true,
    error: null,
    scripts: {
      'wiki_autocommit.py': true,
      'wiki_ingest_watch.py': true,
      'watchdog.py': true,
      'install.py': false
    },
    settings: {
      settings_path: '/srv/audit/settings.json',
      settings_exists: true,
      project_root: '/srv/wiki',
      project: { ok: true, id: 'auto-id', pages: 419, reason: '' },
      audit_dir: '/srv/audit',
      jobs: { autocommit: 'aaa', ingest_watch: 'bbb', watchdog: 'ccc' }
    }
  }
}

/** The runs of the three jobs. `ccc` (watchdog) has been DELETED: its record is not dropped, it shows
 *  with the "deleted job" pill. The labels arrive from the backend, already resolved. */
export function runs() {
  const run = (when, status, delivery, ms, err) => ({
    at: when.at, status, status_label: status === 'failed' ? 'Failed' : 'Completed',
    delivery, delivery_label: delivery === 'delivered' ? 'Delivered' : 'Silent',
    ms, error_preview: err || null
  })
  return {
    ok: true,
    limit: 3,
    jobs: [
      { role: 'autocommit', job_id: 'aaa', name: 'Wiki Auto-Commit', live: true, runs: [
        run(TODAY_SECOND, 'failed', 'delivered', 1254, 'Script exited with code 1'),
        run(TODAY_THIRD, 'completed', 'suppressed', 200)
      ] },
      { role: 'ingest_watch', job_id: 'bbb', name: 'Wiki Ingest Watch', live: true, runs: [
        run(TODAY_NEWEST, 'completed', 'suppressed', 206)
      ] },
      { role: 'watchdog', job_id: 'ccc', name: 'ccc', live: false, runs: [
        run(OLDER_DAY, 'completed', 'delivered', 1282)
      ] }
    ]
  }
}


/** Job management. Two contracts are locked here:
 *   * `autocommit` is live and healthy, `ingest_watch` has NO live job (the panel must offer Create),
 *     `watchdog` is live but its script is gone — its row must name the missing file and the banner
 *     must tell the user to pause it.
 *   * The state is MUTABLE: the stub flips it on `/jobs/act`, so the panel's re-read after an action
 *     is exercised end to end rather than only its first paint. */
/** An ISO stamp `minutes` from now, in THIS process's local offset — the shape the store writes. */
export function isoIn(minutes, base = Date.now()) {
  const at = new Date(Math.floor((base + minutes * 60000) / 60000) * 60000)
  const off = -at.getTimezoneOffset()
  const sign = off < 0 ? '-' : '+'
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}T${pad(at.getHours())}:`
    + `${pad(at.getMinutes())}:00${sign}${pad(Math.floor(Math.abs(off) / 60))}:${pad(Math.abs(off) % 60)}`
}

/** The store's time zone as `/jobs` and `/jobs/preview` report it. */
export function zone() {
  const off = -new Date().getTimezoneOffset()
  const sign = off < 0 ? '-' : '+'
  return { name: 'Europe/Istanbul', offset: `${sign}${pad(Math.floor(Math.abs(off) / 60))}:${pad(Math.abs(off) % 60)}` }
}

// A five-field cron matcher, enough for the stub's `/jobs/preview` to answer with REAL next runs (the
// preview picture must not show runs that contradict the expression it previews). The backend asks the
// core's own `compute_next_run`; this is only the harness's stand-in for it.
function fieldMatches(field, value, lo, hi) {
  return String(field).split(',').some(part => {
    const [range, stepText] = part.split('/')
    const step = stepText === undefined ? 1 : Number(stepText)
    let a = lo
    let b = hi
    if (range !== '*') {
      const [x, y] = range.split('-').map(Number)
      a = x
      b = y === undefined ? (stepText === undefined ? x : hi) : y
    }
    const v = hi === 7 && value === 0 && b === 7 ? 7 : value
    return v >= a && v <= b && (v - a) % step === 0
  })
}

export function cronValid(expr) {
  const parts = String(expr || '').trim().split(/\s+/)
  return parts.length === 5 && parts.every(p => /^(\*|\d+(-\d+)?)(\/\d+)?(,(\*|\d+(-\d+)?)(\/\d+)?)*$/.test(p))
}

export function nextRuns(expr, count = 3, base = Date.now()) {
  if (!cronValid(expr)) return []
  const [mi, hr, dom, mon, dow] = String(expr).trim().split(/\s+/)
  const out = []
  let at = Math.floor(base / 60000) * 60000 + 60000
  for (let i = 0; i < 400 * 1440 && out.length < count; i += 1, at += 60000) {
    const d = new Date(at)
    if (fieldMatches(mi, d.getMinutes(), 0, 59) && fieldMatches(hr, d.getHours(), 0, 23)
      && fieldMatches(dom, d.getDate(), 1, 31) && fieldMatches(mon, d.getMonth() + 1, 1, 12)
      && fieldMatches(dow, d.getDay(), 0, 7)) {
      out.push(isoIn(0, at))
    }
  }
  return out
}

/** The last slot of `expr` at or before now (searched forward from two days back). */
export function lastRun(expr, base = Date.now()) {
  const past = nextRuns(expr, 3000, base - 2 * 86400000)
  return past.filter(iso => Date.parse(iso) <= base).at(-1) || null
}

/** `iso` moved by `minutes`, in the same local shape. */
export const shift = (iso, minutes) => isoIn(minutes, Date.parse(iso))

/** `/jobs/preview` as the backend answers it: three next runs, or the store's refusal. */
export function previewOf(expr) {
  const text = String(expr || '').trim()
  if (!text) return { ok: false, reason: 'no schedule was given' }
  if (!cronValid(text)) {
    return { ok: false, reason: `the store refused that schedule: Invalid cron expression '${text}'` }
  }
  return { ok: true, schedule: text, kind: 'cron', next_runs: nextRuns(text), timezone: zone() }
}

/** The store's run facts for a schedule, CONSISTENT with it: the next run is the expression's own next
 *  slot, the last run started `lateMin` after the last slot, and a late/missed stamp describes that start. */
function ran(schedule, status, lateMin, flag) {
  const slot = lastRun(schedule, Date.now() - (lateMin + 1) * 60000)
  const started = shift(slot, lateMin)
  return {
    next_run_at: nextRuns(schedule, 1)[0], last_run_at: started, last_status: status,
    dispatch: flag ? { flag, scheduled_at: slot, dispatched_at: started, lateness_seconds: lateMin * 60 } : null
  }
}

export function jobsState() {
  const impl = { autocommit: 'wiki_autocommit.py', ingest_watch: 'wiki_ingest_watch.py',
                 watchdog: 'watchdog.py', session_harvest: 'wiki_session_harvest.py' }
  return {
    autocommit: { role: 'autocommit', name: 'Wiki Auto-Commit', id: 'aaa', live: true,
                  state: 'scheduled', schedule: '0 * * * *', impl: impl.autocommit, impl_ok: true,
                  ...ran('0 * * * *', 'ok', 11, 'late') },
    ingest_watch: { role: 'ingest_watch', name: 'Wiki Ingest Watch', id: null, live: false,
                    state: 'absent', schedule: '*/30 * * * *', impl: impl.ingest_watch, impl_ok: true },
    watchdog: { role: 'watchdog', name: 'Watch Dog', id: 'ccc', live: true,
                state: 'scheduled', schedule: '0 9 * * *', planned_schedule: '0 * * * *',
                schedule_source: 'store', impl: impl.watchdog, impl_ok: false,
                ...ran('0 9 * * *', 'error', 120, 'missed') },
    session_harvest: { role: 'session_harvest', name: 'Wiki Session Harvest', id: 'hhh', live: true,
                       kind: 'agent', state: 'scheduled', schedule: '30 21 * * *',
                       impl: impl.session_harvest, impl_ok: true, ...ran('30 21 * * *', 'ok', 0, null) }
  }
}

/** Positive sandbox capability for mutation regression tests, never a claim about native support.
 *  Read-only tests remove or refuse the explicit capability; production `/jobs` currently refuses it. */
export function jobsView(state) {
  const roles = Object.values(state).map(r => ({
    role: r.role, name: r.name, kind: r.kind || 'script', id: r.id, live: r.live, state: r.state,
    schedule: r.schedule,
    planned_schedule: r.planned_schedule || r.schedule, schedule_source: r.schedule_source || 'config',
    next_run_at: r.live ? (r.next_run_at || null) : null, last_run_at: r.live ? (r.last_run_at || null) : null,
    last_status: r.live ? (r.last_status || null) : null, dispatch: r.live ? (r.dispatch || null) : null,
    deliver: 'ntfy',
    target: { ok: r.impl_ok, root_ok: true, impl_ok: r.impl_ok, impl: r.impl, root: '/srv/wiki',
              reason: '' }
  }))
  return {
    ok: true, available: true, cron: true, mutation_available: true,
    error: null, audit_dir: '/srv/audit', timezone: zone(), roles,
    orphans: roles.filter(r => r.live && r.state !== 'paused' && !r.target.ok).map(r => r.role)
  }
}

/** The validation route: only `/srv/wiki` counts as valid — the panel's "a failure never reads as a
 *  success" behaviour rests on that rule (the test exercises both paths). */
export const VALID_ROOT = '/srv/wiki'

/** Harvest candidates, in the shape the engine's `wiki_candidates.py list --json` / `show --json`
 *  print. One of each kind; the update carries a format problem so the detail shows a failing check. */
export function harvestStatus() {
  return { ok: true, agents: [
    { id: 'hermes', enabled: true, found: true, cursor: TODAY_NEWEST.at },
    { id: 'codex', enabled: true, found: true, cursor: TODAY_SECOND.at },
    { id: 'claude', enabled: false, found: true, cursor: 'none (first run looks back 3 days)' },
    { id: 'antigravity', enabled: true, found: false, cursor: 'none (first run looks back 3 days)' }
  ] }
}

export function candidates() {
  return [
    { ref: '20260928-213958/team-glossary', kind: 'new',
      target: '2026-09-28-team-glossary.md', summary: 'The terms every project page uses' },
    { ref: '20260928-213958/project-wiki-structure', kind: 'update',
      target: '2026-09-20-project-wiki-structure.md', summary: 'The wiki layout after the evidence folder move' },
    { ref: '20260928-213958/old-intake', kind: 'retire',
      target: '2026-08-01-old-intake.md', summary: 'Superseded by the source intake decision' }
  ]
}

export function candidateDetail(ref) {
  const row = candidates().find(c => c.ref === ref) || candidates()[0]
  const update = row.kind === 'update'
  return {
    ok: true, ref: row.ref,
    candidate: { kind: row.kind, target: row.target, summary: row.summary,
                 why: 'decided in the 28.09 session', evidence_ids: update ? [] : ['ev-0928-rules'] },
    diff: [`--- current/${row.target}`, `+++ candidate/${row.target}`, '@@ -0,0 +1,3 @@',
           '+# Team glossary', '+', '+## Decisions'],
    review_digest: update ? 'b'.repeat(64) : 'a'.repeat(64),
    format_problems: update ? ['contains [[wikilinks]]'] : [],
    target_exists: row.kind !== 'new' || Boolean(row.corrects),
    corrects: row.corrects || null,
    evidence_folders: update ? [] : ['ev-0928-rules']
  }
}

export function interruptedEngineStatus(state = 'recovery_required') {
  return { ...engineStatus(state), install_id: '1'.repeat(64), plan_digest: '2'.repeat(64) }
}
export function engineRecoveryPlan() {
  return { ...enginePlan('/srv/original-project'), requested_project_root: '/srv/original-project',
    state: 'recovery_prepared', revision: '5'.repeat(40),
    recovery_review_id: '6'.repeat(64), recovery_review_digest: '7'.repeat(64),
    review_expires_at: Date.now() / 1000 + 300 }
}

export const ENGINE_REVISION = '4'.repeat(40)
export function engineStatus(state = 'installed_paused', current = ENGINE_REVISION) {
  return { ok: true, state, selected_revision: ENGINE_REVISION,
    current_revision: state === 'missing' ? null : current }
}
export function enginePlan(project_root = VALID_ROOT) {
  return { ok: true, state: 'prepared', install_id: '1'.repeat(64), plan_digest: '2'.repeat(64),
    revision: ENGINE_REVISION, project_root, project_id: 'auto-id', engine_dir: '/srv/engine/code',
    audit_dir: '/srv/engine/data', jobs: [{ role: 'session_harvest', name: 'Wiki Session Harvest',
      schedule: '*/15 * * * *' }], activation: 'New jobs remain paused. Resume them separately in Scheduled jobs.' }
}
