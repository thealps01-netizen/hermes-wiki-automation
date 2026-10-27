/**
 * Metro (2.5.0) — ONE fixture per contract state, shared by every gate that renders the panel.
 *
 * `render_metro.mjs` (jsdom behaviour), `preview.mjs` (one static HTML per state) and the live boot the
 * Electron gates run (`live-boot.mjs`, loaded by `shot.cjs` / `scroll_check.cjs`) all read this file,
 * so the state the behaviour gate proves is the state the measured render paints.
 *
 * A state is a WORLD (what every endpoint the panel already calls answers) plus what the screen must
 * then say: the `.wa-metro-bar[data-alert]` priority key, the bar's `data-tone`, the `data-state` of
 * each station and branch line, and which `.wa-metro-detail[data-for]` is open after the state's clicks.
 * The contract is `Docs/metro-contract.md`; nothing here invents a route the panel does not call.
 */
import { automation, candidateDetail, candidates, isoIn, lastRun, nextRuns, previewOf, runs, shift, zone,
  engineStatus } from './fixture.mjs'
import { fixture as healthFixture, FINDING_CASES } from './fixture-health.mjs'

/** The alert priority, first match wins (contract § "Alert priority"). */
export const PRIORITY = ['read-failed', 'engine', 'harvest-failed', 'job-broken', 'drafts', 'problems', 'paused',
  'running', 'good']

/** The Session Harvest adapters in `/harvest/status` order, with the words the line must carry. */
export const ADAPTERS = [
  { id: 'hermes', name: 'Hermes' },
  { id: 'codex', name: 'Codex' },
  { id: 'claude', name: 'Claude Code' },
  { id: 'antigravity', name: 'Antigravity' }
]
export const STATIONS = [
  { id: 'harvest', name: 'Harvest' },
  { id: 'review', name: 'Your review' },
  { id: 'wiki', name: 'Wiki' }
]
export const GOOD_SERVICE = 'Good service on the whole line'
export const COMPOSER_MISS = 'The chat box did not open. Start a new chat, then press again.'
export const ASK_HERMES = 'Ask Hermes to fix these'

/** Backend wording each failure carries; the panel must keep it (a failed read keeps its error). */
export const ERRORS = {
  '/jobs': 'cron store unreadable: jobs.json is locked (EBUSY)',
  '/candidates': 'wiki_candidates.py list failed: exit 2',
  '/harvest/status': 'harvest config unreadable: agents.toml line 4',
  '/automation': 'settings.json could not be parsed (line 7)',
  '/health/jobs': 'executions.db is busy (database is locked)',
  '/health/watchdog': 'alerts.log could not be read (permission denied)',
  '/engine/status': 'engine status read failed: install.json is not valid JSON',
  harvest: 'harvest run failed: the model refused the request (429 quota exceeded)',
  sources: 'ingest watch failed: raw/sources is not readable (permission denied)'
}
export const APPROVAL_REFUSAL = "new or changed decisions name a pinned version but have 'Evidence: none'. "
  + "A version number or commit in a decision's text makes the claim depend on that release, so it needs a retained "
  + "copy (an evidence request) that a later upgrade can be re-checked against; when the number is only release "
  + "history, leave it out of the decision's text: **8. The user can see and manage how Asterisk behaves from a settings page"
export const EVIDENCE_COMMIT = 'd923a5eb487a17c0a68801bba9ef0f56c81040a8'
export const EVIDENCE_REQUEST = { id: 'hermes-plugin-pin-handling-d923a5eb',
  supports: 'Automatic plugin updates never apply to a pinned plugin; a pinned plugin changes only through a reinstall with an explicit --ref.',
  github: [`NousResearch/hermes-agent@${EVIDENCE_COMMIT}:hermes_cli/plugins_cadence.py`,
    `NousResearch/hermes-agent@${EVIDENCE_COMMIT}:hermes_cli/plugins_cmd_install.py`],
  passages: ['Pinned/manual/drift/pip are never auto-applied', 'is pinned. Reinstall it with an explicit'] }
export const UNREADABLE_DRAFT = 'the candidates could not be read: exit 1: !! refused: New source target already exists'
export const OLDER_ENGINE = '3'.repeat(40)

