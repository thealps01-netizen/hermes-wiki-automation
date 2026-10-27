/**
 * Wiki Automation — the History detail (diagnostic analytics + the one run journal), rendered
 * with real React in jsdom. The page registers under `/wiki-automation`; each assertion explicitly
 * mounts its owning view. Shared filters/read states are exercised in both views and every run
 * history read goes to the `/health/*` routes.
 *
 * Run: cd tests && node render_health.mjs [<plugin.js path>]   (exit code 0 = passed)
 *
 * What it locks: diagnostic layers (KPI · chart), chronological entries and an adjacent nonmodal
 * inspector, a row is a run, the run
 * flow chart, the job distribution list, ONE filter scope (a preset also sets the server window
 * /health/jobs?window=…), undated runs included only without date bounds, two-step archive-then-clear,
 * the drawer fetching the FULL body through /health/jobs/run, one English bundle with no language
 * picker, closed advanced job/date filters with exposed search, a read-only pending candidate queue
 * with the review desk's SEC-3 scope guarantees, the refresh button, the finding mapping (the retired `not_indexed` class included, printed
 * as a retired check), and the host UI kit components measured on `data-slot`.
 */
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { JSDOM } from 'jsdom'
import { fixture, FINDING_CASES, TODAY_ISO, OLD_ISO, TODAY_AT } from './fixture-health.mjs'
import { automation, candidates, candidateDetail, harvestStatus, jobsState, jobsView, runs, engineStatus } from './fixture.mjs'

const HERE_URL = new URL('.', import.meta.url)
const HERE = fileURLToPath(HERE_URL).replace(/\\/g, '/') + '/'
const SRC = process.argv[2] || `${HERE}../desktop/plugin.js`
const PLUGIN_ID = 'wiki-automation'
const ROUTE = '/wiki-automation'

// The stub mirrors the app's plugin i18n: bundles are registered under the plugin id and resolved by
// dot-path against the ACTIVE app locale, falling back to the plugin's own `en`, then to the key.
// `translateNow` only ever reads the CORE catalog — which holds no plugin key — so it returns the key
// unchanged, exactly like the app would for a key the plugin owns.
writeFileSync(`${HERE}sdk-health-stub.mjs`, `
export const calls = { gets: [], posts: [], registered: [], keys: [], registerKeys: [] }
export const state = { appLocale: 'en' }
const atom = initial => {
  let value = initial
  const listeners = new Set()
  return { get: () => value, listen: fn => { listeners.add(fn); return () => listeners.delete(fn) },
    set: next => { if (Object.is(next, value)) return; value = next; for (const fn of listeners) fn(next) } }
}
export const host = { state: { connectionId: atom('local'), profile: atom('default'), cwd: atom('/srv/wiki') } }

const bundles = new Map()

function leaf(tree, key) {
  let node = tree
  for (const part of String(key).split('.')) {
    if (!node || typeof node !== 'object') return undefined
    node = node[part]
  }
  return node
}

export function registerBundles(id, table) {
  bundles.set(id, table)
  calls.registered.push({ id, locales: Object.keys(table) })
}

export function resolveKey(id, key, args) {
  calls.keys.push(key)
  const table = bundles.get(id) || {}
  const node = leaf(table[state.appLocale], key)
  const fallback = node === undefined ? leaf(table.en, key) : node
  if (typeof fallback === 'function') return fallback(...args)
  return fallback ?? key
}

export function usePluginI18n(id) {
  return (key, ...args) => resolveKey(id, key, args)
}

export function translateNow(key) {
  return key
}

export function useI18n() {
  return { t: key => key }
}

export default {
  host: { notify: () => {}, notifyError: () => {} },
  haptic: () => {},
  relativeTime: () => '2 hours ago',
  EmptyState: null
}

export * from './kit-stub.mjs'
`)

// The panel source is taken as it is; only the SDK import is pointed at the stub, so the test runs
// the REAL file (a stale copy cannot lie).
const src = readFileSync(SRC, 'utf8').replace("'@hermes/plugin-sdk'", `'${HERE_URL.href}sdk-health-stub.mjs'`)
writeFileSync(`${HERE}plugin-health-under-test.mjs`, src)

const dom = new JSDOM('<!doctype html><html><body></body></html>', { pretendToBeVisual: true })
global.window = dom.window
global.document = dom.window.document
Object.defineProperty(global, 'navigator', { value: dom.window.navigator, configurable: true })
global.IS_REACT_ACT_ENVIRONMENT = true

let JOBS = fixture()
// The list carries a preview only; the full body arrives from its own endpoint. This text is only
// visible if the drawer really called `/jobs/run`.
const FULL_BODY = 'FULL BODY · ⚠ Wiki watchdog — 2 finding(s)\n- 2 commit(s) ahead of \'onedrive\'\n'
  + '- DUPLICATE PAGE STEMS: {concepts/abap-bot-fleet, entities/abap-bot-fleet}'
const FOREIGN_BODY = 'FOREIGN RUN OUTPUT — must never enter the selected inspector'
const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

const React = await import('react')
const { createRoot } = await import('react-dom/client')
// `act` moved to `react` in React 18.3; the react-dom copy is deprecated and only warns.
const { act } = React.act ? React : await import('react-dom/test-utils')
// A test file runs for minutes and keeps earlier panels mounted, so their real 60-second polls would land in
// the shared call log at wall-clock-dependent moments and race every read-count assertion. Polls of a minute
// or longer never fire on their own here; a test that needs one captures its callback and calls it.
const realSetInterval = globalThis.setInterval
globalThis.setInterval = (fn, ms, ...rest) => (Number(ms) >= 60000 ? realSetInterval(() => {}, ms) : realSetInterval(fn, ms, ...rest))
const stub = await import(`${HERE_URL.href}sdk-health-stub.mjs`)

const problems = []
const fail = m => { problems.push(m); console.error('  x', m) }
const must = (hay, needles, label) => {
  const lacking = needles.filter(x => !String(hay).includes(x))
  if (lacking.length) fail(`${label}: missing text ${lacking.join(' | ')}`)
}
const RAW_KEY = /\bwd\.[a-z][a-zA-Z0-9_.]*/
const noRawKeys = (text, label) => {
  const leaked = [...String(text).matchAll(new RegExp(RAW_KEY, 'g'))].map(m => m[0])
  if (leaked.length) fail(`RAW KEY leaked (${label}): ${[...new Set(leaked)].join(', ')}`)
}

let version = 0
// The owner's real store: one run a day per job for 13 days, sent newest first like the backend does.
function dailyRuns(payload) {
  const base = payload.runs[0]
  const newest = Math.max(...payload.runs.map(r => r.at_ts).filter(n => typeof n === 'number'))
  return ['daily-a', 'daily-b', 'daily-c', 'daily-d'].flatMap((job, j) => Array.from({ length: 13 - j }, (_, i) => ({
    ...base,
    id: `${job}-${i}`, key: `${job}-${i}`, job_id: job, job_name: job,
    at_ts: newest - i * 86400 - j * 600,
    status: 'completed', status_label: 'Done', silent: false, delivery: 'delivered',
    lateness_s: 0, duration_ms: 1000
  })))
}

// The backend's trend for that store: a 12-day window in 13-hour buckets, one row per job.
function dailyTrend(runs) {
  const t0 = Math.min(...runs.map(r => r.at_ts))
  const buckets = Array.from({ length: 23 }, (_, i) => {
    const d = new Date((t0 + i * 13 * 3600) * 1000)
    const off = -d.getTimezoneOffset()
    const local = new Date(d.getTime() + off * 60000).toISOString().slice(0, 19)
    const sign = off >= 0 ? '+' : '-'
    const tz = `${sign}${String(Math.floor(Math.abs(off) / 60)).padStart(2, '0')}:${String(Math.abs(off) % 60).padStart(2, '0')}`
    return { iso: local + tz, runs: 0, failed: 0, silent: 0, delivered: 0 }
  })
  const per_job = {}
  runs.forEach(r => {
    const i = Math.min(22, Math.floor((r.at_ts - t0) / (13 * 3600)))
    per_job[r.job_id] ||= buckets.map(b => ({ ...b, runs: 0, failed: 0, silent: 0, delivered: 0 }))
    per_job[r.job_id][i].runs += 1
    per_job[r.job_id][i].delivered += 1
    buckets[i].runs += 1
  })
  return { bucket_hours: 13, buckets, per_job }
}