const IDS = { autocommit: 'job-ac', ingest_watch: 'job-iw', watchdog: 'job-wd', session_harvest: 'job-sh' }
const NAMES = { autocommit: 'Wiki Auto-Commit', ingest_watch: 'Wiki Ingest Watch', watchdog: 'Watch Dog',
  session_harvest: 'Wiki Session Harvest' }
const SCHEDULES = { autocommit: '0 * * * *', ingest_watch: '*/30 * * * *', watchdog: '0 9 * * *',
  session_harvest: '30 21 * * *' }
const IMPL = { autocommit: 'wiki_autocommit.py', ingest_watch: 'wiki_ingest_watch.py', watchdog: 'watchdog.py',
  session_harvest: 'wiki_session_harvest.py' }
const PROBLEM_KINDS = ['dup', 'wikilink', 'mirror']
export const PROBLEMS = FINDING_CASES.filter(f => PROBLEM_KINDS.includes(f.kind))

const pad = n => String(n).padStart(2, '0')
const healthStamp = iso => {
  const d = new Date(Date.parse(iso))
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:`
    + `${pad(d.getSeconds())}.000000${iso.slice(-6)}`
}
const watchdogStamp = iso => {
  const d = new Date(Date.parse(iso))
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}:`
    + `${pad(d.getSeconds())}`
}

const missingIds = c => (c.missingFolder === true ? ['claude'] : [].concat(c.missingFolder || []))
const unreadIds = c => [].concat(c.unreadable || [])
export const UNREAD_REPORT = 'UNREADABLE (ValueError: transcript_full.jsonl line 2 is not JSON)'

/**
 * The engine's `--last-run` answer as `/harvest/status` carries it. The newest run belongs to the
 * harvest's newest cron run (`run-job-sh`) and is completed unless `notCommitted`; an engine older
 * than `--last-run` (`oldEngine`) reports `last_run_supported: false` and stops every line while a
 * folder is missing.
 */
function lastRunOf(c) {
  if (c.oldEngine) return { last_run_supported: false, last_run: null }
  const agents = Object.fromEntries(ADAPTERS.map(a => [a.id, missingIds(c).includes(a.id) ? 'not found (fixture)'
    : unreadIds(c).includes(a.id) ? UNREAD_REPORT : '2 conversation(s)']))
  return { last_run_supported: true, last_run: { run: '20261018-213042-590db30b7052', execution_id: `run-${IDS.session_harvest}`,
    created: isoIn(-20), committed: !c.notCommitted, status: c.notCommitted ? null : 'drafted', agents,
    stop_reason: c.stopReason ? { code: 'unread_input', detail: c.stopReason } : null,
    cost_usd: typeof c.costUsd === 'number' ? c.costUsd : null } }
}
const runFailed = (role, c) => (role === 'session_harvest' && Boolean(c.harvestFailed))
  || (role === 'watchdog' && Boolean(c.checkExit)) || (role === 'ingest_watch' && Boolean(c.sourcesFailed))
const failError = role => (role === 'session_harvest' ? ERRORS.harvest : role === 'ingest_watch' ? ERRORS.sources : null)

function jobRow(role, c) {
  const schedule = SCHEDULES[role]
  const slot = lastRun(schedule, Date.now() - 60000) || isoIn(-60)
  const failed = runFailed(role, c)
  const paused = role === 'session_harvest' && c.paused
  return {
    role, name: NAMES[role], kind: role === 'session_harvest' ? 'agent' : 'script', id: IDS[role], live: true,
    state: paused ? 'paused' : 'scheduled', schedule, planned_schedule: schedule, schedule_source: 'store',
    next_run_at: paused ? null : nextRuns(schedule, 1)[0], last_run_at: shift(slot, 0),
    last_status: failed ? 'error' : 'ok', last_error: failed ? failError(role) : null, dispatch: null,
    deliver: 'ntfy',
    target: { ok: !(role === 'watchdog' && c.jobBroken), root_ok: true, impl_ok: !(role === 'watchdog' && c.jobBroken),
      impl: IMPL[role], root: '/srv/wiki', reason: '' }
  }
}

function jobsPayload(c) {
  const roles = Object.keys(IDS).map(role => jobRow(role, c))
  return { ok: true, available: true, cron: true, mutation_available: true, error: null, audit_dir: '/srv/audit',
    timezone: zone(), roles, orphans: roles.filter(r => r.live && r.state !== 'paused' && !r.target.ok).map(r => r.role) }
}