const folioControl = { automation: null, candidates: null, recovery: null }
let activeMount = null
async function mount(appLocale = 'en', mode = 'data', target = 'health') {
  if (activeMount) {
    await act(async () => { activeMount.root.unmount() })
    activeMount.el.remove()
    activeMount = null
  }
  stub.host.state.connectionId.set('local')
  stub.host.state.profile.set('default')
  stub.host.state.cwd.set('/srv/wiki')
  JOBS = fixture()
  // Per-mount backend probes stay in this harness; production source is never mutated.
  if (mode === 'durationprobe') {
    const base = JOBS.runs[1]
    const cases = [
      ['zero', { duration_ms: 0 }], ['fraction', { duration_ms: 12.5 }],
      ['seconds', { duration_ms: 2500, job_id: JOBS.runs[0].job_id, job_name: JOBS.runs[0].job_name }], ['string', { duration_ms: '2500' }],
      ['boolean', { duration_ms: true }], ['negative', { duration_ms: -1 }],
      ['nan', { duration_ms: NaN }], ['infinite', { duration_ms: Infinity }],
      ['unknown', { duration_ms: null }], ['undated', { duration_ms: 10000, at: null, at_ts: null, date: null }],
      ['dateless-clock', { duration_ms: 10000, at: TODAY_ISO }],
      ['bad-instant', { duration_ms: 10000, at_ts: NaN }],
      ['infinite-instant', { duration_ms: 10000, at_ts: Infinity }],
      ['string-instant', { duration_ms: 10000, at_ts: String(base.at_ts) }]
    ]
    JOBS.runs = cases.map(([id, fields]) => ({ ...base, id: `duration-${id}`, ...fields }))
  }
  if (mode === 'zerodurations') JOBS.runs = JOBS.runs.map(run => ({ ...run, duration_ms: 0 }))
  if (mode === 'nodurations') JOBS.runs = JOBS.runs.map(run => ({ ...run, duration_ms: null }))
  if (mode === 'projectioncases') {
    const base = JOBS.runs[0]
    const output = 'OUTPUT IS NOT AN ERROR\nNor a synthesized finding'
    const error = '  Recorded exception <script>literal</script>\r\nSecond error line stays in raw output'
    const cases = [
      ['error-first', 'failed', 'delivered', 'error', error, FINDING_CASES],
      ['bad-finding', 'completed', 'failed', 'output', output, [FINDING_CASES[0], FINDING_CASES[2]]],
      ['first-finding', 'running', 'queued', 'output', output, [FINDING_CASES[1], FINDING_CASES[4]]],
      ['failed-no-error', 'failed', 'suppressed', 'output', output, []],
      ['claimed', 'claimed', 'none', 'none', '', []],
      ['unknown', 'unknown', 'unrecognized-delivery', 'none', '', []],
      ['blank-error', 'failed', 'delivered', 'error', ' \r\n ', []]
    ]
    JOBS.runs = cases.map(([id, status, delivery, body_source, body, findings]) => ({
      ...base, id: `projection-${id}`, status, delivery, body_source, body, findings,
      body_len: body.length, status_label: `backend status: ${status}`,
      delivery_label: `backend delivery: ${delivery}`, body_label: `backend body: ${body_source}`
    }))
  }
  if (mode === 'controlledbody') JOBS.runs[1] = { ...JOBS.runs[1], body_len: 2400 }
  stub.state.appLocale = appLocale
  stub.calls.gets = []
  stub.calls.posts = []
  stub.calls.keys.length = 0
  stub.calls.registerKeys.length = 0
  stub.calls.registered.length = 0
  // Per-mount call arrays: remounting must not rewrite the previous view's evidence.
  const gets = stub.calls.gets
  const posts = stub.calls.posts
  const registrations = []
  const errors = new Set()
  const reads = []
  // Metro (2.5.0) polls /health/jobs?window=24h for its stations before History opens. Run-history
  // modes and read-window assertions key on the reads issued AFTER the History detail opened.
  let historyFrom = Infinity
  const historyGets = () => gets.slice(historyFrom)
  const historyJobs = () => historyGets().filter(g => g.startsWith('/health/jobs?'))
  const historyRead = path => gets.length > historyFrom && path.startsWith('/health/')
  const candidateRows = mode === 'queueidentity' ? [
    ...candidates(),
    { ...candidates()[0], ref: 'batch/ref with % & + ? # ü', target: 'same-name.md', summary: 'Exact-ref proposal A' },
    { ...candidates()[0], ref: 'other-batch/ref with % & + ? # ü', target: 'same-name.md', summary: 'Exact-ref proposal B' }
  ] : candidates()
  const ctx = {
    rest: async (path, opts) => {
      if (opts?.method === 'POST') {
        stub.calls.posts.push({ path, body: opts.body })
        if (path === '/health/runs/archive-clear') {
          const keys = (opts.body && opts.body.keys) || []
          return { ok: true, cleared: keys.length, missing: 0,
                   archive: 'backups/runs-20260918-203207.json', archive_bytes: 2048,
                   archive_sha256: 'deadbeef' }
        }
        return { ok: true }
      }
      stub.calls.gets.push(path)
      if (mode === 'folioscope') {
        if (path === '/automation' && folioControl.automation) return folioControl.automation()
        if (path === '/candidates' && folioControl.candidates) return folioControl.candidates()
        if (path === '/owner/recoverable') return folioControl.recovery?.() || { ok: true, operations: [] }
        if (path === '/owner/activation') {
          return { ok: true, active: true, ready: true, code_changed: false, owner: 'local_owner',
            job: { id: 'job-h', name: 'Wiki Session Harvest', schedule: '30 21 * * *' }, plan_digest: 'd'.repeat(64) }
        }
      }
      // The Metro view mounts first; run-history failure modes must not corrupt its independent reads.
      if (path === '/engine/status') return engineStatus()
      if (path === '/automation') return automation()
      if (path === '/jobs') return jobsView(jobsState())
      if (path.startsWith('/runs')) return runs()
      if (path === '/candidates') {
        const count = gets.filter(path => path === '/candidates').length
        // Metro has ONE candidate reader, the review desk's: its first read carries the queue mode.
        if (mode === 'queuepending') return new Promise(() => {})
        if (mode === 'queueerror') throw new Error('the candidate store is locked')
        if (mode === 'queuerefused') return { ok: false, error: 'the candidate list was refused', candidates: candidateRows }
        if (mode === 'queueempty') return { ok: true, candidates: [] }
        return { ok: true, candidates: mode === 'queuerefresh' && count > 2 ? candidateRows.slice(1) : candidateRows }
      }
      if (path.startsWith('/candidates/show?')) {
        const ref = new URL(path, 'https://fixture.invalid').searchParams.get('ref')
        const row = candidateRows.find(item => item.ref === ref)
        if (!row) throw new Error(`unexpected candidate ref: ${ref}`)
        const detail = candidateDetail(candidates().some(item => item.ref === ref) ? ref : candidates()[0].ref)
        return { ...detail, ref, candidate: { ...detail.candidate, ...row } }
      }
      if (path === '/harvest/status') return harvestStatus()
      // The three kit states a read can land in: still loading (the request never settles), a
      // FAILED read, and a read that answers with no runs at all.
      if (mode === 'pending' && historyRead(path)) return new Promise(() => {})
      if (mode === 'error' && historyRead(path)) throw new Error('the run log could not be read')
      if (mode === 'runfail' && path.startsWith('/health/jobs/run')) throw new Error('the run store is locked')
      if (mode === 'flaky' && historyRead(path) && path.startsWith('/health/jobs?') && historyJobs().length > 1) {
        throw new Error('the scheduler store is busy')
      }
      if (mode === 'slowpoll' && historyRead(path) && path.startsWith('/health/jobs?') && historyJobs().length > 1) {
        return new Promise(() => {})
      }
      if (mode === 'controlledpoll' && historyRead(path) && path.startsWith('/health/jobs?') && historyJobs().length > 1) {
        const read = deferred()
        reads.push(read)
        return read.promise
      }
      if (mode === 'empty') return { ...JOBS, runs: [] }
      if (mode === 'dailydated') {
        const day = ts => { const d = new Date(ts * 1000)
          return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` }
        const runs = dailyRuns(JOBS).map(r => ({ ...r, date: day(r.at_ts) }))
        return { ...JOBS, runs, trend: dailyTrend(runs) }
      }
      if (mode === 'daily') return { ...JOBS, runs: dailyRuns(JOBS), trend: dailyTrend(dailyRuns(JOBS)) }
      if (mode === 'trendcap' && path.startsWith('/health/jobs?')) {
        return { ...JOBS, trend: { ...JOBS.trend, trend_truncated: true } }
      }
      if (path.startsWith('/health/jobs/run')) {
        const id = new URL(path, 'https://fixture.invalid').searchParams.get('id')
        if (mode === 'controlledbody') {
          const read = { ...deferred(), id }
          reads.push(read)
          return read.promise
        }
        if (mode === 'wrongrun') return { ok: true, id: 'run-other-foreign', body: FOREIGN_BODY, body_len: FOREIGN_BODY.length }
        return { ok: true, id, body: FULL_BODY, body_len: FULL_BODY.length }
      }
      // Unlike a permissive stub, a bounded server window really omits older history. Widening a
      // custom date range can recover that history only by asking the server for it again.
      if (mode === 'windowed' && path.startsWith('/health/jobs?')) {
        const window = new URL(path, 'https://fixture.invalid').searchParams.get('window')
        const days = { '24h': 1, '7d': 7, '30d': 30 }[window]
        const cutoff = new Date(TODAY_ISO + 'T00:00:00')
        cutoff.setDate(cutoff.getDate() - (days || 0) + 1)
        return { ...JOBS, window, runs: days ? JOBS.runs.filter(r => r.date && new Date(r.date + 'T00:00:00') >= cutoff) : JOBS.runs }
      }
      if (path.startsWith('/health/jobs')) return JOBS
      throw new Error(`unexpected path: ${path}`)
    },
    os: { notify: () => {} },
    i18n: {
      // The registration-time door: resolve through the registered bundles, like the app does.
      t: (key, ...args) => {
        stub.calls.registerKeys.push(key)
        return stub.resolveKey(PLUGIN_ID, key, args)
      },
      register: table => stub.registerBundles(PLUGIN_ID, table)
    },
    register: r => registrations.push(r)
  }
  const plugin = (await import(`${HERE_URL.href}plugin-health-under-test.mjs?v=${++version}`)).default
  if (plugin?.id !== PLUGIN_ID) fail(`plugin id changed: ${plugin?.id}`)
  plugin.register(ctx)

  const pageReg = registrations.find(r => r.area === 'routes' && r.data?.path === ROUTE)
  const navReg = registrations.find(r => r.area === 'sidebar.nav' && r.data?.path === ROUTE)
  if (!pageReg || !navReg) {
    fail(`route/sidebar registration missing: ${registrations.map(r => `${r.area}:${r.data?.path || r.id}`)}`)
    return null
  }
  if (!navReg.data.label) fail('the sidebar entry has no label (a raw key would be printed)')
  const hostEl = document.createElement('div')
  document.body.appendChild(hostEl)
  const onError = e => errors.add(String(e?.message || e))
  const root = createRoot(hostEl, { onUncaughtError: onError, onRecoverableError: onError })
  await act(async () => { root.render(React.createElement(pageReg.render)) })
  await act(async () => { await new Promise(r => setTimeout(r, 80)) })
  activeMount = { root, el: hostEl }
  // Metro (2.5.0): ONE view, no tabs. The former Chronicle journal and Health diagnostics are the ONE
  // History detail, opened by the header's History button; both targets navigate there.
  if (hostEl.querySelector('[role="tab"], [role="tablist"], [data-slot="tabs-trigger"]')) {
    fail('a tab strip is back (the four tabs were removed in 2.5.0)')
  }
  if (!hostEl.querySelector('.wa-metro')) fail('the page does not open on the Metro view (.wa-metro)')
  // target 'review' opens the Your review station (the review desk) instead of History.
  const opener = target === 'review'
    ? hostEl.querySelector('[data-wa-station="review"]')
    : hostEl.querySelector('[data-wa-nav="history"]')
  const which = target === 'review' ? 'review' : 'history'
  if (!opener) fail(`the ${which} opener is missing (${target === 'review' ? '[data-wa-station="review"]' : '[data-wa-nav="history"]'})`)
  else {
    if (opener.getAttribute('aria-pressed') !== 'false') fail(`${which} is pressed before it was clicked`)
    if (which === 'history') historyFrom = gets.length
    await click(opener, 80)
    if (opener.getAttribute('aria-pressed') !== 'true') fail(`${which} is not aria-pressed after its click`)
  }
  if (!hostEl.querySelector(`.wa-metro-detail[data-for="${which}"]`)) fail(`${which} did not open its detail (${target})`)
  if (hostEl.querySelectorAll('.wa-metro-detail').length > 1) fail('more than one detail is open')
  // 2.5.1: the History detail opens on the m-13 run list; the journal + diagnostics checked here are its
  // "Full technical log", one click away.
  if (which === 'history') {
    if (hostEl.querySelector('.pa-root')) fail('the technical log is open before "Full technical log" was pressed')
    const full = [...hostEl.querySelectorAll('.wa-metro-detail[data-for="history"] button')]
      .find(b => b.textContent.replace(/\s+/g, ' ').trim() === 'Full technical log')
    if (!full) fail('the History detail has no "Full technical log" button')
    else await click(full, 120)
  }
  if (which === 'history' && !hostEl.querySelector('.pa-root')) {
    fail('the History detail does not hold the reused run history (.pa-root)')
  }

  const clean = hostEl.cloneNode(true)
  clean.querySelectorAll('style').forEach(s => s.remove())
  return {
    el: hostEl,
    target,
    text: clean.textContent.replace(/\s+/g, ' ').trim(),
    registered: stub.calls.registered.at(-1),
    registrations,
    nav: navReg,
    page: pageReg,
    errors,
    reads,
    gets,
    historyGets,
    historyJobs,
    posts
  }
}

const setField = (el, value) => {
  Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(el, value)
  el.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
}
const click = async (node, settle = 40) => {
  if (!node) { fail('the element to click was not found'); return }
  await act(async () => { node.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })) })
  await act(async () => { await new Promise(r => setTimeout(r, settle)) })
}
const type = async (node, value, settle = 40) => {
  await act(async () => { setField(node, value) })
  await act(async () => { await new Promise(r => setTimeout(r, settle)) })
}

const hover = async node => {
  await act(async () => { node.dispatchEvent(new dom.window.MouseEvent('mouseover', { bubbles: true })) })
  await act(async () => { await new Promise(r => setTimeout(r, 30)) })
}
const unhover = async node => {
  await act(async () => {
    node.dispatchEvent(new dom.window.MouseEvent('mouseout', { bubbles: true, relatedTarget: null }))
  })
  await act(async () => { await new Promise(r => setTimeout(r, 30)) })
}
const rows = el => [...el.querySelectorAll('.pa-log')]
const drawerOf = el => el.querySelector('.pa-drawer')
const visibleText = el => {
  const clone = el.cloneNode(true)
  clone.querySelectorAll('style').forEach(s => s.remove())
  return clone.textContent.replace(/\s+/g, ' ')
}
const heights = (el, selector) => [...el.querySelectorAll(selector)].map(n => n.style.height)
const preset = (el, label) => [...el.querySelectorAll('.pa-seg button')].find(b => (b.textContent || '').trim() === label)
const chip = (el, label) => [...el.querySelectorAll('button')]
  .filter(b => !b.closest('.pa-seg'))
  .find(b => (b.textContent || '').trim() === label)
const selFace = (el, id) => el.querySelector(`.pa-selwrap[data-sel="${id}"] .pa-sel`)
const popOpts = el => [...el.querySelectorAll('.pa-pop .pa-opt')]
const optLabel = o => (o.querySelector('.pa-sel-txt')?.textContent || '').trim()
const optNamed = (el, text) => popOpts(el).find(o => optLabel(o) === text)
const kpiFigure = (el, labelText) => {
  const card = [...el.querySelectorAll('.pa-kpi')].find(c => (c.children[0].textContent || '').trim() === labelText)
  const fig = card ? card.querySelector('.pa-kpi-fig') : null
  return fig ? fig.textContent.trim() : null
}
const clockOf = run => /T(\d{2}:\d{2}):\d{2}/.exec(String(run.at || ''))?.[1] || '—'
const durationOf = run => typeof run.duration_ms !== 'number' || !Number.isFinite(run.duration_ms) || run.duration_ms < 0
  ? '—' : run.duration_ms < 1000 ? `${Math.round(run.duration_ms)} ms` : `${(run.duration_ms / 1000).toFixed(1)} s`
const outcomeOf = run => ({ completed: 'Completed', failed: 'Failed', running: 'Running', claimed: 'Starting', unknown: 'Unknown' }[run.status] || 'Unknown')
const notificationOf = run => ({ delivered: 'Delivered', suppressed: 'Silent', queued: 'Queued', failed: 'Delivery failed', none: 'No record' }[run.delivery] || 'No record')
const synopsisOf = run => run.body_source === 'error' && String(run.body || '').trim()
  ? String(run.body).trim().split(/\r?\n/)[0]
  : run.findings?.length ? FINDING_CASES.find(item => item.raw === (run.findings.find(item => item.tone === 'bad') || run.findings[0]).raw)?.en
    : run.status === 'failed' ? 'No separate error text is recorded.' : 'No error reported.'
// jsdom has no visibility/layout engine. Exclude closed native disclosure content explicitly;
// textContent alone would let hidden findings, metadata and failed-copy feedback pass.
const exposedText = node => {
  const clone = node.cloneNode(true)
  clone.querySelectorAll('style, [hidden], [aria-hidden="true"]').forEach(n => n.remove())
  clone.querySelectorAll('details:not([open])').forEach(details => {
    for (const child of [...details.children]) if (child.tagName !== 'SUMMARY') child.remove()
  })
  return clone.textContent.replace(/\s+/g, ' ').trim()
}
async function openAdvanced(panel) {
  const details = panel.el.querySelector('details.ch-filters-advanced')
  const summary = details?.querySelector(':scope > summary')
  if (!summary || !summary.textContent.includes('Job & date filters')) {
    fail(`${panel.target}: the job/date disclosure has no named native summary`); return null
  }
  if (!details.open) {
    await click(summary)
    // jsdom may omit the native summary default action, just as for Technical details.
    if (!details.open) await act(async () => { details.open = true })
  }
  if (!details.open) fail(`${panel.target}: the advanced job/date disclosure did not open`)
  return details
}
async function openTechnical(inspector) {
  const details = inspector?.querySelector('details.ch-technical')
  const summary = details?.querySelector(':scope > summary')
  if (!summary || summary.textContent.trim() !== 'Technical details') {
    fail('the inspector has no named native Technical details disclosure'); return null
  }
  if (!details.open) {
    await click(summary)
    // Some jsdom versions omit the native summary default action. Never click twice.
    if (!details.open) await act(async () => { details.open = true })
  }
  if (!details.open) fail('Technical details did not open')
  return details
}
function assertDurationSnapshot(inspector, scope, selectedId, label) {
  if (!inspector) { fail(`${label}: selected inspector is missing`); return }
  const expected = scope.filter(run => typeof run.duration_ms === 'number' && Number.isFinite(run.duration_ms)
    && run.duration_ms >= 0 && typeof run.at_ts === 'number' && Number.isFinite(run.at_ts) && clockOf(run) !== '—')
  const actual = [...inspector.querySelectorAll('.ch-duration-list .ch-duration-row')]
  const keys = actual.map(node => node.getAttribute('data-key'))
  if (keys.join('|') !== expected.map(run => run.id).join('|') || new Set(keys).size !== keys.length) {
    fail(`${label}: duration snapshot exact membership/order ${keys.join('|')} != ${expected.map(run => run.id).join('|')}`)
  }
  const max = Math.max(0, ...expected.map(run => run.duration_ms))
  for (const node of actual) {
    const run = expected.find(run => run.id === node.getAttribute('data-key'))
    if (!run) continue
    if (node.getAttribute('data-status') !== run.status
      || node.getAttribute('data-selected') !== (run.id === selectedId ? '1' : '0')) fail(`${label}: duration identity/status/selection changed: ${run.id}`)
    const clock = node.querySelector('time')
    if (clock?.textContent !== clockOf(run) || clock?.getAttribute('datetime') !== run.at) fail(`${label}: duration clock lost its exact stamp: ${run.id}`)
    const value = node.querySelector('.ch-duration-value')?.textContent
    const job = JOBS.registry.find(job => job.id === run.job_id)
    const name = job?.name || `deleted job (${run.job_id})`
    if (value !== durationOf(run) || node.getAttribute('aria-label') !== `${run.at} · ${name} · ${durationOf(run)}`) fail(`${label}: duration label invented or lost source values: ${run.id}`)
    const track = node.querySelector('.ch-duration-track')
    const width = parseFloat(track?.querySelector('i')?.style.width)
    const want = max > 0 ? run.duration_ms / max * 100 : 0
    if (track?.getAttribute('aria-hidden') !== 'true' || !Number.isFinite(width)
      || Math.abs(width - want) > 0.001) fail(`${label}: duration bar is not proportional to numeric milliseconds: ${run.id} (${width} != ${want})`)
  }
  if (!expected.length && (inspector.querySelector('.ch-duration-list')
    || !exposedText(inspector).includes('No recorded duration can be placed in this snapshot.'))) fail(`${label}: an unplaceable snapshot invented duration bars or omitted its empty explanation`)
}
// Assert the actual mounted surface, not nodes saved before switching tabs. Chronicle identities
// are exact; Health must project the same scope into all KPI figures and the run flow.
function assertScope(panel, expected, label) {
  const { el, target } = panel
  if (!el.isConnected) { fail(`${target} ${label}: detached panel`); return }
  if (target === 'chronicle') {
    const actual = rows(el).map(r => r.getAttribute('data-key')).sort()
    const want = expected.map(r => r.id).sort()
    if (actual.join('|') !== want.join('|') || new Set(actual).size !== actual.length) {
      fail(`Chronicle ${label}: exact run membership ${actual.join('|')} != ${want.join('|')}`)
    }
    return
  }
  const figures = ['Runs', 'Failed', 'Silent', 'Delivered', 'Findings'].map(l => kpiFigure(el, l))
  const want = [expected.length, expected.filter(r => r.status === 'failed').length,
    expected.filter(r => r.silent).length, expected.filter(r => r.delivery === 'delivered').length,
    expected.filter(r => r.findings?.length).length].map(String)
  if (figures.join('/') !== want.join('/')) fail(`Health ${label}: KPI scope ${figures.join('/')} != ${want.join('/')}`)
  const stamped = expected.filter(r => typeof r.at_ts === 'number')
  const oldest = stamped.reduce((min, r) => (r.date && r.date < min ? r.date : min), TODAY_ISO)
  const span = Math.round((Date.parse(TODAY_ISO) - Date.parse(oldest)) / 86400000) + 1
  const flowStart = new Date()
  flowStart.setDate(flowStart.getDate() - (Math.min(31, Math.max(12, span)) - 1))
  const flowDay = `${flowStart.getFullYear()}-${String(flowStart.getMonth() + 1).padStart(2, '0')}-${String(flowStart.getDate()).padStart(2, '0')}`
  const flowExpected = stamped.filter(r => r.date >= flowDay && r.date <= TODAY_ISO).length
  const flowActual = [...el.querySelectorAll('.pa-bar-count')].reduce((n, b) => n + Number(b.textContent || 0), 0)
  if (flowActual !== flowExpected) fail(`Health ${label}: daily flow scope ${flowActual} != ${flowExpected}`)
}


// ===========================================================================
// 1) Registration · fixed layers · English frame
// ===========================================================================
let p = await mount('en')
if (!p) {
  console.error('render check FAILED — the panel did not register a page')
  process.exit(1)
}
if (p.page.data.path !== ROUTE) fail(`page path wrong: ${p.page.data.path}`)
if (p.nav.data.path !== ROUTE) fail(`sidebar path wrong: ${p.nav.data.path}`)
if (p.nav.data.label !== 'Wiki Automation') {
  fail(`the sidebar label is not the visible name: ${JSON.stringify(p.nav.data.label)}`)
}
if (RAW_KEY.test(String(p.nav.data.label || ''))) fail('the sidebar label is a raw i18n key')
if (!p.nav.data.codicon) fail('the sidebar entry has no icon')
if (p.registrations.map(r => r.area).join('|') !== 'routes|sidebar.nav') {
  fail(`the panel must contribute only a page and a sidebar entry: ${p.registrations.map(r => r.area)}`)
}
// The registration-time title goes through the APP translator door (ctx.i18n.t), not a local table.
if (!stub.calls.registerKeys.includes('wa.title')) {
  fail('the registration-time title was not resolved through ctx.i18n.t')
}
// ONE bundle, English, dot-path, registered under the plugin's own id.
if (stub.calls.registered.length !== 1) {
  fail(`exactly one bundle must be registered, got ${stub.calls.registered.length}`)
} else {
  const reg = stub.calls.registered[0]
  if (reg.id !== PLUGIN_ID) fail(`the bundle is registered under the wrong id: ${reg.id}`)
  if (reg.locales.join('|') !== 'en') fail(`the bundle must hold exactly 'en': ${reg.locales.join('|')}`)
}
must(p.text, ['Runs', 'Failed', 'Silent', 'Delivered', 'Findings',
  'Run flow', 'Activity by job',
  'Today', 'Last 7 days', 'Last 30 days', 'All', 'All jobs',
  'Fleet Watch', 'Watch Dog', 'Wiki Ingest Watch'], 'Health frame (en)')
noRawKeys(p.text, 'page')
if (p.errors.size) fail(`the panel threw: ${[...p.errors].join(' | ')}`)

const kpiHeights = new Set([...p.el.querySelectorAll('.pa-kpi')].map(k => k.style.minHeight))
if (kpiHeights.size !== 1 || !kpiHeights.has('86px')) fail(`KPI floors are not one layer: ${[...kpiHeights]}`)
// The card is a FLOOR, not a box: as a fixed 108px box it made flex-shrink squeeze its own children
// (label 26→18.3, sparkline 16→11.3, caption 26→18.4) and cut a two-line caption in half — measured on
// the real engine at 466/560 px. `minHeight` + the floors asserted below are what replaced that.
const kpiStyles = [...p.el.querySelectorAll('.pa-kpi')].map(k => k.style.minHeight)
if (kpiStyles.some(v => v !== '86px')) fail(`a KPI card is not an 86px floor: ${kpiStyles.join('/')}`)
const kpiFixed = [...p.el.querySelectorAll('.pa-kpi')].filter(k => k.style.height).length
if (kpiFixed) fail(`${kpiFixed} KPI card(s) carry a fixed height again — a fixed box is what cut the caption`)
// ONE line for the label; the explanation lives in the card's tooltip, not in a caption box.
if ([...p.el.querySelectorAll('.pa-kpi')].some(k => k.children.length > 4)) fail('a KPI card grew a caption box again')
const labBox = p.el.querySelector('.pa-kpi .pa-kpi-lab')
if (!labBox || labBox.style.height !== '14px' || labBox.style.overflow !== 'hidden') {
  fail(`the KPI label box is not a pinned one-line box: ${labBox?.style.height} / ${labBox?.style.overflow}`)
}
const chartHeights = new Set(heights(p.el, '.pa-chart'))
if (chartHeights.size !== 1 || !chartHeights.has('60px')) fail(`chart height is not fixed: ${[...chartHeights]}`)
// KPI: 5 cards, figures from the FILTERED rows (fixture: 5 runs · 1 failed · 3 silent · 1 delivered ·
// 1 with findings).
if (p.el.querySelectorAll('.pa-kpi').length !== 5) fail('the KPI card count is not 5')
const kpisStart = ['Runs', 'Failed', 'Silent', 'Delivered', 'Findings'].map(l => kpiFigure(p.el, l))
if (kpisStart.join('/') !== '5/1/3/1/1') fail(`KPI figures are wrong: ${kpisStart.join('/')} (expected 5/1/3/1/1)`)
// TIPS ARE THEMED: a native `title` attribute opens the operating system's box (which does not
// follow the theme) — there must be none; the tip comes out in the panel's own layer (.pa-tip).
if (p.el.querySelectorAll('[title]').length) {
  fail(`a native title attribute is left: ${[...p.el.querySelectorAll('[title]')].map(e => e.getAttribute('title')).slice(0, 3)}`)
}
const kpiCard = [...p.el.querySelectorAll('.pa-kpi')].find(c => (c.children[0].textContent || '').trim() === 'Failed')
await hover(kpiCard)
if (!/Failed: 1/.test(p.el.querySelector('.pa-tip')?.textContent || '')) {
  fail(`the KPI tip did not appear in the themed layer: ${[...p.el.querySelectorAll('.pa-tip')].map(t => t.textContent)}`)
}
await unhover(kpiCard)
if (p.el.querySelectorAll('.pa-tip').length) fail('the tip does not close when the pointer leaves')

// THE DELTA'S COLOUR STATES THE MEANING OF THE MOVE, NOT THE ARROW'S DIRECTION. The fixture's Failed
// and Runs cards both rose by the same kind of amount; a rise is bad on Failed and means nothing on
// Runs, so the two must NOT share a colour. Measured before the fix: "▲2" on Delivered was painted in
// the warning colour.
const deltaOf = labelText => {
  const card = [...p.el.querySelectorAll('.pa-kpi')]
    .find(c => (c.children[0].textContent || '').trim() === labelText)
  const d = card?.querySelector('.pa-delta')
  return d ? { dir: d.getAttribute('data-dir'), mark: (d.textContent || '').trim() } : null
}
const deltaDirs = [...p.el.querySelectorAll('.pa-delta')].map(d => d.getAttribute('data-dir'))
if (deltaDirs.some(v => !['good', 'bad', 'flat'].includes(v))) {
  fail(`a delta is coloured by direction again: ${deltaDirs.join('/')}`)
}
const failedDelta = deltaOf('Failed')
if (!failedDelta || !/^▲/.test(failedDelta.mark) || failedDelta.dir !== 'bad') {
  fail(`a RISE on Failed is not painted as bad news: ${JSON.stringify(failedDelta)}`)
}
const runsDelta = deltaOf('Runs')
if (!runsDelta || !/^▲/.test(runsDelta.mark) || runsDelta.dir !== 'flat') {
  fail(`a RISE on Runs is painted as news though nothing is said about runs: ${JSON.stringify(runsDelta)}`)
}
// ONE TYPE SCALE: every size the panel writes inline must be a step of the TYPE table.
const TYPE_STEPS = [10.5, 11, 12, 13, 15, 16, 24]
const inlineSizes = new Set()
p.el.querySelectorAll('[style]').forEach(el => {
  const v = parseFloat(el.style.fontSize)
  if (v) inlineSizes.add(v)
})
const offScale = [...inlineSizes].filter(v => !TYPE_STEPS.includes(v))
if (offScale.length) fail(`font sizes off the TYPE scale: ${offScale.join('/')}`)
// The label box holds ONE line, so a label longer than it can hold would be cut silently.
const labels = [...p.el.querySelectorAll('.pa-kpi-lab')].map(l => (l.textContent || '').trim())
if (labels.length !== 5) fail(`the KPI labels are not five boxes: ${labels.length}`)
const longLabels = labels.filter(l => l.length > 12)
if (longLabels.length) fail(`a KPI label cannot fit its one-line box: ${longLabels.join('/')}`)
// 2.5.0: the History detail's head names it; the old per-view 'Wiki Health' title is gone (contract § Removed).
if (p.el.querySelector('.pa-topbar .pa-title') || /\bWiki Health\b/.test(p.text)) fail('the removed per-view title Wiki Health is back')
if (p.el.querySelector('.pa-topbar .pa-subtitle')) fail('the title bar carries a subtitle again')
if ([...p.el.querySelectorAll('.pa-kpi')].some(c => c.getAttribute('tabindex') !== '0')) {
  fail('a KPI card carries its hint in a tip the keyboard cannot reach')
}
const failedCard = [...p.el.querySelectorAll('.pa-kpi')].find(c => (c.children[0].textContent || '').trim() === 'Failed')
if (failedCard?.getAttribute('data-state') !== 'bad') fail('a non-zero Failed card does not mark its surface')
const runsCard = [...p.el.querySelectorAll('.pa-kpi')].find(c => (c.children[0].textContent || '').trim() === 'Runs')
if (runsCard?.hasAttribute('data-state')) fail('the Runs card is painted as an alarm')
const refreshTipHost = p.el.querySelector('[aria-label="Refresh"]')
await hover(refreshTipHost)
if (!/Refresh/.test(p.el.querySelector('.pa-tip')?.textContent || '')) fail('the refresh button has no themed tip')
await unhover(refreshTipHost)

// Chart: one DAY bucket from the oldest run in scope to today (12 minimum, 31 maximum); empty days a
// 2 px line (fixture: two runs today, one 20 days ago -> 21 buckets, two filled).
let bars = [...p.el.querySelectorAll('.pa-bar-col')]
if (bars.length !== 21) fail(`the run flow chart must hold 21 buckets: ${bars.length}`)
const zeroBars = bars.filter(b => b.querySelector('.pa-bar')?.getAttribute('data-zero') === '1').length
if (zeroBars !== 19) fail(`the empty day count must be 19 (today and 20 days ago are filled): ${zeroBars}`)
if (bars.some(b => !b.querySelector('.pa-bar-day'))) fail('a day has no baseline label (.pa-bar-day)')
must(p.text, ['last 21 days'], 'run flow heading')
const flowSum = p.el.querySelector('.pa-sec .pa-secright .pa-flowsum')?.textContent || ''
const flowTotal = [...bars].reduce((n, b) => n + Number(b.querySelector('.pa-bar-count')?.textContent || 0), 0)
if (!flowSum.startsWith(`${flowTotal} run`) || !/peak \d\d\.\d\d$/.test(flowSum)) {
  fail(`the run flow summary does not state the drawn total and the busiest day: "${flowSum}" (${flowTotal})`)
}
if (bars.filter(b => b.getAttribute('data-zero') === '1').length !== zeroBars) {
  fail('a quiet day is not marked on its column (data-zero), so it cannot be drawn quieter')
}
const heads = [...p.el.querySelectorAll('.pa-sec > .pa-sectitle')]
if (!heads.every(h => h.children[1]?.classList.contains('pa-secmeta'))) {
  fail('a section head does not carry its metadata on its own line (.pa-secmeta)')
}

// Section CARDS: the heading is INSIDE the card (above a separator), the body too.
let cards = [...p.el.querySelectorAll('.pa-sec')]
if (cards.length !== 4) fail(`History must have four section cards (freshness · flow · activity · run journal): ${cards.length}`)
if (p.el.querySelector('.pa-tl-lane, .pa-kindrow')) fail('Health revived the run timeline or job distribution')
// C: the freshness ring is measured from the cycle the scheduler states (last run · next run) — never
// from parsing a cadence string, and never a ring drawn for a job that reports no cycle.
const frCard = cards.find(c => c.querySelector('.pa-ring'))
if (!frCard) fail('the freshness card is missing')
else {
  if (String(frCard.querySelector('.pa-fr')?.style.minHeight) !== '122px') {
    fail(`freshness does not use its floor: ${frCard.querySelector('.pa-fr')?.style.minHeight}`)
  }
  if (frCard.querySelector('.pa-fr')?.style.height) {
    fail('the freshness card is a fixed box again — its orbs painted 38.6px outside it at 466/560 px')
  }
  // The ring's caption lives BESIDE the circle: inside it, 66.5px of text sat in a 70px painted
  // interior (1.7px a side), which is what the user's red box marked.
  const ringCol = frCard.querySelector('.pa-ringcol')
  if (!ringCol) fail('the ring and its caption are not one column')
  if (ringCol.querySelector('.pa-ring-mid s, .pa-ring-mid span')) {
    fail('a caption is drawn INSIDE the ring again — its interior is 70px wide')
  }
  if (ringCol.querySelectorAll(':scope > *').length !== 2
    || !ringCol.lastElementChild?.classList.contains('pa-fr-cap')) {
    fail('the ring has no caption beside it')
  }
  if (Math.round(parseFloat(frCard.querySelector('.pa-ring')?.style.width)) !== 88) {
    fail(`the ring is not the 88px the caption column was measured for: ${frCard.querySelector('.pa-ring')?.style.width}`)
  }
  const ring = frCard.querySelector('.pa-ring')
  const arc = ring?.querySelectorAll('circle')[1]
  const offset = Number(arc?.getAttribute('stroke-dashoffset'))
  if (!Number.isFinite(offset) || offset < 0) fail(`the ring has no measured arc: ${offset}`)
  const mid = ring?.querySelector('.pa-ring-mid b')?.textContent || ''
  // The ring's label is compact: it has 92px and must not wrap (the user saw "26 min ago" break
  // over two lines and spill past the circle).
  if (!/^\d+ (s|min|h)$/.test(mid.trim())) fail(`the ring does not report a compact age: ${mid}`)
  // The headline states the CYCLE, not the delivery: the summary line beside it counts failures, so
  // "every run delivered" over "1 failed" would be the panel contradicting itself in two lines.
  const head = frCard.querySelector('.pa-fr-head')?.textContent || ''
  const soonest = (JOBS.registry || []).filter(j => j.live && j.next_run_at)
    .map(j => Date.parse(j.next_run_at)).sort((a, b) => a - b)[0]
  const nowMs = Date.parse(JOBS.generatedAt)
  const expectHead = `next run in ${Math.round((soonest - nowMs) / 60000)} min`
  if (head !== expectHead) {
    fail(`the freshness headline does not state the real cycle: ${head} (expected ${expectHead})`)
  }
  const summary = frCard.querySelector('.pa-fr-sum')?.textContent || ''
  if (/delivered/i.test(head) && /failed/i.test(summary) && !/0 failed/.test(summary)) {
    fail(`the headline claims delivery while the summary counts a failure: ${head} / ${summary}`)
  }
  const orbs = frCard.querySelectorAll('.pa-orb')
  const liveIds = (JOBS.registry || []).filter(j => j.live).map(j => j.id)
  const shownIds = new Set((JOBS.runs || []).map(r => r.job_id))
  const expectOrbs = liveIds.filter(id => shownIds.has(id)).length
  if (orbs.length !== expectOrbs) {
    fail(`every live job in the filter should draw an orb: ${orbs.length} of ${expectOrbs}`)
  }
  // The orb's OWN line is one line ("no cycle", the tooltip carries the full phrase: a wrapped meta made
  // one orb taller than its neighbours and grew a scrollbar in a three-job card).
  const cycleless = [...orbs].filter(o => /no cycle/.test(o.textContent)).length
  if (cycleless !== 1) {
    fail(`a job with no measured cycle must say so instead of drawing a bare ring: ${cycleless}`)
  }
  const strokes = [...frCard.querySelectorAll('circle')].map(c => c.getAttribute('stroke'))
  if (strokes.some(st => !String(st).startsWith('var(--ui-'))) {
    fail(`a ring is painted with a non-theme colour: ${strokes.join(' ')}`)
  }
}
if (!cards.every(c => c.children.length === 2)) fail('every card must hold two children (head strip + body)')
if (!cards.every(c => c.children[0].classList.contains('pa-sectitle'))) fail('a card does not start with its head strip')
const deliveredCard = [...p.el.querySelectorAll('.pa-kpi')]
  .find(c => (c.children[0].textContent || '').trim() === 'Delivered')
if (deliveredCard?.getAttribute('data-state') === 'warn') fail('the Delivered KPI card is painted as a warning')
if (deliveredCard?.querySelector('.pa-dot')) fail('the Delivered KPI card carries a warning dot')
// Chronicle owns the only journal; diagnostics above remain exclusively on Health.
p = await mount('en', 'data', 'chronicle')
must(p.text, ['Run journal', 'Select a run',
  'Today', 'Last 7 days', 'Last 30 days', 'All', 'All jobs', 'Newest first',
  'Fleet Watch', 'Watch Dog', 'Wiki Ingest Watch', 'deleted job',
  'Completed', 'Failed', 'Running', '10:22'], 'Chronicle frame (en)')
noRawKeys(p.text, 'Chronicle frame')
if (p.errors.size) fail(`Chronicle threw: ${[...p.errors].join(' | ')}`)
if (p.el.querySelector('.pa-log-head, .pa-grid, table')) fail('Chronicle revived the obsolete table journal')
if (p.el.querySelectorAll('.pa-logwrap').length !== 1
  || p.el.querySelectorAll('.pa-logwrap.ch-journal').length !== 1) fail('Chronicle must mount exactly one chronological journal')
const journal = p.el.querySelector('.ch-journal')
const journalMain = journal?.querySelector(':scope > .ch-journal-main')
const journalScroll = journalMain?.querySelector(':scope > .ch-scroll')
const inspectorEmpty = journal?.querySelector(':scope > .ch-inspector-empty')
if (!journalScroll || !inspectorEmpty || journal.children.length !== 2) {
  fail('the journal must pair a scrollable chronology with an adjacent empty inspector')
}
if (journalMain?.querySelector('.ch-axes')) fail('the chronology carries an explanation sentence again')
const advancedFilters = p.el.querySelector('details.ch-filters-advanced')
if (!advancedFilters || advancedFilters.open || !advancedFilters.querySelector('.pa-selwrap[data-sel="jobs"]')
  || !advancedFilters.querySelector('.pa-dateface')) fail('advanced job/date filters must remain available behind a closed disclosure')
const journalSearch = p.el.querySelector('input[aria-label="Filter runs — job, output or status…"]')
if (!journalSearch || journalSearch.closest('details')) fail('journal search must exist outside advanced filters')
if (inspectorEmpty?.tagName !== 'ASIDE' || !inspectorEmpty.querySelector('[data-slot="panel-empty"]')) {
  fail('the unselected inspector must be an aside with the kit empty state')
}
const logCard = [...p.el.querySelectorAll('.pa-sec')].find(c => c.querySelector('.ch-journal'))
if (!logCard) fail('the Chronicle journal card was not found')
else if (logCard.children.length !== 2 || !logCard.children[0].classList.contains('pa-sectitle')) {
  fail('the Chronicle journal card must hold its head strip and body together')
}
if (logCard?.children[1] !== journal) fail('the chronology and inspector are not in the journal card body')

// NO DELETE SURFACE: the panel never writes into the cron history and offers no delete button.
if ([...p.el.querySelectorAll('button')].some(b => /Clear Log|Delete|Cancel/.test(b.textContent || ''))) {
  fail('a delete button is still present — the panel must not delete the cron history')
}
if (p.posts.some(x => /clear|delete/i.test(x.path))) fail(`a delete request went out: ${p.posts.map(x => x.path)}`)

// One run is one chronological entry: status ring, HH:MM/full date, honest error preview,
// readable outcome + duration, and disclosure. Notification belongs to the selected summary,
// independently of status; the full backend values remain in technical metadata.
if (rows(p.el).length !== 5) fail(`5 runs must give 5 entries: ${rows(p.el).length}`)
const entryParts = ['ch-point', 'ch-time', 'ch-description', 'ch-facts', 'ch-caret']
const registryNames = new Map(JOBS.registry.map(job => [job.id, job.name || `deleted job (${job.id})`]))

for (const entry of rows(p.el)) {
  const run = JOBS.runs.find(run => run.id === entry.getAttribute('data-key'))
  if (!run) { fail('a chronological entry does not identify a fixture run'); continue }
  if (!entry.classList.contains('ch-run') || entry.parentElement !== journalScroll
    || entryParts.some((cls, i) => !entry.children[i]?.classList.contains(cls))
    || entry.children.length !== entryParts.length) fail(`the chronological entry shape changed: ${run.id}`)
  if (entry.style.height || entry.style.gridTemplateColumns) fail('journal entries override the responsive CSS layout inline')
  const label = registryNames.get(run.job_id)
  const expectedName = `${run.at || 'no date'} · ${label} · ${run.status_label || run.status}`
  if (entry.getAttribute('aria-label') !== expectedName) fail(`the entry accessible name lost time/job/status: ${entry.getAttribute('aria-label')}`)
  if (entry.getAttribute('role') !== 'button' || entry.tabIndex !== 0
    || entry.getAttribute('aria-expanded') !== 'false'
    || entry.getAttribute('aria-controls') !== 'chronicle-run-detail') fail(`the entry lost its keyboard disclosure contract: ${run.id}`)
  if (entry.querySelector('.ch-point')?.getAttribute('data-status') !== run.status
    || entry.querySelector('.ch-point')?.getAttribute('aria-hidden') !== 'true') fail('the decorative spine point lost its run status')
  if (entry.querySelector('.ch-time > span')?.textContent !== (run.date || 'no date')) fail(`the entry date is not its source date: ${run.id}`)
  if (entry.querySelector('time')?.getAttribute('datetime') !== (run.at || null)) fail(`the clock lost its machine-readable stamp: ${run.id}`)
  if (entry.querySelector('.ch-description strong')?.textContent !== label) fail(`the entry lost its job name: ${run.id}`)
  if (entry.querySelector('.ch-time time')?.textContent !== clockOf(run)) fail(`the entry clock must be HH:MM without losing its full date: ${run.id}`)
  if (entry.querySelector('.ch-preview')?.textContent !== synopsisOf(run)) fail(`the entry error preview is not truthful to its body source: ${run.id}`)
  const outcome = entry.querySelector('.ch-facts .ch-outcome')
  if (outcome?.textContent.trim() !== outcomeOf(run) || outcome?.getAttribute('data-status') !== run.status
    || outcome?.querySelector('.ch-outcome-dot')?.getAttribute('aria-hidden') !== 'true') fail(`the entry lost its readable outcome/decorative status dot: ${run.id}`)
  if (entry.querySelector('.ch-run-duration')?.textContent !== durationOf(run)) fail(`the entry duration invented or lost its numeric value: ${run.id}`)
  if (entry.querySelector('.pa-badge, .ch-duration-track')) fail(`the entry revived badge/track clutter instead of outcome text and duration: ${run.id}`)
  const glyph = entry.querySelector('.ch-point svg')
  const expectedPath = run.status === 'completed' ? 'M3 7 6 10 11 4' : run.status === 'failed' ? 'M4 4 10 10 M4 10 10 4'
    : ['running', 'claimed'].includes(run.status) ? 'M7 3v4l3 2' : 'M4 7h6'
  if (glyph?.getAttribute('viewBox') !== '0 0 14 14' || glyph?.getAttribute('focusable') !== 'false'
    || glyph?.querySelector('path')?.getAttribute('d') !== expectedPath) fail(`the status ring has no truthful nonfocusable glyph: ${run.id}`)
  const history = entry.querySelector('.ch-history')
  if (run.job_live === false ? history?.textContent !== 'Historical job' : Boolean(history)) fail(`the historical marker does not match the source job: ${run.id}`)
  if (history && !history.parentElement?.classList.contains('ch-jobline')) fail(`the historical marker adds a third line to a 52px row: ${run.id}`)
}
// jsdom has no container layout. Lock emitted CSS contracts here; browser screenshots own geometry.
const journalCss = String(p.el.querySelector('.pa-root > style')?.textContent || '')
const cssBody = selector => {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`${escaped}\\s*\\{([^}]*)\\}`).exec(journalCss)?.[1].replace(/\s+/g, ' ').trim() || ''
}
const journalRule = cssBody('.ch-journal')
const entryRule = cssBody('.pa-root .pa-log.ch-run')
const inspectorRule = cssBody('.ch-journal .pa-drawer')
must(journalRule, ['display:grid', 'grid-template-columns:minmax(0,1.8fr) minmax(280px,1fr)', 'min-width:0'], 'adjacent journal grid')
must(entryRule, ['grid-template-columns:24px 64px minmax(0,1fr) auto 12px', 'height:52px', 'position:relative'], 'five-column chronological entry CSS')
must(cssBody('.pa-log'), ['display:grid', 'box-sizing:border-box'], 'journal entry base CSS')
must(cssBody('.ch-run:before'), ['content:', 'position:absolute', 'left:14px', 'border-left:1px solid var(--ui-stroke-primary)'], 'chronological spine CSS')
must(cssBody('.ch-point'), ['width:24px', 'height:24px', 'border-radius:50%', 'border:1px solid var(--ui-stroke-primary)'], 'status ring CSS')
must(cssBody('.ch-time time'), ['font-family:var(--dt-font-mono,monospace)'], 'chronological clock CSS')
must(cssBody('.ch-preview'), ['display:-webkit-box', '-webkit-line-clamp:1', 'overflow-wrap:anywhere'], 'one-line error preview CSS')
must(inspectorRule, ['position:static', 'width:auto', 'height:auto', 'min-height:520px', 'opacity:1', 'transform:none', 'transition:none', 'box-shadow:none'], 'nonoverlay content-led inspector CSS')
must(cssBody('.pa-root .ch-scroll'), ['height:520px', 'max-height:520px', 'overflow-y:auto', 'overflow-x:hidden', 'overscroll-behavior:contain'], 'independent journal scrolling')
must(cssBody('.ch-journal .ch-inspector-body'), ['min-height:0', 'overflow-y:visible', 'mask-image:none'], 'readable summary and duration column')
if (!/@container\s*\(max-width:820px\)\s*\{\s*\.ch-journal\{grid-template-columns:minmax\(0,1fr\)\}/.test(journalCss)) fail('narrow Chronicle no longer stacks the adjacent inspector')
if (!/@container\s*\(max-width:560px\)\s*\{[\s\S]*?\.pa-root \.pa-log\.ch-run\{[^}]*height:64px/.test(journalCss)
  || !journalCss.includes('.ch-facts{grid-column:3;grid-row:2;display:flex;flex-wrap:wrap;align-items:center;gap:7px 12px}')) fail('narrow chronological entries lost their taller stacked outcomes')
must(cssBody('.ch-run:after'), ['inset:2px 0', 'border:1px solid transparent', 'pointer-events:none'], 'inset journal selection frame')
must(cssBody('.pa-root .ch-run[data-open="1"]:after'), ['border-color:var(--ui-stroke-primary)', 'background:var(--hx-raised)'], 'selected journal entry')
must(cssBody('.pa-root .ch-run:focus-visible'), ['outline:2px solid var(--ui-accent)'], 'keyboard-visible journal entry')
const chronicleSizes = [...journalCss.slice(journalCss.indexOf('.ch-status{'), journalCss.indexOf('.pa-root .pa-drawer-sec>')).matchAll(/font-size:([\d.]+)px/g)].map(m => Number(m[1]))
if (!chronicleSizes.length || chronicleSizes.some(size => size < 10.5)) fail(`Chronicle reduced the 10.5px micro floor: ${chronicleSizes.join('/')}`)
must(cssBody('.ch-outcome'), ['color:var(--ui-text-primary)'], 'readable outcome ink')
const statusLabels = rows(p.el).map(r => r.querySelector('.ch-outcome')?.textContent.trim())
must(statusLabels.join('|'), ['Completed', 'Failed', 'Running'], 'readable outcome labels')
// Verify both independent axes by actually selecting every run, not inspecting hidden metadata.
for (const entry of rows(p.el)) {
  const run = JOBS.runs.find(run => run.id === entry.getAttribute('data-key'))
  await click(entry, 80)
  const inspector = drawerOf(p.el)
  if (!inspector) { fail(`run selection did not mount an inspector: ${run.id}`); continue }
  const summary = inspector.querySelector('.ch-summary')
  const keys = [...(summary?.querySelectorAll('dt') || [])].map(node => node.textContent.trim())
  const values = [...(summary?.querySelectorAll('dd') || [])].map(node => node.textContent.trim())
  const claimed = /T(\d{2}:\d{2}:\d{2})/.exec(String(run.at || ''))?.[1] || 'no date'
  if (summary?.getAttribute('data-slot') !== 'panel-meta' || keys.join('|') !== 'Claimed|Duration|Notification'
    || values.join('|') !== [claimed, durationOf(run), notificationOf(run)].join('|')) fail(`three-pair summary lost its independent source values: ${run.id} (${keys.join('|')} / ${values.join('|')})`)
  if (inspector.querySelector('.pa-drawer-head .ch-outcome')?.textContent.trim() !== outcomeOf(run)) fail(`selected run status was coerced into notification: ${run.id}`)
  if (summary?.querySelector('.pa-badge') || inspector.querySelector('.pa-drawer-head .pa-badge')) fail('summary notification/outcome reverted to status-badge clutter')
  const details = inspector.querySelector('details.ch-technical')
  if (!details || details.open || summary?.closest('details')) fail('technical details must start closed without hiding the three-pair summary')
  if (exposedText(inspector).includes(run.body || '\u0000') && run.body) fail(`closed technical details leaked raw output: ${run.id}`)
  if (inspector.querySelector('.ch-error-preview')?.textContent !== synopsisOf(run)) fail(`selected reported error is not source-backed: ${run.id}`)
  assertDurationSnapshot(inspector, JOBS.runs, run.id, `selected ${run.id}`)
  await openTechnical(inspector)
  const rawMeta = inspector.querySelector('.pa-kv')
  const rawKeys = [...(rawMeta?.querySelectorAll('dt') || [])].map(node => node.textContent.trim())
  const rawValues = [...(rawMeta?.querySelectorAll('dd') || [])].map(node => node.textContent.trim())
  if (rawKeys.join('|') !== 'Run time|Job|id|Status|Delivery|Duration|Lateness|Body source'
    || rawValues.length !== 8 || rawValues[0] !== (run.at || 'no date')
    || rawValues[3] !== run.status_label || rawValues[4] !== run.delivery_label
    || rawValues[7] !== run.body_label || !details?.contains(rawMeta)) fail(`eight-pair technical metadata lost exact backend axes: ${run.id}`)
  if (run.delivery === 'delivered' && summary?.querySelector('[data-tone="warn"]')) fail('Delivered notification wears a warning tone')
  await click(inspector.querySelector('.pa-iconbtn'), 0)
}
if (drawerOf(p.el)) fail('the drawer is visible before it was opened')
if (!/10:22/.test(rows(p.el)[0].textContent) || !/Watch Dog/.test(rows(p.el)[0].textContent)) {
  fail(`the row does not carry time and job together: ${rows(p.el)[0].textContent.slice(0, 120)}`)
}
// No raw stamp leaks into the time column: a run without a stamp reads "—" (an ISO stamp is not a time).
const timeCells = rows(p.el).map(r => r.querySelector('.ch-time time')?.textContent.trim() || '')
if (timeCells.some(c => /T\d\d:/.test(c))) fail(`a raw stamp leaked into the time column: ${timeCells}`)
if (!timeCells.includes('—')) fail(`an unparsable stamp must read "—": ${timeCells}`)

// ===========================================================================
// 2) The adjacent nonmodal inspector: full body · findings · metadata · immediate close
// ===========================================================================
// Opening a row must not scroll the page: a bare focus() scrolls the node into view, which drags the
// log out from under the pointer (the user felt exactly that). The harness records every focus call.
const focusCalls = []
const realFocus = window.HTMLElement.prototype.focus
window.HTMLElement.prototype.focus = function focusSpy(opts) {
  focusCalls.push({ opts, cls: String(this.className || ''), tag: this.tagName })
  return typeof realFocus === 'function' ? realFocus.call(this, opts) : undefined
}
await click(rows(p.el)[0], 80)
const drawerFocus = focusCalls.find(c => /pa-drawer/.test(c.cls))
if (!drawerFocus) fail(`opening a row does not move focus into the detail panel: ${JSON.stringify(focusCalls)}`)
if (drawerFocus.opts?.preventScroll !== true) {
  fail(`the drawer's focus scrolls the page, so the log moves: ${JSON.stringify(drawerFocus.opts)}`)
}
if (rows(p.el)[0].getAttribute('aria-expanded') !== 'true') fail('the row does not open (aria-expanded stayed false)')
if (p.el.querySelector('.pa-logwrap').getAttribute('data-drawer') !== '1') {
  fail('the list box is not marked while the drawer is open')
}
const drawer = drawerOf(p.el)
if (!drawer) fail('the drawer did not open')

if (drawer.querySelectorAll('.pa-drawer-head, .pa-drawer-body').length !== 2) {
  fail('the drawer must hold two regions (head + body)')
}
if (drawer.getAttribute('role') !== 'region' || drawer.hasAttribute('aria-modal')) fail('the adjacent inspector must be a nonmodal region')
if (drawer.id !== 'chronicle-run-detail' || drawer.getAttribute('aria-label') !== 'Watch Dog'
  || drawer.tabIndex !== -1) fail('the inspector lost its named, programmatically focusable disclosure target')
if (drawer.parentElement !== journal || journal.children[0] !== journalMain
  || journal.children[1] !== drawer || journal.querySelector('.ch-inspector-empty')) {
  fail('the selected inspector must replace the empty aside adjacent to, not over, the chronology')
}
const headOutcome = drawer.querySelector('.pa-drawer-head .ch-outcome')
if (!headOutcome || headOutcome.textContent.trim() !== 'Failed'
  || headOutcome.getAttribute('data-status') !== 'failed'
  || headOutcome.querySelector('.ch-outcome-dot')?.getAttribute('aria-hidden') !== 'true') fail('the inspector head lost its readable selected outcome and decorative dot')
if (rows(p.el)[0].parentElement.querySelector('.pa-drawer')) fail('the drawer is rendered INSIDE the row')
must(drawer.textContent, ['Run output', 'Run time', 'Job', 'Status', 'Delivery', 'Duration', 'Lateness',
  'Body source', 'failed', 'delivered', 'Watch Dog'], 'drawer sections (the alarm run)')
const technical = drawer.querySelector('details.ch-technical')
if (!technical || technical.open) fail('the selected technical disclosure must start closed')
must(exposedText(drawer), ['Run detail', 'Failed', 'Claimed', 'Duration', 'Notification', 'Delivered',
  'Reported finding', 'Duration across this snapshot', 'Each bar is a recorded run, not a forecast.',
  'stage-by-stage traces require engine support.', 'Technical details'], 'selected inspector visible projection')
if (exposedText(drawer).includes(FULL_BODY) || exposedText(drawer).includes(FINDING_CASES[0].raw)) fail('the default inspector exposed raw output/findings before Technical details opened')
assertDurationSnapshot(drawer, JOBS.runs, rows(p.el)[0].getAttribute('data-key'), 'alarm duration snapshot')
await openTechnical(drawer)
// FULL BODY: the list carries a preview only; the drawer FETCHES the full text from /jobs/run.
if (!p.gets.some(x => x.startsWith('/health/jobs/run'))) fail(`the full-body request did not go: ${p.gets}`)
const bodyRequest = p.gets.find(x => x.startsWith('/health/jobs/run'))
if (bodyRequest && new URL(bodyRequest, 'https://fixture.invalid').searchParams.get('id') !== rows(p.el)[0].getAttribute('data-key')) {
  fail('the full-body success request did not carry the exact selected run id')
}
const runPre = drawer.querySelector('.pa-raw')
if (!runPre || runPre.textContent !== FULL_BODY) {
  fail(`the drawer does not show the full body: ${(runPre?.textContent || '(no pre)').slice(0, 120)}`)
}
// THE KIT OWNS THE DRAWER: the scrolling detail region, the section captions, the caption grid and
// the raw block are the host's own components — a hand-rolled <pre>/<dl> here would drift from the
// application's detail panes the first time either side moves.
if (drawer.querySelector('.pa-drawer-body')?.getAttribute('data-slot') !== 'panel-detail') {
  fail('the drawer body is not a kit PanelDetail')
}
if (technical.querySelectorAll('.pa-drawer-sec [data-slot="panel-section-label"]').length !== 3) {
  fail('the drawer sections do not carry a kit PanelSectionLabel each')
}
const metaGrid = drawer.querySelector('.pa-kv')
if (!technical.contains(metaGrid) || technical.querySelectorAll('.pa-kv').length !== 1
  || drawer.querySelectorAll('.ch-summary').length !== 1) fail('technical eight-pair metadata and visible three-pair summary must remain distinct')
const metaKeys = [...(metaGrid?.querySelectorAll('dt') || [])].map(node => node.textContent.trim())
const expectedMetaKeys = ['Run time', 'Job', 'id', 'Status', 'Delivery', 'Duration', 'Lateness', 'Body source']
if (metaGrid?.getAttribute('data-slot') !== 'panel-meta' || metaKeys.join('|') !== expectedMetaKeys.join('|')
  || metaGrid.querySelectorAll('dd').length !== expectedMetaKeys.length) {
  fail(`the inspector must use kit PanelMeta with its exact eight semantic pairs: ${metaKeys.join('|')}`)
}
const metaValues = [...(metaGrid?.querySelectorAll('dd') || [])].map(node => node.textContent.trim())
const alarmRun = JOBS.runs.find(run => run.id === rows(p.el)[0].getAttribute('data-key'))
if (metaValues[0] !== alarmRun.at || metaValues[1] !== 'Watch Dog' || metaValues[2] !== alarmRun.job_id
  || metaValues[3] !== alarmRun.status_label || metaValues[4] !== alarmRun.delivery_label
  || metaValues[7] !== alarmRun.body_label || metaValues.some(value => !value)) fail(`the inspector metadata lost source values: ${metaValues.join('|')}`)
if (runPre.getAttribute('data-slot') !== 'panel-block' || runPre.tagName !== 'PRE') {
  fail(`the raw output block is not a kit PanelBlock: ${runPre.tagName}/${runPre.getAttribute('data-slot')}`)
}
// Findings come from the backend; the panel only prints them (title · what · action).
must(drawer.textContent, ['Findings', 'Two pages with one name', 'Backup mirror behind',
  'Merge one into the other; keep a single page.'], 'finding cards')
// FINDING MAPPING: each class is printed as the panel's own English sentence, with the checker's
// raw line kept beside it (labelled under the sentence and reachable in the tooltip). The raw line
// is DATA: it never replaces the panel's sentence, and a class without a mapping row gets the
// neutral label instead of an invented translation.
const findCards = [...drawer.querySelectorAll('.pa-find')]
if (findCards.length !== FINDING_CASES.length) {
  fail(`the drawer printed ${findCards.length} finding cards for ${FINDING_CASES.length} findings`)
}
for (const item of FINDING_CASES) {
  const card = findCards.find(c => (c.textContent || '').includes(item.raw))
  if (!card) {
    fail(`${item.kind}: no finding card carries the checker line as written`)
    continue
  }
  const mapped = card.querySelector('p')
  if (!technical.open || !exposedText(drawer).includes(item.raw) || !exposedText(drawer).includes(item.en)) fail(`${item.kind}: actual mapped finding/raw wording remains hidden after disclosure opened`)
  if ((mapped?.textContent || '') !== item.en) {
    fail(`${item.kind}: the English mapping is not the bundle's sentence — got `
      + `${JSON.stringify(mapped?.textContent || '')}, want ${JSON.stringify(item.en)}`)
  }
  const quote = card.querySelector('.pa-quote')
  if (!quote || !quote.textContent.includes(item.raw)) {
    fail(`${item.kind}: the checker line is not kept beside the English sentence: ${quote?.textContent}`)
  } else if (!quote.textContent.startsWith('As written: ')) {
    fail(`${item.kind}: the raw line is printed without its label: ${quote.textContent.slice(0, 40)}`)
  }
  if (!card.textContent.includes(item.what)) fail(`${item.kind}: the backend explanation was dropped`)
  if (!card.textContent.includes(item.title)) fail(`${item.kind}: the class label is missing`)
  if (!card.querySelector('.pa-action') || card.querySelector('.pa-action').textContent !== item.action) fail(`${item.kind}: the backend action was dropped or rewritten`)
  await hover(card)
  const cardTip = p.el.querySelector('.pa-tip')
  if (!cardTip || !(cardTip.textContent || '').includes(item.raw)) {
    fail(`${item.kind}: the checker line is not reachable in the tooltip: ${cardTip?.textContent}`)
  }
  await unhover(card)
}
// The unmatched case: the raw line + the NEUTRAL label, no sentence borrowed from another class.
const unmatchedCase = FINDING_CASES.find(c => c.kind === 'other')
const unmatchedCard = findCards.find(c => (c.textContent || '').includes(unmatchedCase.raw))
if (!unmatchedCard) {
  fail('the unmatched finding card is missing (the raw line must still be shown)')
} else {
  const label = unmatchedCard.querySelector('p')?.textContent || ''
  if (!/^Unrecognized finding/.test(label)) {
    fail(`an unmatched finding did not get the neutral label: ${label}`)
  }
  const borrowed = FINDING_CASES.filter(c => c.kind !== 'other' && label.includes(c.en.slice(0, 24)))
  if (borrowed.length) fail(`an unmatched finding was given another class's sentence: ${borrowed.map(c => c.kind)}`)
}
// The raw output block still prints the checker's own lines verbatim (the data is never edited).
must(drawer.querySelector('.pa-raw')?.textContent || '',
  ["2 commit(s) ahead of 'onedrive'", 'DUPLICATE PAGE STEMS'], 'the raw run body (checker lines)')
// THE FINDING CARD SITS ON THE KIT'S LIST SKELETON: the findings are a PanelList, each card holds a
// PanelListRow whose lead is the class Badge and whose title is the panel's English sentence; the
// row is a DISCLOSURE, so the raw line/what/action in the card body can be folded away and back.
const findList = drawer.querySelector('.pa-findlist')
if (findList?.getAttribute('data-slot') !== 'panel-list') {
  fail(`the findings are not a kit PanelList: ${findList?.getAttribute('data-slot')}`)
}
for (const card of findCards) {
  const row = card.querySelector('[data-slot="panel-list-row"]')
  if (!row) { fail('a finding card holds no kit PanelListRow'); continue }
  if (!row.querySelector('[data-slot="row-button"]')) fail('the finding row has no select target')
  if (!row.querySelector('[data-slot="badge"]')) fail('the finding row carries no kit Badge (the class pill)')
  if (!card.querySelector('.pa-quote')) fail('the finding card lost its raw checker line')
}
const foldCard = findCards[0]
const foldRow = foldCard.querySelector('[data-slot="row-button"]')
await click(foldRow)
if (foldCard.querySelector('.pa-findbody')) fail('clicking a finding row does not fold its detail away')
await click(foldRow)
if (!foldCard.querySelector('.pa-findbody')) fail('clicking the finding row again does not bring the detail back')
// Closing 1: the inline inspector unmounts immediately, restores the empty aside and returns focus.
if (drawerOf(p.el).querySelector('.pa-iconbtn')?.getAttribute('data-slot') !== 'button') {
  fail('the drawer close control is not a kit Button')
}
await click(drawerOf(p.el).querySelector('.pa-iconbtn'), 0)
if (drawerOf(p.el)) fail('the close button does not close the drawer')
if (p.el.querySelector('.pa-logwrap').getAttribute('data-drawer') !== '0') {
  fail('the drawer mark is not reset after closing')
}
if (journal.querySelector(':scope > .ch-inspector-empty')?.tagName !== 'ASIDE'
  || rows(p.el).some(row => row.getAttribute('aria-expanded') !== 'false' || row.getAttribute('data-open') !== '0')) fail('closing the inspector did not restore its empty/unselected state')
if (document.activeElement !== rows(p.el)[0]) fail('the close button did not restore focus to its entry')
// A silent run's body is exactly the list preview: the drawer makes NO extra request.
const fetchesBeforeSilent = p.gets.filter(x => x.startsWith('/health/jobs/run')).length
await click(rows(p.el)[1], 80)
const quietDrawer = drawerOf(p.el)
if (!quietDrawer) fail('the silent run did not open a drawer')
if (quietDrawer.querySelector('.pa-raw')?.textContent !== JOBS.runs.find(run => run.id === rows(p.el)[1].getAttribute('data-key'))?.body) {
  fail(`the silent run's body is not shown: ${(quietDrawer.querySelector('.pa-raw')?.textContent || '').slice(0, 80)}`)
}
await openTechnical(quietDrawer)
must(exposedText(quietDrawer), ['completed', 'silent (no output)'], 'silent run caption')
if (p.gets.filter(x => x.startsWith('/health/jobs/run')).length !== fetchesBeforeSilent) {
  fail('a full-body request was made for a short body')
}
// Closing 2: Esc
await act(async () => { dom.window.document.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })) })
if (drawerOf(p.el)) fail('Esc does not close the drawer')
{
  const opener = rows(p.el)[0]
  await act(async () => { opener.focus() })
  await act(async () => { opener.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })) })
  await act(async () => { await new Promise(r => setTimeout(r, 80)) })
  const inspector = drawerOf(p.el)
  if (!inspector) fail('Enter on an entry does not open the inspector')
  else {
    if (inspector.getAttribute('role') !== 'region' || inspector.hasAttribute('aria-modal')) fail('keyboard opening turned the inline inspector into a modal')
    if (document.activeElement !== inspector) fail('keyboard opening did not focus the inspector')
    await openTechnical(inspector)
    const focusables = [...inspector.querySelectorAll('summary,button:not([disabled]),[href],input,[tabindex]:not([tabindex="-1"])')]
    if (!focusables.length) fail('the inspector exposes no keyboard actions')
    else {
      // jsdom does not implement native Tab traversal. A cancelable event detects a focus trap;
      // keeping focus on the boundary proves no custom wrap, then explicit external focus proves
      // the surrounding filters/navigation remain available (without claiming browser tab geometry).
      for (const [boundary, shiftKey] of [[focusables.at(-1), false], [focusables[0], true], [inspector, true]]) {
        await act(async () => { boundary.focus() })
        const tab = new dom.window.KeyboardEvent('keydown', { key: 'Tab', shiftKey, bubbles: true, cancelable: true })
        await act(async () => { boundary.dispatchEvent(tab) })
        if (tab.defaultPrevented || document.activeElement !== boundary) fail(`the nonmodal inspector traps ${shiftKey ? 'Shift+Tab' : 'Tab'}`)
      }
      await openAdvanced(p)
      const jobFace = selFace(p.el, 'jobs')
      await act(async () => { jobFace.focus() })
      if (document.activeElement !== jobFace || jobFace.disabled || jobFace.closest('[inert], [aria-hidden="true"]')) fail('the open inspector makes external filter navigation unavailable')
      await click(jobFace)
      if (!p.el.querySelector('.pa-pop[role="listbox"]') || drawerOf(p.el) !== inspector) fail('external filters cannot open while the inspector stays selected')
      await click(jobFace)
      const settingsNav = p.el.querySelector('[data-wa-nav="settings"]')
      if (!settingsNav) fail('the Settings button is missing while the History detail is open')
      else {
        await act(async () => { settingsNav.focus() })
        if (document.activeElement !== settingsNav || settingsNav.disabled || settingsNav.closest('[inert], [aria-hidden="true"]')) fail('the open inspector makes external page navigation unavailable')
      }
    }
    await act(async () => { document.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })) })
    if (drawerOf(p.el)) fail('Escape did not immediately remove the inline inspector')
    if (document.activeElement !== opener) fail(`closing the inspector does not return focus to its entry: ${document.activeElement?.className}`)
    const returnFocus = focusCalls.at(-1)
    if (returnFocus?.opts?.preventScroll !== true) fail('restoring entry focus scrolls the chronology')
    // Space toggles the same disclosure, with no lingering exit layer.
    const spaceOpen = new dom.window.KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true })
    await act(async () => { opener.dispatchEvent(spaceOpen) })
    if (!spaceOpen.defaultPrevented || !drawerOf(p.el) || opener.getAttribute('aria-expanded') !== 'true') fail('Space did not open the entry disclosure without scrolling')
    const spaceClose = new dom.window.KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true })
    await act(async () => { opener.dispatchEvent(spaceClose) })
    if (!spaceClose.defaultPrevented || drawerOf(p.el) || opener.getAttribute('aria-expanded') !== 'false') fail('Space did not immediately toggle the selected inspector closed')
  }
}
// The deleted job's drawer says so (a deleted job keeps its history and is named by its short id).
const goneRow = rows(p.el).find(r => /deleted job/.test(r.textContent))
if (!goneRow) fail('the deleted job row is missing')
await click(goneRow, 80)
const goneDrawer = drawerOf(p.el)
if (!goneDrawer) fail('the deleted job drawer did not open')
await openTechnical(goneDrawer)
must(goneDrawer.textContent, ['This job is no longer defined; its run history is kept as the record.'],
  'deleted job note')
await act(async () => { dom.window.document.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })) })

// ===========================================================================
// 3) Shared text/job filters: Chronicle exact membership, Health diagnostic scope
// ===========================================================================
for (const state of ['empty', 'error', 'pending']) {
  const probe = await mount('en', state, 'chronicle')
  // The drafts are independent of the run history: the Your review station still counts them.
  const review = probe.el.querySelector('[data-wa-station="review"]')
  if (!review || !(review.textContent || '').includes(String(candidates().length))) {
    fail(`the independent drafts count left the Your review station when history was ${state}`)
  }
  if (probe.posts.length) fail(`history ${state} issued a write`)
}
// Closed native filters hide only advanced controls; search remains usable, and folding never
// clears an active selection. The existing job/date safety tests below still exercise full scope.
for (const target of ['health', 'chronicle']) {
  const probe = await mount('en', 'data', target)
  const details = probe.el.querySelector('details.ch-filters-advanced')
  const search = probe.el.querySelector('input[aria-label^="Filter runs"]')
  const summary = details?.querySelector(':scope > summary')
  const start = probe.el.querySelector('input[aria-label="Start date"]')
  const end = probe.el.querySelector('input[aria-label="End date"]')
  if (!details || details.open || !summary || summary.textContent.trim() !== 'Job & date filters'
    || !details.contains(selFace(probe.el, 'jobs')) || !details.contains(start) || !details.contains(end)
    || ['Today', 'Last 7 days', 'Last 30 days', 'All'].some(label => !details.contains(preset(probe.el, label)))) {
    fail(`${target}: job picker, all date presets and both date inputs must start behind a closed native disclosure`)
  }
  if (!search || search.disabled || search.type === 'hidden'
    || search.closest('details, [hidden], [aria-hidden="true"], [inert]')) {
    fail(`${target}: search must remain exposed and enabled outside the closed advanced disclosure`)
  }
  if (!details || !search || !summary) continue
  if (/All jobs|Last 7 days|Last 30 days/.test(exposedText(probe.el.querySelector('.pa-filters')))) {
    fail(`${target}: advanced job/date content is exposed while its native disclosure is closed`)
  }
  const beforeSearch = probe.gets.length
  await type(search, 'silent')
  assertScope(probe, JOBS.runs.filter(run => run.delivery === 'suppressed'), 'search with advanced filters closed')
  const clear = chip(probe.el, 'Clear filters')
  if (!clear || clear.closest('details')) fail(`${target}: closed advanced filters hide the search reset`)
  await click(clear)
  assertScope(probe, JOBS.runs, 'reset search while advanced filters stay closed')
  if (details.open || probe.gets.length !== beforeSearch || probe.posts.length) {
    fail(`${target}: search/reset opened advanced controls or issued a read/write`)
  }
  await openAdvanced(probe)
  must(exposedText(details), ['All jobs', 'Today', 'Last 7 days', 'Last 30 days'], `${target} opened advanced controls`)
  await click(selFace(probe.el, 'jobs'))
  await click(optNamed(probe.el, 'Watch Dog'))
  await click(selFace(probe.el, 'jobs'))
  await click(preset(probe.el, 'Today'), 80)
  const selectedScope = JOBS.runs.filter(run => run.job_name === 'Watch Dog' && run.date === TODAY_ISO)
  assertScope(probe, selectedScope, 'advanced job and Today intersection')
  await click(summary)
  if (details.open) await act(async () => { details.open = false })
  if (details.open || !exposedText(details).includes('Filters active')) fail(`${target}: folding active job/date filters hid their active indication`)
  assertScope(probe, selectedScope, 'folding preserves job and date scope')
  await openAdvanced(probe)
  if (selFace(probe.el, 'jobs')?.textContent.trim() !== 'Watch Dog'
    || start.value !== TODAY_ISO || end.value !== TODAY_ISO
    || preset(probe.el, 'Today')?.getAttribute('aria-pressed') !== 'true') {
    fail(`${target}: reopening lost the selected job, Today preset or exact date values`)
  }
  await click(chip(probe.el, 'Clear filters'), 80)
  assertScope(probe, JOBS.runs, 'advanced reset keeps every unbounded record')
  if (start.value || end.value || preset(probe.el, 'All')?.getAttribute('aria-pressed') !== 'true'
    || details.querySelector('.ch-filter-active') || probe.posts.length) fail(`${target}: advanced reset failed to clear date/job state without writes`)
}