function healthPayload(c) {
  if (c.richHistory) return healthFixture()
  const now = Date.now()
  const runsOut = Object.keys(IDS).map((role, i) => {
    const harvest = role === 'session_harvest'
    // lateMorning: the three morning jobs fired together, 91 minutes after their 09:00-style slot (m-13).
    const late = c.lateMorning && !harvest
    const at = isoIn(late ? -20 : -(20 + i * 7), now)
    const failed = runFailed(role, c)
    const running = harvest && c.running
    const findings = role === 'watchdog' && c.problems ? PROBLEMS : []
    const error = failError(role)
    const body = findings.length ? `Wiki watchdog — ${findings.length} findings` : failed && error ? error : 'ok'
    return {
      id: `run-${IDS[role]}`, job_id: IDS[role], job_name: NAMES[role], job_live: true,
      at: healthStamp(at),
      scheduled_at: healthStamp(shift(at, late ? -91 : -1)),
      finished_at: running ? null : healthStamp(shift(at, 1)),
      status: running ? 'running' : failed ? 'failed' : 'completed', delivery: running ? 'none' : 'suppressed',
      duration_ms: running ? null : 64000, lateness_s: late ? 5460 : 60,
      silent: !running && !failed && !findings.length,
      body, body_len: body.length, body_source: failed && error ? 'error' : 'output',
      error_preview: failed ? error : null,
      findings: findings.map(f => ({ kind: f.kind, n: f.n, tone: f.tone, title: f.title, what: f.what,
        action: f.action, detail: f.detail, raw: f.raw, data: f.data })),
      findings_count: findings.length,
      date: healthStamp(at).slice(0, 10), at_ts: Date.parse(at) / 1000,
      status_label: running ? 'running' : failed ? 'failed' : 'completed',
      delivery_label: running ? 'no delivery record' : 'silent (no output)',
      body_label: failed ? 'recorded error' : 'run output'
    }
  })
  const registry = Object.keys(IDS).map(role => {
    const run = runsOut.find(r => r.job_id === IDS[role])
    return { id: IDS[role], name: NAMES[role], live: true, schedule: SCHEDULES[role], script: IMPL[role], mode: 'script',
      deliver: 'ntfy', state: role === 'session_harvest' && c.paused ? 'paused' : 'scheduled', enabled: true,
      last_status: run.status === 'failed' ? 'error' : 'ok', last_error: run.status === 'failed' ? failError(role) : null,
      last_run_at: run.at, next_run_at: healthStamp(nextRuns(SCHEDULES[role], 1)[0]), runs: 1,
      failed: run.status === 'failed' ? 1 : 0, silent: run.silent ? 1 : 0, delivered: 0,
      findings: run.findings_count, last_at: run.at }
  })
  const buckets = Array.from({ length: 24 }, (_, i) => ({
    iso: new Date(now - (24 - i) * 3600000).toISOString(), runs: 0, failed: 0, silent: 0, delivered: 0 }))
  buckets[23] = { ...buckets[23], runs: runsOut.length, failed: runsOut.filter(r => r.status === 'failed').length,
    silent: runsOut.filter(r => r.silent).length }
  return {
    generatedAt: healthStamp(isoIn(0, now)), window: '24h', since: null, truncated: false, cap: 3000,
    cron_dir: '/srv/hermes/cron', registry,
    totals: { runs: runsOut.length, failed: runsOut.filter(r => r.status === 'failed').length,
      silent: runsOut.filter(r => r.silent).length, delivered: 0,
      findings: runsOut.filter(r => r.findings_count).length, jobs: registry.length, deleted_jobs: 0 },
    trend: { bucket_hours: 1, buckets, prev: { runs: 4, failed: 0, silent: 4, delivered: 0 }, prev_basis: '24h',
      per_job: {} },
    runs: runsOut
  }
}

function watchdogPayload(c) {
  if (!c.problems) return { runs: [], total: 0, state: { checked: watchdogStamp(isoIn(-30)) }, log: '/srv/audit/alerts.log' }
  const at = watchdogStamp(isoIn(-30))
  const ts = Date.parse(isoIn(-30)) / 1000
  const date = isoIn(-30).slice(0, 10)
  return {
    runs: [{ at, ts, date, findings: PROBLEMS.map(f => f.raw),
      items: PROBLEMS.map(f => ({ kind: f.kind, n: f.n, tone: f.tone, title: f.title, what: f.what, action: f.action,
        detail: f.detail, raw: f.raw, data: f.data, ts, date, at })) }],
    total: 1, state: { checked: at, checked_ts: ts }, log: '/srv/audit/alerts.log'
  }
}