// REMOVED in 2.5.0 (Docs/metro-contract.md § Removed): the Chronicle lower review queue and its
// exact-ref navigation into Folio (`.nx-queue`, `[role="tab"]` Folio, `.fl-item[aria-pressed]`). The
// review desk is reached from the Your review station and shows ONE draft at a time; its behaviour is
// proved in render_metro.mjs (M8) and below. The queue's read-state guarantees are kept in their Metro
// form: no candidate read state may block the run history, fabricate drafts or issue a write.
const reviewDesk = el => el.querySelector('.wa-metro-detail[data-for="review"]')
const deskButton = (el, label) => [...(reviewDesk(el)?.querySelectorAll('button') || [])]
  .find(b => (b.textContent || '').trim() === label)
const captureIntervals = () => {
  const realInterval = globalThis.setInterval
  const realClear = globalThis.clearInterval
  const intervals = new Map()
  globalThis.setInterval = (fn, ms, ...args) => {
    const id = realInterval(fn, ms, ...args)
    intervals.set(id, { fn, ms })
    return id
  }
  globalThis.clearInterval = id => { intervals.delete(id); return realClear(id) }
  return { intervals, restore: () => { globalThis.setInterval = realInterval; globalThis.clearInterval = realClear } }
}
const pollAll = async intervals => {
  const polls = [...intervals.values()].filter(item => item.ms === 60000)
  await act(async () => { for (const poll of polls) poll.fn() })
  await act(async () => { await new Promise(r => setTimeout(r, 40)) })
  return polls.length
}

// SEC-3: a failed project-context poll cannot leave an old review actionable.
{
  const cap = captureIntervals()
  try {
    const probe = await mount('en', 'folioscope', 'review')
    const approve = deskButton(probe.el, 'Approve')
    const key = approve && Object.keys(approve).find(key => key.startsWith('__reactProps$'))
    const retained = key && approve[key]?.onClick
    if (typeof retained !== 'function') fail('SEC-3 context-failure setup: the review desk shows no Approve for the first draft')
    else {
      folioControl.automation = () => { throw new Error('project context unavailable') }
      const refresh = [...probe.el.querySelectorAll('button')].find(b => (b.textContent || '').trim() === 'Refresh'
        || b.getAttribute('aria-label') === 'Refresh')
      if (refresh) await click(refresh, 0)
      else if (!await pollAll(cap.intervals)) fail('SEC-3: the review desk has neither a Refresh nor a 60 s poll')
      if (exposedText(reviewDesk(probe.el) || probe.el).includes(candidates()[0].summary)
        || deskButton(probe.el, 'Approve')) fail('SEC-3 polling: failed context GET retained the old draft on the review desk')
      const before = probe.posts.length
      await act(async () => { await retained() })
      if (probe.posts.length !== before) fail('SEC-3 polling: failed context GET left a retained approval actionable')
      must(exposedText(probe.el), ['project context unavailable'], 'SEC-3 failed context explanation')
    }
  } finally {
    folioControl.automation = null
    cap.restore()
  }
}

// SEC-3: the draft the desk was on is not a selection instruction in a new SDK scope.
{
  const probe = await mount('en', 'folioscope', 'review')
  await click(deskButton(probe.el, 'Later'), 40)
  await click(deskButton(probe.el, 'Later'), 40)
  if (!exposedText(reviewDesk(probe.el) || probe.el).includes(candidates()[2].summary)) {
    fail('SEC-3 setup: two `Later` presses did not move the desk to the third draft (one draft at a time)')
  }
  await act(async () => { stub.host.state.profile.set('new-queue-profile') })
  await act(async () => { await new Promise(r => setTimeout(r, 60)) })
  const after = exposedText(reviewDesk(probe.el) || probe.el)
  if (after.includes(candidates()[2].summary) && !after.includes(candidates()[0].summary)) {
    fail('SEC-3 navigation: the old draft position rebound into the new SDK scope')
  }
  if (probe.posts.length) fail('SEC-3 navigation: SDK switch dispatched an automatic decision')
}

// SEC-3: real 60-second polling invalidates project identity and discards old-scope deferred reads.
{
  const cap = captureIntervals()
  try {
    const probe = await mount('en', 'folioscope', 'review')
    const polls = [...cap.intervals.values()].filter(item => item.ms === 60000)
    if (polls.length < 1) throw new Error('SEC-3: the review desk owns no 60 s polling loop')
    const oldCandidates = deferred()
    const oldRecovery = deferred()
    let dispatched = 0
    folioControl.candidates = () => { dispatched += 1; return oldCandidates.promise }
    folioControl.recovery = () => { dispatched += 1; return oldRecovery.promise }
    await pollAll(cap.intervals)
    if (dispatched < 1) fail('SEC-3 poll did not dispatch the deferred candidate inventory')
    folioControl.candidates = () => ({ ok: true, candidates: [{ ...candidates()[0], summary: 'NEW SDK SCOPE' }] })
    folioControl.recovery = () => ({ ok: true, operations: [] })
    await act(async () => { stub.host.state.profile.set('second-profile') })
    await act(async () => { await new Promise(r => setTimeout(r, 60)) })
    if (!reviewDesk(probe.el)) {
      const station = probe.el.querySelector('[data-wa-station="review"]')
      if (station?.getAttribute('aria-pressed') !== 'true') await click(station, 60)
    }
    if (!exposedText(probe.el).includes('NEW SDK SCOPE')) fail('SEC-3 polling: old pending reads blocked the new SDK scope')
    await act(async () => {
      oldCandidates.resolve({ ok: true, candidates: [{ ...candidates()[0], summary: 'OLD POLLING RESULT' }] })
      oldRecovery.resolve({ ok: true, operations: [{ request_id: 'd'.repeat(64), ref: 'old/approved', target: 'OLD RECOVERY RESULT', kind: 'new', state: 'applying' }] })
      await Promise.all([oldCandidates.promise, oldRecovery.promise])
    })
    if (exposedText(probe.el).includes('OLD POLLING RESULT') || exposedText(probe.el).includes('OLD RECOVERY RESULT')
      || !exposedText(probe.el).includes('NEW SDK SCOPE')) fail('SEC-3 polling: late old inventories overwrote the current scope')
    const candidateRead = deferred()
    folioControl.automation = () => ({ ...automation(), settings: { ...automation().settings, project_root: '/srv/new-project', project: { ...automation().settings.project, id: 'new-project', path: '/srv/new-project' } } })
    folioControl.candidates = () => candidateRead.promise
    await pollAll(cap.intervals)
    if (exposedText(reviewDesk(probe.el) || probe.el).includes('NEW SDK SCOPE') && deskButton(probe.el, 'Approve')) {
      fail('SEC-3 polling: a changed project kept the old draft actionable before its new inventory arrived')
    }
    await act(async () => { candidateRead.resolve({ ok: true, candidates: candidates() }); await candidateRead.promise })
    await act(async () => { await new Promise(r => setTimeout(r, 40)) })
    if (!exposedText(probe.el).includes(candidates()[0].summary) || probe.posts.length) {
      fail('SEC-3 polling: the fresh project did not become a read-only review desk')
    }
    if (probe.errors.size) fail(`SEC-3 polling threw: ${[...probe.errors].join(' | ')}`)
  } finally {
    folioControl.automation = null
    folioControl.candidates = null
    folioControl.recovery = null
    cap.restore()
  }
}

// A candidate read in any state (pending, empty, failed, refused) never blocks the run history,
// fabricates a draft or issues a decision/detail request.
for (const [mode, text] of [['queuepending', ''], ['queueempty', ''], ['queueerror', 'the candidate store is locked'],
  ['queuerefused', 'the candidate list was refused']]) {
  const probe = await mount('en', mode, 'chronicle')
  assertScope(probe, JOBS.runs, `${mode} cannot block the independent run history`)
  if (probe.posts.length || probe.gets.some(path => path.startsWith('/candidates/show?'))) fail(`${mode}: a candidate read state issued a decision or detail request`)
  if (text) {
    await click(probe.el.querySelector('[data-wa-station="review"]'), 80)
    must(exposedText(probe.el), [text], `${mode}: the review desk keeps the backend's error`)
  }
}