/** The `/wiki/map` answer: 334 pages in four folder bands, dated by a fixed spread; with wiki problems,
 * three link targets are missing and four pages name them. */
function wikiMapPayload(c) {
  const bands = [['concepts', 160], ['entities', 110], ['sources', 56], ['other', 8]]
  const pages = []
  for (const [band, n] of bands) {
    for (let i = 0; i < n; i += 1) {
      pages.push({ id: `${band}-page-${i + 1}`, band, title: `${band[0].toUpperCase()}${band.slice(1)} page ${i + 1}`,
        age: (i * 37 + band.length * 11) % 60 })
    }
  }
  const missing = c.problems ? [
    { name: 'hermes-standing-behaviour-rules', count: 2, holders: ['concepts-page-4', 'sources-page-9'] },
    { name: 'hermes-plugin-vetting', count: 1, holders: ['entities-page-12'] },
    { name: 'evaluating-skills-not-just-agents', count: 1, holders: ['concepts-page-77'] }
  ] : []
  return { ok: true, pages, truncated: false, missing_total: missing.length, holders: c.problems ? 4 : 0, missing }
}

/** Every condition a state can combine. Two of them at once is how the priority order is proven. */
export function world(conditions = {}) {
  const c = { ...conditions }
  const auto = automation()
  auto.scripts = { 'wiki_autocommit.py': true, 'wiki_ingest_watch.py': true, 'watchdog.py': true, 'install.py': true }
  auto.settings = { ...auto.settings, project: { ok: true, id: 'auto-id', pages: 334, reason: '' },
    jobs: { autocommit: IDS.autocommit, ingest_watch: IDS.ingest_watch, watchdog: IDS.watchdog } }
  const fail = {}
  for (const path of [].concat(c.readFailed || [])) fail[path] = ERRORS[path] || `read failed: ${path}`
  return {
    conditions: c,
    automation: auto,
    engine: engineStatus(c.engine || 'installed_with_existing_jobs', c.engineUpdate ? OLDER_ENGINE : undefined),
    owner: { ok: true, active: true, ready: true, code_changed: false, owner: 'local_owner',
      job: { id: IDS.session_harvest, name: NAMES.session_harvest, schedule: SCHEDULES.session_harvest },
      plan_digest: 'd'.repeat(64) },
    harvest: { ok: true, agents: ADAPTERS.map(a => ({ id: a.id,
      enabled: !(a.id === 'claude' && c.lineOff), found: !missingIds(c).includes(a.id),
      cursor: missingIds(c).includes(a.id) ? 'none (first run looks back 3 days)' : healthStamp(isoIn(-90)) })),
      ...lastRunOf(c) },
    jobs: jobsPayload(c),
    candidates: c.drafts ? candidates().slice(0, c.drafts) : [],
    unreadable: c.unreadableDraft && c.drafts ? candidates()[0].ref : null,
    health: healthPayload(c),
    watchdog: watchdogPayload(c),
    wikiMap: wikiMapPayload(c),
    runs: runs(),
    fail,
    pending: Boolean(c.pending),
    calls: { gets: [], posts: [] }
  }
}

/**
 * The panel's `ctx.rest` for one world. A path in `world.fail` answers the backend's error the way
 * that route does (`{ ok:false, error }`), `throwOn` makes the transport itself fail, and `pending`
 * never resolves (the loading skeleton). Writes are answered without touching anything.
 */
export function makeRest(w, { throwOn = [] } = {}) {
  const throws = new Set([].concat(throwOn))
  return async (path, opts) => {
    const method = opts?.method || 'GET'
    if (method === 'POST') w.calls.posts.push({ path, body: opts.body })
    else w.calls.gets.push(path)
    if (w.pending) return new Promise(() => {})
    const bare = path.split('?')[0]
    if (throws.has(bare)) throw new Error(`backend unreachable (500) on ${bare}: ${w.fail[bare] || ERRORS[bare] || ''}`)
    if (method !== 'POST' && w.fail[bare]) {
      return bare === '/health/watchdog' ? { ok: false, error: w.fail[bare] } : { ok: false, error: w.fail[bare],
        reason: w.fail[bare], available: false }
    }
    if (method === 'POST') {
      if (path === '/jobs/preview') return previewOf(opts.body?.schedule)
      if (path === '/candidates/act' || path === '/owner/decision') {
        const ref = String(opts.body?.ref || '')
        const row = w.candidates.find(x => x.ref === ref)
        if (!row) return { ok: false, ref, reason: 'a candidate is named <run>/<name>' }
        if (opts.body?.action === 'fetch_evidence') {
          w.evidenceFetched = true
          return { ok: true, ref, action: 'fetch_evidence', pending: [],
            results: [{ id: EVIDENCE_REQUEST.id, ok: true, status: 'captured', passages_verified: 1 }] }
        }
        if ((opts.body?.action || 'approve') === 'reject') {
          if (!String(opts.body?.reason || '').trim()) return { ok: false, ref, reason: 'rejecting a candidate needs a reason' }
          w.candidates = w.candidates.filter(x => x.ref !== ref)
          return { ok: true, ref, output: `OK rejected ${ref}` }
        }
        if (!opts.body?.confirm) {
          return { ok: false, ref, action: 'approve', needs_confirm: true, request_id: `metro-${w.calls.posts.length}`,
            review_digest: candidateDetail(ref).review_digest,
            reason: "approving writes this source into the wiki's raw/sources folder, and the LLM Wiki app will then "
              + 'ingest it, which costs model usage', output: `[dry-run] would ${row.kind} ${row.target}` }
        }
        w.candidates = w.candidates.filter(x => x.ref !== ref)
        return { ok: true, ref, output: `OK ${row.kind} ${row.target} applied` }
      }
      if (path === '/automation/validate') return { ok: false, reason: 'wiki/ klasörü yok', reason_source: 'checker' }
      if (path === '/jobs/act') return { ok: false, needs_confirm: true, reason: 'this action needs an explicit confirmation' }
      return { ok: false, reason: `the preview answers no ${path}` }
    }
    if (bare === '/automation') return { ...w.automation, settings: { ...w.automation.settings } }
    if (bare === '/engine/status') return w.engine
    if (bare === '/owner/activation') return w.owner
    if (bare === '/owner/recoverable') return { ok: true, operations: [] }
    if (bare === '/harvest/status') return w.harvest
    if (bare === '/jobs') return w.jobs
    if (bare === '/candidates') return { ok: true, audit_dir: '/srv/audit', candidates: [...w.candidates] }
    if (bare === '/candidates/show') {
      const ref = decodeURIComponent(path.slice('/candidates/show?ref='.length))
      if (w.unreadable && ref === w.unreadable) return { ok: false, ref, error: UNREADABLE_DRAFT }
      const shown = candidateDetail(ref)
      if (w.conditions.refusal) return { ...shown, approval_refusal: APPROVAL_REFUSAL }
      if (!w.conditions.evidence) return shown
      const fetched = w.conditions.evidence === 'fetched' || w.evidenceFetched
      return { ...shown, review_digest: fetched ? 'e'.repeat(64) : shown.review_digest,
        evidence_requests: [{ ...EVIDENCE_REQUEST, fetched,
          ...(fetched ? { status: 'captured', commit: EVIDENCE_COMMIT, files: { 'files/d923a5eb/hermes_cli/plugins_cadence.py': 9214 } } : {}) }],
        pending_evidence: fetched ? [] : [EVIDENCE_REQUEST.id],
        evidence_folders: fetched ? [EVIDENCE_REQUEST.id] : [] }
    }
    if (bare === '/health/jobs/run') {
      const id = new URL(path, 'http://fixture').searchParams.get('id')
      const run = w.health.runs.find(r => r.id === id)
      return { ok: true, id, body: run?.body || 'run output', body_label: 'run output', body_source: 'output',
        truncated: false }
    }
    if (bare === '/health/jobs') {
      const win = new URL(path, 'http://fixture').searchParams.get('window') || '24h'
      return w.health && typeof w.health === 'object' ? { ...w.health, window: win } : w.health
    }
    if (bare === '/health/watchdog') return w.watchdog
    if (bare === '/wiki/map') return w.wikiMap
    if (bare === '/runs') return w.runs
    if (bare === '/automation/candidates') {
      return { ok: true, root: '/srv', scanned: 102, skipped: 1, truncated: false,
        found: [{ root: '/srv/other-wiki', id: 'auto-id', pages: 12, duplicates: [] }] }
    }
    throw new Error(`the Metro fixture has no route ${path}`)
  }
}