// Source-backed projection probes: errors outrank findings; a real bad finding outranks
// the first neutral one; ordinary output never becomes a fabricated error or finding.
{
  const probe = await mount('en', 'projectioncases', 'chronicle')
  const scope = [...JOBS.runs]
  assertScope(probe, scope, 'projection probe membership')
  for (const entry of rows(probe.el)) {
    const run = scope.find(run => run.id === entry.getAttribute('data-key'))
    if (!entry.getAttribute('aria-label')?.includes(run.status_label)
      || entry.querySelector('.ch-outcome')?.textContent.trim() !== outcomeOf(run)) fail(`projection probe lost source/backend vs readable outcome distinction: ${run.id}`)
    if (entry.querySelector('.ch-preview')?.textContent !== synopsisOf(run)) fail(`projection probe invented or chose the wrong synopsis: ${run.id}`)
    const glyph = entry.querySelector('.ch-point svg path')?.getAttribute('d')
    if (!glyph || (run.status === 'unknown' && glyph !== 'M4 7h6')
      || (run.status === 'claimed' && glyph !== 'M7 3v4l3 2')) fail(`projection probe lost claimed/unknown ring glyph: ${run.id}`)
    await click(entry)
    const inspector = drawerOf(probe.el)
    if (!inspector) { fail(`projection probe could not select ${run.id}`); continue }
    const reportedTitle = run.body_source === 'error' && run.body.trim() ? 'Reported error'
      : run.findings.length ? 'Reported finding' : 'Reported error'
    if (inspector.querySelector('.ch-error-section h3')?.textContent !== reportedTitle
      || inspector.querySelector('.ch-error-section')?.getAttribute('aria-label') !== reportedTitle
      || inspector.querySelector('.ch-error-preview')?.textContent !== synopsisOf(run)) fail(`projection probe reported error/finding is not honest and named: ${run.id}`)
    const values = [...inspector.querySelectorAll('.ch-summary dd')].map(node => node.textContent.trim())
    if (values.length !== 3 || values[2] !== notificationOf(run)
      || inspector.querySelector('.pa-drawer-head .ch-outcome')?.textContent.trim() !== outcomeOf(run)) fail(`projection probe coerced status and delivery: ${run.id}`)
    if (inspector.querySelector('script') || entry.querySelector('script')) fail('recorded error markup was interpreted instead of rendered literally')
    await openTechnical(inspector)
    const metadata = [...inspector.querySelectorAll('.pa-kv dd')].map(node => node.textContent.trim())
    if (metadata[3] !== run.status_label || metadata[4] !== run.delivery_label || metadata[7] !== run.body_label) fail(`projection probe replaced exact backend labels with badge text: ${run.id}`)
    if (inspector.querySelector('.pa-raw')?.textContent !== (run.body || 'no body record')) fail(`projection probe rewrote raw output: ${run.id}`)
    if (!exposedText(inspector).includes(run.body.replace(/\s+/g, ' ').trim()) && run.body.trim()) fail(`projection probe raw output remains hidden after disclosure: ${run.id}`)
    await click(inspector.querySelector('.pa-iconbtn'), 0)
  }
  if (probe.gets.some(path => path.startsWith('/health/jobs/run')) || probe.posts.length) fail('complete-body projection probes issued unnecessary body reads or writes')
}
for (const mode of ['durationprobe', 'zerodurations', 'nodurations']) {
  const probe = await mount('en', mode, 'chronicle')
  const scope = [...JOBS.runs]
  assertScope(probe, scope, `${mode} keeps every journal record`)
  for (const entry of rows(probe.el)) {
    const run = scope.find(run => run.id === entry.getAttribute('data-key'))
    if (entry.querySelector('.ch-run-duration')?.textContent !== durationOf(run)) fail(`${mode}: row coerced invalid duration into a number: ${run.id}`)
  }
  await click(rows(probe.el)[0], 80)
  const inspector = drawerOf(probe.el)
  if (!inspector) fail(`${mode}: inspector missing`)
  else assertDurationSnapshot(inspector, scope, scope[0].id, mode)
  if (mode === 'durationprobe') {
    await click(inspector?.querySelector('.pa-iconbtn'), 0)
    const search = probe.el.querySelector('input[aria-label^="Filter runs"]')
    await type(search, 'Fleet Watch')
    // The shown snapshot owns the scale and membership; a status/text filter must never
    // leave duration bars for excluded records in the selected inspector.
    const filtered = scope.filter(run => run.job_name === 'Fleet Watch')
    assertScope(probe, filtered, 'durationprobe actual filtered membership')
    await click(rows(probe.el)[0])
    const selected = rows(probe.el)[0]?.getAttribute('data-key')
    assertDurationSnapshot(drawerOf(probe.el), filtered, selected, 'durationprobe filtered scope')
  }
}
async function checkTextAndJobs(p) {
  await openAdvanced(p)
  const jobFace = p.el.querySelector('[aria-label^="Job filter"]')
  if (!jobFace) fail('the job picker face has no accessible name')
  if (!/^Job filter: All jobs$/.test(jobFace.getAttribute('aria-label'))) {
    fail(`the picker face does not name the current value: ${jobFace.getAttribute('aria-label')}`)
  }
  if (jobFace.getAttribute('aria-haspopup') !== 'listbox') {
    fail(`the picker does not announce that it opens a list: ${jobFace.getAttribute('aria-haspopup')}`)
  }
  await click(jobFace)
  const pop = p.el.querySelector('.pa-pop')
  if (!pop) fail('the picker popup did not open')
  if (pop.getAttribute('role') !== 'listbox') fail(`the picker popup is not a listbox: ${pop.getAttribute('role')}`)
  const opts = [...pop.querySelectorAll('[role="option"]')]
  if (opts.length !== 5) fail(`the picker does not offer one option per job: ${opts.length}`)
  if (opts.some(o => !['true', 'false'].includes(o.getAttribute('aria-selected')))) {
    fail('a picker option does not report whether it is selected')
  }
  if (!/^Job filter: All jobs$/.test(jobFace.getAttribute('aria-label'))) {
    fail(`the picker face lost its value: ${jobFace.getAttribute('aria-label')}`)
  }
  await click(jobFace)
  const search = p.el.querySelector('input[aria-label^="Filter runs"]') || p.el.querySelector('input')
  if (!search) fail('the filter box is missing')
  await type(search, 'silent')
  assertScope(p, JOBS.runs.filter(r => r.delivery === 'suppressed'), 'text filter silent')
  if (p.target === 'chronicle') must(visibleText(p.el), ['3 of 5 runs shown'], 'filter counter')
  if (!chip(p.el, 'Clear filters')) fail('the "Clear filters" button did not appear')
  if (chip(p.el, 'Clear filters').getAttribute('data-slot') !== 'button') {
    fail('"Clear filters" is not a kit Button')
  }
  await click(chip(p.el, 'Clear filters'))
  assertScope(p, JOBS.runs, 'cleared text filter')

  // JOB PICKER: not a native select but the panel's own window; checkbox rows, multi-select. The
  // selection filters KPIs + chart + job list + rows TOGETHER.
  if (p.el.querySelector('select')) fail('a native select is used (the OS list does not follow the theme)')
  if (!selFace(p.el, 'jobs')) fail('the job picker is missing (.pa-selwrap[data-sel="jobs"])')
  if (!/All jobs/.test(selFace(p.el, 'jobs').textContent)) {
    fail(`the picker face does not start as "All jobs": ${selFace(p.el, 'jobs').textContent}`)
  }
  await click(selFace(p.el, 'jobs'))
  if (!p.el.querySelector('.pa-pop')) fail('the picker window does not open')
  const jobOpts = popOpts(p.el)
  if (jobOpts.length !== 5) fail(`there must be 5 job options (All + 4 jobs): ${jobOpts.length}`)
  if (jobOpts.some(o => !o.querySelector('.pa-check'))) fail('the options carry no checkbox')
  if (!jobOpts.every(o => ['true', 'false'].includes(o.getAttribute('aria-selected')))) {
    fail('the options do not report whether they are selected (aria-selected)')
  }
  if (jobOpts[0].getAttribute('data-on') !== '1') fail('the "All jobs" row does not read as selected')
  if (!jobOpts[0].querySelector('.pa-check svg')) fail('the checkbox draws no mark')
  if (!jobOpts.some(o => /^deleted job \(/.test(optLabel(o)))) {
    fail(`the deleted job is missing from the options: ${jobOpts.map(optLabel)}`)
  }
  await click(optNamed(p.el, 'Watch Dog'))
  assertScope(p, JOBS.runs.filter(r => r.job_name === 'Watch Dog'), 'Watch Dog picker')
  if (!p.el.querySelector('.pa-pop')) fail('the window closed after one pick (multi-select impossible)')
  if (!/Watch Dog/.test(selFace(p.el, 'jobs').textContent)) fail('the picker face does not show the picked job')
  await click(optNamed(p.el, 'Fleet Watch'))
  assertScope(p, JOBS.runs.filter(r => ['Watch Dog', 'Fleet Watch'].includes(r.job_name)), 'two jobs picked')
  if (!/2 jobs/.test(selFace(p.el, 'jobs').textContent)) {
    fail(`the picker face does not say "2 jobs": ${selFace(p.el, 'jobs').textContent}`)
  }
  await click(optNamed(p.el, 'All jobs'))
  assertScope(p, JOBS.runs, 'All jobs picker')
}
p = await mount('en', 'data', 'health')
await checkTextAndJobs(p)
p = await mount('en', 'data', 'chronicle')
await checkTextAndJobs(p)

// Chronicle's status axis is independent of delivery. Counts use the text/job/date scope
// BEFORE the status selection, so changing status cannot erase sibling option counts.
await click(selFace(p.el, 'jobs')) // close the multi-select left open by checkTextAndJobs
const statusChoices = [
  ['All', () => true],
  ['Completed', run => run.status === 'completed'],
  ['Failed', run => run.status === 'failed'],
  ['Active', run => ['running', 'claimed'].includes(run.status)]
]
const statusButtons = () => [...p.el.querySelectorAll('.ch-status [data-slot="segmented-control"] button')]
const checkStatusCounts = (scope, selected) => {
  const group = p.el.querySelector('.ch-status')
  if (group?.getAttribute('role') !== 'group' || group.getAttribute('aria-label') !== 'Run status filter') fail('Chronicle status filtering lost its named group')
  const buttons = statusButtons()
  const expectedLabels = statusChoices.map(([label, matches]) => `${label} ${scope.filter(matches).length}`)
  if (buttons.map(button => button.textContent.trim()).join('|') !== expectedLabels.join('|')) fail(`status counts disagree with the pre-status scope: ${buttons.map(button => button.textContent).join('|')} != ${expectedLabels.join('|')}`)
  if (buttons.some((button, i) => button.getAttribute('aria-pressed') !== String(statusChoices[i][0] === selected))) fail(`status selection is not announced: ${selected}`)
}
checkStatusCounts(JOBS.runs, 'All')
for (const [i, [label, matches]] of statusChoices.entries()) {
  if (label === 'Completed') {
    await click(rows(p.el)[0], 80)
    if (!drawerOf(p.el)) fail('the inspector did not open before changing status')
  }
  await click(statusButtons()[i])
  assertScope(p, JOBS.runs.filter(matches), `${label} status membership`)
  checkStatusCounts(JOBS.runs, label)
  if (drawerOf(p.el)) fail('changing status left an inspector for a hidden entry')
}
await click(statusButtons()[0])
const silentScope = JOBS.runs.filter(run => run.delivery === 'suppressed')
await type(p.el.querySelector('input[aria-label^="Filter runs"]'), 'silent')
checkStatusCounts(silentScope, 'All')
await click(statusButtons()[1])
assertScope(p, silentScope.filter(run => run.status === 'completed'), 'completed + silent exact membership')
checkStatusCounts(silentScope, 'Completed')
await click(statusButtons()[2])
assertScope(p, [], 'failed + silent has no matching entries')
checkStatusCounts(silentScope, 'Failed')
if (p.el.querySelector('.ch-journal') || !p.el.querySelector('[data-slot="panel-empty"]')) fail('a status with no matches did not replace the journal with the kit empty state')
await click(chip(p.el, 'Clear filters'))
assertScope(p, JOBS.runs, 'clear filters resets status and text')
checkStatusCounts(JOBS.runs, 'All')

// ARCHIVE & CLEAR: the run log can be cleared, and the safety is that the panel sends EXACTLY the
// records it is showing — the backend archives those keys and removes nothing else. The control is
// two-step, and the receipt states what really happened.
stub.calls.posts.length = 0
const clearOpen = p.el.querySelector('.pa-clear-open')
if (!clearOpen) fail('the run log has no archive-and-clear control')
if (!/Archive & clear/.test(clearOpen.textContent)) {
  fail(`the control is not named: ${clearOpen.textContent}`)
}
await click(clearOpen)
if (!p.el.querySelector('.pa-clear-ask')) fail('the first press did not arm a confirm step')
if (stub.calls.posts.length) fail('the first press already wrote to the store')
const askText = p.el.querySelector('.pa-clear-ask').textContent
if (!askText.includes(String(rows(p.el).length))) {
  fail(`the confirm does not name how many records it would take: ${askText}`)
}
if (!/backups\//.test(askText)) fail(`the confirm does not say where the archive goes: ${askText}`)
if (!/Nothing is removed until the archive is written and read back/.test(askText)) {
  fail(`the confirm hides its full warning in a hover tip: ${askText}`)
}
if (!/1 running run is kept/.test(askText)) {
  fail(`the confirm does not say that a run the scheduler still owns is kept: ${askText}`)
}
if (p.el.querySelector('.pa-clear-ask [tabindex="-1"], .pa-clear-ask span[aria-describedby]')) {
  fail('the confirm text is carried by an element the keyboard cannot reach')
}
await click([...p.el.querySelectorAll('.pa-clear-ask button')].find(b => /Cancel/.test(b.textContent)))
if (p.el.querySelector('.pa-clear-ask')) fail('cancel does not disarm the confirm')
if (stub.calls.posts.length) fail('cancel still wrote to the store')
await click(p.el.querySelector('.pa-clear-open'))
const goBtn = [...p.el.querySelectorAll('.pa-clear-ask button')].find(b => /Archive & clear/.test(b.textContent))
if (!goBtn) fail('the confirm step has no go button')
await click(goBtn)
const posted = stub.calls.posts.filter(c => c.path === '/health/runs/archive-clear')
if (posted.length !== 1) fail(`the clear did not post exactly once: ${posted.length}`)
const postedKeys = posted[0]?.body?.keys || []
const expectedArchived = JOBS.runs.filter(r => !['running', 'claimed'].includes(r.status)).map(r => r.id).sort()
if ([...postedKeys].sort().join('|') !== expectedArchived.join('|') || new Set(postedKeys).size !== postedKeys.length) {
  fail(`archive posted the wrong exact keys: ${postedKeys.join(',')} (expected ${expectedArchived.join(',')})`)
}
const ownedByScheduler = JOBS.runs.filter(r => r.status === 'running' || r.status === 'claimed').map(r => r.id)
if (ownedByScheduler.some(id => postedKeys.includes(id))) {
  fail(`the clear posted a run the scheduler still owns: ${postedKeys.join(',')}`)
}
if (postedKeys.length !== rows(p.el).length - ownedByScheduler.length) {
  fail(`the panel posted ${postedKeys.length} keys for ${rows(p.el).length} rows`)
}
const onScreen = [...JOBS.runs].filter(r => postedKeys.includes(r.id)).length
if (onScreen !== postedKeys.length) {
  fail(`the keys posted are not records of the payload: ${onScreen} of ${postedKeys.length}`)
}
const filteredOut = [...JOBS.runs].filter(r => !postedKeys.includes(r.id)).length
if (postedKeys.length !== [...JOBS.runs].length - ownedByScheduler.length) {
  // Every row is on screen in this state, so the clear must cover all of them and nothing else.
  fail(`the clear left ${filteredOut} record(s) out of a full log`)
}
const note = p.el.querySelector('.pa-clear-note')?.textContent || ''
if (!/archived to backups\//.test(note)) fail(`the receipt does not name the archive: ${note}`)
if (!new RegExp(String(postedKeys.length)).test(note)) {
  fail(`the receipt does not state the count: ${note}`)
}

p = await mount('en', 'data', 'health')
assertScope(p, JOBS.runs, 'before orb toggle')
// The freshness orb is a filter control: one press selects that job, a second press on the SAME orb
// clears the filter instead of leaving it stuck on.
const orbOf = (el, needle) => [...el.querySelectorAll('.pa-orb')].find(o => needle.test(o.textContent))
const watchOrb = orbOf(p.el, /Watch Dog/)
if (!watchOrb) fail('the freshness card draws no orb for Watch Dog')
await click(watchOrb)
assertScope(p, JOBS.runs.filter(r => r.job_name === 'Watch Dog'), 'orb 5→1')
if (!/Watch Dog/.test(selFace(p.el, 'jobs').textContent)) {
  fail(`the orb did not tell the picker: ${selFace(p.el, 'jobs').textContent}`)
}
await click(orbOf(p.el, /Watch Dog/))
assertScope(p, JOBS.runs, 'second orb press 1→5')
if (!/All jobs/.test(selFace(p.el, 'jobs').textContent)) {
  fail(`the picker face still shows a pick after the orb was pressed again: ${selFace(p.el, 'jobs').textContent}`)
}

p = await mount('en', 'data', 'health')
// ONE KEY, ONE SHAPE. The colour key is the same component on every surface and names only the
// tones a chart draws.
const ckeys = p.el.querySelectorAll('.pa-ck')
if (ckeys.length !== 1) {
  fail(`the colour key should be drawn once, not once per card: ${ckeys.length}`)
}
if (p.el.querySelector('.pa-ck-dot[data-tone="late"]')) fail('the colour key names a lateness tick no chart draws')
const toneDots = new Set([...p.el.querySelectorAll('.pa-ck-dot')].map(d => d.getAttribute('data-tone')))
const colorLabels = [...p.el.querySelectorAll('.pa-ck-item')].map(item => item.querySelector('span')?.textContent.trim())
if (colorLabels.length !== 3 || colorLabels.some(label => !label) || new Set(colorLabels).size !== 3) fail(`timeline color key has empty or duplicated labels: ${colorLabels.join('|')}`)
if (!['bad', 'warn', 'neutral'].every(x => toneDots.has(x))) {
  fail(`the keys do not name every tone: ${[...toneDots]}`)
}
if (!/All jobs/.test(selFace(p.el, 'jobs').textContent)) fail('the picker face was not updated after "All"')
await act(async () => { dom.window.document.dispatchEvent(new dom.window.MouseEvent('mousedown', { bubbles: true })) })
await act(async () => { await new Promise(r => setTimeout(r, 40)) })
if (p.el.querySelector('.pa-pop')) fail('an outside click does not close the picker window')

// Date presets also set the SERVER WINDOW (data is fetched only as far back as needed) and drop the
// run from 20 days ago. An UNDATED run cannot be placed in a bounded range, so a bounded range leaves
// it out; "All" (no bound) shows it.
async function checkDates(p) {
  await openAdvanced(p)
  // History's own reads only: the Metro station's 24h read before History opened is not its window.
  const jobsGets = () => p.historyGets().filter(x => x.startsWith('/health/jobs?window='))
  if (jobsGets()[0] !== '/health/jobs?window=all') fail(`${p.target}: default "All" preset did not read the whole history: ${jobsGets()}`)
  const getsBeforeToday = jobsGets().length
  await click(preset(p.el, 'Today'), 80)
  if (!jobsGets().some(x => x === '/health/jobs?window=24h')) fail(`"Today" did not change the server window: ${jobsGets()}`)
  if (jobsGets().length <= getsBeforeToday) fail('the data was not re-read when the preset changed')
  assertScope(p, JOBS.runs.filter(r => r.date === TODAY_ISO), 'Today excludes old/undated runs')
  // Today fetched only recent rows. An earlier custom start must widen the SERVER history, not
  // merely refilter that short response; explicit bounds must still exclude the undated row.
  const beforeCustom = jobsGets().length
  await type(p.el.querySelector('input[aria-label="Start date"]'), OLD_ISO, 80)
  if (jobsGets().length !== beforeCustom + 1 || jobsGets().at(-1) !== '/health/jobs?window=all') {
    fail(`${p.target}: widening Today to custom dates did not fetch all history: ${jobsGets()}`)
  }
  assertScope(p, JOBS.runs.filter(r => r.date && r.date >= OLD_ISO && r.date <= TODAY_ISO),
    'custom start after Today recovers the older run, excludes undated')
  await click(preset(p.el, 'Last 30 days'), 80)
  if (!jobsGets().some(x => x === '/health/jobs?window=30d')) fail(`the "Last 30 days" window is not 30d: ${jobsGets()}`)
  assertScope(p, JOBS.runs.filter(r => r.date), 'Last 30 days excludes undated run')
  const getsBeforeAll = jobsGets().length
  await click(preset(p.el, 'All'), 80)
  if (jobsGets().length <= getsBeforeAll || jobsGets().at(-1) !== '/health/jobs?window=all') {
    fail(`"All" did not ask the server for the whole history: ${jobsGets()}`)
  }
  assertScope(p, JOBS.runs, 'All includes undated run')
  await click(preset(p.el, 'Last 7 days'), 80)
  if (jobsGets().at(-1) !== '/health/jobs?window=7d') fail(`${p.target}: Last 7 days did not set the 7d window`)
  assertScope(p, JOBS.runs.filter(r => r.date === TODAY_ISO), 'Last 7 days')
  await click(preset(p.el, 'All'), 80)

  // Date fields: a day picked from the themed calendar; a bounded range leaves the UNDATED run out.
  const fromBox = p.el.querySelector('input[aria-label="Start date"]')
  const toBox = p.el.querySelector('input[aria-label="End date"]')
  if (!fromBox || !toBox) fail('the date range boxes are missing')
  const startFace = p.el.querySelector('[aria-label^="Start date:"]')
  if (!startFace) fail('the themed date face is missing')
  if (!/^Start date: not set$/.test(startFace.getAttribute('aria-label'))) {
    fail(`the date face does not name its value: ${startFace.getAttribute('aria-label')}`)
  }
  await click(startFace)
  const cal = p.el.querySelector('.pa-cal')
  if (!cal) fail('the calendar window did not open')
  if (cal.querySelectorAll('.pa-cal-wd span').length !== 7) fail('the calendar has no weekday headings')
  // The calendar opens on this month; step back until the day from 20 days ago is reachable.
  let calDay = null
  for (let i = 0; i < 4 && !calDay; i += 1) {
    const openCal = p.el.querySelector('.pa-cal')
    calDay = openCal.querySelector(`button[aria-label="${OLD_ISO}"]`)
    if (calDay) break
    const prev = [...openCal.querySelectorAll('button')].find(b => b.getAttribute('aria-label') === 'Previous month')
    if (!prev) break
    await click(prev)
  }
  if (!calDay) fail(`the day ${OLD_ISO} is unreachable in the calendar`)
  const calGrid = p.el.querySelector('.pa-cal-grid')
  const dayBtns = [...calGrid.querySelectorAll('button')]
  const arrowFrom = dayBtns[9]
  await act(async () => { arrowFrom.focus() })
  const arrow = async key => {
    await act(async () => {
      dom.window.document.activeElement.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key, bubbles: true }))
    })
  }
  await arrow('ArrowRight')
  if (dom.window.document.activeElement !== dayBtns[10]) fail('ArrowRight does not move to the next day in the calendar')
  await arrow('ArrowDown')
  if (dom.window.document.activeElement !== dayBtns[17]) fail('ArrowDown does not move one week on in the calendar')
  await arrow('ArrowUp')
  await arrow('ArrowLeft')
  if (dom.window.document.activeElement !== arrowFrom) fail('ArrowUp/ArrowLeft do not move back in the calendar')
  if (calGrid.getAttribute('role') !== 'grid' && !calGrid.getAttribute('aria-label')) {
    fail('the calendar grid is not named for a screen reader')
  }
  await click(calDay)
  if (p.el.querySelector('.pa-cal')) fail('the calendar does not close after picking a day')
  if (fromBox.value !== OLD_ISO) fail(`the calendar pick was not written into the input: ${fromBox.value}`)
  await type(toBox, OLD_ISO)
  const faceText = [...p.el.querySelectorAll('.pa-dateface')].map(f => f.textContent.trim())
  if (!faceText.includes(OLD_ISO)) fail(`the themed date face is not the ISO day: ${faceText}`)
  assertScope(p, JOBS.runs.filter(r => r.date === OLD_ISO), 'one-day old/deleted-job range')
  await type(fromBox, '2030-01-01')
  await type(toBox, '2030-12-31')
  assertScope(p, [], 'future range is empty')
  await click(preset(p.el, 'All'), 80)
  assertScope(p, JOBS.runs, 'cleared date range')
}
p = await mount('en', 'windowed', 'health')
await checkDates(p)
p = await mount('en', 'windowed', 'chronicle')
await checkDates(p)