const ALL_OK = { harvest: 'ok', review: 'ok', wiki: 'ok' }
const LINES_OK = Object.fromEntries(ADAPTERS.map(a => [a.id, 'ok']))

/**
 * One entry per state. `open` is what the state clicks (a station, `line:<id>`, `history`, `settings`);
 * `then` is a follow-up step inside the open detail. `expect` is what the screen must say.
 * The narrow mocks (m-15/m-16) are `problems` and `wiki` measured in a 390 px pane.
 */
export const STATES = {
  good: { mock: 'm-05', conditions: {},
    expect: { alert: 'good', tone: 'ok', stations: ALL_OK, lines: LINES_OK, text: [GOOD_SERVICE] } },
  problems: { mock: 'm-01', conditions: { problems: true },
    expect: { alert: 'problems', tone: 'warn', stations: { harvest: 'ok', review: 'ok', wiki: 'warn' }, lines: LINES_OK } },
  wiki: { mock: 'm-02', conditions: { problems: true }, open: 'wiki',
    // The bar steps aside while the detail it opens is the open one (m-02, m-07, m-08).
    expect: { alert: 'problems', bar: 0, detail: 'wiki', text: [ASK_HERMES] } },
  harvest: { mock: 'm-03', conditions: {}, open: 'harvest', expect: { alert: 'good', detail: 'harvest' } },
  branch: { mock: 'm-04', conditions: {}, open: 'line:hermes', expect: { alert: 'good', detail: 'line:hermes' } },
  running: { mock: 'm-06', conditions: { running: true },
    expect: { alert: 'running', tone: 'ask', stations: { harvest: 'run' },
      lines: Object.fromEntries(ADAPTERS.map(a => [a.id, 'run'])) } },
  drafts: { mock: 'm-07', conditions: { drafts: 3 }, open: 'review',
    expect: { alert: 'drafts', bar: 0, stations: { review: 'ask' }, detail: 'review',
      text: ['1 of 3', 'Your review · draft 1 of 3'] } },
  approve: { mock: 'm-08', conditions: { drafts: 3 }, open: 'review', then: 'approve',
    expect: { alert: 'drafts', bar: 0, detail: 'review', dialog: true,
      text: ['Approve this draft?', 'LLM Wiki may then use model credits to read it.'] } },
  'harvest-failed': { mock: 'm-09', conditions: { harvestFailed: true },
    expect: { alert: 'harvest-failed', tone: 'bad', stations: { harvest: 'bad' } } },
  'branch-missing': { mock: 'm-10', conditions: { missingFolder: true },
    // A tool that is not installed is skipped by the engine; it is drawn, never alarmed (2.5.13).
    expect: { alert: 'good', lines: { hermes: 'ok', codex: 'ok', claude: 'missing', antigravity: 'ok' },
      stations: ALL_OK, text: ['folder not found', GOOD_SERVICE] } },
  loading: { mock: 'm-11', conditions: { pending: true }, expect: { skeleton: true, notAlert: ['good'] } },
  'read-failed': { mock: 'm-12', conditions: { readFailed: '/jobs' },
    // m-12: with no timetable no line is drawn; the raw error sits behind `Show the error`.
    expect: { alert: 'read-failed', tone: 'bad', noMap: true, noGood: true,
      text: [ERRORS['/jobs'], 'The timetable could not be read', 'Your wiki and its jobs are untouched.'] } },
  history: { mock: 'm-13', conditions: { problems: true, lateMorning: true }, open: 'history',
    expect: { detail: 'history', text: ['Show older runs', 'Full technical log', 'were due at'] } },
  'history-log': { conditions: { richHistory: true }, open: 'history', then: 'full-log', expect: { detail: 'history' } },
  settings: { mock: 'm-14', conditions: {}, open: 'settings',
    expect: { detail: 'settings', text: ['Wiki folder', 'Scheduled jobs', 'Engine and files'] } },
  'settings-jobs': { conditions: {}, open: 'settings', then: 'timetable', expect: { detail: 'settings' } },
  engine: { conditions: { engine: 'missing' }, expect: { alert: 'engine' } },
  'job-broken': { conditions: { jobBroken: true }, expect: { alert: 'job-broken' } },
  paused: { conditions: { paused: true }, expect: { alert: 'paused', stations: { harvest: 'paused' } } },
  'line-off': { conditions: { lineOff: true }, expect: { lines: { claude: 'off' }, text: ['off'] } },
  'engine-update': { conditions: { engineUpdate: true },
    expect: { alert: 'engine', tone: 'ask', text: ['Engine update ready', '3333333', '4444444'] } },
  'settings-update': { conditions: { engineUpdate: true }, open: 'settings',
    expect: { detail: 'settings', text: ['3333333', 'This plugin ships engine 4444444'], notText: [OLDER_ENGINE] } },
  'draft-unreadable': { conditions: { drafts: 3, unreadableDraft: true, engineUpdate: true }, open: 'review',
    expect: { detail: 'review', text: ['This draft could not be read', 'New source target already exists',
      'Updating the engine fixes this'], notText: ['New page'] } },
  'draft-evidence': { conditions: { drafts: 1, evidence: 'pending' }, open: 'review',
    // A finding that needs a copy: nothing is fetched until the owner presses Fetch; Approve waits.
    expect: { bar: 0, detail: 'review', text: ['Evidence to fetch', 'Nothing has been downloaded yet', 'Fetch evidence (1)',
      'not fetched', 'Pinned/manual/drift/pip are never auto-applied', 'hermes_cli/plugins_cadence.py'],
      notText: ['Approve'] } },
  'draft-refused': { conditions: { drafts: 1, refusal: true }, open: 'review',
    // Approval would refuse this draft: the engine's own reason is shown before the owner presses Approve.
    expect: { bar: 0, detail: 'review', text: ['This draft cannot be approved as written', 'pinned version',
      'Reject it with this reason'] } },
  'draft-evidence-fetch': { conditions: { drafts: 1, evidence: 'pending' }, open: 'review', then: 'fetch',
    expect: { bar: 0, detail: 'review', text: ['Evidence fetched and checked', 'fetched', 'Approve'],
      notText: ['Fetch evidence', 'not fetched'] } },
  'draft-evidence-fetched': { conditions: { drafts: 1, evidence: 'fetched' }, open: 'review',
    expect: { bar: 0, detail: 'review', text: ['Evidence to fetch', 'fetched', 'Approve'], notText: ['Fetch evidence', 'not fetched'] } },
  'history-failed': { conditions: { problems: true, checkExit: true, sourcesFailed: true }, open: 'history',
    expect: { detail: 'history', runs: { watchdog: 'warn', ingest_watch: 'bad' },
      text: ['found 3 problems', ERRORS.sources] } },
  'branches-missing': { conditions: { missingFolder: ['codex', 'claude'] },
    expect: { alert: 'good', lines: { codex: 'missing', claude: 'missing' }, stations: ALL_OK,
      notText: ['lines closed', 'still run'] } },
  'branches-missing-old': { conditions: { missingFolder: ['codex', 'claude'], oldEngine: true },
    expect: { alert: 'job-broken', tone: 'bad', lines: { codex: 'missing', claude: 'missing' }, stations: { harvest: 'bad' },
      text: ['Codex and Claude Code lines closed: folders not found', 'This engine stops every line',
        'stopped: a line folder is missing'], notText: ['still run'] } },
  'line-missing': { conditions: { missingFolder: true }, open: 'line:claude',
    expect: { detail: 'line:claude', text: ['Claude Code folder', 'not found',
      'On — skipped while the folder is missing; the other lines are read'],
      notText: ['Wiki folder', 'On — collected', 'does not prove', 'nothing collected'] } },
  'line-missing-old': { conditions: { missingFolder: true, oldEngine: true }, open: 'line:claude',
    expect: { detail: 'line:claude', text: ['On — nothing collected while the folder is missing'],
      notText: ['the other lines are read'] } },
  'line-unread': { conditions: { unreadable: 'antigravity' },
    expect: { alert: 'job-broken', tone: 'warn', stations: { harvest: 'ok' },
      lines: { hermes: 'ok', codex: 'ok', claude: 'ok', antigravity: 'unread' },
      text: ['Antigravity line could not be read', 'the other three lines were read', 'could not be read'] } },
  'line-unread-detail': { conditions: { unreadable: 'antigravity' }, open: 'line:antigravity',
    expect: { bar: 0, detail: 'line:antigravity', text: ['On — its history could not be read, so its conversations wait'] } },
  'harvest-unfinished': { conditions: { notCommitted: true },
    // The cron store says the run completed; the engine says nothing was saved. The engine wins.
    expect: { alert: 'harvest-failed', tone: 'bad', stations: { harvest: 'bad' },
      text: ['No drafts were written. Reason: The engine did not finish this run; its conversations wait for the next run.'] } },
  'harvest-stop-reason': { conditions: { notCommitted: true, stopReason: '2 of 7 captured inputs were not read completely, first: conversations/b.md.' },
    // The engine recorded why the run stopped; the owner sees that reason, not the generic sentence.
    expect: { alert: 'harvest-failed', tone: 'bad', stations: { harvest: 'bad' },
      text: ['Reason: 2 of 7 captured inputs were not read completely'], notText: ['its conversations wait for the next run'] } },
  'harvest-cost': { conditions: { costUsd: 0.95 }, open: 'harvest',
    expect: { detail: 'harvest', text: ["about $0.95 (Hermes' estimate)"] } },
  'harvest-lines': { conditions: { missingFolder: ['codex', 'claude'] }, open: 'harvest',
    expect: { detail: 'harvest', text: ['Reads your Hermes and Antigravity conversations'], notText: ['Codex'] } }
}