// SORT MENU: it only changes journal ORDER, never membership (Health owns KPI figures).
if (!selFace(p.el, 'sort')) fail('the sort menu is missing (.pa-selwrap[data-sel="sort"])')
if (!/Newest first/.test(selFace(p.el, 'sort').textContent)) {
  fail(`the default sort is not "Newest first": ${selFace(p.el, 'sort').textContent}`)
}
const firstRow = rows(p.el)[0].textContent
await click(selFace(p.el, 'sort'))
const sortOpts = popOpts(p.el)
if (sortOpts.length !== 4) fail(`there must be 4 sort options: ${sortOpts.length}`)
if (sortOpts.some(o => o.querySelector('.pa-check'))) fail('a single-select menu shows checkboxes (reads as multi)')
await click(optNamed(p.el, 'Oldest first'))
if (p.el.querySelector('.pa-pop')) fail('the window does not close after a single pick')
if (rows(p.el)[0].textContent === firstRow) fail('the sort did not change the row order')
if (rows(p.el).at(-1).textContent !== firstRow) {
  fail(`"Oldest first" did not fully reverse the list: last row ${rows(p.el).at(-1).textContent.slice(0, 40)}`)
}
assertScope(p, JOBS.runs, 'sorting preserves exact journal membership')
await click(selFace(p.el, 'sort'))
await click(optNamed(p.el, 'By status'))
if (!/Failed/.test(rows(p.el)[0].textContent)) {
  fail(`"By status" did not put the failed run first: ${rows(p.el)[0].textContent.slice(0, 40)}`)
}
await click(selFace(p.el, 'sort'))
await click(optNamed(p.el, 'By job'))
const jobLabelOf = row => (row.querySelector('.pa-titlecell .pa-clamp, .ch-description strong')?.textContent || '').trim()
const seq = rows(p.el).map(jobLabelOf)
const grouped = seq.every((label, i) => seq.indexOf(label) === i || seq[i - 1] === label)
if (!grouped) fail(`"By job" did not group the rows: ${seq}`)
// The two runs of one job must sit NEXT TO each other — the grouping property, independent of which
// job happens to sort first under the (now English) collation.
if (!seq.some((label, i) => i > 0 && seq[i - 1] === label)) {
  fail(`"By job" did not bring the two runs of one job together: ${seq}`)
}
await click(selFace(p.el, 'sort'))
await click(optNamed(p.el, 'Newest first'))
if (rows(p.el)[0].textContent !== firstRow) fail('returning to the default sort did not restore the rows')
assertScope(p, JOBS.runs, 'returning to default sort restores membership')

// Esc closes an OPEN PICKER WINDOW first: the drawer stays (one cancel gesture does one thing).
await click(rows(p.el)[0])
if (!drawerOf(p.el)) fail('the drawer did not open (Esc priority check)')
await click(selFace(p.el, 'sort'))
if (!p.el.querySelector('.pa-pop')) fail('the sort menu did not open (Esc priority check)')
await act(async () => { dom.window.document.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })) })
await act(async () => { await new Promise(r => setTimeout(r, 40)) })
if (p.el.querySelector('.pa-pop')) fail('Esc does not close the picker window')
if (!drawerOf(p.el)) fail('Esc closed the drawer while closing the picker window')
await click(drawerOf(p.el).querySelector('.pa-iconbtn'))
if (drawerOf(p.el)) fail('the close button does not close the drawer (after the Esc check)')

async function checkReadStates(target) {
  const p = await mount('en', 'data', target)
  const jobsGets = () => p.historyGets().filter(x => x.startsWith('/health/jobs?window='))
  // The refresh button really re-reads the data (a dead button is not accepted).
  const beforeGets = jobsGets().length
  const refreshBtn = p.el.querySelector('[aria-label="Refresh"]')
  if (!refreshBtn) fail('the refresh button is missing (aria-label="Refresh")')
  await click(refreshBtn, 60)
  const afterGets = jobsGets().length
  if (afterGets <= beforeGets) fail(`the refresh button did not re-read the data: ${beforeGets} → ${afterGets}`)

  // ===========================================================================
  // 4) The host UI KIT: the actions, the pills, the choice control and the three
  //    read states are the kit's own components — a hand-rolled button would
  //    pass every behaviour check while looking foreign in the application.
  // ===========================================================================
  const kitCount = sel => p.el.querySelectorAll(sel).length
  if (target === 'chronicle' && rows(p.el).some(row => !row.querySelector('.ch-outcome')?.textContent.trim())) fail('Chronicle has an empty readable outcome instead of its status label')
  if (kitCount('[data-slot="badge"]') !== kitCount('.pa-badge')) fail('a pill is not a kit Badge')
  const segmentCount = kitCount('[data-slot="segmented-control"]')
  // Metro (2.5.0): both targets mount the ONE History detail, so each holds exactly one shared filter bar
  // (one date-preset control) plus the journal's status control.
  const expectedSegments = 2
  if (segmentCount !== expectedSegments) fail(`${target}: date/status presets are not kit SegmentedControls (${segmentCount} != ${expectedSegments})`)
  if (!p.el.querySelector('[data-slot="segmented-control"] button[aria-pressed]')) {
    fail('the preset control reports no pressed state')
  }
  if (kitCount('[data-slot="button"]') < 1) {
    fail(`the actions are not kit Buttons: ${kitCount('[data-slot="button"]')}`)
  }
  const kitRefresh = p.el.querySelector('[aria-label="Refresh"]')
  if (kitRefresh?.getAttribute('data-slot') !== 'button') fail('the refresh action is not a kit Button')
  if (!kitRefresh?.querySelector('svg')) fail('the refresh button lost its glyph')
  // The three read states: nothing yet (Loader) · the read failed (ErrorState) · no runs (PanelEmpty).
  const noRuns = await mount('en', 'empty', target)
  if (!noRuns) fail('the empty read did not mount')
  else if (!noRuns.el.querySelector('[data-slot="panel-empty"]')) {
    fail('a read with no runs is not a kit PanelEmpty')
  } else {
    must(visibleText(noRuns.el), ['No runs recorded', 'the Hermes scheduler'], 'empty state')
    if (noRuns.el.querySelectorAll('.pa-kpi, .pa-log').length) fail('the panel drew cards for zero runs')
  }
  const failing = await mount('en', 'error', target)
  if (failing && !failing.el.querySelector('[data-slot="error-state"]')) {
    fail('a failed read is not a kit ErrorState')
  } else if (failing) {
    must(visibleText(failing.el), ['Run log unreadable', 'The cron run log could not be read',
      'the run log could not be read'], 'error state')
  }
  // A read that fails AFTER a good one keeps the last data on screen and SAYS it is stale: before 2.16.2
  // the error was dropped the moment any data existed.
  const flaky = await mount('en', 'flaky', target)
  if (flaky) {
    assertScope(flaky, JOBS.runs, 'first good read before failed refresh')
    await click(flaky.el.querySelector('[aria-label="Refresh"]'), 80)
    const stale = flaky.el.querySelector('.pa-stale')
    if (!stale) fail('a failed refresh over existing data shows no stale notice')
    else must(stale.textContent, ['could not be refreshed', 'the scheduler store is busy'], 'stale notice')
    assertScope(flaky, JOBS.runs, 'stale refresh retains data')
    if (flaky.el.querySelector('[data-slot="error-state"]')) fail('a stale refresh blocked the page with an error state')
  }
  const slow = await mount('en', 'pending', target)
  if (slow && !slow.el.querySelector('[data-slot="loader"]')) fail('a read in flight shows no kit Loader')
  // The refresh control spins for EVERY read, the timed ones included, not only for a manual press.
  {
    const realInterval = globalThis.setInterval
    const ticks = []
    globalThis.setInterval = (fn, ms, ...rest) => { if (ms === 60000) ticks.push(fn); return realInterval(fn, ms, ...rest) }
    let pp
    try { pp = await mount('en', 'controlledpoll', target) }
    finally { globalThis.setInterval = realInterval }
    const spin = () => pp.el.querySelector('[aria-label="Refresh"]')?.getAttribute('data-busy')
    const reads = () => pp.historyJobs().length
    if (spin() !== '0') fail(`the refresh control spins at rest: ${spin()}`)
    if (!ticks.length) fail('the panel set no 60 s poll')
    else {
      await act(async () => { ticks.at(-1)() })
      await act(async () => { await new Promise(r => setTimeout(r, 30)) })
      if (spin() !== '1') fail('a timed poll in flight does not show the busy state')
      const timedPoll = ticks.at(-1)
      const pendingCount = reads()
      if (pendingCount !== 2 || pp.reads.length !== 1) fail(`${target}: the first timed tick did not start exactly one pending read`)
      await act(async () => { timedPoll(); timedPoll() })
      if (reads() !== pendingCount) fail(`${target}: timed polling started overlapping reads while one was pending`)
      if (spin() !== '1') fail(`${target}: skipped timed ticks cleared the pending read busy state`)
      assertScope(pp, JOBS.runs, 'pending timed poll retains the last snapshot')

      // A rejection must release the same effect's guard; a subsequent timed tick can retry.
      await act(async () => { pp.reads[0]?.reject(new Error('controlled timed read failed')) })
      if (spin() !== '0') fail(`${target}: a rejected timed read left refresh busy`)
      const stale = pp.el.querySelector('.pa-stale')
      if (!stale) fail(`${target}: a rejected timed read did not expose stale data`)
      else must(stale.textContent, ['controlled timed read failed'], `${target} timed read failure`)
      assertScope(pp, JOBS.runs, 'rejected timed poll retains the last snapshot')
      await act(async () => { timedPoll() })
      if (reads() !== pendingCount + 1 || spin() !== '1') fail(`${target}: polling did not retry after a rejection`)
      await act(async () => { pp.reads[1]?.resolve(JOBS) })
      if (spin() !== '0' || pp.el.querySelector('.pa-stale')) fail(`${target}: successful timed retry did not clear busy/stale state`)
      assertScope(pp, JOBS.runs, 'successful timed retry')

      // Refresh starts a new effect epoch even while the old request is pending. Resolve NEW
      // first, then OLD: the abandoned epoch must never replace the newer snapshot.
      await act(async () => { timedPoll() })
      const oldRead = pp.reads.at(-1)
      const beforeRefresh = reads()
      await click(pp.el.querySelector('[aria-label="Refresh"]'), 30)
      if (reads() !== beforeRefresh + 1 || spin() !== '1') fail(`${target}: refresh did not start a new epoch while the old read was pending`)
      const newRead = pp.reads.at(-1)
      if (newRead === oldRead) fail(`${target}: refresh reused the old pending request`)
      const NEW = { ...JOBS, runs: JOBS.runs.slice(1, 3) }
      const OLD = { ...JOBS, runs: JOBS.runs.slice(0, 1) }
      await act(async () => { newRead?.resolve(NEW) })
      assertScope(pp, NEW.runs, 'NEW refresh snapshot resolved before OLD')
      if (spin() !== '0') fail(`${target}: the NEW refresh snapshot left busy set`)
      await act(async () => { oldRead?.resolve(OLD) })
      assertScope(pp, NEW.runs, 'late OLD response cannot overwrite NEW refresh snapshot')
      if (spin() !== '0' || pp.el.querySelector('.pa-stale')) fail(`${target}: late OLD response changed NEW read state`)
      const afterRefresh = reads()
      await act(async () => { timedPoll() })
      if (reads() !== afterRefresh) fail(`${target}: an abandoned epoch's timer still issued a read`)
    }
  }
}
await checkReadStates('health')
await checkReadStates('chronicle')

// The drawer's full-body request can fail: the drawer says so instead of silently keeping the preview.
const runFail = await mount('en', 'runfail', 'chronicle')
if (runFail) {
  await click(rows(runFail.el)[0], 80)
  const d = drawerOf(runFail.el)
  if (!d) fail('the drawer did not open for the full-body failure check')
  else {
    const details = d.querySelector('details.ch-technical')
    const error = d.querySelector('.pa-body-fail')
    if (!details || details.open || !error || error.closest('details') || error.getAttribute('role') !== 'status') fail('full-body failure feedback is hidden inside the closed technical disclosure')
    must(exposedText(d), ['The full body could not be loaded', 'the run store is locked'], 'visible drawer body failure')
    await click(rows(runFail.el)[1])
    const next = drawerOf(runFail.el)
    if (!next || next.querySelector('.pa-body-fail, .pa-copy-fail') || next.querySelector('details.ch-technical')?.open) fail('switching away from a failed body retained its error/disclosure state')
  }
}

// A successful transport response is not enough: the payload must belong to the requested run.
const wrongRun = await mount('en', 'wrongrun', 'chronicle')
if (wrongRun) {
  const selected = rows(wrongRun.el)[0]
  const selectedId = selected?.getAttribute('data-key')
  const original = JOBS.runs.find(r => r.id === selectedId)
  await click(selected, 80)
  const d = drawerOf(wrongRun.el)
  const request = wrongRun.gets.find(g => g.startsWith('/health/jobs/run'))
  if (!request || new URL(request, 'https://fixture.invalid').searchParams.get('id') !== selectedId) {
    fail('wrong-run rejection check did not request the selected run id')
  }
  if (!d) fail('the inspector did not open for the wrong-run rejection check')
  else {
    if (!original || !(original.body_len > original.body.length)) fail('wrong-run check did not start with a truncated preview')
    if (d.querySelector('.pa-raw')?.textContent !== original?.body) fail('a wrong-run payload replaced the selected run preview')
    if (visibleText(wrongRun.el).includes(FOREIGN_BODY)) fail('a wrong-run payload leaked foreign output into Chronicle')
    const error = d.querySelector('.pa-body-fail')
    if (error?.getAttribute('role') !== 'status') fail('wrong-run body rejection has no accessible error status')
    else must(error.textContent, ['The full body could not be loaded'], 'wrong-run body rejection')
    if (d.querySelector('details.ch-technical')?.open || error?.closest('details')
      || !exposedText(d).includes('The full body could not be loaded')) fail('wrong-run rejection feedback is hidden while Technical details is closed')
    if (/loading the body/.test(d.textContent)) fail('wrong-run rejection left the body loading indicator active')
  }
}


// A copy that fails says so instead of doing nothing.
// Full-body completion is tied to the selected ID, not merely a successful transport:
// resolve B before A, then copy exactly B's loaded body through the visible control.
{
  const keepClip = Object.getOwnPropertyDescriptor(globalThis.navigator, 'clipboard')
  const copies = []
  Object.defineProperty(globalThis.navigator, 'clipboard', {
    configurable: true, value: { writeText: async text => { copies.push(text) } }
  })
  try {
    const probe = await mount('en', 'controlledbody', 'chronicle')
    const selectedRows = rows(probe.el)
    await click(selectedRows[0])
    const readA = probe.reads[0]
    if (readA?.id !== selectedRows[0].getAttribute('data-key')) fail('controlled body A did not request its selected ID')
    await click(selectedRows[1])
    const readB = probe.reads[1]
    const selectedId = selectedRows[1].getAttribute('data-key')
    if (readB?.id !== selectedId) fail('controlled body B did not request its selected ID')
    const fullB = 'MATCHING B FULL OUTPUT\nLiteral <b>markup</b> · trailing newline\n'
    await act(async () => { readB?.resolve({ ok: true, id: selectedId, body: fullB, body_len: fullB.length }) })
    const inspector = drawerOf(probe.el)
    await openTechnical(inspector)
    if (inspector.querySelector('.pa-raw')?.textContent !== fullB || inspector.querySelector('b')) fail('matching body B was not loaded literally before copying')
    await act(async () => { readA?.resolve({ ok: true, id: readA.id, body: FOREIGN_BODY, body_len: FOREIGN_BODY.length }) })
    if (drawerOf(probe.el) !== inspector || inspector.querySelector('.pa-raw')?.textContent !== fullB
      || visibleText(probe.el).includes(FOREIGN_BODY)) fail('late body A replaced or leaked into selected body B')
    const copy = inspector.querySelector('.pa-copy')
    if (!copy || copy.closest('details')?.open !== true) fail('loaded body B has no reachable copy action after disclosure')
    await click(copy)
    if (copies.length !== 1 || copies[0] !== fullB || copy.textContent.trim() !== 'Copied'
      || inspector.querySelector('.pa-copy-fail')) fail('copy did not use exactly the selected matching full body or report success')
    await click(inspector.querySelector('.pa-iconbtn'), 0)
    await click(selectedRows[0])
    const abandoned = probe.reads.at(-1)
    await click(drawerOf(probe.el)?.querySelector('.pa-iconbtn'), 0)
    await act(async () => { abandoned?.reject(new Error('late closed-body failure')) })
    if (drawerOf(probe.el) || visibleText(probe.el).includes('late closed-body failure')) fail('a closed inspector was resurrected or leaked a late body failure')
    await click(selectedRows[1])
    const retry = probe.reads.at(-1)
    if (drawerOf(probe.el)?.querySelector('.pa-copy-fail, .pa-body-fail')
      || drawerOf(probe.el)?.querySelector('details.ch-technical')?.open) fail('new run selection retained previous copy/body/disclosure state')
    await act(async () => { retry?.resolve({ ok: true, id: selectedId, body: fullB, body_len: fullB.length }) })
    if (probe.posts.length || copies.length !== 1) fail('read/selection/close issued a write or an extra clipboard operation')
  } finally {
    if (keepClip) Object.defineProperty(globalThis.navigator, 'clipboard', keepClip)
    else delete globalThis.navigator.clipboard
  }
}
{
  const keepClip = Object.getOwnPropertyDescriptor(globalThis.navigator, 'clipboard')
  Object.defineProperty(globalThis.navigator, 'clipboard', {
    configurable: true, value: { writeText: () => Promise.reject(new Error('clipboard denied')) }
  })
  const cp = await mount('en', 'data', 'chronicle')
  await click(rows(cp.el)[1], 80)
  const copyDetails = await openTechnical(drawerOf(cp.el))
  const copyBtn = drawerOf(cp.el)?.querySelector('.pa-copy')
  if (!copyBtn) fail('the drawer has no copy control while a clipboard exists')
  else {
    await click(copyBtn, 60)
    await click(copyDetails.querySelector('summary'))
    if (copyDetails.open) await act(async () => { copyDetails.open = false })
    const said = drawerOf(cp.el).querySelector('.pa-copy-fail')
    if (!said || said.getAttribute('role') !== 'status' || said.closest('details')
      || !/clipboard denied/.test(exposedText(drawerOf(cp.el)))) {
      fail(`a failed copy is silent: ${said?.textContent || 'nothing shown'}`)
    }
  }
  if (keepClip) Object.defineProperty(globalThis.navigator, 'clipboard', keepClip)
  else delete globalThis.navigator.clipboard
}
for (const target of ['chronicle', 'health']) {
  const p = await mount('en', 'data', target)
  const css = p.el.querySelector('.pa-root > style')?.textContent || ''
  if (target === 'chronicle' && (!/\.ch-journal \.pa-drawer\{[^}]*position:static/.test(css)
    || !/\.ch-journal \.pa-drawer\{[^}]*[;{]height:auto[;}]/.test(css)
    || !/\.ch-journal \.pa-drawer\{[^}]*min-height:520px/.test(css)
    || !/\.pa-root \.ch-scroll\{[^}]*overflow-y:auto/.test(css)
    || !/\.ch-journal \.ch-inspector-body\{[^}]*overflow-y:visible/.test(css))) {
    fail('the adjacent content-led inspector reverted to an overlay/fixed box or the chronology lost independent scrolling')
  }
  if (/#[0-9a-fA-F]{3,8}\b|rgba?\(|color-scheme:\s*dark/.test(css)) {
    fail('the panel CSS carries a fixed colour or forces a colour scheme')
  }
  if (/ui-bg-sidebar/.test(p.el.querySelector('.pa-root')?.getAttribute('style') || '')) {
    fail('the page paints itself with the sidebar background')
  }
  const actMeta = [...p.el.querySelectorAll('.pa-sectitle')].find(s => /Activity by job/.test(s.textContent))
    ?.querySelector('.pa-secmeta')?.textContent || ''
  if (target === 'health' && !/^last \d+ (days|h)$/.test(actMeta)) {
    fail(`the activity card does not state its window in one phrase: ${actMeta}`)
  }
}