/** Two conditions at once; the first-named key must win (proves the order, pair by pair). */
export const PRIORITY_PAIRS = [
  ['read-failed', 'engine', { readFailed: '/candidates', engine: 'missing' }],
  ['read-failed', 'drafts', { readFailed: '/harvest/status', drafts: 2 }],
  ['read-failed', 'engine', { readFailed: '/candidates', engineUpdate: true }],
  ['engine', 'harvest-failed', { engineUpdate: true, harvestFailed: true }],
  ['engine', 'harvest-failed', { engine: 'missing', harvestFailed: true }],
  ['harvest-failed', 'job-broken', { harvestFailed: true, jobBroken: true }],
  ['job-broken', 'drafts', { jobBroken: true, drafts: 2 }],
  ['drafts', 'problems', { drafts: 2, problems: true }],
  ['problems', 'paused', { problems: true, paused: true }],
  ['paused', 'running', { paused: true, running: true }],
  ['running', 'good', { running: true }]
]

/** Locate what a state clicks. Stations and branch lines are buttons (or wrap one). */
export function target(root, what) {
  const pick = sel => {
    const el = root.querySelector(sel)
    if (!el) return null
    return el.tagName === 'BUTTON' ? el : el.querySelector('button') || el
  }
  if (what === 'history' || what === 'settings') return pick(`[data-wa-nav="${what}"]`)
  if (what.startsWith('line:')) return pick(`[data-wa-line="${what.slice(5)}"]`)
  return pick(`[data-wa-station="${what}"]`)
}