// ===========================================================================
// 5) Language contract: one bundle, app-locale driven, no picker, no raw key
// ===========================================================================
p = await mount('en', 'data', 'chronicle')
if (p.el.querySelector('.pa-seg button')?.textContent.trim().match(/^(TR|EN)$/)) {
  fail('a language button survives in a segment')
}
if ([...p.el.querySelectorAll('button')].some(b => ['TR', 'EN', 'Tr', 'En'].includes((b.textContent || '').trim()))) {
  fail('a TR/EN language button is present')
}
if (p.el.querySelector('[class*="lang"]')) fail('an element carrying a "lang" class is present')
if (p.gets.includes('/settings') || p.posts.some(x => x.path === '/settings')) {
  fail('the panel still calls the removed /settings language route')
}
for (const appLocale of ['tr', 'ja']) for (const target of ['health', 'chronicle']) {
  const other = await mount(appLocale, 'data', target)
  if (!other) continue
  if (other.el.querySelector('[class*="lang"]') ||
      [...other.el.querySelectorAll('button')].some(b => ['TR', 'EN'].includes((b.textContent || '').trim()))) {
    fail(`a language picker appeared under the ${appLocale} app locale`)
  }
  if (stub.calls.registered.length !== 1 || stub.calls.registered[0].locales.join('|') !== 'en') {
    fail(`the ${appLocale} run did not register exactly one 'en' bundle`)
  }
  if (other.nav.data.label !== 'Wiki Automation') {
    fail(`the sidebar label is not the visible name under ${appLocale}: ${other.nav.data.label}`)
  }
  const frame = target === 'health'
    ? ['Runs', 'Failed', 'Silent', 'Delivered', 'Findings', 'Run flow', 'Activity by job', 'Today', 'All jobs']
    : ['Run journal', 'Select a run', 'Today', 'Newest first', 'All jobs', 'Completed', 'Running']
  must(other.text, frame, `${target} frame under ${appLocale}`)
  if (RAW_KEY.test(other.text)) fail(`a raw key reached the screen under ${appLocale}`)
  if (other.errors.size) fail(`the panel threw under ${appLocale}: ${[...other.errors].join(' | ')}`)
}

// ===========================================================================
// MOTION: the values come from ONE table (no hand-written duration reaches the stylesheet) and
// reduced motion is honoured — the caret's INLINE transition included, which a media query cannot
// reach (it kept turning for a reader who asked for no motion).
{
  const dp = await mount('en', 'daily')
  // Activity over a 12-day window: every job row is visible without scrolling and the axis names days.
  const act = [...dp.el.querySelectorAll('.pa-sec')].find(c => /Activity by job/.test(c.textContent))
  const actRows = act?.querySelectorAll('.pa-act-row').length || 0
  const actScroll = act?.querySelector('.pa-act-scroll')
  if (actRows !== 4) fail(`activity: ${actRows} of 4 job rows drawn`)
  if (act?.querySelector('.pa-act')?.style.height) {
    fail(`activity: a fixed ${act.querySelector('.pa-act').style.height} box hides rows behind a scroll`)
  }
  if (parseFloat(actScroll?.style.maxHeight) < actRows * 18) {
    fail(`activity: ${actRows} rows of 18px do not fit the ${actScroll?.style.maxHeight} scroll box`)
  }
  const axis = [...(act?.querySelectorAll('.pa-act-axis span span') || [])].map(s => s.textContent)
  if (!axis.length || axis.some(a => !/^\d{2}\.\d{2} \d{2}:\d{2}$/.test(a))) {
    fail(`activity: a 12-day axis must name the day and the time: ${axis.join(' … ')}`)
  }
  const actMeta = act?.querySelector('.pa-sectitle')?.textContent || ''
  if (!/last 12 days/.test(actMeta)) fail(`activity: the window reads in hours: ${actMeta}`)
  const cell = act?.querySelector('.pa-act-cell')
  if (cell) {
    await hover(cell)
    const tip = dp.el.querySelector('.pa-tip')?.textContent || ''
    await unhover(cell)
    if (!/^\d{2}\.\d{2} \d{2}:\d{2} · /.test(tip)) fail(`activity: a cell's tooltip has no day: ${tip}`)
  }
}
p = await mount('en', 'data', 'health')
cards = [...p.el.querySelectorAll('.pa-sec')]
bars = [...p.el.querySelectorAll('.pa-bar-col')]
// A: the sparkline and the delta come from the trend the payload carries — the delta is compared
// against the PREVIOUS window, never against the current one (which would invent the baseline).
const actCard = p.el.querySelector('.pa-act') ? cards.find(c => c.querySelector('.pa-act')) : null
if (!actCard) fail('the activity card is missing')
else {
  const rows = actCard.querySelectorAll('.pa-act-row')
  if (!rows.length) fail('the activity card drew no job row')
  if (rows.length > 24) fail(`the activity card drew ${rows.length} rows (the cap is 24)`)
  const actJobs = Object.keys(JOBS.trend?.per_job || {})
    .filter(jid => (JOBS.trend.per_job[jid] || []).some(c => c.runs > 0)).length
  if (rows.length !== Math.min(24, actJobs)) {
    fail(`the activity card drew ${rows.length} of ${actJobs} job(s) with runs`)
  }
  const actScroll = actCard.querySelector('.pa-act-scroll')
  if (!actScroll) fail('the activity card does not scroll, so jobs past the visible rows are unreachable')
  if (!actScroll.style.maxHeight || actScroll.style.overflowY !== 'auto') {
    fail(`the activity card scrolls wrongly: ${actScroll.style.maxHeight} / ${actScroll.style.overflowY}`)
  }
  const cells = actCard.querySelectorAll('.pa-act-cell')
  const bucketCount = (JOBS.trend?.buckets || []).length
  if (cells.length !== rows.length * bucketCount) {
    fail(`the heat strip is not lanes × buckets: ${cells.length}`)
  }
  const tones = new Set([...cells].map(c => c.getAttribute('data-tone')))
  if (!tones.has('bad')) fail('a failed bucket has no bad cell')
  if (!tones.has('warn')) fail('a silent bucket has no warn cell')
  if (actCard.querySelectorAll('.pa-act-axis span span').length !== 2) {
    fail('the activity card has no first/last bucket axis under its cells')
  }
  if (String(actScroll?.style.maxHeight) !== '72px') {
    fail(`the activity card does not show four job rows before it scrolls: ${actScroll?.style.maxHeight}`)
  }
}
const sparks = p.el.querySelectorAll('.pa-spark')
if (sparks.length !== 5) fail(`every KPI card should carry a sparkline: ${sparks.length}`)
else {
  const columns = sparks[0].querySelectorAll('rect').length
  if (columns !== (JOBS.trend?.buckets || []).length) {
    fail(`the sparkline does not draw one column per trend bucket: ${columns} column(s)`)
  }
  const strokes = new Set([...sparks].flatMap(s => [...s.querySelectorAll('rect')].map(r => r.getAttribute('fill'))))
  if ([...strokes].some(s => !String(s).startsWith('var(--ui-'))) {
    fail(`a sparkline is painted with a non-theme colour: ${[...strokes].join(' ')}`)
  }
}
const deltas = [...p.el.querySelectorAll('.pa-delta')].map(d => d.textContent)
if (!deltas.some(d => d.startsWith('▲') || d.startsWith('▼'))) {
  fail(`no KPI delta reached the screen: ${deltas.join(' ')}`)
}
if (deltas.length !== 4) fail(`a delta is drawn where no previous window exists: ${deltas.length}`)
if (deltas.some(d => d.includes('≈'))) fail(`a complete trend drew an approximate delta: ${deltas.join(' ')}`)
const css = String(p.el.querySelector('.pa-root > style')?.textContent || '')
for (const [job, ms] of [['hover', 120], ['row', 200], ['caret', 200],
  ['drawer', 320]]) {
  if (!css.includes(`${ms}ms`)) fail(`the ${job} job's duration is not in the rendered stylesheet`)
}
if (!css.includes('cubic-bezier(.4,0,.2,1)')) fail('the standard curve is missing from the stylesheet')
const badSeconds = (css.match(/transition:[^;}]*/g) || []).filter(d => /\.\d+s\b/.test(d))
if (badSeconds.length) fail(`a hand-written second duration reached a transition: ${badSeconds[0]}`)
const healthReport = {
  buckets: bars.length, empty: bars.filter(b => b.getAttribute('data-zero') === '1').length,
  badges: p.el.querySelectorAll('[data-slot="badge"]').length
}
// K3: a trend read cut at the row cap undercounts the previous window, so its delta is marked approximate.
const capVm = await mount('en', 'trendcap')
const capDeltas = [...capVm.el.querySelectorAll('.pa-delta')]
if (capDeltas.length !== 4) fail(`a capped trend lost its deltas: ${capDeltas.length}`)
if (capDeltas.some(d => d.getAttribute('data-approx') !== 'true' || !d.textContent.startsWith('≈'))) {
  fail(`a delta from a capped trend is shown as exact: ${capDeltas.map(d => d.textContent).join(' ')}`)
}
if (capDeltas.some(d => !String(d.getAttribute('aria-label') || d.getAttribute('data-tip') || d.outerHTML).includes('approximate'))) {
  fail('a capped-trend delta does not say it is approximate')
}
p = await mount('en', 'data', 'chronicle')
const journalReport = { rows: rows(p.el).length, badges: p.el.querySelectorAll('[data-slot="badge"]').length }
const caret = p.el.querySelector('.pa-caret, .ch-caret')
if (!caret) fail('the caret is missing from a run row')
else if (!String(caret.style.transition).includes('200ms cubic-bezier(.4,0,.2,1)')) {
  fail(`the caret transition does not come from the table: ${caret.style.transition}`)
}
const realMatch = global.window.matchMedia
global.window.matchMedia = () => ({
  matches: true, addEventListener: () => {}, removeEventListener: () => {}
})
// LEAN: Health and Chronicle carry only what the reader acts on; one chart per question.
{
  const lp = await mount('en', 'dailydated')
  const said = lp.el.textContent.replace(/\s+/g, ' ')
  for (const gone of ['freshness · outcomes', 'the ring shows', 'rows in scope', 'reached its target',
    'no output to deliver', 'time = when the run started', 'filters apply to everything', 'Run timeline',
    'Job distribution']) {
    if (said.includes(gone)) fail(`lean: Health still says "${gone}"`)
  }
  const sum = lp.el.querySelector('.pa-flowsum')?.textContent || ''
  if (!/^46 runs/.test(sum)) fail(`lean: the run flow drops runs outside a fixed day count: "${sum}"`)
  const counts = [...lp.el.querySelectorAll('.pa-act-row .pa-act-count')].map(n => Number(n.textContent))
    .sort((a, b) => b - a)
  if (counts.join(',') !== '13,12,11,10') fail(`lean: activity rows do not carry their run counts: ${counts}`)
  const tp = await mount('en', 'trendcap')
  const approx = [...tp.el.querySelectorAll('.pa-act-row .pa-act-count')].map(n => n.textContent)
  if (!approx.length || approx.some(v => !v.startsWith('≈'))) fail(`lean: capped activity counts are not approximate: ${approx}`)
  const fp = await mount('en', 'data', 'health')
  const orb = [...fp.el.querySelectorAll('.pa-orb')].find(o => /Watch Dog/.test(o.textContent))
  await click(orb)
  const fmeta = [...fp.el.querySelectorAll('.pa-sec')].find(c => /Activity by job/.test(c.textContent))
    ?.querySelector('.pa-secmeta')?.textContent || ''
  if (!/all runs/.test(fmeta)) fail(`lean: unfiltered activity under a job filter is not labelled: "${fmeta}"`)
  const cp = await mount('en', 'data', 'chronicle')
  const csaid = cp.el.textContent.replace(/\s+/g, ' ')
  for (const gone of ['Status is the run outcome', 'Outcome, delivery and output in one record',
    'Read the proposal, its reason']) {
    if (csaid.includes(gone)) fail(`lean: Chronicle still says "${gone}"`)
  }
  const ccss = String(cp.el.querySelector('.pa-root > style')?.textContent || '')
  const rowH = /\.pa-root \.pa-log\.ch-run\{[^}]*height:(\d+)px/.exec(ccss)
  if (!rowH || Number(rowH[1]) > 56) fail(`lean: a Chronicle row is ${rowH?.[1]}px tall for one line of facts`)
  const hcss = ccss
  if (!/\.pa-act-name\{overflow:hidden;[^}]*font-size:[\d.]+px;[^}]*\}/.test(hcss)
    || !/\.pa-act-count\{margin-left:auto/.test(hcss)) fail('lean: the activity name/count rules are broken')
}
const reducedVm = await mount('en', 'data', 'chronicle')
// A CSS transition is switched off in the STYLESHEET (the audit rule walks every selector); the
// inline caret is the case no media query can reach, and it is checked just below.

const reducedCaret = reducedVm.el.querySelector('.pa-caret, .ch-caret')
if (String(reducedCaret?.style.transition || '') !== 'none') {
  fail(`reduced motion was ignored: the caret still transitions (${reducedCaret?.style.transition})`)
}
const reducedHealth = await mount('en', 'data', 'health')
const reducedCss = String(reducedHealth.el.querySelector('.pa-root > style')?.textContent || '')
// Since 2.3.8 Health plays no entry choreography of its own (bars, ring, KPI figures): the four views
// share one entry rule in the shell, which the audit checks for a reduced-motion switch.
if (/\.pa-(bar|kpi|kpi-fig|ring-arc)\{[^}]*animation:(?!none)/.test(reducedCss)) {
  fail('Health animates its bars, ring or KPI figures again — entry motion belongs to the shared rule')
}
global.window.matchMedia = realMatch

if (problems.length) {
  console.error(`\nrender check FAILED — ${problems.length} problem(s)`)
  process.exit(1)
}
console.log('  motion: one table (hover 120 · row 200 · caret 200 · tab 280 · drawer 320 · shell 340) · reduced motion honoured, inline caret included')
console.log('render check OK — History detail: one journal (status · delivery) + Health diagnostics (position = when claimed, '
  + 'bar = duration, lateness tick, fixed layer), fixed layers, one scope filter, sorting, '
  + 'full body, the finding mapping (English sentence + the raw checker line beside it), '
  + 'one English bundle with no language picker and no raw key')
console.log(`  layers: KPI 112 floor · freshness 122 floor · chart 60 · Chronicle entry 94 / narrow 110 `
  + `(${journalReport.rows} entries) · independently scrolling chronology + adjacent content-led nonmodal inspector, immediate close`)
console.log(`  kit: ${journalReport.badges} Chronicle + ${healthReport.badges} Health Badge pills on screen · kit Button actions (the refresh `
  + 'control at rest; clear-filters · drawer close · copy · date-clear appear with their own control) · '
  + 'SegmentedControl presets · PanelDetail/PanelSectionLabel/PanelMeta/PanelBlock drawer · '
  + 'PanelList/PanelListRow findings (class Badge lead) · PanelEmpty/Loader/ErrorState read states')
console.log(`  Health chart: ${healthReport.buckets} day buckets (${healthReport.empty} empty) · Chronicle readable outcomes ${statusLabels.join('/')}`)
console.log('  scope: both views Today 5→3 · job picker 5→1→3→5 · Health orb 5→1→5 · outside the range 0 · Chronicle exact membership / Health KPI and flow')
console.log('  window: both views presets set all / 24h / 7d / 30d server windows')
console.log('  review regressions: both views single-flight timed polls · rejection releases retry guard · NEW refresh beats late OLD · Today→custom refetches all history and recovers the older run · wrong-run body rejected, selected preview retained')
console.log('  advanced filters: both views start closed · search/reset stay exposed and usable · native disclosure opens job/date controls · folding/reopening preserves exact scope and active indication')
console.log('  Metro: History reached by its header button (aria-pressed, one detail) · no tab strip · the review desk reached by its station: SEC-3 failed-context / scope-switch / late-poll guarantees · candidate read states never block runs or write')
console.log('  Chronicle sort: newest first ↔ oldest first ↔ by status ↔ by job · exact run membership unchanged')
console.log(`  inspector: the full body came from /health/jobs/run · ${FINDING_CASES.length} finding classes ` +
    'mapped to English with exact raw lines/actions after native disclosure · three visible summary pairs + eight technical metadata pairs · no Tab trap · immediate close and focus return')
console.log('  faithful projection: 28px glyph rings · HH:MM/full-date rows · error-first / actual bad-or-first finding synopsis · status/notification independent, backend labels exact · literal output unchanged')
console.log('  duration snapshot: finite numeric milliseconds and clock-bearing finite instants only · exact membership/order/selection · zero/unknown/invalid values · all-zero and empty states · filtered maximum scale')
console.log('  body/copy safety: wrong-ID rejected · B-before-A body completion cannot leak · exact matching full body copied after disclosure · closed-body completion ignored · failure statuses remain visible outside closed disclosure')
console.log('  language: one en bundle under wiki-automation · neither view offers a picker · English under tr/ja')
console.log(`  fixture: today ${TODAY_ISO} · oldest ${OLD_ISO} · ${TODAY_AT}`)

// Anything collected AFTER the check above is still a failure: a problem that cannot fail the gate is
// not a gate (this is how the motion block's assertions were silently swallowed before they moved up).
if (problems.length) {
  console.error(`\nrender check FAILED — ${problems.length} problem(s) (collected after the gate)`)
  process.exit(1)
}
// The polling timers stay open, so the process must exit explicitly (otherwise node hangs).
process.exit(0)