/** Drive a mounted panel into a state's open detail. `api.click(el)` dispatches a real click. */
export async function drive(state, root, api) {
  const s = STATES[state]
  if (!s?.open) return
  const el = target(root, s.open)
  if (!el) throw new Error(`state ${state}: nothing to click for ${s.open}`)
  await api.click(el)
  const pressIn = async (which, label) => {
    const detail = root.querySelector(`.wa-metro-detail[data-for="${which}"]`)
    const button = [...(detail?.querySelectorAll('button') || [])].find(b => b.textContent.trim() === label)
    if (!button) throw new Error(`state ${state}: the ${which} detail has no "${label}" button`)
    await api.click(button, 200)
  }
  if (s.then === 'full-log') await pressIn('history', 'Full technical log')
  if (s.then === 'timetable') {
    // 2.12.0: the jobs are open on arrival; this state shows one job row expanded.
    const row = root.querySelector('.wa-metro-detail[data-for="settings"] [data-sec="jobs"] .wa-job-summary')
    if (!row) throw new Error(`state ${state}: the settings detail lists no scheduled job`)
    await api.click(row, 200)
  }
  if (s.then === 'fetch') await pressIn('review', 'Fetch evidence (1)')
  if (s.then === 'approve') {
    const detail = root.querySelector('.wa-metro-detail[data-for="review"]')
    const approve = [...(detail?.querySelectorAll('button') || [])].find(b => b.textContent.trim() === 'Approve')
    if (!approve) throw new Error('state approve: the review desk has no Approve button')
    await api.click(approve, 160)
  }
}
