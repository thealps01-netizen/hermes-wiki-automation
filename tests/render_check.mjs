/**
 * Wiki Automation panel — rendered in jsdom with the real React and exercised like a user would.
 *
 * Run: cd tests && node render_check.mjs [<plugin.js path>]   (exit code 0 = passed)
 *
 * What it locks (every item answers "does it really work?"):
 *   1. Registration: page path `/wiki-automation` + sidebar entry (label RESOLVED, never a raw key).
 *   2. ONE Metro view (2.5.0, Docs/metro-contract.md): the line (stations Harvest → Your review → Wiki,
 *      one branch line per reported adapter), the alert bar and at most one detail under the map. The
 *      reused 2.3.12 components are reached by clicks: Settings (root, install, jobs), History (the sole
 *      run journal), the Your review station (the review desk, one draft at a time). The 2.3.x tabs,
 *      Nexus map/inspector/wires, heartbeat strip, lower queue and per-view titles must stay gone.
 *   3. ROOT SELECTION uses the right SDK surface (`ctx.os.pickOpenPath`) and the backend derives the
 *      root from the picked FILE; a cancelled pick sends no request and the message stays honest.
 *   4. SAVE GATE: for an unverified root the panel does NOT write "saved" — it prints the backend's
 *      reason and does not refresh the state for nothing.
 *   5. A verified root is saved; the request body is right, the draft is cleared, the state REFRESHES.
 *   6. Candidate scan walks the folder ABOVE the root; clicking a row puts the root in the draft.
 *   7. Project settings consumes the staged engine lifecycle; its script diagnostics retain 3 of 4.
 *      Missing-engine local root selection, exact-plan confirmation, retry/refusal, native-context
 *      invalidation and bounded literal plan rendering are exercised without a real backend install.
 *   8. RUN STAMPS: another day's run carries its date; the run log itself lives once, in History
 *      (render_health.mjs). The 2.3.x Recent-runs card and its heartbeat were removed in 2.5.0.
 *   9. LANGUAGE: exactly ONE bundle is registered, the DOM has NO language picker, the text is English
 *      and a raw `wa.*` key never reaches the screen — the app translator resolves the plugin's own
 *      bundle by APP LOCALE, so the panel must work under any app language.
 *  10. Root editing writes only `/automation/*`; staged installation writes only `/engine/*`.
 *      The panel never writes cron history, and the removed
 *      `/settings` language route is not called at all.
 *  11. Refresh really re-reads; there is no native <select> (theme contract).
 *  12. EXTERNAL CHECK TEXT: every `reason` the Turkish checker (`~/.llmwiki-audit/wikiconfig.py`)
 *      produces is shown in English, taken from the panel's own `en` bundle with the paths and
 *      numbers intact, while the raw text stays reachable in the detail block and the tooltip. An
 *      unrecognized reason falls back to ONE neutral label — never to an invented translation. A
 *      reason the backend already resolved is printed as it arrived, with no second reading.
 *  13. HOST UI KIT: the panel is built from the kit (`Button` · `Badge` · `Input` · `SearchField` ·
 *      `SegmentedControl` · `PanelSectionLabel` · `PanelMeta` · `PanelBlock` · `CopyButton` ·
 *      `EmptyState` · `ErrorState` · `Loader` · `Tip`), stubbed in `kit-stub.mjs`. NOT one native
 *      `title=` reaches the DOM (the kit's `Tip` carries the raw text as `data-tip` on the trigger),
 *      the candidate list is filtered through the kit's `SearchField`.
 *  14. REVIEW DESK PROJECTION: actual Markdown heading (summary fallback), exact ref/destination binding,
 *      readable added/removed/context lines with accessible signs, literal HTML/Markdown and whitespace,
 *      original diff behind a closed native disclosure with an exact Copy payload, read-only reason/
 *      evidence navigation and proposal reset on candidate switches. jsdom verifies structure/type,
 *      not pixel clipping or CSS visibility of closed details.
 *  15. REFERENCE PASS (supabase + mintlify): ONE code language — every `.wa-mono` element (the root
 *      path, the candidate path, the raw check body, the run stamps/durations) resolves to the SAME
 *      family/size/leading, and the raw checker text sits in the kit's `PanelBlock` inside
 *      `.wa-raw`; both code surfaces are COPYABLE through the kit's `CopyButton` (the payload it is
 *      handed is asserted, and its trigger is aria-labelled). A message is a HELP CARD — a heading
 *      (`Why this was refused` / `Note` / `Result`), the one-sentence reason, the raw wording under
 *      an `as written` caption, and an action ONLY beside a refusal that carries the checker's own
 *      text. Secondary actions share ONE secondary shape (`data-variant="outline"`: pick · verify ·
 *      scan · scan folder · cancel) while Save and the confirmed copy/mirror write stay filled, and every icon button
 *      is ONE shape (the kit's `icon-sm`, circular, `aria-label`led) and the same size. An empty
 *      state carries its own second line (the kit's `EmptyState.description`).
 */
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { createRequire } from 'node:module'
import { JSDOM } from 'jsdom'
import { fixture as healthFixture } from './fixture-health.mjs'
import { automation, candidateDetail, candidates, cronValid, harvestStatus, isoIn, jobsState, jobsView, nextRuns, previewOf,
  runs, RUN_STAMPS, VALID_ROOT, engineStatus, enginePlan, ENGINE_REVISION, interruptedEngineStatus, engineRecoveryPlan } from './fixture.mjs'

const HERE_URL = new URL('.', import.meta.url)
const HERE = fileURLToPath(HERE_URL).replace(/\\/g, '/') + '/'
const SRC = process.argv[2] || `${HERE}../desktop/plugin.js`
const PLUGIN_ID = 'wiki-automation'

const SystemDate = Date
let clockNow = SystemDate.now()
globalThis.Date = class extends SystemDate {
  constructor(...args) { super(...(args.length ? args : [clockNow])) }
  static now() { return clockNow }
}

const problems = []
const failSeen = new Map()
const fail = m => {
  const n = (failSeen.get(m) || 0) + 1
  failSeen.set(m, n)
  problems.push(m)
  if (n === 1) console.error('  x', m)
  else if (n === 2) console.error('  x (repeats; counted once more each time)', m)
}
const must = (hay, needles, label) => {
  let missing = 0
  for (const n of needles) {
    if (!String(hay).includes(n)) { fail(`${label}: missing text ${JSON.stringify(n)}`); missing += 1 }
  }
  return missing
}
const RAW_KEY = /\bwa\.[a-z][a-zA-Z]*/

// The stub mirrors the app's plugin i18n: bundles are registered under the plugin id and resolved by
// dot-path against the ACTIVE app locale, falling back to the plugin's own `en`, then to the key.
// `translateNow` only ever reads the CORE catalog — which holds no plugin key — so it returns the key
// unchanged, exactly like the app would for a key the plugin owns.
writeFileSync(`${HERE}sdk-stub.mjs`, `
export * from './kit-stub.mjs'

export const calls = { posts: [], gets: [], registered: [], keys: [], registerKeys: [] }
const atom = initial => {
  let value = initial
  const listeners = new Set()
  return { get: () => value, listen: fn => { listeners.add(fn); return () => listeners.delete(fn) },
    set: next => { if (Object.is(next, value)) return; value = next; for (const fn of listeners) fn(next) } }
}
export const host = { state: { connectionId: atom('local'), profile: atom('default'), cwd: atom('/srv/wiki') },
  restartCalls: 0, restartGateway: async () => { host.restartCalls += 1; return host.onRestart ? host.onRestart() : { ok: true, pid: 1, name: 'gateway-restart' } } }
export const state = { appLocale: 'en', pickResult: '/srv/wiki/.llm-wiki/project.json',
                       pickCalls: [], emptyCandidates: false,
                       checker: { validate: null, derive: null, candidates: null,
                                  scanRoot: null, settings: null } }

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
`)

const src = readFileSync(SRC, 'utf8').replace("'@hermes/plugin-sdk'", `'${HERE_URL.href}sdk-stub.mjs'`)
writeFileSync(`${HERE}plugin-under-test.mjs`, src)

const dom = new JSDOM('<!doctype html><html><body></body></html>', { pretendToBeVisual: true })
global.window = dom.window
global.document = dom.window.document
Object.defineProperty(global, 'navigator', { value: dom.window.navigator, configurable: true })
global.IS_REACT_ACT_ENVIRONMENT = true

let AUTO = automation()
let RUNS = runs()

const React = await import('react')
const { createRoot } = await import('react-dom/client')
// `act` moved to `react` in React 18.3; the react-dom copy is deprecated and only warns.
const { act } = React.act ? React : await import('react-dom/test-utils')
// A test file runs for minutes and keeps earlier panels mounted, so their real 60-second polls would land in
// the shared call log at wall-clock-dependent moments and race every read-count assertion. Polls of a minute
// or longer never fire on their own here; a test that needs one captures its callback and calls it.
const realSetInterval = globalThis.setInterval
globalThis.setInterval = (fn, ms, ...rest) => (Number(ms) >= 60000 ? realSetInterval(() => {}, ms) : realSetInterval(fn, ms, ...rest))
const stub = await import(`${HERE_URL.href}sdk-stub.mjs`)

const mountedPanels = new Map()
let version = 0
async function mount(appLocale = 'en', overrides = {}) {
  AUTO = overrides.automation || automation()
  RUNS = overrides.runs || runs()
  stub.state.appLocale = appLocale
  await act(async () => {
    if (overrides.hostScopeSetter) overrides.hostScopeSetter(overrides.hostScope)
    else {
      stub.host.state.connectionId.set(overrides.hostScope?.connectionId === undefined ? 'local' : overrides.hostScope.connectionId)
      stub.host.state.profile.set(overrides.hostScope?.profile === undefined ? 'default' : overrides.hostScope.profile)
      stub.host.state.cwd.set(overrides.hostScope?.cwd === undefined ? '/srv/wiki' : overrides.hostScope.cwd)
    }
  })
  stub.state.engineStatus = overrides.engineStatus || engineStatus()
  stub.state.enginePrepare = overrides.enginePrepare || (body => enginePlan(body.project_root))
  stub.state.engineApply = overrides.engineApply || (body => ({ ok: true, state: 'installed_paused',
    install_id: body.install_id, revision: ENGINE_REVISION, activation_required: true }))
  stub.state.pickResult = overrides.pickResult === undefined
    ? '/srv/wiki/.llm-wiki/project.json' : overrides.pickResult
  stub.state.emptyCandidates = false
  stub.state.jobsState = jobsState()
  stub.state.jobFailure = null
  stub.state.throwOn = overrides.throwOn || null
  stub.state.jobsOverride = overrides.jobs || null
  stub.state.harvestPayload = overrides.harvest || null
  stub.state.candList = overrides.candidates || candidates()
  stub.state.candPayload = overrides.candidatesPayload || null
  stub.state.candRefuse = false
  stub.state.candShowError = null
  stub.state.candShow = overrides.candShow || null
  stub.state.candAct = overrides.candAct || null
  stub.state.checker = { validate: null, derive: null, candidates: null, scanRoot: null,
                         settings: null }
  stub.calls.gets.length = 0
  stub.calls.posts.length = 0
  stub.calls.keys.length = 0
  stub.calls.registerKeys.length = 0
  stub.calls.registered.length = 0
  const registrations = []
  const ctx = {
    rest: async (path, opts) => {
      if (overrides.panelRest && (path.startsWith('/automation') || path.startsWith('/jobs'))) {
        if (opts?.method === 'POST') stub.calls.posts.push({ path, body: opts.body })
        else stub.calls.gets.push(path)
        const response = overrides.panelRest(path, opts)
        if (response !== undefined) return response
        if (opts?.method === 'POST') stub.calls.posts.pop()
        else stub.calls.gets.pop()
      }
      if (overrides.folioRest && ['/automation', '/candidates', '/owner/recoverable'].includes(path)) {
        stub.calls.gets.push(path)
        return overrides.folioRest(path)
      }
      if (overrides.lifecycleRest && path.startsWith('/engine/')) {
        if (opts?.method === 'POST') stub.calls.posts.push({ path, body: opts.body })
        else stub.calls.gets.push(path)
        return overrides.lifecycleRest(path, opts)
      }
      if (opts?.method === 'POST') {
        stub.calls.posts.push({ path, body: opts.body })
        if (path === '/engine/prepare') return stub.state.enginePrepare(opts.body)
        if (path === '/engine/apply') return stub.state.engineApply(opts.body)
        if (path === '/automation/derive') {
          if (stub.state.checker.derive) {
            return { ok: false, reason: stub.state.checker.derive, reason_source: 'checker' }
          }
          return { ok: true, root: VALID_ROOT }
        }
        if (path === '/automation/validate') {
          if (stub.state.checker.validate) {
            return { ok: false, reason: stub.state.checker.validate, reason_source: 'checker' }
          }
          const ok = String(opts.body?.path || '') === VALID_ROOT
          return ok ? { ok: true, id: 'auto-id', pages: 419, reason: '' }
                    : { ok: false, reason: 'the folder is not a verified wiki root' }
        }
        if (path === '/automation/settings') {
          if (stub.state.checker.settings) {
            return { ok: false, reason: stub.state.checker.settings, reason_source: 'checker' }
          }
          const root = String(opts.body?.project_root || '')
          // COPY/MIRROR GATE: same id + different path is REFUSED unless `force` comes back.
          if (root === '/srv/mirror' && !opts.body?.force) {
            return { ok: false, needs_force: true,
                     reason: 'this folder carries the SAME project id but a different path '
                       + '(possibly a copy/mirror) — making it the root degrades the backup check. '
                       + 'Confirm to save.' }
          }
          const ok = root === VALID_ROOT || (root === '/srv/mirror' && opts.body?.force)
          return ok ? { ok: true, project_root: root, project: { ok: true, id: 'auto-id', pages: 419 },
                        settings: AUTO.settings }
                    : { ok: false, reason: 'the folder is not a verified wiki root' }
        }
        if (path === '/automation/scan_root') {
          if (stub.state.checker.scanRoot) {
            return { ok: false, reason: stub.state.checker.scanRoot, reason_source: 'checker' }
          }
          const dir = String(opts.body?.path || '')
          return dir ? { ok: true, scan_root: dir } : { ok: false, reason: 'no path given' }
        }
        if (path === '/jobs/preview') {
          if (stub.state.previewThrows) throw new Error('backend unreachable (500) on /jobs/preview')
          return previewOf(opts.body?.schedule)
        }
        if (path === '/jobs/act') {
          const role = String(opts.body?.role || '')
          const action = String(opts.body?.action || '')
          const row = stub.state.jobsState[role]
          if (stub.state.jobFailure) return { ok: false, ...stub.state.jobFailure }
          if (!row) return { ok: false, reason: 'unknown role' }
          if (action === 'remove' && !opts.body?.confirm) {
            return { ok: false, needs_confirm: true,
                     reason: 'removing a job needs an explicit confirmation' }
          }
          if (action === 'create') {
            row.live = true
            row.state = 'scheduled'
            row.id = 'job-new'
          }
          if (action === 'schedule') {
            const expr = String(opts.body?.schedule || '').trim()
            if (!expr) return { ok: false, reason: 'no schedule was given' }
            if (!cronValid(expr)) {
              return { ok: false, reason: `the store refused that schedule: invalid expression ${expr}` }
            }
            row.schedule = expr
            row.schedule_source = 'store'
            return { ok: true, action, role, schedule: expr,
                     view: jobsView(stub.state.jobsState) }
          }
          if (action === 'pause') row.state = 'paused'
          if (action === 'resume') row.state = 'scheduled'
          if (action === 'remove') {
            row.live = false
            row.state = 'absent'
            row.id = null
          }
          return { ok: true, action, role, view: jobsView(stub.state.jobsState) }
        }
        if (path === '/owner/activation') {
          if (stub.state.ownerActivate) return stub.state.ownerActivate(opts.body)
          stub.state.ownerSetup = { ...stub.state.ownerSetup, active: true, ready: false }
          return { ok: true, restart_required: true }
        }
        if (path === '/owner/recover') {
          if (stub.state.recoverAct) return stub.state.recoverAct(opts.body)
          stub.state.recoverable = []
          return { ok: true, state: 'applied', operation_id: 'fixture-recovered' }
        }
        if (['/candidates/act', '/owner/decision'].includes(path)) {
          if (stub.state.candAct) return stub.state.candAct(opts.body)
          const ref = String(opts.body?.ref || '')
          const action = path === '/owner/decision' ? 'approve' : String(opts.body?.action || '')
          const row = stub.state.candList.find(c => c.ref === ref)
          const head = { ok: false, ref, action }
          if (!row) return { ...head, reason: 'a candidate is named <run>/<name>, with letters, digits, - and _ only' }
          if (stub.state.candRefuse) {
            return { ...head, reason: `the engine refused to ${action} this candidate`,
                     output: '!! refused: format: contains [[wikilinks]]' }
          }
          if (action === 'reject') {
            if (!String(opts.body?.reason || '').trim()) return { ...head, reason: 'rejecting a candidate needs a reason' }
            stub.state.candList = stub.state.candList.filter(c => c.ref !== ref)
            return { ...head, ok: true, output: `OK rejected ${ref}: ${opts.body.reason}` }
          }
          if (!opts.body?.confirm) {
            return { ...head, needs_confirm: true, request_id: `fixture-owner-${stub.calls.posts.length}`,
                     review_digest: candidateDetail(ref).review_digest,
                     reason: "approving writes this source into the wiki's raw/sources folder, and the LLM Wiki "
                       + 'app will then ingest it, which costs model usage',
                     output: `[dry-run] would ${row.kind} ${row.target}; new evidence folders: []` }
          }
          stub.state.candList = stub.state.candList.filter(c => c.ref !== ref)
          return { ...head, ok: true, output: `OK ${row.kind} ${row.target} applied; evidence added: 1.` }
        }
        return { ok: false, reason: 'unexpected POST' }
      }
      stub.calls.gets.push(path)
      if (stub.state.throwOn && path.startsWith(stub.state.throwOn)) {
        throw new Error(`backend unreachable (500) on ${path}`)
      }
      if (path.startsWith('/health/jobs/run')) return { ok: true, body: 'run output', body_len: 10 }
      if (path.startsWith('/health/jobs')) return healthFixture()
      if (path === '/engine/status') return typeof stub.state.engineStatus === 'function'
        ? stub.state.engineStatus() : stub.state.engineStatus
      if (path === '/automation') return { ...AUTO, settings: { ...AUTO.settings } }
      if (path === '/harvest/status') return stub.state.harvestPayload || harvestStatus()
      if (path === '/jobs') return stub.state.jobsOverride || jobsView(stub.state.jobsState)
      if (path.startsWith('/runs')) return RUNS
      if (path === '/owner/recoverable') return { ok: true, operations: stub.state.recoverable || [] }
      if (path === '/owner/activation') return stub.state.ownerSetup
        || { ok: true, active: true, ready: true, code_changed: false, owner: 'local_owner',
             job: { id: 'job-h', name: 'Wiki Session Harvest', schedule: '30 21 * * *' }, plan_digest: 'd'.repeat(64) }
      if (path === '/candidates') {
        return stub.state.candPayload || { ok: true, audit_dir: '/srv/audit', candidates: [...stub.state.candList] }
      }
      if (path.startsWith('/candidates/show?ref=')) {
        const ref = decodeURIComponent(path.slice('/candidates/show?ref='.length))
        if (stub.state.candShowError) return { ok: false, ref, error: stub.state.candShowError }
        if (stub.state.candShow) return stub.state.candShow(ref)
        return candidateDetail(ref)
      }
      if (path.startsWith('/automation/candidates')) {
        if (stub.state.checker.candidates) {
          return { ok: false, reason: stub.state.checker.candidates, reason_source: 'checker' }
        }
        if (stub.state.emptyCandidates) {
          return { ok: true, root: '/srv', found: [], scanned: 102, skipped: 1, truncated: false }
        }
        return { ok: true, root: '/srv', scanned: 102, skipped: 1, truncated: false, found: [
          { root: '/srv/other-wiki', id: 'other', pages: 12, duplicates: [] },
          // SAME ID: the local folder and its mirror — making it the root would make the backup
          // check compare a path with itself.
          { root: '/srv/mirror', id: 'auto-id', pages: 419, duplicates: ['/srv/wiki'] }
        ] }
      }
      throw new Error(`unexpected path: ${path}`)
    },
    os: {
      pickOpenPath: opts => {
        stub.state.pickCalls.push(opts || {})
        return overrides.pickOpenPath ? overrides.pickOpenPath(opts) : Promise.resolve(stub.state.pickResult)
      }
    },
    i18n: {
      // The registration-time door: resolve through the registered bundles, like the app does.
      t: (key, ...args) => {
        stub.calls.registerKeys.push(key)
        return stub.resolveKey(PLUGIN_ID, key, args)
      },
      register: table => stub.registerBundles(PLUGIN_ID, table)
    },
    register: c => registrations.push(c)
  }
  const mod = await import(`${HERE_URL.href}plugin-under-test.mjs?v=${++version}`)
  const plugin = mod.default
  if (plugin?.id !== PLUGIN_ID) fail(`plugin id changed: ${plugin?.id}`)
  const seen = new Set()
  const onError = e => { seen.add(String(e?.message || e)) }
  plugin.register(ctx)
  const host = document.createElement('div')
  document.body.appendChild(host)
  const root = createRoot(host, { onUncaughtError: onError, onRecoverableError: onError })
  mountedPanels.set(root, host)
  const page = registrations.find(r => r.area === 'routes')
  if (!page) throw new Error('no page registration')
  await act(async () => { root.render(React.createElement(page.render)) })
  await act(async () => { await new Promise(r => setTimeout(r, 80)) })
  // Metro (2.5.0): ONE view. `mapFirst` records what the page shows before any click: the line, the
  // alert bar and no detail. The reused 2.3.12 components live inside details reached by clicks
  // (Docs/metro-contract.md § Details): `openConfig` opens Settings (RootCard, InstallCard, JobsCard,
  // InstallationFilesCard), `tab: 'Folio'` opens the Your review station (the review desk),
  // `tab: 'Chronicle' | 'Health'` opens History. The tab names stay only as names of those openers.
  const mapFirst = {
    metro: Boolean(host.querySelector('.wa-metro')),
    map: Boolean(host.querySelector('.wa-metro-map')),
    bar: host.querySelector('.wa-metro-bar')?.getAttribute('data-alert') || null,
    detail: host.querySelector('.wa-metro-detail')?.getAttribute('data-for') || null,
    healthShown: Boolean(host.querySelector('.pa-root')),
    tabs: [...host.querySelectorAll('[role="tab"], [role="tablist"]')].map(txt),
    tabSlots: [...host.querySelectorAll('[data-slot="tabs-trigger"]')].length,
    gets: [...stub.calls.gets]
  }
  if (overrides.openConfig !== false && !overrides.tab) await openDetail(host, 'settings')
  if (overrides.tab && overrides.tab !== 'Nexus') await selectTab(host, overrides.tab)
  return { root, host, registrations, errors: seen, mapFirst, unmount: () => root.unmount() }
}

const settle = (ms = 80) => act(async () => { await new Promise(r => setTimeout(r, ms)) })
const txt = el => (el?.textContent || '').replace(/\s+/g, ' ')
const click = async (el, ms = 60) => {
  if (!el) { fail('the button to click was not found'); return }
  await act(async () => {
    el.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }))
    await new Promise(r => setTimeout(r, ms))
  })
}
const setField = async (el, value) => {
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set
    setter.call(el, value)
    el.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
  })
}
const cards = host => [...host.querySelectorAll('.wa-card')]
// A card's head is the panel's own section head. The design language renamed it (`.wa-head` in the
// first grammar, `.g-panel-head` in the one that ships), so the lookup accepts either and the checks
// below stay about CONTENT, not about which stylesheet generation drew it.
const headOf = c => c.querySelector('.wa-head, .g-panel-head')
const cardByTitle = (host, title) =>
  cards(host).find(c => { const h = headOf(c); return h ? txt(h).includes(title) : false })
const btn = (scope, label) =>
  [...(scope?.querySelectorAll('button') || [])].find(b => txt(b).includes(label))
// jsdom mounts closed-details children; opening the named job first prevents impossible hidden clicks.
// Do not open Project, Folio originals or any other disclosure as a side effect of an action.
const openJobDisclosure = async row => {
  if (!row?.matches('details.wa-job')) { fail('the job action has no native job disclosure'); return false }
  if (!row.open) await click(row.querySelector(':scope > summary.wa-job-summary'), 0)
  if (!row.open) { fail('the job summary did not open before its action'); return false }
  return true
}
const clickJobButton = async (row, label, ms = 60) => {
  if (await openJobDisclosure(row)) await click(btn(row.querySelector(':scope > .wa-job-expanded'), label), ms)
}
// Metro openers. A detail opens under the map; pressing the same opener again folds it.
const OPENER = {
  settings: '[data-wa-nav="settings"]', history: '[data-wa-nav="history"]',
  review: '[data-wa-station="review"]', harvest: '[data-wa-station="harvest"]', wiki: '[data-wa-station="wiki"]'
}
const opener = (host, which) => host.querySelector(OPENER[which] || `[data-wa-line="${String(which).replace(/^line:/, '')}"]`)
const detailOf = (host, which) => host.querySelector(`.wa-metro-detail[data-for="${which}"]`)
const openDetail = async (host, which) => {
  if (detailOf(host, which)) return detailOf(host, which)
  const el = opener(host, which)
  if (!el) { fail(`the Metro opener for ${which} is missing`); return null }
  await click(el, 80)
  if (el.getAttribute('aria-pressed') !== 'true') fail(`${which} is not aria-pressed after it opened its detail`)
  if (!detailOf(host, which)) fail(`${which} did not open .wa-metro-detail[data-for="${which}"]`)
  if (host.querySelectorAll('.wa-metro-detail').length > 1) fail('more than one detail is open')
  if (RAW_KEY.test(txt(host))) fail(`${which} printed a raw i18n key`)
  // 2.5.1: History shows the m-13 run list; the 2.3.x run history (journal + diagnostics) is its
  // "Full technical log". The 2.3.x checks below exercise that log, so open it.
  if (which === 'history' && !detailOf(host, which)?.querySelector('.pa-root')) {
    const full = [...(detailOf(host, which)?.querySelectorAll('button') || [])].find(b => txt(b) === 'Full technical log')
    if (!full) fail('History has no "Full technical log" button')
    else await click(full, 120)
  }
  return detailOf(host, which)
}
const closeDetail = async host => {
  const open = host.querySelector('.wa-metro-detail')?.getAttribute('data-for')
  if (!open) return
  await click(opener(host, open), 80)
  if (host.querySelector('.wa-metro-detail')) fail(`a second press of ${open} did not fold its detail`)
}
// The 2.3.x tab names map onto the Metro openers; 'Nexus' (the old map) is "no detail open".
const selectTab = async (host, label) => {
  const which = { Folio: 'review', Chronicle: 'history', Health: 'history', Project: 'settings' }[label]
  if (label === 'Nexus') return closeDetail(host)
  if (!which) { fail(`unknown navigation target: ${label}`); return }
  await openDetail(host, which)
}
// The header's Refresh (2.3.x put it in `.nx-toolbar`).
const refreshButton = host => host.querySelector('.wa-metro [aria-label="Refresh"]') || host.querySelector('[aria-label="Refresh"]')
// The review desk (2.5.0) is the Your review station's detail: ONE draft at a time with `k of N`. The
// 2.3.x Folio index list (`.wa-pend` rows, `.fl-item`) is gone; a draft is reached by `Later`, and the
// desk re-reads its first draft when the station is folded and pressed again.
const folioDesk = host => host.querySelector('.wa-metro-detail[data-for="review"]')
const deskRef = desk => desk?.querySelector('[data-candidate-ref]')?.getAttribute('data-candidate-ref') || null
const deskPosition = desk => {
  const m = /\b(\d+) of (\d+)\b/.exec(txt(desk))
  return m ? { at: Number(m[1]), of: Number(m[2]) } : { at: deskRef(desk) ? 1 : 0, of: deskRef(desk) ? 1 : 0 }
}
const draftCount = desk => deskPosition(desk).of
const gotoDraft = async (desk, ref, max = 8) => {
  for (let i = 0; i < max && deskRef(desk) !== ref; i += 1) await click(btn(desk, 'Later'), 80)
  if (deskRef(desk) !== ref) fail(`Later never reached the draft ${ref} (desk on ${deskRef(desk)})`)
  return deskRef(desk) === ref
}
const reopenDesk = async host => {
  if (folioDesk(host)) await click(opener(host, 'review'), 80)
  await click(opener(host, 'review'), 120)
  return folioDesk(host)
}
const rawDiff = detail => detail?.querySelector('details.fl-original .wa-raw pre')?.textContent
const documentTitle = payload => {
  const heading = (payload.diff || []).find(line => /^[+ ]# /.test(line))
  return heading ? heading.slice(3) : payload.candidate?.summary || payload.ref
}
// Identity is independent of the humanised index title; never infer a ref from visible text.
const matchingDocument = (detail, payload) => {
  const title = documentTitle(payload)
  const summary = payload.candidate?.summary
  const summaryNode = detail?.querySelector('.fl-summary')
  return detail?.dataset.candidateRef === payload.ref
    && detail.querySelector('.fl-document-head h2')?.textContent === title
    && detail.querySelector('.fl-file')?.textContent === (payload.candidate?.target || payload.ref)
    && (summary && summary !== title ? summaryNode?.textContent === summary : !summaryNode)
    && rawDiff(detail) === (payload.diff || []).join('\n')
}
const proposalRows = detail => [...(detail?.querySelectorAll('.fl-proposal > .fl-line') || [])].map(row => ({
  change: row.dataset.change,
  sign: row.querySelector('.fl-gutter')?.textContent,
  hiddenSign: row.querySelector('.fl-gutter')?.getAttribute('aria-hidden'),
  heading: Boolean(row.querySelector('.fl-line-heading')),
  text: row.querySelector('.fl-line-heading, .fl-line-text')?.textContent
}))
const expectedProposal = payload => (payload.diff || []).filter((line, index) =>
  !(index < 2 && /^(--- |\+\+\+ )/.test(line)) && !/^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@/.test(line)).map(line => {
  const marked = /^[+\- ]/.test(line)
  const sign = marked ? line[0] : ' '
  const text = marked ? line.slice(1) : line
  const heading = /^(#{1,6})\s+(.*)$/.exec(text)
  return { change: sign === '+' ? 'added' : sign === '-' ? 'removed' : 'context',
    sign: sign.trim() || '·', hiddenSign: null, heading: Boolean(heading),
    text: heading ? heading[2] : text || '\u00a0' }
})
const faithfulProposal = (detail, payload) =>
  JSON.stringify(proposalRows(detail)) === JSON.stringify(expectedProposal(payload))

async function runChecks() {
// App-managed engine lifecycle uses the real mounted Project settings, not exported helpers.
const engineCard = panel => panel.host.querySelector('#wa-sec-install')
const enginePosts = () => stub.calls.posts.filter(call => call.path.startsWith('/engine/'))
const closeEnginePanel = async panel => {
  await act(async () => panel.unmount())
  panel.host.remove()
}
if (process.env.WIKI_LIFECYCLE_E2E === '1') {
  const rootPath = process.env.WIKI_LIFECYCLE_ROOT
  const outcomes = []
  // Compile real host producers and REST door, not a copied SDK routing algorithm.
  const core = process.env.HERMES_AGENT_DIR.replace(/\\/g, '/')
  const hostRequire = createRequire(core + '/package.json')
  const { build } = hostRequire('esbuild')
  const producer = (file, expression) => {
    const match = readFileSync(core + '/apps/desktop/src/' + file, 'utf8').match(expression)
    if (!match) throw new Error('Host producer contract changed: ' + file)
    return match[0]
  }
  const connectionProducer = producer('store/connections.ts', /export const \$activeConnectionId = computed\([^\n]+/)
  const profileProducer = producer('store/profile.ts', /export const \$activeGatewayProfile = atom<string>\([^\n]+/)
  const cwdProducer = producer('store/session.ts', /export const \$currentCwd = atom\([^\n]+/)
  const rememberedProducer = producer('store/session.ts', /export const getRememberedWorkspaceCwd = [^\n]+/)
  const sdkSource = readFileSync(core + '/apps/desktop/src/sdk/index.ts', 'utf8')
  const readonlyProducer = sdkSource.match(/const readonlyAtom = [^\n]+/)[0]
  const stateEntries = ['connectionId', 'profile', 'cwd'].map(name => {
    const entry = sdkSource.match(new RegExp('    ' + name + ': readonlyAtom[^\\n]+'))
    if (!entry) throw new Error('Host SDK state changed: ' + name)
    return entry[0]
  }).join('\n')
  const measuredSdkPath = process.env.WIKI_HOST_HARNESS_DIR.replace(/\\/g, '/') + '/measured-host-sdk.mjs'
  await build({ stdin: { contents: `
    import { atom, computed } from 'nanostores'
    export { pluginRest } from '${core}/apps/desktop/src/api/plugins.ts'
    export { setApiRequestConnection, setApiRequestProfile } from '${core}/apps/desktop/src/api/client.ts'
    export { backendScopeKey } from '${core}/apps/shared/src/backend-scope.ts'
    const $connection = atom(null)
    const storedString = () => null
    const workspaceCwdKey = () => 'disposable-host-producer-probe'
    ${rememberedProducer}
    ${connectionProducer}
    ${profileProducer}
    ${cwdProducer}
    ${readonlyProducer}
    export const measuredHost = { state: { ${stateEntries} } }
    export const setMeasuredScope = scope => {
      $connection.set(scope.connectionId === null ? null : { connectionId: scope.connectionId })
      $activeGatewayProfile.set(scope.profile)
      $currentCwd.set(scope.cwd)
    }
    `, resolveDir: core, loader: 'ts' }, bundle: true, platform: 'node', format: 'esm', outfile: measuredSdkPath,
    alias: { '@': core + '/apps/desktop/src' }, plugins: [{ name: 'actual-shared-client-exports', setup(builder) {
      builder.onResolve({ filter: /^@hermes\/shared$/ }, () => ({ path: 'actual-shared-client-exports', namespace: 'measured' }))
      builder.onLoad({ filter: /.*/, namespace: 'measured' }, () => ({ contents:
        `export { JsonRpcGatewayClient } from '${core}/apps/shared/src/json-rpc-gateway.ts';
         export { reconnectBackoffDelayMs } from '${core}/apps/shared/src/reconnect-backoff.ts';`, loader: 'ts', resolveDir: core }))
    } }] })
  const sdk = await import(pathToFileURL(measuredSdkPath).href)
  const nativeInitial = Object.fromEntries(Object.entries(sdk.measuredHost.state).map(([name, value]) => [name, value.get()]))
  console.log('REAL_HOST_INITIAL_SCOPE', JSON.stringify(nativeInitial))
  const measuredScopes = []
  for (const raw of [{ connectionId: null, profile: null }, { connectionId: '', profile: '' },
    { connectionId: 'local', profile: 'default' }, { connectionId: 'fixture-remote', profile: null },
    { connectionId: 'fixture-remote', profile: 'research' }]) {
    let routed
    window.hermesDesktop = { api: async request => { routed = request; return {} } }
    sdk.setApiRequestConnection(raw.connectionId)
    sdk.setApiRequestProfile(raw.profile)
    await sdk.pluginRest(PLUGIN_ID, '/engine/status')
    const expectedConnection = raw.connectionId || null
    const expectedProfile = raw.profile || null
    if ((routed.connectionId ?? null) !== expectedConnection || (routed.profile ?? null) !== expectedProfile)
      fail('Real host REST routing changed null/empty or explicit remote semantics')
    measuredScopes.push({ raw, canonicalKey: sdk.backendScopeKey(raw.connectionId, raw.profile),
      routed: { connectionId: routed.connectionId ?? null, profile: routed.profile ?? null } })
  }
  console.log('REAL_HOST_SCOPE_MATRIX', JSON.stringify(measuredScopes))
  stub.host.state = sdk.measuredHost.state
  let transportScope = process.env.WIKI_HOST_SCOPE ? JSON.parse(process.env.WIKI_HOST_SCOPE) : nativeInitial
  let credential = process.env.WIKI_HTTP_CREDENTIAL || 'installation-e2e-fixture'
  window.hermesDesktop = { api: async request => {
    const response = await fetch(process.env.WIKI_LIFECYCLE_URL + request.path, {
      method: request.method || 'GET', headers: { 'Content-Type': 'application/json',
        ...(process.env.WIKI_HTTP_AUTH === 'bearer' ? { Authorization: 'Bearer ' + credential }
          : { 'X-Hermes-Session-Token': credential }) },
      body: request.body ? JSON.stringify(request.body) : undefined })
    const result = await response.json()
    clockNow = SystemDate.now()
    outcomes.push({ path: request.path, scope: { connectionId: request.connectionId ?? null, profile: request.profile ?? null }, http: response.status, ...result })
    if (!response.ok) throw new Error(result.reason || result.detail || 'Backend refused')
    return result
  } }
  const lifecycleRest = (path, options) => sdk.pluginRest(PLUGIN_ID, path, options)
  sdk.setApiRequestConnection(transportScope.connectionId)
  sdk.setApiRequestProfile(transportScope.profile)
  const panel = await mount('en', { automation: { ...automation(), available: false, settings: null }, lifecycleRest,
    hostScope: transportScope, hostScopeSetter: sdk.setMeasuredScope })
  const resultFor = path => outcomes.find(result => result.path === '/api/plugins/' + PLUGIN_ID + path)
  if (process.env.WIKI_RECOVERY_HTTP === '1') {
    const card = engineCard(panel)
    const waitFor = async condition => {
      for (let count = 0; count < 200; count += 1) { if (condition()) return true; await settle(50) }
      return false
    }
    await waitFor(() => resultFor('/engine/status'))
    const review = btn(card, 'Review interrupted installation')
    if (!review || review.disabled) fail('real HTTP recovery status did not expose an actionable review')
    else {
      await click(review)
      if (!await waitFor(() => card.querySelector('.wa-engine-plan'))) fail('real HTTP recovery review was not displayed')
      else {
        const reviewed = resultFor('/engine/recovery/prepare')
        must(txt(card), [reviewed.revision, reviewed.plan_digest, reviewed.project_id], 'real HTTP exact original recovery plan')
        if (enginePosts().some(post => post.path === '/engine/recovery/apply')) fail('real HTTP recovery applied before explicit confirmation')
        const confirm = btn(card, 'Resume this exact installation')
        if (!confirm || confirm.disabled) fail('real HTTP recovery confirmation was unavailable')
        else {
          await click(confirm)
          await waitFor(() => resultFor('/engine/recovery/apply'))
          await waitFor(() => !card.querySelector('.wa-engine-plan'))
          const result = resultFor('/engine/recovery/apply')
          if (result?.state !== 'installed_paused' || !result.ok) fail('real HTTP recovery did not return installed_paused')
          const payload = enginePosts().find(post => post.path === '/engine/recovery/apply')?.body
          if (JSON.stringify(Object.keys(payload || {}).sort()) !== JSON.stringify(['confirm', 'install_id', 'plan_digest', 'recovery_review_digest', 'recovery_review_id'])) fail('real HTTP recovery sent fields beyond the exact five-field confirmation')
          // Repeat the exact actual React payload through the actual SDK: review is single-use.
          try { await lifecycleRest('/engine/recovery/apply', { method: 'POST', body: payload }); fail('real HTTP recovery review replay succeeded') } catch {}
          if (outcomes.at(-1)?.http !== 409) fail('real HTTP recovery replay did not return 409')
        }
      }
    }
    await closeEnginePanel(panel)
    console.log('REAL_RECOVERY_UI_HTTP', JSON.stringify(outcomes.map(({ path, http, state, scope }) => ({ path, http, state, scope }))))
    process.exitCode = problems.length ? 1 : 0
    return
  }
  const card = engineCard(panel)
  const waitFor = async condition => {
    for (let count = 0; count < 200; count += 1) {
      if (condition()) return true
      await settle(50)
    }
    return false
  }
  await waitFor(() => resultFor('/engine/status'))
  await setField(card.querySelector('input'), rootPath)
  await waitFor(() => {
    const action = btn(card, 'Preview install') || btn(card, 'Preview update')
    return action && !action.disabled
  })
  const preview = btn(card, 'Preview install') || btn(card, 'Preview update')
  if (!preview || preview.disabled) fail('real backend missing-state response disabled initial installation')
  else {
    await click(preview)
    if (!await waitFor(() => card.querySelector('.wa-engine-plan'))) fail('real backend plan was not displayed')
    else {
      const prepared = resultFor('/engine/prepare')
      if (enginePosts().some(post => post.path === '/engine/apply')) fail('real backend applied without confirmation')
      must(txt(card), [prepared.revision, prepared.plan_digest, prepared.project_id], 'real backend exact plan')
      await click(btn(card, 'Install this exact plan'))
      if (!await waitFor(() => resultFor('/engine/apply'))) fail('real backend never received confirmation')
      else if (!await waitFor(() => !card.querySelector('.wa-engine-plan'))) fail('real backend installed result was not accepted')
      const applied = resultFor('/engine/apply')
      const expected = process.env.WIKI_LIFECYCLE_EXPECTED_STATE || 'installed_paused'
      if (applied?.ok !== true || applied?.state !== expected) fail('real backend did not return the expected installation state')
      const request = enginePosts().find(post => post.path === '/engine/apply')?.body
      if (request?.install_id !== prepared.install_id || request?.plan_digest !== prepared.plan_digest || request?.confirm !== true) fail('real backend did not receive the exact displayed confirmation')
    }
  }
  await closeEnginePanel(panel)
  console.log('REAL_LIFECYCLE_UI_API', JSON.stringify(outcomes.map(({ path, http, state, scope }) => ({ path, http, state, scope }))))
  process.exitCode = problems.length ? 1 : 0
  return
}

// Retain the actual mounted React event, rather than invoking an exported helper or a detached node.
const retainedPanelEvent = (element, event = 'onClick') => {
  const key = element && Object.keys(element).find(key => key.startsWith('__reactProps$'))
  const callback = key && element[key]?.[event]
  if (typeof callback !== 'function') throw new Error(`mounted panel has no ${event} event`)
  return callback
}
const closeScopedPanel = async panel => {
  await act(async () => panel.root.unmount())
  panel.host.remove()
}
const panelRoot = panel => panel.host.querySelector('#wa-sec-root')
const panelJobs = panel => panel.host.querySelector('#wa-sec-jobs')
const panelJob = panel => panelJobs(panel)?.querySelector('details.wa-job')
// Job listing remains readable; native mutation is opt-in and fail-closed on absent/malformed capability.
for (const capability of [undefined, false, null, 'true']) {
  const view = jobsView(jobsState())
  if (capability === undefined) delete view.mutation_available
  else view.mutation_available = capability
  view.management_reason = 'This Hermes version does not offer the cron store lock, so job changes stay off.'
  const panel = await mount('en', { jobs: view })
  const card = panelJobs(panel)
  must(txt(card), [view.management_reason, ...view.roles.map(row => row.name)], 'READONLY JOBS readable list/reason')
  const buttons = [...card.querySelectorAll('.wa-job-acts button')]
  if (!buttons.length || buttons.some(button => !button.disabled)) fail(`READONLY JOBS capability ${capability}: native mutation controls enabled`)
  const before = stub.calls.posts.length
  await act(async () => { for (const button of buttons) await retainedPanelEvent(button)() })
  if (stub.calls.posts.length !== before || card.querySelector('[role="dialog"], .wa-sched'))
    fail('READONLY JOBS: retained callbacks armed mutation/schedule UI or posted')
  if (!engineCard(panel).querySelector('input')) fail('READONLY JOBS: capability hid ordinary install settings flow')
  await closeScopedPanel(panel)
}
const panelScopeStart = version
for (const key of ['profile', 'connectionId']) {
  {
    const panel = await mount()
    await setField(panelRoot(panel).querySelector('input'), VALID_ROOT)
    const save = retainedPanelEvent(btn(panelRoot(panel), 'Save'))
    const before = stub.calls.posts.length
    await act(async () => {
      stub.host.state[key].set(`retained-root-${key}`)
      await save()
    })
    if (stub.calls.posts.length !== before) fail(`SEC-1 retained Root Save dispatched after ${key} switched, before React rendered`)
    if (panelRoot(panel).querySelector('input')?.value) fail(`SEC-1 ${key} switch retained the old root draft`)
    await closeScopedPanel(panel)
  }
  {
    const panel = await mount()
    await clickJobButton(panelJob(panel), 'Delete')
    const confirm = retainedPanelEvent(btn(panelJobs(panel).querySelector('[role="dialog"]'), 'Delete'))
    const before = stub.calls.posts.length
    await act(async () => {
      stub.host.state[key].set(`retained-delete-${key}`)
      await confirm()
    })
    if (stub.calls.posts.length !== before) fail(`SEC-1 retained Job Delete dispatched after ${key} switched, before React rendered`)
    if (panelJobs(panel).querySelector('[role="dialog"]')) fail(`SEC-1 ${key} switch retained the armed delete dialog`)
    await closeScopedPanel(panel)
  }
}
const scopeDeferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  promise.catch(() => {})
  return { promise, resolve, reject }
}
const scopedActionPosts = () => stub.calls.posts.filter(call =>
  ['/automation/settings', '/automation/scan_root', '/jobs/act'].includes(call.path))
const rootEvent = async (panel, kind) => {
  const card = panelRoot(panel)
  if (kind === 'force') {
    await click(btn(card, 'Scan for candidates'))
    await click([...card.querySelectorAll('.wa-cand')].find(row => txt(row).includes('/srv/mirror')))
    return retainedPanelEvent(card.querySelector('.wa-danger-fill'))
  }
  if (kind !== 'pickScan') await setField(card.querySelector('input'), VALID_ROOT)
  return retainedPanelEvent(btn(card, {
    pick: 'Choose folder', verify: 'Verify', scan: 'Scan for candidates', save: 'Save',
    pickScan: 'Choose scan folder'
  }[kind]))
}
const jobEvent = async (panel, kind) => {
  const rows = [...panelJobs(panel).querySelectorAll('details.wa-job')]
  const row = kind === 'create' ? rows[1] : rows[0]
  if (kind === 'resume') {
    await clickJobButton(row, 'Pause')
  }
  if (kind === 'remove') {
    await clickJobButton(row, 'Delete')
    return retainedPanelEvent(panelJobs(panel).querySelector('[data-slot="confirm-confirm"]'))
  }
  if (kind === 'schedule') {
    await clickJobButton(row, 'Schedule')
    await setField(row.querySelector('.wa-sched-num'), '17')
    return retainedPanelEvent(btn(row.querySelector('.wa-sched'), 'Save schedule'))
  }
  await openJobDisclosure(row)
  return retainedPanelEvent(btn(row.querySelector('.wa-job-expanded'), {
    create: 'Create', pause: 'Pause', resume: 'Resume', arm: 'Delete', edit: 'Schedule'
  }[kind]))
}
const readOnlyRevocationStart = version
// Revoking capability retires every previously captured job intent, including open reviews.
for (const kind of ['create', 'pause', 'resume', 'remove', 'schedule', 'arm', 'edit']) {
  const panel = await mount()
  const event = await jobEvent(panel, kind)
  const before = scopedActionPosts().length
  stub.state.jobsOverride = { ...jobsView(stub.state.jobsState), mutation_available: false }
  await click(refreshButton(panel.host), 0)
  await act(async () => event())
  if (scopedActionPosts().length !== before || panelJobs(panel).querySelector('[role="dialog"], .wa-sched'))
    fail(`READONLY JOBS revoked: old ${kind} intent remained actionable`)
  must(txt(panelJobs(panel)), ['This Hermes version does not offer the cron store lock, so job changes stay off.'], 'READONLY JOBS missing reason fallback')
  await closeScopedPanel(panel)
}
const readOnlyRevocationCases = version - readOnlyRevocationStart
// All callbacks must fail synchronously on an SDK change; switching back is still a new epoch.
for (const key of ['profile', 'connectionId', 'cwd']) {
  for (const kind of ['save', 'force', 'verify', 'scan', 'pick']) {
    const panel = await mount()
    const event = await rootEvent(panel, kind)
    const posts = stub.calls.posts.length, gets = stub.calls.gets.length, picks = stub.state.pickCalls.length
    await act(async () => {
      const old = stub.host.state[key].get()
      stub.host.state[key].set(`root-action-${key}`)
      stub.host.state[key].set(old)
      await event()
    })
    if (stub.calls.posts.length !== posts || stub.state.pickCalls.length !== picks
      || stub.calls.gets.slice(gets).some(path => path.startsWith('/automation/candidates'))) {
      fail(`SEC-1 retained root ${kind} survived ${key} ABA before render`)
    }
    if (panelRoot(panel).querySelector('.wa-danger-fill, .wa-cands')) fail(`SEC-1 root ${kind} review survived ${key}`)
    await closeScopedPanel(panel)
  }
  for (const kind of ['create', 'pause', 'resume', 'remove', 'schedule', 'arm', 'edit']) {
    const panel = await mount()
    const event = await jobEvent(panel, kind)
    const before = scopedActionPosts().length
    await act(async () => {
      stub.host.state[key].set(`jobs-action-${key}`)
      await event()
    })
    if (scopedActionPosts().length !== before) fail(`SEC-1 retained job ${kind} dispatched after ${key}`)
    if (panelJobs(panel).querySelector('[role="dialog"], .wa-sched')) fail(`SEC-1 retained job ${kind} armed UI after ${key}`)
    await closeScopedPanel(panel)
  }
}
// Resolve and reject old requests only after the new context has mounted. Neither may publish or refresh.
for (const key of ['profile', 'connectionId', 'cwd']) {
  for (const kind of ['save', 'force', 'verify', 'scan', 'pick']) {
    for (const rejects of [false, true]) {
      const pending = scopeDeferred()
      let active = false, dispatched = 0
      const route = { save: '/automation/settings', force: '/automation/settings',
        verify: '/automation/validate', scan: '/automation/candidates', pick: '/automation/derive' }[kind]
      const panel = await mount('en', { panelRest: path => {
        if (active && path.startsWith(route)) { dispatched += 1; return pending.promise }
      } })
      const event = await rootEvent(panel, kind)
      active = true
      let work
      await act(async () => { work = event() })
      if (dispatched !== 1) fail(`SEC-1 pending root ${kind} did not dispatch its positive control`)
      active = false
      await act(async () => stub.host.state[key].set(`pending-root-${kind}-${key}`))
      const before = stub.calls.gets.length
      await act(async () => {
        if (rejects) pending.reject(new Error('OLD ROOT ERROR'))
        else pending.resolve({ ok: true, root: '/old/root', project_root: '/old/root', id: 'OLD-RESULT',
          pages: 999, found: [{ root: '/old/candidate', pages: 999 }] })
        await work
      })
      if (/OLD ROOT ERROR|OLD-RESULT|\/old\//.test(txt(panelRoot(panel)) + panelRoot(panel).querySelector('input')?.value)) fail(`SEC-1 ${key} leaked pending root ${kind} ${rejects ? 'error' : 'result'}`)
      if (stub.calls.gets.length !== before) fail(`SEC-1 pending root ${kind} refreshed the new ${key} context`)
      await closeScopedPanel(panel)
    }
  }
  for (const kind of ['pause', 'resume', 'remove', 'schedule']) {
    for (const rejects of [false, true]) {
      const pending = scopeDeferred()
      let active = false, dispatched = 0
      const panel = await mount('en', { panelRest: (path, opts) => {
        if (active && path === '/jobs/act' && opts?.body?.action === kind) { dispatched += 1; return pending.promise }
      } })
      const event = await jobEvent(panel, kind)
      active = true
      let work
      await act(async () => { work = event().catch(error => fail(`SEC-1 pending job ${kind} propagated stale error: ${error.message}`)) })
      if (dispatched !== 1) fail(`SEC-1 pending job ${kind} did not dispatch its positive control`)
      active = false
      await act(async () => stub.host.state[key].set(`pending-job-${kind}-${key}`))
      const before = stub.calls.gets.length
      await act(async () => {
        if (rejects) pending.reject(new Error('OLD JOB ERROR'))
        else pending.resolve({ ok: true, schedule: '17 * * * *' })
        await work
      })
      if (panelJobs(panel).querySelector('.wa-jobs-note, [role="dialog"], .wa-sched')) fail(`SEC-1 ${key} leaked pending job ${kind} ${rejects ? 'error' : 'result'}`)
      if (stub.calls.gets.length !== before) fail(`SEC-1 pending job ${kind} refreshed the new ${key} context`)
      await closeScopedPanel(panel)
    }
  }
}
for (const kind of ['pick', 'pickScan']) {
  const pending = scopeDeferred()
  const empty = automation()
  if (kind === 'pickScan') empty.settings.project_root = ''
  const panel = await mount('en', { automation: empty, pickOpenPath: () => pending.promise })
  const card = panelRoot(panel)
  const button = kind === 'pick' ? btn(card, 'Choose folder') : [...card.querySelectorAll('button')].find(button => txt(button).includes('scan') && !txt(button).includes('Scan for'))
  const event = retainedPanelEvent(button)
  let work
  await act(async () => { work = event() })
  await act(async () => stub.host.state.profile.set(`pending-picker-${kind}`))
  const before = stub.calls.posts.length
  await act(async () => { pending.resolve('/old/.llm-wiki/project.json'); await work })
  if (stub.calls.posts.length !== before) fail(`SEC-1 delayed ${kind} picker dispatched against the new context`)
  await closeScopedPanel(panel)
}
// Fresh reads are a prerequisite, not just clearing a dialog. Old pending reads cannot win later.
{
  const oldAuto = scopeDeferred(), freshAuto = scopeDeferred(), freshJobs = scopeDeferred()
  let phase = 'initial'
  const panel = await mount('en', { panelRest: path => {
    if (path === '/automation' && phase === 'old') return oldAuto.promise
    if (path === '/automation' && phase === 'fresh') return freshAuto.promise
    if (path === '/jobs' && phase === 'fresh') return freshJobs.promise
  } })
  const staleSave = await rootEvent(panel, 'save')
  const stalePause = await jobEvent(panel, 'pause')
  phase = 'old'
  await click(refreshButton(panel.host), 0)
  phase = 'fresh'
  await act(async () => stub.host.state.profile.set('fresh-read-profile'))
  if (panelRoot(panel).querySelector('input') || panelJob(panel)) fail('SEC-1 old props remained actionable before fresh context reads')
  const before = scopedActionPosts().length
  await act(async () => { await staleSave(); await stalePause() })
  if (scopedActionPosts().length !== before) fail('SEC-1 pending fresh reads allowed retained mutations')
  const fresh = automation()
  fresh.settings = { ...fresh.settings, project_root: '/fresh/wiki', project: { ...fresh.settings.project, id: 'fresh-id' } }
  await act(async () => freshAuto.resolve(fresh))
  if (panelJob(panel)) fail('SEC-1 jobs became actionable without their fresh job read')
  const freshRows = jobsView(jobsState())
  freshRows.roles[0] = { ...freshRows.roles[0], name: 'FRESH JOB', id: 'fresh-job-id' }
  await act(async () => freshJobs.resolve(freshRows))
  await act(async () => oldAuto.resolve(automation()))
  must(txt(panelRoot(panel)), ['/fresh/wiki'], 'SEC-1 fresh root wins over old pending read')
  must(txt(panelJob(panel)), ['FRESH JOB'], 'SEC-1 fresh jobs are visible')
  await setField(panelRoot(panel).querySelector('input'), VALID_ROOT)
  await click(btn(panelRoot(panel), 'Save'))
  await clickJobButton(panelJob(panel), 'Pause')
  if (scopedActionPosts().length !== before + 2) fail('SEC-1 fresh root/job controls were not actionable')
  await closeScopedPanel(panel)
}
// A changed backend project and a changed native job id invalidate retained approvals.
for (const change of ['project', 'jobId']) {
  const panel = await mount()
  const save = await rootEvent(panel, 'force')
  const confirm = await jobEvent(panel, 'remove')
  if (change === 'project') AUTO = { ...AUTO, settings: { ...AUTO.settings, project_root: '/new/wiki',
    project: { ...AUTO.settings.project, id: 'new-project' } } }
  else stub.state.jobsState.autocommit.id = 'replacement-job'
  await click(refreshButton(panel.host))
  const before = scopedActionPosts().length
  await act(async () => { if (change === 'project') await save(); await confirm() })
  if (scopedActionPosts().length !== before) fail(`SEC-1 ${change} change allowed retained confirmation`)
  if (panelJobs(panel).querySelector('[role="dialog"]')) fail(`SEC-1 ${change} change retained armed delete`)
  if (change === 'project' && panelRoot(panel).querySelector('.wa-danger-fill')) fail('SEC-1 project change retained root force approval')
  await closeScopedPanel(panel)
}
// Duplicate events before render and replay after completion must be single use.
for (const kind of ['save', 'force', 'remove', 'schedule', 'pause']) {
  const panel = await mount()
  const event = ['save', 'force'].includes(kind) ? await rootEvent(panel, kind) : await jobEvent(panel, kind)
  const before = scopedActionPosts().length
  await act(async () => { await Promise.all([event(), event()]) })
  if (scopedActionPosts().length !== before + 1) fail(`SEC-1 duplicate ${kind} event was not single-dispatch`)
  await act(async () => event())
  if (scopedActionPosts().length !== before + 1) fail(`SEC-1 retained ${kind} event replayed after completion`)
  await closeScopedPanel(panel)
}
// Delayed cancellation and duplicate picker opens must not arm or mutate a new context.
for (const kind of ['pick', 'pickScan']) {
  const pending = scopeDeferred()
  const empty = automation()
  if (kind === 'pickScan') empty.settings.project_root = ''
  const panel = await mount('en', { automation: empty, pickOpenPath: () => pending.promise })
  const card = panelRoot(panel)
  const button = kind === 'pick' ? btn(card, 'Choose folder') : [...card.querySelectorAll('button')].find(button => txt(button).includes('scan') && !txt(button).includes('Scan for'))
  const event = retainedPanelEvent(button)
  const before = stub.state.pickCalls.length
  let first, second
  await act(async () => { first = event(); second = event() })
  if (stub.state.pickCalls.length !== before + 1) fail(`SEC-1 ${kind} opened duplicate pending pickers`)
  await act(async () => stub.host.state.cwd.set(`/cancelled/${kind}`))
  await act(async () => { pending.resolve(null); await Promise.all([first, second]) })
  if (panelRoot(panel).querySelector('.wa-help')) fail(`SEC-1 ${kind} published stale picker cancellation`)
  await closeScopedPanel(panel)
}
for (const key of ['profile', 'connectionId', 'cwd']) {
  const pending = scopeDeferred()
  const empty = automation()
  empty.settings.project_root = ''
  let active = false
  const panel = await mount('en', { automation: empty, panelRest: path => {
    if (active && path === '/automation/scan_root') return pending.promise
  } })
  const card = panelRoot(panel)
  const button = [...card.querySelectorAll('button')].find(button => txt(button).includes('scan') && !txt(button).includes('Scan for'))
  const event = retainedPanelEvent(button)
  active = true
  let work
  await act(async () => { work = event() })
  active = false
  await act(async () => stub.host.state[key].set(`pending-scan-root-${key}`))
  const before = stub.calls.gets.length
  await act(async () => { pending.resolve({ ok: true, scan_root: '/old/scan' }); await work })
  if (stub.calls.gets.length !== before || panelRoot(panel).querySelector('.wa-cands, .wa-help')) fail(`SEC-1 ${key} allowed delayed scan-root continuation`)
  await closeScopedPanel(panel)
}
for (const cancel of ['force', 'remove', 'schedule']) {
  const panel = await mount()
  const event = cancel === 'force' ? await rootEvent(panel, cancel) : await jobEvent(panel, cancel)
  const scope = cancel === 'force' ? panelRoot(panel).querySelector('.wa-confirm')
    : cancel === 'remove' ? panelJobs(panel).querySelector('[role="dialog"]') : panelJobs(panel).querySelector('.wa-sched')
  await click(btn(scope, 'Cancel'))
  const before = scopedActionPosts().length
  await act(async () => event())
  if (scopedActionPosts().length !== before) fail(`SEC-1 cancelled ${cancel} approval remained actionable`)
  await closeScopedPanel(panel)
}
{
  const panel = await mount()
  const event = await rootEvent(panel, 'force')
  await setField(panelRoot(panel).querySelector('input'), '/srv/edited')
  const before = scopedActionPosts().length
  await act(async () => event())
  if (scopedActionPosts().length !== before || panelRoot(panel).querySelector('.wa-danger-fill')) fail('SEC-1 editing a draft retained an old force grant')
  await closeScopedPanel(panel)
}
// An obsolete completion must not release the newer context's pending mutation lock.
for (const target of ['root', 'jobs']) {
  const old = scopeDeferred(), fresh = scopeDeferred()
  let phase = 'initial'
  const panel = await mount('en', { panelRest: (path, opts) => {
    const match = target === 'root' ? path === '/automation/settings' : path === '/jobs/act' && opts?.body?.action === 'pause'
    if (match && phase === 'old') return old.promise
    if (match && phase === 'fresh') return fresh.promise
  } })
  const first = target === 'root' ? await rootEvent(panel, 'save') : await jobEvent(panel, 'pause')
  phase = 'old'
  let oldWork, freshWork
  await act(async () => { oldWork = first() })
  phase = 'initial'
  await act(async () => stub.host.state.connectionId.set(`pending-lock-${target}`))
  const second = target === 'root' ? await rootEvent(panel, 'save') : await jobEvent(panel, 'pause')
  phase = 'fresh'
  await act(async () => { freshWork = second() })
  await act(async () => { old.resolve({ ok: true, project_root: '/old/root' }); await oldWork })
  const card = target === 'root' ? panelRoot(panel) : panelJobs(panel)
  if (!card.querySelector('[aria-busy="true"]')) fail(`SEC-1 old ${target} completion cleared the newer pending flag`)
  const before = scopedActionPosts().length
  const latest = target === 'root' ? retainedPanelEvent(btn(card, 'Save')) : await jobEvent(panel, 'pause')
  await act(async () => latest())
  if (scopedActionPosts().length !== before) fail(`SEC-1 old ${target} completion released a newer mutation lock`)
  await act(async () => { fresh.resolve({ ok: true, project_root: VALID_ROOT }); await freshWork })
  await closeScopedPanel(panel)
}
// The actual schedule debounce callback must check SDK state before dispatch, not await React cleanup.
{
  const panel = await mount()
  const originalTimeout = globalThis.setTimeout
  let previewTick = null
  try {
    globalThis.setTimeout = (callback, ms, ...args) => {
      if (ms === 250) previewTick = callback
      return originalTimeout(callback, ms, ...args)
    }
    await clickJobButton(panelJob(panel), 'Schedule', 0)
  } finally { globalThis.setTimeout = originalTimeout }
  if (!previewTick) throw new Error('SEC-1 schedule preview timer was not mounted')
  const before = stub.calls.posts.length
  await act(async () => {
    stub.host.state.profile.set('preview-debounce-profile')
    await previewTick()
  })
  if (stub.calls.posts.length !== before) fail('SEC-1 schedule preview dispatched after SDK switch before React cleanup')
  await closeScopedPanel(panel)
}
// Pending responses are also fenced by a project refresh within the same SDK context.
for (const target of ['root', 'jobs']) {
  const pending = scopeDeferred()
  let active = false
  const panel = await mount('en', { panelRest: (path, opts) => {
    if (active && (target === 'root' ? path === '/automation/settings' : path === '/jobs/act' && opts?.body?.action === 'pause')) return pending.promise
  } })
  const event = target === 'root' ? await rootEvent(panel, 'save') : await jobEvent(panel, 'pause')
  active = true
  let work
  await act(async () => { work = event() })
  active = false
  AUTO = { ...AUTO, settings: { ...AUTO.settings, project_root: '/changed/wiki', project: { ...AUTO.settings.project, id: 'changed-id' } } }
  await click(refreshButton(panel.host))
  const before = stub.calls.gets.length
  await act(async () => { pending.resolve({ ok: true, project_root: '/old/project' }); await work })
  const card = target === 'root' ? panelRoot(panel) : panelJobs(panel)
  if (card.querySelector('.wa-help, .wa-jobs-note') || stub.calls.gets.length !== before) fail(`SEC-1 project refresh leaked pending ${target} response`)
  await closeScopedPanel(panel)
}
// A root mutation refreshes its new project before jobs may act, without waiting for a timer.
{
  const panel = await mount('en', { panelRest: (path, opts) => {
    if (path !== '/automation/settings') return undefined
    AUTO = { ...AUTO, settings: { ...AUTO.settings, project_root: opts.body.project_root,
      project: { ...AUTO.settings.project, id: 'saved-project' } } }
    return { ok: true, project_root: opts.body.project_root }
  } })
  const before = stub.calls.gets.filter(path => path === '/jobs').length
  await setField(panelRoot(panel).querySelector('input'), '/saved/wiki')
  await click(btn(panelRoot(panel), 'Save'))
  if (stub.calls.gets.filter(path => path === '/jobs').length <= before) fail('SEC-1 root save did not fresh-read jobs for the changed project')
  const posts = scopedActionPosts().length
  await clickJobButton(panelJob(panel), 'Pause')
  if (scopedActionPosts().length !== posts + 1) fail('SEC-1 changed project had no fresh actionable jobs after root save')
  await closeScopedPanel(panel)
}
// Cancelling and rearming must not revive the previous root or schedule grant.
for (const kind of ['force', 'schedule']) {
  const panel = await mount()
  const first = kind === 'force' ? await rootEvent(panel, kind) : await jobEvent(panel, kind)
  const card = kind === 'force' ? panelRoot(panel) : panelJobs(panel)
  await click(btn(card.querySelector(kind === 'force' ? '.wa-confirm' : '.wa-sched'), 'Cancel'))
  const second = kind === 'force' ? await rootEvent(panel, kind) : await jobEvent(panel, kind)
  const before = scopedActionPosts().length
  await act(async () => first())
  if (scopedActionPosts().length !== before) fail(`SEC-1 ${kind} rearming revived an old confirmation`)
  await act(async () => second())
  if (scopedActionPosts().length !== before + 1) fail(`SEC-1 ${kind} rearmed confirmation did not dispatch its fresh positive control`)
  await closeScopedPanel(panel)
}
// A job-id ABA refresh cannot revive a retained action from its original render.
{
  const panel = await mount()
  const pause = await jobEvent(panel, 'pause')
  stub.state.jobsState.autocommit.id = 'replacement-job'
  await click(refreshButton(panel.host))
  stub.state.jobsState.autocommit.id = 'aaa'
  await click(refreshButton(panel.host))
  const before = scopedActionPosts().length
  await act(async () => pause())
  if (scopedActionPosts().length !== before) fail('SEC-1 job-id ABA revived a retained pause action')
  await closeScopedPanel(panel)
}
// Successful mutation does not authorize another action against pre-refresh job facts.
{
  const freshRead = scopeDeferred()
  let hold = false
  const panel = await mount('en', { panelRest: path => {
    if (hold && path === '/jobs') return freshRead.promise
  } })
  const pause = await jobEvent(panel, 'pause')
  hold = true
  await act(async () => pause())
  const before = scopedActionPosts().length
  const again = await jobEvent(panel, 'pause')
  await act(async () => again())
  if (scopedActionPosts().length !== before) fail('SEC-1 fresh job refresh pending allowed a second mutation using old row facts')
  hold = false
  await act(async () => freshRead.resolve(jobsView(stub.state.jobsState)))
  await clickJobButton(panelJob(panel), 'Resume')
  if (scopedActionPosts().length !== before + 1) fail('SEC-1 finished fresh job read did not re-enable its current action')
  await closeScopedPanel(panel)
}
console.log(`SEC-1 exercised — ${version - panelScopeStart - readOnlyRevocationCases} mounted React/jsdom cases: retained Root Save / Job Delete review cases · SDK profile/connection/cwd and ABA predispatch guards · pending results/errors · fresh context reads · project/job-id invalidation · picker/debounce continuations · cancellation and single-use mutations; fixture API only, no native pixel or live-write proof`)
if (process.env.WIKI_PANEL_SCOPE_ONLY) {
  console.log(`Panel SEC-1 scope: ${problems.length ? 'FAILED' : 'PASSED'} (${problems.length} failures)`)
  process.exitCode = problems.length ? 1 : 0
  return
}


// Interrupted-install recovery uses the original approved plan, never a newly selected revision/root.
const recoveryRest = (prepare = () => engineRecoveryPlan(), apply = body => ({ ok: true,
  state: 'installed_paused', install_id: body.install_id, revision: engineRecoveryPlan().revision,
  activation_required: true })) => (path, options) => {
  if (path === '/engine/status') return interruptedEngineStatus()
  if (path === '/engine/recovery/prepare') return prepare(options.body)
  if (path === '/engine/recovery/apply') return apply(options.body)
  throw new Error(`unexpected recovery route: ${path}`)
}
const recoveryButton = panel => btn(engineCard(panel), 'Review interrupted installation')
const resumeButton = panel => btn(engineCard(panel), 'Resume this exact installation')
const retainedClick = node => {
  const key = node && Object.keys(node).find(key => key.startsWith('__reactProps$'))
  const handler = key && node[key]?.onClick
  if (typeof handler !== 'function') throw new Error('No retained React action callback')
  return handler
}
// Backend identity tokens are lowercase hexadecimal; never repair malformed identifiers.
for (const field of ['install_id', 'plan_digest']) {
  const value = 'A'.repeat(64)
  const probe = await mount('en', { lifecycleRest: path => path === '/engine/status'
    ? { ...interruptedEngineStatus(), [field]: value } : { ...engineRecoveryPlan(), [field]: value } })
  if (recoveryButton(probe) && !recoveryButton(probe).disabled) fail(`LOWER HEX: uppercase status ${field} offered recovery review`)
  if (enginePosts().length) fail('LOWER HEX: malformed status automatically posted')
  await closeEnginePanel(probe)
}
for (const field of ['revision', 'recovery_review_id', 'recovery_review_digest']) {
  const probe = await mount('en', { lifecycleRest: recoveryRest(() => ({ ...engineRecoveryPlan(), [field]: 'A'.repeat(field === 'revision' ? 40 : 64) })) })
  await click(recoveryButton(probe), 0)
  if (resumeButton(probe)) fail(`LOWER HEX: uppercase recovery ${field} became confirmable`)
  await closeEnginePanel(probe)
}
// Recovery displays the exact requested alias separately from the canonical approved root.
{
  const requested = '/srv/Original-Alias/<literal>'
  const original = { ...engineRecoveryPlan(), requested_project_root: requested }
  const probe = await mount('en', { lifecycleRest: recoveryRest(() => original) })
  await click(recoveryButton(probe), 0)
  const card = engineCard(probe)
  const values = [...card.querySelectorAll('.wa-engine-plan dd')].map(node => node.textContent)
  if (!values.includes(requested) || !values.includes(original.project_root) || card.querySelector('literal'))
    fail('REQUESTED ROOT: exact original alias and canonical root must be separately displayed as literal values')
  must(txt(card), ['Original requested root'], 'REQUESTED ROOT label')
  await click(resumeButton(probe), 0)
  if (Object.keys(enginePosts().at(-1)?.body || {}).sort().join(',') !== 'confirm,install_id,plan_digest,recovery_review_digest,recovery_review_id')
    fail('REQUESTED ROOT: recovery apply sent a root override rather than exact five-field confirmation')
  await closeEnginePanel(probe)
}
for (const requested of [undefined, null, '', 'relative-root']) {
  const probe = await mount('en', { lifecycleRest: recoveryRest(() => ({ ...engineRecoveryPlan(), requested_project_root: requested })) })
  await click(recoveryButton(probe), 0)
  if (resumeButton(probe)) fail('REQUESTED ROOT: missing or malformed original requested root became actionable')
  await closeEnginePanel(probe)
}
// Recovery review contract: fresh approval lasts at most the backend's 300 seconds.
if (engineRecoveryPlan().review_expires_at !== clockNow / 1000 + 300) fail('TTL: recovery fixture must match backend expiry 300')
for (const duration of [300, 300.001, 600]) {
  const probe = await mount('en', { lifecycleRest: recoveryRest(() => ({ ...engineRecoveryPlan(), review_expires_at: clockNow / 1000 + duration })) })
  await click(recoveryButton(probe), 0)
  if (Boolean(resumeButton(probe)) !== (duration === 300)) fail(`TTL: recovery review accepted wrong maximum lifetime ${duration}`)
  await closeEnginePanel(probe)
}
// Malformed SDK atoms are unavailable. Null/empty values are supported host ambient/default scope.
for (const key of ['profile', 'connectionId']) {
  for (const recovery of [false, true]) {
    const probe = await mount('en', recovery ? { lifecycleRest: recoveryRest() } : { engineStatus: engineStatus('missing') })
    const preview = retainedClick(recovery ? recoveryButton(probe) : btn(engineCard(probe), 'Preview install'))
    await act(async () => stub.host.state[key].set(undefined))
    await act(async () => preview())
    const current = recovery ? recoveryButton(probe) : btn(engineCard(probe), 'Preview install')
    if (current) await click(current, 0)
    if (enginePosts().length || engineCard(probe).querySelector('.wa-engine-plan')) fail(`UNDEFINED SDK ${key}: malformed identity allowed lifecycle prepare`)
    must(txt(engineCard(probe)), ['App connection or profile identity is unavailable.'], `UNDEFINED SDK ${key} visible reason`)
    if (engineCard(probe).querySelector('[data-slot="loader"]')) fail(`UNDEFINED SDK ${key}: unavailable identity stayed loading`)
    await closeEnginePanel(probe)
  }
}
for (const scope of [{ connectionId: null, profile: 'default', cwd: '' },
  { connectionId: '', profile: null, cwd: '' }, { connectionId: 'remote-source', profile: '', cwd: '' }]) {
  for (const recovery of [false, true]) {
    const probe = await mount('en', { ...(recovery ? { lifecycleRest: recoveryRest() }
      : { engineStatus: engineStatus('missing'), automation: { ...automation(), settings: null } }), hostScope: scope })
    if (!recovery) await setField(engineCard(probe).querySelector('input'), '/srv/explicit-host-default-install')
    const action = recovery ? recoveryButton(probe) : btn(engineCard(probe), 'Preview install')
    if (!action || action.disabled) fail('HOST AMBIENT: supported null/empty identity disabled an explicit lifecycle review')
    else await click(action, 0)
    if (!engineCard(probe).querySelector('.wa-engine-plan')) fail('HOST AMBIENT: supported null/empty identity lost lifecycle review')
    const oldConfirm = retainedClick(recovery ? resumeButton(probe) : btn(engineCard(probe), 'Install this exact plan'))
    const before = enginePosts().length
    // Keep the same canonical key; raw atom drift must still retire the old authorization.
    await act(async () => stub.host.state.profile.set(scope.profile === 'default' ? null : 'default'))
    await act(async () => oldConfirm())
    if (enginePosts().length !== before || engineCard(probe).querySelector('.wa-engine-plan')) fail('HOST AMBIENT: same-canonical-key raw scope drift retained confirmation')
    await closeEnginePanel(probe)
  }
}
// A null working directory is legitimate without a selected host project; identity stays explicit.
{
  const probe = await mount('en', { engineStatus: engineStatus('missing'), automation: { ...automation(), settings: null } })
  await act(async () => stub.host.state.cwd.set(null))
  await setField(engineCard(probe).querySelector('input'), '/srv/explicit-first-install')
  await click(btn(engineCard(probe), 'Preview install'), 0)
  if (enginePosts().at(-1)?.body.project_root !== '/srv/explicit-first-install') fail('NULL SDK cwd: legitimate no-project host blocked explicit first install')
  await closeEnginePanel(probe)
}
// Every rendered local/read action retains the displayed SDK epoch and exact review.
for (const action of ['picker', 'input', 'preview']) {
  const probe = await mount('en', { engineStatus: engineStatus('missing') })
  const card = engineCard(probe)
  let callback
  if (action === 'input') {
    const input = card.querySelector('input')
    const key = Object.keys(input).find(key => key.startsWith('__reactProps$'))
    const handler = input[key].onChange
    callback = () => handler({ target: { value: '/srv/stale-input' } })
  } else callback = retainedClick(btn(card, action === 'picker' ? 'Choose project folder' : 'Preview install'))
  await click(btn(card, 'Preview install'), 0)
  const review = card.querySelector('.wa-engine-plan')
  const posts = enginePosts().length, picks = stub.state.pickCalls.length
  await act(async () => callback())
  if (enginePosts().length !== posts || stub.state.pickCalls.length !== picks || card.querySelector('.wa-engine-plan') !== review)
    fail(`CALLBACK exact review: retained ${action} mutated a newer displayed plan`)
  await closeEnginePanel(probe)
}
{
  const probe = await mount('en', { lifecycleRest: recoveryRest() })
  const retry = retainedClick(btn(engineCard(probe), 'Retry status'))
  await click(recoveryButton(probe), 0)
  const review = engineCard(probe).querySelector('.wa-engine-plan')
  const reads = stub.calls.gets.length
  await act(async () => retry())
  if (stub.calls.gets.length !== reads || engineCard(probe).querySelector('.wa-engine-plan') !== review)
    fail('CALLBACK exact review: retained Retry status cleared a newer recovery review')
  const picker = retainedClick(btn(engineCard(probe), 'Choose project folder'))
  const input = engineCard(probe).querySelector('input')
  const handler = input[Object.keys(input).find(key => key.startsWith('__reactProps$'))].onChange
  await act(async () => { stub.host.state.profile.set('other'); stub.host.state.profile.set('default') })
  const count = stub.calls.gets.length, picks = stub.state.pickCalls.length
  await act(async () => { await retry(); await picker(); handler({ target: { value: '/srv/stale' } }) })
  if (stub.calls.gets.length !== count || stub.state.pickCalls.length !== picks || engineCard(probe).querySelector('input')?.value === '/srv/stale')
    fail('CALLBACK epoch: local/read callbacks rebound to a new SDK epoch')
  await closeEnginePanel(probe)
}
// UI-04: Discard belongs to the exact displayed review, not the current one.
for (const recovery of [true, false]) {
  const probe = await mount('en', recovery ? { lifecycleRest: recoveryRest() } : { engineStatus: engineStatus('missing') })
  const preview = () => recovery ? recoveryButton(probe) : btn(engineCard(probe), 'Preview install')
  await click(preview(), 0)
  const discard = retainedClick(btn(engineCard(probe), 'Discard plan'))
  await click(preview(), 0)
  const review = engineCard(probe).querySelector('.wa-engine-plan')
  const count = enginePosts().length
  await act(async () => discard())
  if (engineCard(probe).querySelector('.wa-engine-plan') !== review || enginePosts().length !== count)
    fail(`UI-04: retained ${recovery ? 'recovery' : 'ordinary'} Discard cleared a newer exact review`)
  await click(btn(engineCard(probe), 'Discard plan'), 0)
  if (engineCard(probe).querySelector('.wa-engine-plan')) fail('UI-04: current displayed Discard no longer clears locally')
  await closeEnginePanel(probe)
}
// UI-03: ordinary Preview must retain its displayed status/root/SDK context.
for (const key of ['profile', 'connectionId', 'cwd']) {
  const probe = await mount('en', { engineStatus: engineStatus('missing') })
  const preview = retainedClick(btn(engineCard(probe), 'Preview install'))
  await act(async () => { stub.host.state[key].set(`other-${key}`); stub.host.state[key].set(key === 'profile' ? 'default' : key === 'connectionId' ? 'local' : '/srv/wiki') })
  const count = enginePosts().length
  await act(async () => preview())
  if (enginePosts().length !== count) fail(`UI-03: ordinary Preview rebound to new ${key} epoch`)
  await closeEnginePanel(probe)
}
{
  let armed = false, resolveStatus
  const response = new Promise(resolve => { resolveStatus = resolve })
  const probe = await mount('en', { engineStatus: () => armed ? response : engineStatus('missing') })
  const preview = retainedClick(btn(engineCard(probe), 'Preview install'))
  armed = true
  await setField(engineCard(probe).querySelector('input'), '/srv/new-selected-root')
  const count = enginePosts().length
  await act(async () => preview())
  if (enginePosts().length !== count || btn(engineCard(probe), 'Preview install')?.disabled !== true)
    fail('UI-03: old ordinary Preview bypassed fresh status readiness after root edit')
  await act(async () => { resolveStatus(engineStatus('missing')); await response })
  await act(async () => preview())
  if (enginePosts().length !== count) fail('UI-03: old ordinary Preview rebound after fresh root status arrived')
  await click(btn(engineCard(probe), 'Preview install'), 0)
  if (enginePosts().at(-1)?.body.project_root !== '/srv/new-selected-root') fail('UI-03: fresh Preview failed to preserve ordinary typed-root install flow')
  await closeEnginePanel(probe)
}
// Automation read readiness suspends ordinary actions without retiring unchanged identity/review.
{
  let pendingRead = false, resolveRead
  const response = new Promise(resolve => { resolveRead = resolve })
  const probe = await mount('en', { engineStatus: engineStatus('missing'),
    folioRest: path => path === '/automation' ? pendingRead ? response : automation()
      : { ok: true, candidates: [], operations: [] } })
  await click(btn(engineCard(probe), 'Preview install'), 0)
  const confirm = retainedClick(btn(engineCard(probe), 'Install this exact plan'))
  const preview = retainedClick(btn(engineCard(probe), 'Preview install'))
  const count = enginePosts().length
  pendingRead = true
  await click(refreshButton(probe.host), 0)
  await act(async () => { await confirm(); await preview() })
  if (enginePosts().length !== count || !engineCard(probe).querySelector('.wa-engine-plan'))
    fail('READINESS ordinary: pending automation read posted or discarded the unchanged review')
  await act(async () => { resolveRead(automation()); await response })
  await act(async () => confirm())
  if (enginePosts().length !== count + 1) fail('READINESS ordinary: unchanged completed read did not restore exact confirmation')
  await closeEnginePanel(probe)
}
// UI-02: unchanged read-only refresh preserves the ordinary draft and exact review object.
{
  const info = { ...automation(), available: false, settings: null }
  const probe = await mount('en', { engineStatus: engineStatus('missing'), automation: info })
  const root = '/srv/chosen-first-install'
  await setField(engineCard(probe).querySelector('input'), root)
  await click(btn(engineCard(probe), 'Preview install'), 0)
  const confirmation = retainedClick(btn(engineCard(probe), 'Install this exact plan'))
  const count = stub.calls.gets.filter(path => path === '/engine/status').length
  await click(refreshButton(probe.host), 0)
  if (engineCard(probe).querySelector('input')?.value !== root || !engineCard(probe).querySelector('.wa-engine-plan'))
    fail('UI-02: unchanged refresh erased the ordinary first-install draft or review')
  if (stub.calls.gets.filter(path => path === '/engine/status').length !== count)
    fail('UI-02: unchanged ordinary refresh automatically reread engine status')
  await act(async () => confirmation())
  if (enginePosts().filter(call => call.path === '/engine/apply').length !== 1)
    fail('UI-02: unchanged refresh invalidated the exact ordinary approval')
  await closeEnginePanel(probe)
}
// UI-01: invoke the actual registered automation interval, not an invented status poll.
{
  const intervals = []
  const originalInterval = globalThis.setInterval
  let refreshPending = false, resolveRefresh
  const refresh = new Promise(resolve => { resolveRefresh = resolve })
  let probe
  try {
    globalThis.setInterval = (callback, ms, ...args) => {
      intervals.push({ callback, ms })
      return originalInterval(callback, ms, ...args)
    }
    probe = await mount('en', { lifecycleRest: recoveryRest(),
      folioRest: path => path === '/automation' ? refreshPending ? refresh : automation()
        : { ok: true, candidates: [], operations: [] } })
  } finally { globalThis.setInterval = originalInterval }
  await click(recoveryButton(probe), 0)
  const resume = retainedClick(resumeButton(probe))
  const count = stub.calls.gets.filter(path => path === '/engine/status').length
  refreshPending = true
  await act(async () => intervals.find(timer => timer.ms === 60000).callback())
  if (!resumeButton(probe)) fail('UI-01: automation busy discarded the unexpired recovery review')
  await act(async () => { resolveRefresh(automation()); await refresh })
  if (!resumeButton(probe) || stub.calls.gets.filter(path => path === '/engine/status').length !== count)
    fail('UI-01: unchanged automation refresh retired review or automatically polled engine status')
  await act(async () => resume())
  if (enginePosts().filter(call => call.path === '/engine/recovery/apply').length !== 1)
    fail('UI-01: unchanged refresh invalidated the displayed fresh approval')
  await closeEnginePanel(probe)
}
{
  const probe = await mount('en', { lifecycleRest: recoveryRest(),
    automation: { ...automation(), available: false, settings: null } })
  const card = engineCard(probe)
  if (enginePosts().length) fail('RECOVERY explicit review: mount/status must not prepare/apply')
  const review = recoveryButton(probe)
  if (!review || review.disabled) fail('RECOVERY explicit review: original approved interrupted install has no enabled review button')
  else {
    await click(review)
    const original = engineRecoveryPlan()
    if (JSON.stringify(enginePosts()) !== JSON.stringify([{ path: '/engine/recovery/prepare',
      body: { install_id: original.install_id } }])) fail('RECOVERY review must send only original install_id')
    const region = card.querySelector('.wa-engine-plan')
    must(txt(region), [original.revision, original.project_root, original.project_id, original.engine_dir,
      original.audit_dir, original.install_id, original.plan_digest, original.activation,
      `${original.jobs[0].role} · ${original.jobs[0].name} · ${original.jobs[0].schedule}`,
      'Original approved installation', 'Review expires at',
      'This is fresh approval in this app session, not a transfer of previous-session approval.'], 'RECOVERY original full review')
    if (card.querySelector('input[aria-label="Project root for engine install"]')?.value !== original.project_root)
      fail('RECOVERY review must show canonical server root without input reselection')
    if (enginePosts().length !== 1) fail('RECOVERY review display performed automatic apply')
  }
  await closeEnginePanel(probe)
}
for (const state of ['installed_paused', 'installed_with_existing_jobs']) {
  let resolve
  const pending = new Promise(yes => { resolve = yes })
  const probe = await mount('en', { lifecycleRest: recoveryRest(undefined, () => pending) })
  await click(recoveryButton(probe), 0)
  const resume = resumeButton(probe)
  if (!resume || resume.disabled) fail('RECOVERY fresh confirm: missing enabled exact resume button')
  else {
    const retained = retainedClick(resume)
    await act(async () => { retained(); retained() })
    const review = engineRecoveryPlan()
    const expected = { path: '/engine/recovery/apply', body: { install_id: review.install_id,
      plan_digest: review.plan_digest, recovery_review_id: review.recovery_review_id,
      recovery_review_digest: review.recovery_review_digest, confirm: true } }
    if (JSON.stringify(enginePosts()) !== JSON.stringify([{ path: '/engine/recovery/prepare',
      body: { install_id: review.install_id } }, expected])) fail('RECOVERY fresh confirm: dispatch must be exact and single-use')
    if (!engineCard(probe).querySelector('[data-slot="loader"]')) fail('RECOVERY resume pending: no loader')
    await act(async () => { resolve({ ok: true, state, install_id: review.install_id,
      revision: review.revision, activation_required: true }); await pending })
    must(txt(engineCard(probe)), [review.revision.slice(0, 7), state === 'installed_paused'
      ? 'Installed — activation required' : 'Installed — existing jobs unchanged'], 'RECOVERY accepted result')
    if (!engineCard(probe).querySelector(`[data-tip="${review.revision}"]`)) fail('RECOVERY accepted result lost the full engine id')
    if (engineCard(probe).querySelector('.wa-engine-plan')) fail('RECOVERY success retained approval surface')
    const before = enginePosts().length
    await act(async () => { await retained() })
    if (enginePosts().length !== before) fail('RECOVERY success retained callback resumed twice')
    if (stub.calls.posts.some(call => !call.path.startsWith('/engine/recovery/'))) fail('RECOVERY resume wrote root/jobs/source-owner state')
  }
  await closeEnginePanel(probe)
}
// Expired/server-refused reviews never transfer or retry an approval automatically.
for (const [response, text] of [
  [{ ok: false, state: 'refused', reason: 'same administrator session required' }, 'same administrator session required'],
  [{ ok: false, state: 'refused', reason: 'legacy installation has no original approval; adoption refused' }, 'legacy installation has no original approval; adoption refused'],
  [{ ok: false, state: 'unavailable', reason: 'recovery service unavailable' }, 'recovery service unavailable'],
  [{ ok: true }, 'The prepared plan is incomplete or does not match this preview.'],
  [{ ...engineRecoveryPlan(), install_id: 'f'.repeat(64) }, 'The prepared plan is incomplete or does not match this preview.'],
  [{ ...engineRecoveryPlan(), plan_digest: 'f'.repeat(64) }, 'The prepared plan is incomplete or does not match this preview.'],
  [{ ...engineRecoveryPlan(), recovery_review_id: 'bad' }, 'The prepared plan is incomplete or does not match this preview.'],
  [{ ...engineRecoveryPlan(), project_root: 'relative' }, 'The prepared plan is incomplete or does not match this preview.'],
  [{ ...engineRecoveryPlan(), review_expires_at: clockNow / 1000 - 1 }, 'This recovery review expired. Review the interrupted installation again.'],
  [new Error('HTTP 403: fresh app session rejected'), 'HTTP 403: fresh app session rejected']
]) {
  const probe = await mount('en', { lifecycleRest: recoveryRest(() => {
    if (response instanceof Error) throw response
    return response
  }) })
  await click(recoveryButton(probe), 0)
  must(txt(engineCard(probe)), [text], 'RECOVERY prepare refusal/expiry')
  if (resumeButton(probe) || engineCard(probe).querySelector('.wa-engine-plan') || enginePosts().length !== 1)
    fail('RECOVERY prepare refusal/expiry became actionable or auto-approved')
  if (!recoveryButton(probe) || recoveryButton(probe).disabled) fail('RECOVERY prepare refusal has no explicit re-review')
  await closeEnginePanel(probe)
}
for (const response of [
  { ok: false, state: 'refused', reason: 'review expired or session rejected' },
  { ok: false, state: 'recovery_required', reason: 'journal recovery was refused' },
  { ok: true },
  { ok: true, state: 'installed_paused', install_id: 'f'.repeat(64),
    revision: engineRecoveryPlan().revision, activation_required: true },
  { ok: true, state: 'installed_paused', install_id: engineRecoveryPlan().install_id,
    revision: engineRecoveryPlan().revision, activation_required: false },
  new Error('HTTP 503: recovery service disconnected')
]) {
  const probe = await mount('en', { lifecycleRest: recoveryRest(undefined, () => {
    if (response instanceof Error) throw response
    return response
  }) })
  await click(recoveryButton(probe), 0)
  const resume = resumeButton(probe)
  if (!resume) throw new Error('RECOVERY failure setup has no resume')
  const retained = retainedClick(resume)
  await click(resume, 0)
  must(txt(engineCard(probe)), [response.message || response.reason || 'Engine installation was not confirmed.'], 'RECOVERY failed resume')
  if (engineCard(probe).querySelector('.wa-engine-plan') || /Installed —/.test(txt(engineCard(probe))))
    fail('RECOVERY failed resume retained consumed approval or claimed success')
  const before = enginePosts().length
  await act(async () => { await retained() })
  if (enginePosts().length !== before || !recoveryButton(probe) || recoveryButton(probe).disabled)
    fail('RECOVERY failed resume retried consumed callback or omitted explicit re-review')
  await click(recoveryButton(probe), 0)
  if (enginePosts().at(-1)?.path !== '/engine/recovery/prepare' || !resumeButton(probe))
    fail('RECOVERY failed resume explicit re-review did not prepare a fresh review')
  await closeEnginePanel(probe)
}
{
  const saved = clockNow
  const realTimeout = globalThis.setTimeout
  const timers = []
  globalThis.setTimeout = (fn, ms, ...args) => {
    if (ms === 10000) timers.push(fn)
    return realTimeout(fn, ms, ...args)
  }
  try {
    const probe = await mount('en', { lifecycleRest: recoveryRest(() => ({ ...engineRecoveryPlan(),
      review_expires_at: clockNow / 1000 + 10 })) })
    await click(recoveryButton(probe), 0)
    const retained = retainedClick(resumeButton(probe))
    clockNow += 10000
    if (!timers.length) fail('RECOVERY expiry: no session-local review expiry timer')
    await act(async () => { for (const fn of timers) fn() })
    must(txt(engineCard(probe)), ['This recovery review expired. Review the interrupted installation again.'], 'RECOVERY expiry visible')
    await act(async () => { await retained() })
    if (enginePosts().length !== 1 || resumeButton(probe) || !recoveryButton(probe))
      fail('RECOVERY expiry allowed stale approval or omitted explicit re-review')
    await closeEnginePanel(probe)
  } finally { globalThis.setTimeout = realTimeout; clockNow = saved }
}
// SDK/local project context epochs bind callbacks at render time, including round trips.
for (const key of ['profile', 'connectionId', 'cwd']) {
  for (const stage of ['review', 'resume', 'review-pending', 'resume-pending', 'result']) {
    let resolve
    const pending = new Promise(yes => { resolve = yes })
    const probe = await mount('en', { lifecycleRest: recoveryRest(
      stage === 'review-pending' ? () => pending : undefined,
      stage === 'resume-pending' ? () => pending : undefined) })
    let retained = retainedClick(recoveryButton(probe))
    if (stage !== 'review') await click(recoveryButton(probe), 0)
    if (['resume', 'resume-pending', 'result'].includes(stage)) retained = retainedClick(resumeButton(probe))
    if (['resume-pending', 'result'].includes(stage)) await click(resumeButton(probe), 0)
    const before = enginePosts().length
    await act(async () => {
      const old = stub.host.state[key].get()
      stub.host.state[key].set(`new-${key}`)
      stub.host.state[key].set(old)
      if (stage === 'review-pending') resolve(engineRecoveryPlan())
      if (stage === 'resume-pending') resolve({ ok: true, state: 'installed_paused',
        install_id: engineRecoveryPlan().install_id, revision: engineRecoveryPlan().revision, activation_required: true })
    })
    await act(async () => { await retained() })
    if (enginePosts().length !== before) fail(`RECOVERY ${key} ${stage}: retained callback rebound to current scope`)
    if (engineCard(probe).querySelector('.wa-engine-plan') || /Installed —/.test(txt(engineCard(probe))))
      fail(`RECOVERY ${key} ${stage}: old review/deferred result survived scope roundtrip`)
    await closeEnginePanel(probe)
  }
}
for (const stage of ['review', 'resume', 'resume-pending', 'result']) {
  let resolve
  const pending = new Promise(yes => { resolve = yes })
  const probe = await mount('en', { lifecycleRest: recoveryRest(undefined,
    stage === 'resume-pending' ? () => pending : undefined) })
  let retained = retainedClick(recoveryButton(probe))
  if (stage !== 'review') { await click(recoveryButton(probe), 0); retained = retainedClick(resumeButton(probe)) }
  if (['resume-pending', 'result'].includes(stage)) await click(resumeButton(probe), 0)
  const before = enginePosts().length
  await setField(engineCard(probe).querySelector('input'), '/srv/changed-local-root')
  await act(async () => {
    if (stage === 'resume-pending') resolve({ ok: true, state: 'installed_paused',
      install_id: engineRecoveryPlan().install_id, revision: engineRecoveryPlan().revision, activation_required: true })
    await retained()
  })
  if (enginePosts().length !== before || engineCard(probe).querySelector('.wa-engine-plan')
    || /Installed —/.test(txt(engineCard(probe)))) fail(`RECOVERY local input ${stage}: old approval/result remained bound`)
  await closeEnginePanel(probe)
}
for (const change of ['root', 'id', 'error']) {
  const probe = await mount('en', { lifecycleRest: recoveryRest() })
  await click(recoveryButton(probe), 0)
  const retained = retainedClick(resumeButton(probe))
  if (change === 'root') AUTO = { ...AUTO, settings: { ...AUTO.settings, project_root: '/srv/another-root' } }
  if (change === 'id') AUTO = { ...AUTO, settings: { ...AUTO.settings, project: { ...AUTO.settings.project, id: 'other-id' } } }
  if (change === 'error') stub.state.throwOn = '/automation'
  await click(refreshButton(probe.host), 0)
  await act(async () => { await retained() })
  if (enginePosts().length !== 1 || (change === 'error'
    ? !engineCard(probe).querySelector('.wa-engine-plan') || resumeButton(probe)?.disabled !== true
    : engineCard(probe).querySelector('.wa-engine-plan')))
    fail(`RECOVERY project context ${change}: drift must retire review; read errors retain it without allowing apply`)
  await closeEnginePanel(probe)
}
{
  const probe = await mount('en', { lifecycleRest: recoveryRest() })
  const retained = retainedClick(recoveryButton(probe))
  await act(async () => { await retained(); await retained() })
  if (enginePosts().length !== 1) fail('RECOVERY review callback: one explicit review intent prepared twice')
  const oldResume = retainedClick(resumeButton(probe))
  await click(recoveryButton(probe), 0)
  const before = enginePosts().length
  await act(async () => { await oldResume() })
  if (enginePosts().length !== before) fail('RECOVERY re-review rebound an old resume callback to the new review')
  await closeEnginePanel(probe)
}
for (const status of [
  { ...engineStatus('recovery_required'), reason: 'legacy approval unavailable; recovery refused' },
  { ...interruptedEngineStatus(), install_id: 'bad', reason: 'invalid installation record' },
  { ...interruptedEngineStatus(), plan_digest: 'bad', reason: 'invalid plan record' },
  { ok: false, state: 'unavailable', reason: 'installation service refused this session' }
]) {
  const probe = await mount('en', { lifecycleRest: () => status })
  must(txt(engineCard(probe)), [status.reason], 'RECOVERY unavailable record explanation')
  if (recoveryButton(probe) || resumeButton(probe) || enginePosts().length)
    fail('RECOVERY legacy/invalid/unavailable status offered adoption or write')
  await closeEnginePanel(probe)
}
for (const patch of [
  { recovery_review_digest: 'bad' }, { recovery_review_id: true }, { revision: 'bad' },
  { project_id: '' }, { engine_dir: 'relative' }, { audit_dir: '' },
  { jobs: null }, { jobs: [{ role: 'watchdog', name: 'Watch Dog' }] }, { activation: '' },
  { review_expires_at: '1234567890' }, { review_expires_at: true },
  { review_expires_at: Infinity }, { review_expires_at: NaN }, { review_expires_at: 1e20 }
]) {
  const probe = await mount('en', { lifecycleRest: recoveryRest(() => ({ ...engineRecoveryPlan(), ...patch })) })
  await click(recoveryButton(probe), 0)
  if (resumeButton(probe) || engineCard(probe).querySelector('.wa-engine-plan') || probe.errors.size)
    fail('RECOVERY malformed review became actionable or threw during display')
  must(txt(engineCard(probe)), ['The prepared plan is incomplete or does not match this preview.'], 'RECOVERY malformed review refusal')
  await closeEnginePanel(probe)
}
for (const state of ['applying', 'recovery_required']) {
  const probe = await mount('tr', { lifecycleRest: (path, opts) => path === '/engine/status'
    ? interruptedEngineStatus(state) : recoveryRest()(path, opts) })
  if (!recoveryButton(probe) || recoveryButton(probe).disabled || enginePosts().length)
    fail(`RECOVERY ${state}: missing explicit review without writes`)
  await click(recoveryButton(probe), 0)
  if (RAW_KEY.test(txt(engineCard(probe)))) fail('RECOVERY fallback locale leaked raw key')
  await closeEnginePanel(probe)
}
{
  const probe = await mount('en', { lifecycleRest: recoveryRest() })
  await click(recoveryButton(probe), 0)
  const retainedReview = retainedClick(recoveryButton(probe))
  await click(resumeButton(probe), 0)
  const before = enginePosts().length
  await act(async () => { await retainedReview() })
  if (enginePosts().length !== before || engineCard(probe).querySelector('.wa-engine-plan'))
    fail('RECOVERY completed resume: retained review reopened an already completed installation')
  await closeEnginePanel(probe)
}
// Status re-reads are read-only and retire any previous review. Failed reads cannot preserve approval.
for (const outcome of ['changed', 'failure', 'pending']) {
  let resolve
  const pending = new Promise(yes => { resolve = yes })
  let armed = false
  const probe = await mount('en', { lifecycleRest: (path, opts) => {
    if (path !== '/engine/status') return recoveryRest()(path, opts)
    if (!armed) return interruptedEngineStatus()
    if (outcome === 'failure') throw new Error('HTTP 503: status service unavailable')
    if (outcome === 'pending') return pending
    return { ...interruptedEngineStatus(), install_id: 'a'.repeat(64), plan_digest: 'b'.repeat(64) }
  } })
  await click(recoveryButton(probe), 0)
  const oldResume = retainedClick(resumeButton(probe))
  const oldReview = retainedClick(recoveryButton(probe))
  armed = true
  await click(btn(engineCard(probe), 'Retry status'), 0)
  await act(async () => { await oldResume(); await oldReview() })
  if (enginePosts().length !== 1 || engineCard(probe).querySelector('.wa-engine-plan'))
    fail(`RECOVERY ${outcome} status refresh left retained approval/review actionable`)
  if (outcome === 'pending') await act(async () => { resolve(interruptedEngineStatus()); await pending })
  await closeEnginePanel(probe)
}
{
  let resolve
  const pending = new Promise(yes => { resolve = yes })
  const probe = await mount('en', { lifecycleRest: recoveryRest(() => pending) })
  const retained = retainedClick(recoveryButton(probe))
  await act(async () => { retained(); retained() })
  if (enginePosts().length !== 1) fail('RECOVERY pending review: duplicate retained callback dispatch')
  await closeEnginePanel(probe)
  await act(async () => { resolve(engineRecoveryPlan()); await pending; await retained() })
  if (enginePosts().length !== 1 || probe.errors.size) fail('RECOVERY unmounted review callback/result became active')
}
{
  const saved = clockNow
  const probe = await mount('en', { lifecycleRest: recoveryRest() })
  await click(recoveryButton(probe), 0)
  const retained = retainedClick(resumeButton(probe))
  clockNow += 600000
  await act(async () => { await retained() })
  if (enginePosts().length !== 1 || resumeButton(probe)) fail('RECOVERY expiry dispatch guard relied only on timer')
  must(txt(engineCard(probe)), ['This recovery review expired. Review the interrupted installation again.'], 'RECOVERY suspended-clock expiry')
  clockNow = saved
  await closeEnginePanel(probe)
}
{
  const original = { ...engineRecoveryPlan(), project_root: '/srv/Original project <literal>',
    requested_project_root: '/srv/Original project alias', project_id: 'original-id <not markup>',
    jobs: [{ role: 'watchdog', name: 'Original <strong>job</strong>', schedule: '0 9 * * *' }] }
  const probe = await mount('en', { lifecycleRest: recoveryRest(() => original) })
  await click(recoveryButton(probe), 0)
  const region = engineCard(probe).querySelector('.wa-engine-plan')
  must(txt(region), ['Original approved revision', 'Original install id', 'Original plan digest',
    original.project_root, original.project_id, original.jobs[0].name,
    new Date(original.review_expires_at * 1000).toISOString()], 'RECOVERY truthful original metadata')
  if (region?.getAttribute('aria-label') !== 'Original approved installation review')
    fail('RECOVERY review region mislabelled as ordinary prepared installation')
  if (region?.querySelector('strong')) fail('RECOVERY original server values were parsed as markup')
  if (process.env.WIKI_RECOVERY_SNAPSHOT === '1') writeFileSync(`${HERE}../handoff/recovery-review.html`,
    `<!doctype html><html lang="en"><meta charset="utf-8"><title>Isolated jsdom recovery review</title>${engineCard(probe).outerHTML}</html>`)
  await closeEnginePanel(probe)
}
{
  const probe = await mount('en', { lifecycleRest: recoveryRest() })
  await click(recoveryButton(probe), 0)
  stub.state.throwOn = '/automation'
  await click(refreshButton(probe.host), 0)
  const action = recoveryButton(probe)
  if (action && !action.disabled) fail('RECOVERY unreadable local project context offers a new approval review')
  const before = enginePosts().length
  if (action) await act(async () => { await retainedClick(action)() })
  if (enginePosts().length !== before) fail('RECOVERY unreadable local project context dispatched re-review')
  await closeEnginePanel(probe)
}
console.log('RECOVERY exercised — original approved plan, explicit fresh review/confirm, single-use callbacks, expiry/refusal/service/legacy responses, SDK/project epochs and deferred results; isolated React/jsdom only')
if (process.env.WIKI_RECOVERY_ONLY === '1') {
  console.log(`RECOVERY focused render: ${problems.length} problem(s)`)
  process.exitCode = problems.length ? 1 : 0
  return
}
// Ordinary update remains the original exact-plan contract; no recovery fields/routes leak into it.
{
  const probe = await mount('en', { engineStatus: engineStatus('installed_with_existing_jobs'),
    engineApply: body => ({ ok: true, state: 'installed_with_existing_jobs', install_id: body.install_id,
      revision: ENGINE_REVISION, activation_required: true }) })
  const card = engineCard(probe)
  await click(btn(card, 'Preview update'), 0)
  const original = enginePlan()
  if (resumeButton(probe) || recoveryButton(probe)) fail('ordinary update exposed interrupted-install controls')
  must(txt(card), [original.revision, original.project_root, original.plan_digest, 'Install this exact plan'],
    'ordinary update unchanged preview')
  await click(btn(card, 'Install this exact plan'), 0)
  const expected = [{ path: '/engine/prepare', body: { project_root: VALID_ROOT } },
    { path: '/engine/apply', body: { install_id: original.install_id, plan_digest: original.plan_digest, confirm: true } }]
  if (JSON.stringify(enginePosts()) !== JSON.stringify(expected)) fail('ordinary update exact-plan request changed')
  must(txt(card), ['Installed — existing jobs unchanged', ENGINE_REVISION.slice(0, 7),
    'Existing job activation is unchanged.'], 'ordinary update unchanged result')
  if (!card.querySelector(`[data-tip="${ENGINE_REVISION}"]`)) fail('installed engine id lost its full value behind the short id')
  if (txt(card).includes(ENGINE_REVISION)) fail('installed engine block printed the full 40-char id')
  await closeEnginePanel(probe)
}

{
  const missing = await mount('en', { engineStatus: engineStatus('missing'),
    automation: { ...automation(), available: false, settings: null }, pickResult: `${VALID_ROOT}/README.md` })
  const card = engineCard(missing)
  must(txt(card), ['Engine not installed', 'Choose project folder', 'Preview install'], 'missing engine controls')
  if (enginePosts().length) fail('mount/status automatically prepared or applied an engine')
  const preview = btn(card, 'Preview install')
  if (!preview?.disabled) fail('missing engine preview must require an explicit chosen project root')
  const beforePick = stub.state.pickCalls.length
  await click(btn(card, 'Choose project folder'))
  if (stub.state.pickCalls.length !== beforePick + 1
    || stub.state.pickCalls.at(-1)?.title !== 'Pick a file directly inside the project folder') fail('initial install must use the SDK single-file picker with honest root guidance')
  if (enginePosts().length || stub.calls.posts.some(call => /automation\/(derive|validate|settings)/.test(call.path))) {
    fail('missing engine project pick called an engine-dependent root endpoint or wrote settings')
  }
  if (card.querySelector('input[aria-label="Project root for engine install"]')?.value !== VALID_ROOT) fail('locally chosen install root lost the exact folder path')
  await click(btn(card, 'Preview install'))
  if (JSON.stringify(enginePosts()) !== JSON.stringify([{ path: '/engine/prepare', body: { project_root: VALID_ROOT } }])) {
    fail('initial prepare must send only the exact chosen absolute project_root')
  }
  must(txt(card), [ENGINE_REVISION], 'prepared revision')
  await closeEnginePanel(missing)
}
{
  const probe = await mount('en', { engineStatus: engineStatus('missing'), pickResult: `${VALID_ROOT}/README.md` })
  await click(btn(engineCard(probe), 'Choose project folder'))
  await click(btn(engineCard(probe), 'Preview install'))
  const card = engineCard(probe)
  const plan = enginePlan()
  const pairs = [...card.querySelectorAll('.wa-engine-plan dd')].map(node => node.textContent)
  const exact = [plan.revision, plan.project_root, plan.project_id, plan.engine_dir, plan.audit_dir,
    plan.install_id, plan.plan_digest]
  if (JSON.stringify(pairs) !== JSON.stringify(exact)) fail('prepared plan must visibly preserve exact revision/project/code/data/install ID/digest')
  const job = card.querySelector('.wa-engine-plan .wa-engine-job')
  if (job?.textContent !== `${plan.jobs[0].role} · ${plan.jobs[0].name} · ${plan.jobs[0].schedule}`) fail('prepared jobs must show exact role/name/schedule without synthesis')
  must(txt(card), [plan.activation, 'Installing does not publish sources or activate new jobs.', 'Install this exact plan'], 'explicit install consequence')
  if (enginePosts().length !== 1) fail('plan render automatically applied the engine')
  await click(btn(card, 'Install this exact plan'))
  const calls = enginePosts()
  if (JSON.stringify(calls[1]) !== JSON.stringify({ path: '/engine/apply', body: {
    install_id: plan.install_id, plan_digest: plan.plan_digest, confirm: true } })) fail('explicit apply must send only exact staged ID/digest/confirm:true')
  must(txt(card), ['Installed — activation required', ENGINE_REVISION.slice(0, 7), 'Resume jobs separately in Scheduled jobs.'], 'installed paused result')
  if (!card.querySelector(`[data-tip="${ENGINE_REVISION}"]`)) fail('installed paused engine id lost its full value behind the short id')
  if (stub.calls.posts.some(call => !call.path.startsWith('/engine/'))) fail('engine install performed a job/root/source-owner write')
  await closeEnginePanel(probe)
}
const engineDeferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
{
  const pendingPrepare = engineDeferred()
  const probe = await mount('en', { engineStatus: engineStatus('missing'),
    enginePrepare: () => pendingPrepare.promise })
  const card = engineCard(probe)
  await click(btn(card, 'Preview install'), 0)
  if (!card.querySelector('[data-slot="loader"]') || [...card.querySelectorAll('button')].some(button => !button.disabled)) fail('prepare pending must expose a loader and disable every install control')
  await click(btn(card, 'Preview install'), 0)
  if (enginePosts().length !== 1) fail('pending prepare dispatched a duplicate request')
  await act(async () => pendingPrepare.resolve(enginePlan()))
  const pendingApply = engineDeferred()
  stub.state.engineApply = () => pendingApply.promise
  await click(btn(card, 'Install this exact plan'), 0)
  if (!card.querySelector('[data-slot="loader"]') || [...card.querySelectorAll('button')].some(button => !button.disabled)) fail('apply pending must retain the displayed plan and disable every install control')
  await click(btn(card, 'Install this exact plan'), 0)
  if (enginePosts().length !== 2) fail('pending apply dispatched a duplicate request')
  await act(async () => pendingApply.reject(new Error('connection interrupted after dispatch')))
  must(txt(card), ['connection interrupted after dispatch', enginePlan().install_id, enginePlan().plan_digest], 'retry preserves prepared identity')
  if (/Installed — activation required/.test(txt(card))) fail('apply exception claimed install success')
  stub.state.engineApply = body => ({ ok: true, state: 'installed_paused', install_id: body.install_id,
    revision: ENGINE_REVISION, activation_required: true })
  await click(btn(card, 'Install this exact plan'))
  if (JSON.stringify(enginePosts()[1]) !== JSON.stringify(enginePosts()[2])
    || enginePosts().filter(call => call.path === '/engine/prepare').length !== 1) fail('retry must reuse the same staged ID/digest without preparing again')
  await closeEnginePanel(probe)
}
for (const [response, text] of [
  [{ ok: false, state: 'refused', reason: 'digest no longer matches' }, 'digest no longer matches'],
  [{ ok: true }, 'Engine installation was not confirmed.'],
  [{ ok: true, state: 'installed_paused', install_id: 'f'.repeat(64), revision: ENGINE_REVISION,
    activation_required: true }, 'Engine installation was not confirmed.'],
  [{ ok: false, state: 'recovery_required', reason: 'journal needs inspection' }, 'journal needs inspection']
]) {
  const probe = await mount('en', { engineStatus: engineStatus('missing'), engineApply: () => response })
  await click(btn(engineCard(probe), 'Preview install'))
  await click(btn(engineCard(probe), 'Install this exact plan'))
  must(txt(engineCard(probe)), [text], 'apply refusal is not HTTP success')
  if (/Installed — activation required/.test(txt(engineCard(probe)))) fail('refused/partial/mismatched apply claimed success')
  if (response.state === 'recovery_required'
    && [...engineCard(probe).querySelectorAll('button')].some(button => /Preview|Install this/.test(txt(button)) && !button.disabled)) fail('recovery-required must block prepare/apply; never expose automatic rollback')
  await closeEnginePanel(probe)
}
{
  const older = '3'.repeat(40)
  const probe = await mount('en', { engineStatus: engineStatus('installed_paused', older),
    enginePrepare: () => ({ ok: false, state: 'refused', reason: 'project marker is invalid' }) })
  const card = engineCard(probe)
  must(txt(card), ['Installed — activation required', 'Preview update', '3333333',
    'This plugin ships engine 4444444'], 'installed activation-needed update state')
  if (!card.querySelector(`[data-tip="${older}"]`)) fail('older install lost its full engine id behind the short id')
  await click(btn(card, 'Preview update'))
  must(txt(card), ['project marker is invalid'], 'prepare refusal')
  if (card.querySelector('.wa-engine-plan')) fail('refused prepare fabricated a plan')
  await closeEnginePanel(probe)
}
for (const state of ['applying', 'recovery_required', 'unavailable']) {
  const probe = await mount('en', { engineStatus: { ...engineStatus(state), reason: `state is ${state}` } })
  const card = engineCard(probe)
  must(txt(card), [`state is ${state}`], 'non-actionable engine status reason')
  if ([...card.querySelectorAll('button')].some(button => /Preview/.test(txt(button)) && !button.disabled)
    || enginePosts().length) fail(`${state} status allowed a lifecycle write`)
  await closeEnginePanel(probe)
}
// A pre-panel engine is offered as an explicit exact-plan adoption, never adopted on mount.
{
  const adoption = { ...enginePlan(), jobs: [
    { role: 'watchdog', name: 'Watch Dog', schedule: '0 9 * * *', disposition: 'adopt_existing' },
    { role: 'session_harvest', name: 'Wiki Session Harvest', schedule: '30 21 * * *', disposition: 'adopt_paused' },
    { role: 'autocommit', name: 'Wiki Auto-Commit', schedule: '0 9 * * *', disposition: 'keep_existing' },
    { role: 'ingest_watch', name: 'Wiki Ingest Watch', schedule: '0 9 * * *', disposition: 'create_paused' }] }
  const probe = await mount('en', { engineStatus: { ...engineStatus('existing_unverified'), current_revision: null },
    enginePrepare: () => adoption,
    engineApply: body => ({ ok: true, state: 'installed_with_existing_jobs', install_id: body.install_id,
      revision: ENGINE_REVISION, activation_required: true }) })
  const card = engineCard(probe)
  must(txt(card), ['Existing engine found — not yet verified by this panel',
    'nothing changes until you confirm the plan', 'Preview update'], 'legacy engine status')
  if (enginePosts().length) fail('legacy engine status prepared or applied on mount')
  await click(btn(card, 'Preview update'), 0)
  must(txt(card), ['watchdog · Watch Dog · 0 9 * * * · adopted in place: schedule and on/off state kept; working folder, interpreter and launcher updated',
    'session_harvest · Wiki Session Harvest · 30 21 * * * · adopted in place and paused: new drafting prompt and tools; turn it on in Tasks after checking',
    'autocommit · Wiki Auto-Commit · 0 9 * * * · kept as is',
    'ingest_watch · Wiki Ingest Watch · 0 9 * * * · new, paused', adoption.plan_digest], 'legacy adoption plan')
  await click(btn(card, 'Install this exact plan'), 0)
  const expected = [{ path: '/engine/prepare', body: { project_root: VALID_ROOT } },
    { path: '/engine/apply', body: { install_id: adoption.install_id, plan_digest: adoption.plan_digest, confirm: true } }]
  if (JSON.stringify(enginePosts()) !== JSON.stringify(expected)) fail('legacy adoption exact-plan request changed')
  await closeEnginePanel(probe)
}
for (const key of ['profile', 'connectionId']) {
  const probe = await mount('en', { engineStatus: engineStatus('missing') })
  await click(btn(engineCard(probe), 'Preview install'))
  const staleConfirm = btn(engineCard(probe), 'Install this exact plan')
  const before = enginePosts().length
  await act(async () => stub.host.state[key].set(`other-${key}`))
  must(txt(engineCard(probe)), ['Project or app context changed. Preview again before confirming.'], `${key} switch explanation`)
  if (engineCard(probe).querySelector('.wa-engine-plan')) fail(`${key} switch retained an actionable prepared plan`)
  await click(staleConfirm, 0)
  if (enginePosts().length !== before) fail(`${key} switch allowed stale exact-plan confirmation`)
  await closeEnginePanel(probe)
}
for (const stage of ['prepare', 'apply']) {
  for (const key of ['profile', 'connectionId']) {
    const pending = engineDeferred()
    const probe = await mount('en', { engineStatus: engineStatus('missing'),
      ...(stage === 'prepare' ? { enginePrepare: () => pending.promise } : { engineApply: () => pending.promise }) })
    await click(btn(engineCard(probe), 'Preview install'), 0)
    if (stage === 'apply') await click(btn(engineCard(probe), 'Install this exact plan'), 0)
    await act(async () => {
      stub.host.state[key].set(`other-${key}`)
      stub.host.state[key].set(key === 'profile' ? 'default' : 'local')
    })
    await act(async () => pending.resolve(stage === 'prepare' ? enginePlan()
      : { ok: true, state: 'installed_paused', install_id: enginePlan().install_id,
        revision: ENGINE_REVISION, activation_required: true }))
    const card = engineCard(probe)
    if (card.querySelector('.wa-engine-plan') || /Installed — activation required/.test(txt(card))) fail(`late ${stage} result survived ${key} switch/roundtrip`)
    await closeEnginePanel(probe)
  }
}
{
  const probe = await mount('en', { engineStatus: engineStatus('missing') })
  await click(btn(engineCard(probe), 'Preview install'))
  AUTO = { ...AUTO, settings: { ...AUTO.settings, project_root: '/srv/other-project',
    project: { ...AUTO.settings.project, id: 'another-project' } } }
  await click(refreshButton(probe.host))
  if (engineCard(probe).querySelector('.wa-engine-plan')) fail('a saved project root/id change retained exact-plan confirmation')
  must(txt(engineCard(probe)), ['Project or app context changed. Preview again before confirming.'], 'project context invalidation')
  await closeEnginePanel(probe)
}
{
  const probe = await mount('en', { engineStatus: engineStatus('missing'), pickResult: `${VALID_ROOT}/README.md` })
  await click(btn(engineCard(probe), 'Preview install'))
  stub.state.pickResult = '/srv/other-project/README.md'
  await click(btn(engineCard(probe), 'Choose project folder'))
  if (engineCard(probe).querySelector('.wa-engine-plan')) fail('choosing a new project kept a prepared confirmation')
  await closeEnginePanel(probe)
}
// Contract failures must never make an opaque prepared plan actionable.
for (const patch of [
  { install_id: 'not-a-digest' }, { plan_digest: 'not-a-digest' }, { revision: 'f'.repeat(40) },
  { project_root: '/srv/different' }, { project_id: '' }, { engine_dir: '' }, { audit_dir: '' },
  { jobs: null }, { jobs: [{ role: 'session_harvest', name: 'Wiki Session Harvest' }] }, { activation: '' }
]) {
  const probe = await mount('en', { engineStatus: engineStatus('missing'),
    enginePrepare: () => ({ ...enginePlan(), ...patch }) })
  await click(btn(engineCard(probe), 'Preview install'))
  must(txt(engineCard(probe)), ['The prepared plan is incomplete or does not match this preview.'], 'invalid prepared contract')
  if (engineCard(probe).querySelector('.wa-engine-plan') || btn(engineCard(probe), 'Install this exact plan')) fail('incomplete/mismatched plan became confirmable')
  await closeEnginePanel(probe)
}
{
  const probe = await mount('en', { engineStatus: engineStatus('missing'), pickResult: null })
  await click(btn(engineCard(probe), 'Choose project folder'))
  must(txt(engineCard(probe)), ['selection cancelled'], 'picker cancellation')
  if (enginePosts().length || /root found|saved:/.test(txt(engineCard(probe)))) fail('cancelled picker reported success or dispatched a write')
  stub.state.pickResult = 'relative-project/README.md'
  await click(btn(engineCard(probe), 'Choose project folder'))
  must(txt(engineCard(probe)), ['Choose a file using an absolute project path.'], 'relative picker refusal')
  if (txt(engineCard(probe)).includes('relative-project') || enginePosts().length) fail('relative picker result became a project root')
  await click(btn(engineCard(probe), 'Preview install'))
  await click(btn(engineCard(probe), 'Discard plan'))
  if (engineCard(probe).querySelector('.wa-engine-plan') || enginePosts().length !== 1) fail('discard must invalidate confirmation locally without applying or rolling back')
  await closeEnginePanel(probe)
}
{
  const probe = await mount('en', { engineStatus: () => { throw new Error('status service unavailable') } })
  const card = engineCard(probe)
  must(txt(card), ['Could not read the engine installation state.', 'status service unavailable', 'Retry status'], 'status read failure')
  if ([...card.querySelectorAll('button')].some(button => /Preview/.test(txt(button)) && !button.disabled)) fail('failed status read allowed a preview')
  stub.state.engineStatus = engineStatus('missing')
  await click(btn(card, 'Retry status'))
  must(txt(card), ['Engine not installed'], 'explicit status retry')
  if (enginePosts().length) fail('status retry dispatched a lifecycle write')
  await closeEnginePanel(probe)
}
{
  const statusRead = engineDeferred()
  const probe = await mount('en', { engineStatus: () => statusRead.promise })
  if (!engineCard(probe).querySelector('[data-slot="loader"]')) fail('pending engine status needs a loading state')
  await act(async () => stub.host.state.profile.set('other-profile'))
  await act(async () => statusRead.resolve(engineStatus('missing')))
  if (btn(engineCard(probe), 'Preview install')?.disabled !== true) fail('new profile reused the previous profile project root after a late status read')
  await closeEnginePanel(probe)
}
{
  const probe = await mount('en', { engineApply: body => ({ ok: true, state: 'installed_with_existing_jobs',
    install_id: body.install_id, revision: ENGINE_REVISION, activation_required: true }) })
  await click(btn(engineCard(probe), 'Preview update'))
  await click(btn(engineCard(probe), 'Install this exact plan'))
  must(txt(engineCard(probe)), ['Installed — existing jobs unchanged'], 'existing-job update outcome')
  if (/Installed — activation required/.test(txt(engineCard(probe))) || stub.calls.posts.some(call => call.path === '/jobs/act')) fail('existing-job update fabricated paused jobs or activated them')
  await closeEnginePanel(probe)
}
const retainEngineConfirm = panel => {
  const button = btn(engineCard(panel), 'Install this exact plan')
  const key = button && Object.keys(button).find(key => key.startsWith('__reactProps$'))
  const callback = key && button[key]?.onClick
  if (typeof callback !== 'function') throw new Error('could not retain the rendered engine confirmation callback')
  return callback
}
{
  const probe = await mount('en', { engineStatus: engineStatus('missing') })
  await click(btn(engineCard(probe), 'Preview install'))
  const cancelledConfirm = retainEngineConfirm(probe)
  await click(btn(engineCard(probe), 'Discard plan'))
  await click(btn(engineCard(probe), 'Preview install'))
  const before = enginePosts().length
  const currentConfirm = retainEngineConfirm(probe)
  await act(async () => cancelledConfirm())
  if (enginePosts().length !== before) fail('discard/reprepare rearmed an old confirmation callback even with identical staged ID/digest')
  await act(async () => currentConfirm())
  const applied = enginePosts().length
  await act(async () => currentConfirm())
  if (enginePosts().length !== applied) fail('a completed exact-plan confirmation callback was reusable')
  await closeEnginePanel(probe)
}
{
  const probe = await mount('en', { engineStatus: engineStatus('missing') })
  await click(btn(engineCard(probe), 'Preview install'))
  const confirm = retainEngineConfirm(probe)
  const getProfile = stub.host.state.profile.get
  stub.host.state.profile.get = () => 'switched-without-notification'
  const before = enginePosts().length
  try { await act(async () => confirm()) }
  finally { stub.host.state.profile.get = getProfile }
  if (enginePosts().length !== before) fail('pre-request native context guard depended only on a host notification')
  await closeEnginePanel(probe)
}
{
  const plan = { ...enginePlan(), engine_dir: '/srv/code/<script>literal</script>/' + 'very-long-segment-'.repeat(40),
    activation: 'No activation <script>is permitted</script>.', jobs: [
      ...enginePlan().jobs, { role: 'watchdog', name: '<script>Watch Dog</script>', schedule: '0 * * * *' }] }
  const probe = await mount('en', { engineStatus: engineStatus('missing'), enginePrepare: () => plan })
  await click(btn(engineCard(probe), 'Preview install'))
  const region = engineCard(probe).querySelector('.wa-engine-plan')
  if (region?.getAttribute('role') !== 'region' || region.tabIndex !== 0
    || region.getAttribute('aria-label') !== 'Prepared installation plan') fail('prepared plan needs a keyboard-reachable named scroll region')
  const css = probe.host.querySelector('.wa-root > style')?.textContent || ''
  if (!css.includes('.wa-engine-plan{max-height:420px;overflow-y:auto;min-width:0;scrollbar-width:thin')
    || !css.includes('.wa-engine-plan dd{white-space:pre-wrap;overflow-wrap:anywhere}')) fail('prepared plan must emit bounded scrolling and full wrapped exact values; jsdom does not prove pixel fit')
  if (region?.querySelector('script') || !region?.textContent.includes(plan.engine_dir)
    || !region?.textContent.includes(plan.activation) || region?.querySelectorAll('.wa-engine-job').length !== 2) fail('long plan paths/jobs/activation lost exact literal source text')
  const confirm = btn(region, 'Install this exact plan')
  await act(async () => confirm?.focus())
  if (document.activeElement !== confirm || confirm?.disabled) fail('explicit install confirmation is not keyboard reachable')
  await closeEnginePanel(probe)
}
{
  const probe = await mount('en', { engineStatus: engineStatus('missing'),
    automation: { ...automation(), available: false, settings: null } })
  const card = engineCard(probe)
  const input = card.querySelector('input[aria-label="Project root for engine install"]')
  if (!input) fail('engine install needs a local absolute-root field when a native file pick is unavailable')
  else {
    await setField(input, 'relative-project')
    if (btn(card, 'Preview install')?.disabled !== true) fail('relative typed root became previewable')
    await setField(input, VALID_ROOT)
    await click(btn(card, 'Preview install'))
    const staleConfirm = retainEngineConfirm(probe)
    await setField(input, '/srv/other-project')
    if (card.querySelector('.wa-engine-plan')) fail('editing the install root retained the previous exact plan')
    const before = enginePosts().length
    await act(async () => staleConfirm())
    if (enginePosts().length !== before) fail('edited project root permitted an old confirmation callback')
    if (stub.calls.posts.some(call => !call.path.startsWith('/engine/'))) fail('local install root typing called a root validation/save endpoint')
  }
  await closeEnginePanel(probe)
}
{
  const picked = fileURLToPath(new URL('fixture.mjs', import.meta.url))
  const folder = fileURLToPath(new URL('.', import.meta.url)).replace(/[\\/]+$/, '')
  const probe = await mount('en', { engineStatus: engineStatus('missing'),
    automation: { ...automation(), available: false, settings: null }, pickResult: picked })
  await click(btn(engineCard(probe), 'Choose project folder'))
  if (engineCard(probe).querySelector('input[aria-label="Project root for engine install"]')?.value !== folder) fail('native picker path lost platform separators or its exact containing folder')
  await click(btn(engineCard(probe), 'Preview install'))
  if (enginePosts()[0]?.body.project_root !== folder) fail('native absolute project path was not passed unchanged to prepare')
  await closeEnginePanel(probe)
}
for (const stage of ['prepare', 'apply']) {
  const pending = engineDeferred()
  const probe = await mount('en', { engineStatus: engineStatus('missing'),
    ...(stage === 'prepare' ? { enginePrepare: () => pending.promise } : { engineApply: () => pending.promise }) })
  await click(btn(engineCard(probe), 'Preview install'), 0)
  if (stage === 'apply') await click(btn(engineCard(probe), 'Install this exact plan'), 0)
  await closeEnginePanel(probe)
  await act(async () => pending.resolve(stage === 'prepare' ? enginePlan()
    : { ok: true, state: 'installed_paused', install_id: enginePlan().install_id,
      revision: ENGINE_REVISION, activation_required: true }))
  if (probe.host.querySelector('.wa-engine-plan') || probe.errors.size) fail(`late ${stage} result escaped unmount invalidation`)
}
{
  const probe = await mount('en', { engineStatus: engineStatus('missing'),
    engineApply: () => ({ ok: false, state: 'recovery_required', reason: 'installation journal is uncertain' }) })
  await click(btn(engineCard(probe), 'Preview install'))
  const confirm = retainEngineConfirm(probe)
  await act(async () => confirm())
  const before = enginePosts().length
  await act(async () => confirm())
  if (enginePosts().length !== before) fail('a retained confirmation callback bypassed recovery-required after its first result')
  await closeEnginePanel(probe)
}
if (process.env.WIKI_INSTALL_ONLY) {
  if (problems.length) { console.error(`engine render FAILED: ${problems.length} violation(s)`); process.exitCode = 1; return }
  console.log('engine render passed — local SDK root pick/input · exact prepared plan and explicit apply · pending/refusal/retry · installed activation-needed/update states · native connection/profile/project invalidation · stale/single-use confirmation · bounded literal plan and keyboard reachability (not native pixels or backend installation)')
  process.exitCode = 0
  return
}

// ===========================================================================
// 1) Registration + English layout
// ===========================================================================
let p = await mount('en')
const page = p.registrations.find(r => r.area === 'routes')
const nav = p.registrations.find(r => r.area === 'sidebar.nav')
if (page?.data?.path !== '/wiki-automation') fail(`page path wrong: ${page?.data?.path}`)
if (nav?.data?.path !== '/wiki-automation') fail(`sidebar path wrong: ${nav?.data?.path}`)
if (nav?.data?.label !== 'Wiki Automation') {
  fail(`sidebar label not resolved to the English name: ${JSON.stringify(nav?.data?.label)}`)
}
if (RAW_KEY.test(String(nav?.data?.label || ''))) fail('sidebar label is a raw i18n key')
if (!nav?.data?.codicon) fail('the sidebar entry has no icon')
// The registration-time title goes through the APP translator door (ctx.i18n.t), not a local table.
if (!stub.calls.registerKeys.includes('wa.title')) {
  fail('the registration-time title was not resolved through ctx.i18n.t')
}
// ONE bundle, English, registered under the plugin's own id.
if (stub.calls.registered.length !== 1) {
  fail(`exactly one bundle must be registered, got ${stub.calls.registered.length}`)
} else {
  const reg = stub.calls.registered[0]
  if (reg.id !== PLUGIN_ID) fail(`the bundle is registered under the wrong id: ${reg.id}`)
  if (reg.locales.join('|') !== 'en') fail(`the bundle must hold exactly 'en': ${reg.locales.join('|')}`)
}
const areas = p.registrations.map(r => r.area)
if (areas.join('|') !== 'routes|sidebar.nav') {
  fail(`the panel must contribute only a page and a sidebar entry: ${areas.join('|')}`)
}

// ONE METRO VIEW (2.5.0). The four tabs (Nexus | Chronicle | Folio | Health), the Nexus map with its
// inspector, wires and comets, the heartbeat strip, the Chronicle lower review queue and the per-view
// titles were REMOVED (Docs/metro-contract.md § Removed). The page opens on the line, the alert bar and
// no detail; every 2.3.12 component lives inside a detail reached by a click.
if (!p.mapFirst.metro || !p.mapFirst.map) fail('the page does not open on the Metro line (.wa-metro > .wa-metro-map)')
if (p.mapFirst.tabs.length || p.mapFirst.tabSlots) {
  fail(`a tab strip is back: ${p.mapFirst.tabs.join('|')} (${p.mapFirst.tabSlots} kit TabsTrigger)`)
}
if (p.mapFirst.detail) fail(`a detail is open before any click: ${p.mapFirst.detail}`)
if (p.mapFirst.healthShown) fail('the run history is rendered before History was pressed')
if (!p.mapFirst.bar) fail('the alert bar (.wa-metro-bar[data-alert]) is missing on first open')
if (p.mapFirst.gets.some(path => path.startsWith('/health/jobs/run'))) fail('the line eagerly loaded a run body')
if (p.mapFirst.gets.some(path => path.startsWith('/candidates/show'))) fail('the line eagerly loaded a candidate detail')
for (const route of ['/automation', '/jobs', '/candidates', '/harvest/status']) {
  if (!p.mapFirst.gets.includes(route)) fail(`the line did not load ${route} on first open`)
}
for (const gone of ['.nx-map', '.nx-node', '#wa-inspector', '.nx-wires', '.nx-comet', '.nx-lower', '.nx-queue',
  '.wa-hb-row', '.wa-hb-pill', '.wa-tabbody', 'details.nx-config']) {
  if (p.host.querySelector(gone)) fail(`the removed 2.3.x surface ${gone} is back`)
}
// History opens the run history under the line; a second press folds it; the line never leaves.
await selectTab(p.host, 'Health')
if (!p.host.querySelector('.wa-metro-detail[data-for="history"] .pa-root')) fail('History does not hold the run history')
if (!p.host.querySelector('.wa-metro-map')) fail('opening History moved the line away')
await selectTab(p.host, 'Nexus')
if (p.host.querySelector('.pa-root, .wa-metro-detail')) fail('a second press of History did not fold its detail')
if (opener(p.host, 'history')?.getAttribute('aria-pressed') !== 'false') fail('History stays pressed after it folded')
if (txt(p.host).includes('the watched root, the install state and the scheduler jobs')) {
  fail('the legacy Automation subtitle remains')
}
for (const title of ['Automation map', 'Source review', 'Run journal']) {
  if ([...p.host.querySelectorAll('h1')].some(h => txt(h).trim() === title)) fail(`the per-view title "${title}" is back`)
}
// Settings: wiki folder (RootCard), engine (InstallCard), scheduled jobs (JobsCard), installation files.
await openDetail(p.host, 'settings')
if (txt(p.host).includes('undefined')) fail('"undefined" appeared in the panel (function key used as label)')
const settingsDetail = detailOf(p.host, 'settings')
for (const id of ['wa-sec-root', 'wa-sec-install', 'wa-sec-jobs']) {
  if (!settingsDetail?.querySelector(`#${id}`)) fail(`Settings lost the retained section #${id}`)
}
if (settingsDetail?.querySelector('.wa-pend, .wa-pend-detail, .fl-desk')) fail('Settings embeds the review desk')
if (settingsDetail?.querySelector('.pa-log, .wa-run, .wa-runs-head')) fail('Settings lists runs (runs are listed once, in History)')
const rootCard = cardByTitle(p.host, 'Wiki folder') || settingsDetail?.querySelector('#wa-sec-root') || cards(p.host)[0]
const installCard = cardByTitle(p.host, 'Engine and files') || settingsDetail?.querySelector('#wa-sec-install')
const jobsCard = cardByTitle(p.host, 'Scheduled jobs') || settingsDetail?.querySelector('#wa-sec-jobs')
if (!installCard) fail('the install card is missing from Settings')
if (!jobsCard) fail('the scheduled jobs card is missing from Settings')
if (p.host.querySelector('.g-kpis, .g-gauge, .g-grid')) fail('the obsolete gauge/KPI shell is still rendered')

// BRANCH LINES carry the backend's adapter facts; a click opens that line's detail and never writes.
const expectedAgents = harvestStatus().agents
const map = () => p.host.querySelector('.wa-metro-map')
const lineNodes = () => [...p.host.querySelectorAll('[data-wa-line]')]
if (lineNodes().map(n => n.dataset.waLine).join('|') !== expectedAgents.map(a => a.id).join('|')) {
  fail(`the branch lines do not match the reported adapter IDs and order: ${lineNodes().map(n => n.dataset.waLine).join('|')}`)
}
const postsBeforeMap = stub.calls.posts.length
for (const agent of expectedAgents) {
  const node = lineNodes().find(n => n.dataset.waLine === agent.id)
  if (!node) continue
  const state = !agent.enabled ? 'off' : agent.found ? 'ok' : 'missing'
  if (node.dataset.state !== state) fail(`${agent.id}: the branch line is data-state=${node.dataset.state}, expected ${state}`)
  if (!txt(node).trim()) fail(`${agent.id}: the branch line has no visible words`)
  await click(node, 40)
  const pressed = [...p.host.querySelectorAll('[data-wa-line][aria-pressed="true"], [data-wa-station][aria-pressed="true"], [data-wa-nav][aria-pressed="true"]')]
  if (pressed.length !== 1 || pressed[0] !== node) fail(`${agent.id}: the pressed opener is not exclusive`)
  const detail = detailOf(p.host, `line:${agent.id}`)
  if (!detail) { fail(`${agent.id}: the branch did not open .wa-metro-detail[data-for="line:${agent.id}"]`); continue }
  if (map()?.contains(detail)) fail(`${agent.id}: the branch detail expanded inside the map`)
  // A dated cursor reads as a plain time ('Today 17:30'); the raw ISO stamp stays off the screen.
  const isoCursor = /^\d{4}-\d{2}-\d{2}T(\d{2}:\d{2})/.exec(agent.cursor || '')
  must(txt(detail), [agent.found ? 'found' : 'not found', isoCursor ? isoCursor[1] : agent.cursor],
    `${agent.id} branch detail backend facts`)
  if (isoCursor && txt(detail).includes(agent.cursor)) fail(`${agent.id}: the branch detail prints the raw cursor stamp`)
  if (agent.found && !/does not prove every conversation was read/i.test(txt(detail))) {
    fail(`${agent.id}: the branch detail lost the honesty note (a found folder does not prove every conversation was read)`)
  }
}
await closeDetail(p.host)
// HARVEST STATION: what it does, timetable, next and last run; `Change time` and the two-step Pause.
const harvestDetail = await openDetail(p.host, 'harvest')
must(txt(harvestDetail), ['Next', 'Last'], 'harvest station detail')
if (!btn(harvestDetail, 'Change time')) fail('the Harvest detail lost `Change time` (the ScheduleEditor)')
if (!btn(harvestDetail, 'Pause') && !btn(harvestDetail, 'Resume')) fail('the Harvest detail lost Pause / Resume')
if (txt(harvestDetail).includes('Cursor')) fail('the Harvest detail carries an adapter cursor (that is a branch fact)')
await closeDetail(p.host)
if (stub.calls.posts.length !== postsBeforeMap) fail('opening a branch or a station posted a write')

// LIVE: the Harvest station (and the found, enabled branch lines) read `run` only while the run store
// holds an ACTIVE run of the session-harvest job itself; a claimed run counts, a five-hour-old one does not.
const harvestRun = status => ({ at: new Date().toISOString(), status, status_label: status, delivery: 'none',
  delivery_label: 'None', ms: null, error_preview: null })
const withHarvest = (...statuses) => {
  const value = runs()
  value.jobs.push({ role: 'session_harvest', job_id: 'hhh', name: 'Wiki Session Harvest', live: true,
    runs: statuses.map(harvestRun) })
  return value
}
const otherActive = runs()
otherActive.jobs[0].runs.unshift(harvestRun('running'))
const stationState = (panel, id) => panel.host.querySelector(`[data-wa-station="${id}"]`)?.dataset.state
for (const [label, value, live] of [
  ['running', withHarvest('running', 'completed'), true], ['claimed', withHarvest('claimed'), true],
  ['completed', withHarvest('completed', 'running'), false], ['no harvest runs', withHarvest(), false],
  ['another job running', otherActive, false]]) {
  const view = await mount('en', { runs: value, openConfig: false })
  if ((stationState(view, 'harvest') === 'run') !== live) fail(`${label}: the Harvest station is data-state=${stationState(view, 'harvest')}`)
  const running = [...view.host.querySelectorAll('[data-wa-line][data-state="run"]')].map(n => n.dataset.waLine).join('|')
  const lit = live ? expectedAgents.filter(a => a.enabled && a.found).map(a => a.id).join('|') : ''
  if (running !== lit) fail(`${label}: the marching branch lines are "${running}", expected "${lit}"`)
  if (view.errors.size) fail(`${label} threw: ${[...view.errors].join(' | ')}`)
  await act(async () => view.unmount())
}
{
  const view = await mount('en', { runs: withHarvest('failed'), openConfig: false })
  if (stationState(view, 'harvest') === 'run') fail('failed: a failed Harvest run reads as live')
  await act(async () => view.unmount())
}
const liveRefused = await mount('en', { openConfig: false, runs: withHarvest('running'),
  jobs: { roles: [], orphans: [], ok: false, available: false, error: 'jobs unreadable', reason: 'jobs unreadable',
    mutation_available: false, management_reason: 'n/a' } })
if (stationState(liveRefused, 'harvest') === 'run') fail('the line shows a live Harvest run while the jobs read failed')
if (liveRefused.host.querySelector('.wa-metro-bar')?.dataset.alert !== 'read-failed') {
  fail(`a failed jobs read is not the read-failed alert: ${liveRefused.host.querySelector('.wa-metro-bar')?.dataset.alert}`)
}
const abandoned = withHarvest('running')
abandoned.jobs.at(-1).runs[0].at = new Date(Date.now() - 5 * 3600 * 1000).toISOString()
const staleLive = await mount('en', { openConfig: false, runs: abandoned })
if (stationState(staleLive, 'harvest') === 'run') fail('a run claimed five hours ago still reads as live')
const replay = await mount('en', { openConfig: false, runs: withHarvest('running') })
RUNS = runs()
const replayRefresh = refreshButton(replay.host)
if (replayRefresh) {
  await click(replayRefresh, 80)
  if (stationState(replay, 'harvest') === 'run') fail('the refreshed idle store still reads as live')
}
{
  const css = [...replay.host.ownerDocument.querySelectorAll('style')].map(s => s.textContent).join('\n')
  if (!/\.wa-metro\{[^}]*container-type:inline-size/.test(css)) fail('the Metro root is not an inline-size query container')
  // NO ORNAMENT: the only animation allowed is the dash-offset march on the branch lines.
  const keyframes = [...css.matchAll(/@keyframes ([\w-]+)\{((?:[^{}]*\{[^{}]*\})*)[^{}]*\}/g)]
  const animated = [...css.matchAll(/animation(?:-name)?:\s*([\w-]+)/g)].map(m => m[1]).filter(n => n !== 'none')
  for (const name of new Set(animated)) {
    const frames = keyframes.find(k => k[1] === name)?.[2] || ''
    if (!/stroke-dashoffset/.test(frames)) fail(`the animation ${name} is not the dash-offset march (no ornament: only the march moves)`)
  }
  if (!keyframes.some(k => /stroke-dashoffset/.test(k[2]))) fail('the branch lines have no dash-offset march for a running harvest')
}
// A refused read is not a fact. The real pre-panel engine answers /jobs and /runs with this refusal;
// the line must not turn it into "no schedule", "not run yet" or an empty history, and never says
// "Good service" while it stands.
const refusal = 'Selected native job policy source is unavailable or unverified'
const refusedJobs = await mount('en', { openConfig: false,
  jobs: { roles: [], orphans: [], ok: false, available: false, error: refusal, reason: refusal,
    mutation_available: false, management_reason: 'This Hermes version does not offer the cron store lock, so job changes stay off.' },
  runs: { ok: false, available: false, error: refusal, reason: refusal } })
const refusedBar = refusedJobs.host.querySelector('.wa-metro-bar')
if (refusedBar?.dataset.alert !== 'read-failed' || refusedBar?.dataset.tone !== 'bad') {
  fail(`refused reads are not the read-failed/bad alert: ${refusedBar?.dataset.alert}/${refusedBar?.dataset.tone}`)
}
if (/Good service/i.test(txt(refusedJobs.host))) fail('"Good service" is shown while a read failed')
must(txt(refusedBar), [refusal], 'the read-failed alert keeps the backend reason')
// 2.5.1 (m-12): with no readable timetable no line is drawn, so no station can turn the refusal into a fact;
// the bar holds the reason (checked above) and the map is its title alone.
if (!refusedJobs.host.querySelector('.wa-metro-map[data-unread="1"]') || refusedJobs.host.querySelector('[data-wa-station]')) {
  fail('a refused timetable read still draws the line (m-12 shows the title only)')
}
for (const invented of ['no schedule in the config', 'not run yet', 'no run recorded yet']) {
  if (txt(refusedJobs.host).includes(invented)) fail(`a refused job read was shown as a fact: "${invented}"`)
}
// The Auto-Commit job does publish the wiki to its mirrors, so an unqualified "No automatic publishing"
// stays untrue.
if (txt(refusedJobs.host).includes('No automatic publishing')) fail('the panel claims no automatic publishing')
// Opening the panel is not a context change: nothing was previewed, so nothing was discarded.
{
  const fresh = await mount('en', { engineStatus: engineStatus('missing') })
  if (txt(engineCard(fresh)).includes('Project or app context changed')) {
    fail('the engine card announced a context change on first load, before anything was previewed')
  }
  await closeEnginePanel(fresh)
}
// Every animated rule is switched off for a reader who asked for less motion.
const reducedOff = css => {
  let off = ''
  for (const chunk of css.split(/@media \(prefers-reduced-motion: ?reduce\)/).slice(1)) {
    let depth = 0
    let body = ''
    for (const ch of chunk) {
      if (ch === '{') depth += 1
      else if (ch === '}') { depth -= 1; if (depth <= 0) break }
      body += ch
    }
    off += ` ${body}`
  }
  const missing = []
  for (const match of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (!/(^|;)\s*animation:(?!none)/.test(match[2])) continue
    for (const selector of match[1].split(',').map(s => s.trim()).filter(Boolean)) {
      if (selector.startsWith('@') || /^(from|to|\d+%)$/.test(selector)) continue
      if (!off.includes(selector)) missing.push(selector)
    }
  }
  return missing
}
const allStyles = [...replay.host.ownerDocument.querySelectorAll('style')].map(s => s.textContent).join('\n')
const unswitched = reducedOff(allStyles)
if (unswitched.length) fail(`animated without a reduced-motion switch: ${unswitched.join(', ')}`)
if (/\.wa-tabbody|animation:nx-|animation:wa-enter\b/.test(allStyles)) fail('a removed 2.3.x entry choreography is back')
// YOUR REVIEW STATION opens the review desk: ONE draft at a time, the first by default, read once.
const reviewJump = await mount('en', { openConfig: false })
const readsBeforeReview = stub.calls.gets.length
await openDetail(reviewJump.host, 'review')
const desk = detailOf(reviewJump.host, 'review')
if (!desk || !reviewJump.host.querySelector('.wa-metro-map')) fail('Your review does not open the review desk under the line')
must(txt(desk), ['1 of 3', 'Approve', 'Reject', 'Later'], 'review desk (one draft at a time)')
if (desk?.querySelectorAll('.wa-pend-detail').length > 1) fail('the review desk shows more than one draft at a time')
if (stub.calls.posts.length) fail('Review navigation posted a write')
const reviewFirst = candidates()[0]
const reviewReads = stub.calls.gets.slice(readsBeforeReview).filter(path => path.startsWith('/candidates/show'))
if (reviewReads.length !== 1 || reviewReads[0] !== `/candidates/show?ref=${encodeURIComponent(reviewFirst.ref)}`) {
  fail(`the review desk did not read exactly the first draft once: ${reviewReads.join(' | ')}`)
}
must(txt(desk), [reviewFirst.summary], 'the first draft on the desk')
// `Later` moves to the next draft by IDENTITY: it reads exactly that ref and never writes.
await click(btn(desk, 'Later'), 80)
const laterReads = stub.calls.gets.slice(readsBeforeReview).filter(path => path.startsWith('/candidates/show'))
if (laterReads.at(-1) !== `/candidates/show?ref=${encodeURIComponent(candidates()[1].ref)}`) {
  fail(`Later did not read exactly the second draft: ${laterReads.at(-1)}`)
}
must(txt(detailOf(reviewJump.host, 'review')), ['2 of 3', candidates()[1].summary], 'Later shows the second draft')
if (stub.calls.posts.length) fail('Later posted a write (it only moves the desk)')
if (reviewJump.errors.size) fail(`Review navigation threw: ${[...reviewJump.errors].join(' | ')}`)
await act(async () => reviewJump.unmount())

// A failed project read clears any verified-project indication and becomes the read-failed alert.
const projectFailure = await mount('en', { openConfig: false })
stub.state.throwOn = '/automation'
const failRefresh = refreshButton(projectFailure.host)
if (!failRefresh) fail('the Metro header has no Refresh (aria-label="Refresh") to re-read the line')
else await click(failRefresh, 80)
if (projectFailure.host.querySelector('.wa-metro [data-tone="ok"][class*="project"], .wa-brand-project .g-dot[data-tone="ok"]')) {
  fail('a failed automation read left a stale verified project indicator')
}
if (failRefresh && projectFailure.host.querySelector('.wa-metro-bar')?.dataset.alert !== 'read-failed') {
  fail('a failed automation read is not the read-failed alert')
}
stub.state.throwOn = null
if (stub.calls.posts.length) fail('project context invalidation posted a write')
await act(async () => projectFailure.unmount())

must(txt(rootCard), ['Project root', '/srv/wiki', 'Verified', 'Choose folder…', 'Verify', 'Save',
  'Scan for candidates', 'Without a wiki folder the jobs do not stay silent'], 'root card')
must(txt(installCard), ['Settings file', '/srv/audit/settings.json', 'Automation folder', '/srv/audit',
  'Scripts', '3 of 4'], 'install card')
if (/Task Scheduler|Registered/.test(txt(installCard))) fail('the retired Task Scheduler row is still in the install card')
if (/Task Scheduler/.test(txt(p.host))) fail('the retired Task Scheduler is still named in Settings')
must(txt(jobsCard), ['Scheduled jobs',
  '3 of 4 jobs live',
  'Wiki Auto-Commit', 'Every hour, on the hour',
  '0 * * * *', 'aaa', 'Wiki Ingest Watch', 'No job ID', 'Watch Dog', 'ccc', 'Create in installation',
  'Pause job', 'Delete job', 'Live', 'the script watchdog.py is missing from the automation folder',
  'one live job has no working target — pause it, or point it at a folder'], 'jobs card')
if (txt(jobsCard).includes('the entries that keep the watched folder current')) fail('the redundant jobs paragraph remains')
// The row's own state word: `live` may NOT be satisfied by the card header's counter, so the check is
// scoped to the row (a header-only match is what made this lock pass with the badge removed).
const rowOf = name => Array.from(jobsCard.querySelectorAll('.wa-job'))
  .find(el => txt(el).includes(name))
// Native job disclosures are compact read-only summaries until a user explicitly opens one.
// jsdom has no painted visibility/layout: assert the native open flag, DOM boundaries and CSS contract.
const initialJobRows = [...jobsCard.querySelectorAll('.wa-job')]
if (initialJobRows.some(row => !row.matches('details.wa-job') || row.open || row.hasAttribute('open'))) {
  fail('all four supporting jobs must start as closed native disclosures')
}
const initialControls = new Map([
  ['Wiki Auto-Commit', ['Pause job', 'Schedule', 'Delete job']],
  ['Wiki Ingest Watch', ['Create in installation']],
  ['Watch Dog', ['Pause job', 'Schedule', 'Delete job']],
  ['Wiki Session Harvest', ['Pause job', 'Schedule']]
])
const disclosurePosts = stub.calls.posts.length
const disclosureGets = stub.calls.gets.length
for (const [name, labels] of initialControls) {
  const row = rowOf(name)
  const summary = row?.querySelector(':scope > summary.wa-job-summary')
  const expanded = row?.querySelector(':scope > .wa-job-expanded')
  if (!summary || row.firstElementChild !== summary || !expanded || row.children.length !== 2
    || summary.nextElementSibling !== expanded) {
    fail(`${name}: the native summary must lead its existing expanded job content`)
  }
  if (summary) {
    if (dom.window.getComputedStyle(summary).minHeight !== '52px') fail(`${name}: summary lost its 52px minimum height`)
    if (summary.querySelector('button, input, .wa-job-acts, .wa-job-runs, .wa-job-drift')) {
      fail(`${name}: an action or expanded diagnostic leaked into the closed summary`)
    }
    const summaryName = summary.querySelector('strong')
    const summarySchedule = summary.querySelector('.wa-job-summary-schedule')
    const summaryState = summary.querySelector('.wa-job-summary-state')
    const role = jobsView(jobsState()).roles.find(role => role.name === name)
    const state = role?.live && !role.target?.ok ? 'Needs attention' : role?.live ? 'Live' : 'No job ID'
    if (summaryName?.textContent !== name || !txt(summarySchedule).trim()
      || txt(summarySchedule) !== txt(expanded?.querySelector('.wa-job-human'))
      || txt(summaryState) !== state
      || summaryState?.dataset.tone !== (state === 'Needs attention' ? 'bad' : 'quiet')) {
      fail(`${name}: closed summary lost the exact name, schedule or backend state`)
    }
  }
  const controls = [...(expanded?.querySelectorAll('.wa-job-acts button') || [])]
  if (JSON.stringify(controls.map(txt)) !== JSON.stringify(labels)
    || controls.some(button => button.disabled || button.getAttribute('type') !== 'button')
    || row?.querySelectorAll('button').length !== controls.length
    || !expanded?.querySelector('.wa-job-main .wa-job-line') || !expanded?.querySelector('.wa-job-sched')) {
    fail(`${name}: expanded job lost or changed its actionable controls or diagnostics`)
  }
  const otherDisclosures = [...p.host.querySelectorAll('details')].filter(other => other !== row)
    .map(other => ({ node: other, open: other.open }))
  await click(summary, 0)
  if (!row?.open) fail(`${name}: clicking the native summary did not open the job`)
  if (otherDisclosures.some(({ node, open }) => node.open !== open)) {
    fail(`${name}: opening the job changed another disclosure`)
  }
  if (controls.some(button => button.closest('details.wa-job') !== row || !row.open)) {
    fail(`${name}: opening did not expose the original controls inside its own job disclosure`)
  }
  if (stub.calls.posts.length !== disclosurePosts || stub.calls.gets.length !== disclosureGets
    || jobsCard.querySelector('.wa-sched, [data-slot="confirm-dialog"]')) {
    fail(`${name}: opening the summary issued a request or armed an action`)
  }
  await click(summary, 0)
  if (row?.open || otherDisclosures.some(({ node, open }) => node.open !== open)) {
    fail(`${name}: summary did not close independently of other disclosures`)
  }
  if (stub.calls.posts.length !== disclosurePosts || stub.calls.gets.length !== disclosureGets
    || jobsCard.querySelector('.wa-sched, [data-slot="confirm-dialog"]')) {
    fail(`${name}: closing the summary issued a request or armed an action`)
  }
}
if (initialJobRows.some(row => row.open)) fail('summary round trips left a supporting job open')
if (!rowOf('Wiki Auto-Commit') || !txt(rowOf('Wiki Auto-Commit')).includes('Live')) {
  fail('the live state is not printed on the job row itself')
}
if (txt(jobsCard).includes('Paused')) fail('a paused state is shown before anything was paused')
// FOUR ROLES FROM THE ENGINE: the agent job (Wiki Session Harvest) is listed like the others, marked as
// an agent job, and offers neither Delete nor Create — the engine's installer owns its definition.
if (jobsCard.querySelectorAll('.wa-job').length !== 4) {
  fail(`the jobs card does not list the four engine roles: ${jobsCard.querySelectorAll('.wa-job').length}`)
}
const harvestRow = rowOf('Wiki Session Harvest')
if (!harvestRow) fail('the fourth job (Wiki Session Harvest) is missing from the jobs card')
else {
  must(txt(harvestRow), ['Agent', 'Every day at 21:30', '30 21 * * *', 'Live', 'Pause job', 'Schedule'],
    'agent job row')
  if (txt(harvestRow).includes('Delete job') || txt(harvestRow).includes('Create in installation')) {
    fail('the agent job offers a create or delete the engine owns')
  }
}
// THE ROW SUMMARY (2.1.0): the schedule as a sentence first, the cron beside it in mono behind a Tip, then
// the next run (absolute and relative), the last run with its result, and a late/missed flag when the
// store's dispatch stamp says so.
{
  const ac = rowOf('Wiki Auto-Commit')
  const wd = rowOf('Watch Dog')
  const human = wd?.querySelector('.wa-job-human')
  const cron = wd?.querySelector('.wa-job-cron')
  if (txt(human) !== 'Every day at 09:00') fail(`the schedule is not read as a sentence: ${txt(human)}`)
  if (!cron || txt(cron) !== '0 9 * * *' || !cron.classList.contains('wa-mono')) {
    fail(`the raw cron is not kept beside the sentence in mono: ${cron ? cron.outerHTML.slice(0, 120) : 'none'}`)
  } else {
    if (cron.getAttribute('data-tip') !== 'the cron expression the store holds') fail('the raw cron has no Tip')
    if (human.compareDocumentPosition(cron) !== dom.window.Node.DOCUMENT_POSITION_FOLLOWING) {
      fail('the raw cron is printed before the sentence it explains')
    }
  }
  const nextOf = row => txt(row?.querySelector('[data-run="next"]'))
  const lastOf = row => txt(row?.querySelector('[data-run="last"]'))
  const at = iso => iso.slice(11, 16)
  const S = stub.state.jobsState
  const rel = iso => {
    const mins = Math.abs(Date.parse(iso) - Date.now()) / 60000
    return mins < 60 ? `${Math.max(1, Math.round(mins))} min` : (mins < 2880 ? `${Math.round(mins / 60)} h`
      : `${Math.round(mins / 1440)} d`)
  }
  for (const [row, key] of [[wd, 'watchdog'], [ac, 'autocommit']]) {
    const want = S[key].next_run_at
    if (!nextOf(row).includes(at(want)) || !nextOf(row).includes(`in ${rel(want)}`)
      || !/(today|tomorrow) /.test(nextOf(row))) {
      fail(`the next run is not given as a local time and a distance: ${nextOf(row)} (want ${want})`)
    }
    if (!lastOf(row).includes(at(S[key].last_run_at)) || !lastOf(row).includes(`${rel(S[key].last_run_at)} ago`)) {
      fail(`the last run is not given as a local time and a distance: ${lastOf(row)}`)
    }
  }
  if (at(S.watchdog.next_run_at) !== '09:00' || at(S.autocommit.next_run_at).slice(3) !== '00') {
    fail('the fixture next runs contradict their schedules')
  }
  if (!lastOf(wd).startsWith('Last') || !nextOf(wd).startsWith('Next')) {
    fail(`the last run is not labelled: ${lastOf(wd)}`)
  }
  if (!lastOf(wd).endsWith('Failed') || lastOf(wd).includes('OK')) fail(`a failed last run has no Failed badge: ${lastOf(wd)}`)
  if (!lastOf(ac).endsWith('OK')) fail(`an ok last run lacks its OK badge: ${lastOf(ac)}`)
  const flag = row => row?.querySelector('.wa-job-flag')
  if (flag(wd)?.getAttribute('data-flag') !== 'missed' || txt(flag(wd)) !== 'Missed') {
    fail(`a catch-up dispatch is not flagged Missed: ${txt(flag(wd))}`)
  } else if (!/missed its slot: due .* caught up at .* \(2 h late\)/.test(flag(wd).getAttribute('data-tip') || '')) {
    fail(`the Missed flag does not explain itself in its Tip: ${flag(wd).getAttribute('data-tip')}`)
  }
  if (flag(ac)?.getAttribute('data-flag') !== 'late' || txt(flag(ac)) !== 'Late'
    || !/— 11 min late$/.test(flag(ac).getAttribute('data-tip') || '')) {
    fail(`a late dispatch is not flagged Late with its lateness: ${txt(flag(ac))} ${flag(ac)?.getAttribute('data-tip')}`)
  }
  if (flag(rowOf('Wiki Session Harvest'))) fail('an on-time job carries a late/missed flag')
  if (rowOf('Wiki Ingest Watch')?.querySelector('.wa-job-runs')) fail('a job with no store record prints run times')
  for (const row of [ac, wd]) {
    if (row.querySelector('.wa-job-line .wa-job-flag, .wa-job-line [data-run]')) {
      fail('the run facts were folded into the name line')
    }
  }
}
// ONE RUN VIEW: the runs are listed ONCE, in the History detail's journal. The 2.3.x Recent-runs card
// with its per-job heartbeat and "Open the run log" jump went with the heartbeat strip; the header's
// History button is the way to the log.
if (RUN_STAMPS.slice(0, 3).some(s => s.includes('.'))) fail('a same-day stamp carries a date')
if (!RUN_STAMPS[3].includes('.')) fail('an older run dropped its date')
{
  const jump = await mount('en', { openConfig: false })
  await openDetail(jump.host, 'history')
  if (jump.host.querySelectorAll('.pa-logwrap').length !== 1 || jump.host.querySelector('.wa-hb-row, .wa-run, .wa-runs-head')) {
    fail('History does not hold the sole run journal')
  }
  if (!stub.calls.gets.some(x => x.startsWith('/health/jobs?window='))) fail('History did not read /health/jobs')
  if (RAW_KEY.test(txt(jump.host))) fail('History printed a raw i18n key')
  await act(async () => jump.unmount())
}
if (p.host.querySelectorAll('select').length) fail('a native <select> is present (theme contract)')
// NO NATIVE TITLE: every label the panel shows is the kit's `Tip` (a glyph-only button keeps an
// `aria-label`). A native `title=` is unstyled and ~500ms late; the kit stub exposes the Tip label
// as `data-tip` on the trigger itself, so the DOM proves it.
const titled = [...p.host.querySelectorAll('[title]')]
if (titled.length) {
  fail(`a native title= reached the DOM: `
    + titled.map(el => `${el.tagName}:${el.getAttribute('title')}`).join(' | '))
}
if (p.errors.size) fail(`the panel threw: ${[...p.errors].join(' | ')}`)
// NO LANGUAGE PICKER and never a raw key.
if (p.host.querySelector('.wa-lang, .wa-lang-btn, [class*="lang"]')) {
  fail('the panel still renders a language picker')
}
if ([...p.host.querySelectorAll('button')].some(b => ['TR', 'EN'].includes(txt(b)))) {
  fail('a TR/EN language button is present')
}
if (RAW_KEY.test(txt(p.host))) fail(`the panel printed a raw i18n key: ${txt(p.host).slice(0, 120)}`)
if (stub.calls.gets.includes('/settings') || stub.calls.posts.some(x => x.path === '/settings')) {
  fail('the panel still calls the removed /settings language route')
}

// ===========================================================================
// 2) Root selection: the right SDK surface + cancellation + derivation
// ===========================================================================
const input = rootCard.querySelector('input')
if (!input) fail('the root input is missing')
await click(btn(rootCard, 'Choose folder…'), 80)
if (!stub.state.pickCalls.length) fail('ctx.os.pickOpenPath was not called (wrong SDK surface)')
const pickOpts = stub.state.pickCalls.at(-1) || {}
if (!pickOpts.filters?.length) fail('the picker got no file filters')
// The dialog opens on the CURRENT root's identity file so the user does not have to navigate, and
// its title stays short enough to read in a title bar.
if (!String(pickOpts.defaultPath || '').includes('.llm-wiki')) {
  fail(`the picker does not preselect the identity file: ${pickOpts.defaultPath}`)
}
if (!String(pickOpts.defaultPath || '').startsWith('/srv/wiki')) {
  fail(`the picker opens in the wrong folder: ${pickOpts.defaultPath}`)
}
if (!pickOpts.title || pickOpts.title.length > 60) {
  fail(`the picker title is unusable (empty or too long): ${JSON.stringify(pickOpts.title)}`)
}
if (!pickOpts.filters.some(f => (f.extensions || []).includes('*'))) {
  fail('the picker has no "all files" option (the user cannot pick an unexpected file)')
}
const derive = stub.calls.posts.filter(x => x.path === '/automation/derive').at(-1)
if (!derive || derive.body.picked !== '/srv/wiki/.llm-wiki/project.json') {
  fail(`wrong derive request: ${JSON.stringify(derive)}`)
}
if (input.value !== VALID_ROOT) fail(`the root picked from the file did not reach the draft: ${input.value}`)
must(txt(rootCard), [`root found: ${VALID_ROOT}`], 'derive message')

// CANCELLED PICK: no request, no silent success.
const postsBefore = stub.calls.posts.length
stub.state.pickResult = null
await click(btn(rootCard, 'Choose folder…'), 80)
if (stub.calls.posts.length !== postsBefore) fail('a request was sent although the pick was cancelled')
must(txt(rootCard), ['selection cancelled'], 'cancel message')
if (rootCard.querySelector('.wa-msg')?.getAttribute('data-tone') !== 'info') {
  fail('a cancelled pick is reported as a refusal (red) instead of a note')
}
if (txt(rootCard.querySelector('.wa-help-title')) === 'Why this was refused') {
  fail('a cancelled pick is headed "Why this was refused"')
}
stub.state.pickResult = '/srv/wiki/.llm-wiki/project.json'

// ===========================================================================
// 3) Verify · Save (gate) · refresh
// ===========================================================================
await click(btn(rootCard, 'Verify'), 80)
if (!stub.calls.posts.some(x => x.path === '/automation/validate')) fail('the Verify request did not go')
must(txt(rootCard), ['Verified · 419 pages · id auto-id'], 'verification result')

await setField(input, '/srv/elsewhere')
const rootBadge = () => txt(rootCard.querySelector('.wa-kv .wa-badge'))
const rootValue = () => txt(rootCard.querySelector('.wa-kv .wa-root-value'))
const draftBadge = () => txt(rootCard.querySelector('.wa-inline .wa-badge'))
// The Project root row is the SAVED root: a typed, unsaved draft never reads as the root in force.
if (rootValue().includes('/srv/elsewhere') || !rootValue().includes(VALID_ROOT)) {
  fail(`the Project root row shows an unsaved draft as the saved root: ${JSON.stringify(rootValue())}`)
}
if (rootBadge() !== 'Verified') {
  fail(`the saved root lost its own verdict while a draft was typed: ${JSON.stringify(rootBadge())}`)
}
if (draftBadge() === 'Verified') {
  fail('a "Verified" badge sits next to a typed draft nobody verified')
}
await click(btn(rootCard, 'Verify'), 80)
if (draftBadge() !== 'Not verified') {
  fail(`a refused draft does not carry its own badge: ${JSON.stringify(draftBadge())}`)
}
if (rootValue().includes('/srv/elsewhere') || rootBadge() !== 'Verified') {
  fail(`verifying a draft rewrote the saved root row: ${JSON.stringify(rootValue())}`)
}
await settle(120)
const autoGetsBefore = stub.calls.gets.filter(x => x === '/automation').length
await click(btn(rootCard, 'Save'), 80)
const bad = stub.calls.posts.filter(x => x.path === '/automation/settings').at(-1)
if (!bad || bad.body.project_root !== '/srv/elsewhere') fail(`wrong save request: ${JSON.stringify(bad)}`)
if (/saved:/.test(txt(rootCard))) fail('"saved" was written for an unverified root (silent wrong answer)')
must(txt(rootCard), ['the folder is not a verified wiki root'], 'rejection message')
if (stub.calls.gets.filter(x => x === '/automation').length !== autoGetsBefore) {
  fail('the state was refreshed although the save was rejected')
}
await settle(120)

await setField(input, VALID_ROOT)
await click(btn(rootCard, 'Save'), 80)
const good = stub.calls.posts.filter(x => x.path === '/automation/settings').at(-1)
if (!good || good.body.project_root !== VALID_ROOT) fail(`wrong valid save: ${JSON.stringify(good)}`)
must(txt(rootCard), [`saved: ${VALID_ROOT}`], 'save message')
if (input.value !== '') fail('the draft was not cleared after saving')
if (stub.calls.gets.filter(x => x === '/automation').length <= autoGetsBefore) {
  fail('the automation state was not refreshed after saving')
}
await settle(120)

// ===========================================================================
// 4) Candidate scan: the folder above the root is walked, a row fills the draft
// ===========================================================================
await setField(input, VALID_ROOT)
await click(btn(rootCard, 'Scan for candidates'), 80)
const candPath = stub.calls.gets.filter(x => x.startsWith('/automation/candidates')).at(-1)
if (!candPath || (!candPath.includes('root=%2Fsrv') && !candPath.includes('root=/srv'))) {
  fail(`the scan did not ask for the folder above the root: ${candPath}`)
}
must(txt(rootCard), ['Wiki projects found', '/srv/other-wiki', '/srv/mirror',
  '102 folders scanned', '1 folder unreadable', 'SAME ID',
  '12 pages', '419 pages'], 'candidate list')
// COPY: a count is a sentence, not a template — `folder(s)` makes the reader choose the number, and
// the job id is a label the reader can act on, not a bare hex fragment.
if (/[A-Za-z]\(s\)/.test(txt(p.host))) {
  fail('a count on screen is written as a machine plural, like "folder(s)"')
}
if (!txt(jobsCard).includes('id aaa')) {
  fail(`the job row does not label its id: ${txt(jobsCard).slice(0, 160)}`)
}
if (installCard && !txt(installCard).includes('3 of 4')) {
  fail(`the install row does not say how many scripts are there: ${txt(installCard)}`)
}
// SEARCH FIELD: the list narrows to what matches, and a miss is ONE neutral empty state.
const candFilter = rootCard.querySelector('.wa-cand-head input')
if (!candFilter) fail('the candidate list has no filter field (the kit SearchField)')
await setField(candFilter, 'mirror')
if (!rootCard.querySelectorAll('.wa-cand').length) fail('the filter emptied a matching list')
if (txt(rootCard).includes('/srv/other-wiki')) fail('the filter did not narrow the candidate list')
await setField(candFilter, 'nothing-matches-this')
must(txt(rootCard), ['no candidate matches the filter',
  'clear the field to see the whole candidate list'], 'filtered-empty state')
if (rootCard.querySelectorAll('.wa-cand').length) fail('the filtered list is not empty')
await setField(candFilter, '')
if (rootCard.querySelectorAll('.wa-cand').length !== 2) fail('clearing the filter did not restore the list')
// COPY/MIRROR GATE: picking a same-id candidate opens the confirmation row and the save goes with force.
await click([...rootCard.querySelectorAll('.wa-cand')].find(b => txt(b).includes('SAME ID')), 80)
must(txt(rootCard), ['has the same project id as the current root'], 'copy/mirror warning')
if (!rootCard.querySelector('.wa-confirm')) fail('no confirmation row for a copy/mirror candidate')
await click(btn(rootCard, 'Yes, take it'), 80)
const forced = stub.calls.posts.filter(x => x.path === '/automation/settings').at(-1)
if (!forced || forced.body.force !== true) fail(`the copy save did not go with force: ${JSON.stringify(forced)}`)
must(txt(rootCard), ['saved: /srv/mirror'], 'forced save message')
await settle(120)
// Back to a normal root: the confirmation row CLOSES (it does not stick) and the save carries no force.
await setField(input, VALID_ROOT)
await click(btn(rootCard, 'Save'), 80)
if (rootCard.querySelector('.wa-confirm')) fail('the confirmation row stayed open for a normal save')
const plain = stub.calls.posts.filter(x => x.path === '/automation/settings').at(-1)
if (plain?.body.force !== false) fail(`a normal save carries force: ${JSON.stringify(plain)}`)
await settle(120)
// NO CANDIDATES: the message is informational, not an error (never red).
stub.state.emptyCandidates = true
await click(btn(rootCard, 'Scan for candidates'), 80)
const msgEl = rootCard.querySelector('[data-tone]')
if (!msgEl || msgEl.getAttribute('data-tone') !== 'info') {
  fail(`the "no candidates" message is not neutral: ${msgEl ? msgEl.getAttribute('data-tone') : 'no message'}`)
}
if (String(msgEl.style.color || '').includes('red')) fail('the "no candidates" message is painted red')
must(txt(rootCard), ['no other wiki project under'], 'no candidates message')
// Back to candidates: a row writes the draft.
stub.state.emptyCandidates = false
await click(btn(rootCard, 'Scan for candidates'), 80)
await click(rootCard.querySelector('.wa-cand'), 80)
if (input.value !== '/srv/other-wiki') fail(`the candidate row did not fill the draft: ${input.value}`)
await settle(120)

// ===========================================================================
// 4b) Jobs: the two-step delete arms before it removes, Create/Pause go through the same route and
//     the panel re-reads the view the backend returns (the fixture mutates on each action).
const jobRow = name => Array.from(jobsCard.querySelectorAll('.wa-job'))
  .find(el => txt(el).includes(name) && !el.querySelector('.wa-confirm'))
const postsTo = path => stub.calls.posts.filter(x => x.path === path)
// The confirmation is the HOST's dialog now, not a row inside the job it belongs to. In the harness
// it renders inline (the real one is portalled), so the panel's state is still measurable as a DOM fact.
const armedNow = () => jobsCard.querySelector('[data-slot="confirm-dialog"]')
if (armedNow()) fail('a delete confirmation is open before anything was clicked')
await clickJobButton(jobRow('Wiki Auto-Commit'), 'Delete job', 60)
if (!armedNow()) fail('clicking Delete did not arm the confirmation - one click must not delete')
if (postsTo('/jobs/act').length) fail('the armed delete already reached the backend')
must(txt(armedNow()), ['Delete this scheduler entry?',
  'The panel keeps the definition and can create it again.'], 'delete confirmation')
await click(btn(armedNow(), 'Cancel'), 60)
if (armedNow()) fail('Cancel did not close the confirmation')
if (postsTo('/jobs/act').length) fail('Cancel reached the backend')
await clickJobButton(jobRow('Wiki Ingest Watch'), 'Create in installation', 120)
if (postsTo('/jobs/act').length) fail('Create wrote a native job itself instead of opening the reviewed installation')
// 2.12.0: every Settings section is open; Create brings the installation section into view and focus.
if (jobsCard.ownerDocument.activeElement !== jobsCard.closest('.wa-root')?.querySelector('#wa-sec-install')) {
  fail('Create did not take the owner to the installation section where the reviewed plan creates the job')
}
// The reviewed installation creates the missing job PAUSED; the fixture stands in for that apply.
Object.assign(stub.state.jobsState.ingest_watch, { live: true, state: 'paused', id: 'job-new' })
await click(refreshButton(p.host), 120)
await clickJobButton(jobRow('Wiki Ingest Watch'), 'Resume job', 120)
const resumes = postsTo('/jobs/act').filter(x => x.body?.action === 'resume')
const seenFacts = { id: 'job-new', state: 'paused', schedule: '*/30 * * * *' }
if (resumes.length !== 1 || JSON.stringify(resumes[0].body?.expected) !== JSON.stringify(seenFacts)) {
  fail(`Resume did not send the record the page showed: ${JSON.stringify(resumes.map(x => x.body?.expected))}`)
}
await clickJobButton(jobRow('Wiki Ingest Watch'), 'Pause job', 120)
if (!txt(jobRow('Wiki Ingest Watch')).includes('Resume job')) {
  fail('pausing did not come back as a paused row')
}
if (!txt(jobRow('Wiki Ingest Watch')).includes('Paused')) {
  fail('the paused state is not printed on the job row itself')
}
if (!txt(jobsCard).includes('job paused')) fail('the pause did not report back what happened')
if (txt(jobsCard.querySelector('.wa-help-title')) !== 'Result') {
  fail(`a successful job action has the wrong heading: ${txt(jobsCard.querySelector('.wa-help-title'))}`)
}

// The job row's shape is a DOM fact before it is a layout fact: the state badge is a SIBLING of the
// job name inside the name line, so it can only ever be drawn on that line.
for (const row of jobsCard.querySelectorAll('.wa-job')) {
  const line = row.querySelector('.wa-job-line')
  if (!line) fail('a job row has no name line — the badge would drop onto a line of its own')
  else {
    if (!line.querySelector('.wa-job-name')) fail('a job row keeps its name outside the name line')
    if (!line.querySelector('.wa-badge')) fail('a job row keeps its state badge off the name line')
    if (line.querySelector('.wa-job-meta')) fail('a job row folded its schedule line into the name line')
  }
  if (row.querySelector('.wa-job-main > .wa-badge')) {
    fail('a job state badge is still a direct child of the main column (its own line)')
  }
}
await clickJobButton(jobRow('Wiki Auto-Commit'), 'Delete job', 60)
await click(btn(armedNow(), 'Delete'), 120)
const removals = postsTo('/jobs/act').filter(x => x.body?.action === 'remove')
if (removals.length !== 1) fail(`the confirmed delete did not reach the backend once: ${removals.length}`)
if (removals[0].body?.confirm !== true) fail('the delete was sent without its confirm flag')
if (removals[0].body?.role !== 'autocommit') fail('the delete was sent for the wrong role')
const afterRemove = jobRow('Wiki Auto-Commit')
if (!afterRemove || afterRemove.querySelector('.wa-confirm')) {
  fail('the removed job still shows a confirmation')
}
if (txt(afterRemove).includes('Delete job')) fail('the removed job still offers Delete')
if (!txt(afterRemove).includes('Create in installation')) fail('the removed job does not offer Create again')
if (!txt(afterRemove).includes('No job ID')) fail('the removed job still claims a job id')
if ((txt(jobsCard).match(/live jobs have no working target|live job has no working target/g) || [])
  .length !== 1) {
  fail('the orphan banner is not printed exactly once')
}

// DRIFT: the store and the wiki config can disagree about when a job fires. Showing only one of them
// would hide the disagreement, so the row says both.
if (!txt(rowOf('Watch Dog')).includes('the store holds 0 9 * * * while the config still asks for 0 * * * *')) {
  fail('the drift between the store and the config is not printed on the row')
}
if (!txt(rowOf('Wiki Ingest Watch')).includes('none while paused')
  || !txt(rowOf('Wiki Ingest Watch')).includes('not run yet')) {
  fail(`a paused job that never ran does not say so: ${txt(rowOf('Wiki Ingest Watch'))}`)
}

// THE SCHEDULE EDITOR (2.1.0). Frequency → cron, cron → frequency, a live preview asked of the BACKEND,
// and the one write path (/jobs/act 'schedule') with the backend as the authority that refuses.
const editorOf = () => jobsCard.querySelector('.wa-sched')
const modeBtn = label => [...(editorOf()?.querySelectorAll('.wa-sched-freq button') || [])]
  .find(b => txt(b) === label)
const modeNow = () => txt(editorOf()?.querySelector('.wa-sched-freq [aria-pressed="true"]'))
const exprNow = () => txt(editorOf()?.querySelector('.wa-sched-expr'))
const humanNow = () => txt(editorOf()?.querySelector('.wa-sched-human'))
const runsNow = () => txt(editorOf()?.querySelector('.wa-sched-runs'))
const saveBtn = () => btn(editorOf(), 'Save schedule')
const field = cls => editorOf()?.querySelector(cls)
const dayBtn = label => [...(editorOf()?.querySelectorAll('.wa-day') || [])].find(b => txt(b) === label)
const previews = () => postsTo('/jobs/preview').map(x => x.body?.schedule)
const openEditor = async name => {
  if (editorOf()) await click(btn(editorOf(), 'Cancel'), 40)
  await clickJobButton(rowOf(name), 'Schedule', 80)
  await settle(400)
  if (!editorOf()) fail(`the schedule editor did not open on ${name}`)
}
await openEditor('Watch Dog')
if (jobsCard.querySelector('.wa-sched-chip')) fail('the old preset chips are back in the editor')
if (modeNow() !== 'Daily') fail(`0 9 * * * did not open in Daily: ${modeNow()}`)
if (field('.wa-sched-time')?.value !== '09:00') fail(`the time field does not read 09:00: ${field('.wa-sched-time')?.value}`)
if (field('.wa-sched-time')?.getAttribute('type') !== 'time') fail('the time is not a time input')
if (exprNow() !== '0 9 * * *' || humanNow() !== 'Every day at 09:00') {
  fail(`the preview does not read the current schedule: ${humanNow()} / ${exprNow()}`)
}
if ((runsNow().match(/09:00/g) || []).length !== 3 || !runsNow().startsWith('Next runs')) {
  fail(`the preview does not list the next three runs from the backend: ${runsNow()}`)
}
if (!previews().includes('0 9 * * *')) fail(`the preview was not asked of /jobs/preview: ${previews()}`)
{
  const z = jobsView(stub.state.jobsState).timezone
  if (!txt(editorOf()).includes(`Times are in the store's time zone: ${z.name} (UTC${z.offset})`)) {
    fail(`the editor does not name the store's time zone once: ${txt(editorOf()).slice(-120)}`)
  }
  if (txt(editorOf()).split("store's time zone").length !== 2) fail('the time zone is printed more than once')
}
if (!saveBtn()?.disabled) fail('Save is offered although nothing changed')
// Save is the panel's emphasised action on THEME tokens (primary ink on an accent tint, AA in shot.cjs), not
// the old accent-coloured text link that measured 4.22:1 on the drawer.
if (!saveBtn()?.classList.contains('wa-sched-save') || saveBtn()?.getAttribute('data-variant') !== 'outline') {
  fail(`Save schedule lost its emphasised theme-token shape: ${saveBtn()?.outerHTML.slice(0, 140)}`)
}
if (jobsCard.querySelectorAll('[title]').length) fail('the schedule editor wrote a native title=')
// The preview line UPDATES with the model: a new time is a new expression, a new question, new runs.
await setField(field('.wa-sched-time'), '21:30')
await settle(400)
if (exprNow() !== '30 21 * * *' || humanNow() !== 'Every day at 21:30') {
  fail(`Daily 21:30 did not map to 30 21 * * *: ${humanNow()} / ${exprNow()}`)
}
if ((runsNow().match(/21:30/g) || []).length !== 3 || runsNow().includes('09:00')) {
  fail(`the preview did not follow the new time: ${runsNow()}`)
}
if (previews().at(-1) !== '30 21 * * *') fail(`the preview was not re-asked: ${previews().at(-1)}`)
const MODE_CASES = [
  ['Minutes', async () => {}, '*/15 * * * *', 'Every 15 minutes'],
  ['Minutes', async () => click(btn(field('.wa-sched-every'), '30 min'), 40), '*/30 * * * *', 'Every 30 minutes'],
  ['Hourly', async () => {}, '0 * * * *', 'Every hour, on the hour'],
  ['Hourly', async () => setField(field('.wa-sched-num'), '5'), '5 * * * *', 'Every hour at :05'],
  ['Daily', async () => setField(field('.wa-sched-time'), '09:00'), '0 9 * * *', 'Every day at 09:00'],
  ['Weekly', async () => {}, '0 9 * * 1', 'Mondays at 09:00'],
  ['Weekly', async () => { await click(dayBtn('Thu'), 40); await setField(field('.wa-sched-time'), '08:15') },
    '15 8 * * 1,4', 'Mondays and Thursdays at 08:15'],
  ['Weekly', async () => { for (const d of ['Tue', 'Wed', 'Fri']) await click(dayBtn(d), 30) },
    '15 8 * * 1-5', 'Weekdays at 08:15'],
  ['Monthly', async () => setField(field('.wa-sched-time'), '03:00'), '0 3 1 * *', 'Day 1 of every month at 03:00'],
  ['Monthly', async () => setField(field('.wa-sched-num'), '15'), '0 3 15 * *', 'Day 15 of every month at 03:00']
]
for (const [mode, act, want, human] of MODE_CASES) {
  if (modeNow() !== mode) await click(modeBtn(mode), 60)
  await act()
  await settle(400)
  if (modeNow() !== mode) fail(`the ${mode} mode is not selected`)
  if (exprNow() !== want) fail(`${mode} mapped to ${JSON.stringify(exprNow())}, expected ${want}`)
  if (humanNow() !== human) fail(`${want} reads as ${JSON.stringify(humanNow())}, expected ${human}`)
  const want3 = nextRuns(want)
  if (want3.length !== 3 || !runsNow().startsWith('Next runs') || previews().at(-1) !== want) {
    fail(`the preview did not follow ${want}: ${runsNow()} (asked ${previews().at(-1)})`)
  }
  if (want !== '0 9 * * *' && saveBtn()?.disabled) fail(`Save is disabled for a new valid schedule ${want}`)
}
// A weekly schedule with no day is no schedule: nothing to save and the editor says why.
await click(modeBtn('Weekly'), 60)
for (const d of ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']) {
  if (dayBtn(d)?.getAttribute('aria-pressed') === 'true') await click(dayBtn(d), 30)
}
await settle(400)
if (exprNow() || !saveBtn()?.disabled || !txt(editorOf()).includes('pick at least one day')) {
  fail(`a weekly schedule with no day can be saved: ${exprNow()}`)
}
await click(dayBtn('Sun'), 40)
await click(dayBtn('Sat'), 40)
await settle(400)
if (exprNow() !== '0 3 * * 0,6' || humanNow() !== 'Weekends at 03:00') fail(`weekends: ${humanNow()} / ${exprNow()}`)
await click(modeBtn('Monthly'), 40)
await setField(field('.wa-sched-num'), '31')
await settle(300)
if (!txt(editorOf()).includes('months without this day are skipped')) fail('day 31 does not warn about short months')
// CUSTOM keeps the old behaviour: the raw expression, starting from what the other modes had built.
await click(modeBtn('Custom'), 60)
if (field('.wa-sched-input')?.value !== '0 3 31 * *') {
  fail(`Custom did not start from the built expression: ${field('.wa-sched-input')?.value}`)
}
// A REFUSED expression: the preview says the store would refuse it, and Save goes to the backend, which
// refuses it — the existing mapped error card, the editor left open and the row untouched.
await setField(field('.wa-sched-input'), 'every blue moon')
await settle(400)
if (!editorOf().querySelector('.wa-sched-runs.wa-bad')
  || !runsNow().includes('the store would refuse this schedule') || !runsNow().includes('every blue moon')) {
  fail(`a refused expression is not shown as refused in the preview: ${runsNow()}`)
}
await click(saveBtn(), 160)
{
  const tried = postsTo('/jobs/act').filter(x => x.body?.action === 'schedule')
  if (tried.at(-1)?.body?.schedule !== 'every blue moon') fail('the refused schedule never reached the backend')
  const note = jobsCard.querySelector('.wa-jobs-note')
  if (!note || txt(note.querySelector('.wa-help-title')) !== 'Why this was refused'
    || !txt(note).includes('the store refused that schedule')) {
    fail(`the backend's refusal is not printed in the job note: ${txt(note)}`)
  }
  if (!editorOf()) fail('a refused save closed the editor')
  if (!txt(rowOf('Watch Dog')).includes('Every day at 09:00')) fail('a refused save moved the row')
}
// A preview the backend could not answer keeps its error instead of a spinner.
stub.state.previewThrows = true
await setField(field('.wa-sched-input'), '0 7 * * *')
await settle(400)
if (!runsNow().includes('backend unreachable')) fail(`a failed preview read lost its error: ${runsNow()}`)
stub.state.previewThrows = false
// SAVE: the one write path, the human sentence and the expression the store read back.
await click(modeBtn('Weekly'), 40)
for (const d of ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']) {
  const on = ['Mon', 'Thu'].includes(d)
  if ((dayBtn(d)?.getAttribute('aria-pressed') === 'true') !== on) await click(dayBtn(d), 30)
}
await setField(field('.wa-sched-time'), '08:15')
await settle(400)
await click(saveBtn(), 160)
const sched = postsTo('/jobs/act').filter(x => x.body?.action === 'schedule')
if (sched.at(-1)?.body?.schedule !== '15 8 * * 1,4') fail(`the reschedule sent the wrong expression: ${sched.at(-1)?.body?.schedule}`)
if (sched.at(-1)?.body?.role !== 'watchdog') fail(`the reschedule was sent for the wrong role: ${sched.at(-1)?.body?.role}`)
if (sched.length !== 2) fail(`the reschedule did not reach the backend once per Save: ${sched.length}`)
if (!txt(jobsCard).includes('schedule saved: Mondays and Thursdays at 08:15 (15 8 * * 1,4)')) {
  fail('the panel did not print the schedule the store read back')
}
if (editorOf()) fail('the editor stayed open after a successful save')
if (!txt(rowOf('Watch Dog')).includes('Mondays and Thursdays at 08:15')) fail('the row did not re-read the saved schedule')
// ROUND TRIP: every live expression (and each mode's shape) opens in its own mode, unchanged, with nothing
// to save; an expression with no visual form opens in Custom exactly as written and is never rewritten.
const ROUND_TRIP = [
  ['0 9 * * *', 'Daily'], ['30 21 * * *', 'Daily'], ['*/5 * * * *', 'Minutes'], ['*/30 * * * *', 'Minutes'],
  ['5 * * * *', 'Hourly'], ['15 8 * * 1,4', 'Weekly'], ['30 21 * * 1-5', 'Weekly'], ['0 3 1 * *', 'Monthly'],
  ['0 9,17 * * *', 'Custom'], ['*/7 * * * *', 'Custom'], ['0 9 * 1 *', 'Custom'], ['15 10 1-7 * 1', 'Custom'],
  ['0 9 * * MON', 'Custom'], ['every 2h', 'Custom'], ['0 9 * * 7', 'Weekly'], ['00 09 * * *', 'Daily']
]
for (const [expr, mode] of ROUND_TRIP) {
  stub.state.jobsState.watchdog.schedule = expr
  if (editorOf()) await click(btn(editorOf(), 'Cancel'), 40)
  await click(refreshButton(p.host), 120)
  await openEditor('Watch Dog')
  if (modeNow() !== mode) fail(`${expr} opened in ${modeNow() || 'no mode'}, expected ${mode}`)
  const shown = mode === 'Custom' ? field('.wa-sched-input')?.value : exprNow()
  if (shown !== expr || exprNow() !== expr) fail(`${expr} was rewritten on open: ${shown} / ${exprNow()}`)
  if (!saveBtn()?.disabled) fail(`${expr}: Save is offered although nothing changed`)
  if (mode === 'Custom' && !txt(editorOf()).includes('opens as written and is kept')) {
    fail(`${expr}: an unrepresentable schedule does not say it is kept as written`)
  }
  if (mode === 'Custom' && !txt(rowOf('Watch Dog')).includes('Custom schedule')) {
    fail(`${expr}: the row gives an unrepresentable schedule a sentence it does not mean`)
  }
}
if (postsTo('/jobs/act').filter(x => x.body?.action === 'schedule').length !== 2) {
  fail('opening the editor wrote a schedule — a round trip must never save')
}
await click(btn(editorOf(), 'Cancel'), 40)
stub.state.jobsState.watchdog.schedule = '0 9 * * *'
await click(refreshButton(p.host), 120)

// A FAILED action: the mapped sentence must be printed, the checker's own wording kept beside it, and
// the row must NOT flip (a latency-free failure that still moved the row would read as success).
stub.state.jobFailure = { reason: 'klas\u00f6r yok', reason_source: 'checker' }
await clickJobButton(jobRow('Wiki Ingest Watch'), 'Resume job', 120)
if (!txt(jobsCard).includes('top-level folder not found')) {
  fail('the mapped failure sentence is not printed')
}
if (!txt(jobsCard).includes('klas\u00f6r yok')) {
  fail('the checker wording is not kept beside the mapped sentence')
}
if (!txt(jobRow('Wiki Ingest Watch')).includes('Resume job')) {
  fail('a failed action still moved the row')
}
// The result wears the SAME card as every other note (heading · one sentence · the raw wording under
// its caption) instead of a bare line: the job card and the root card must not diverge.
const jobNote = jobsCard.querySelector('.wa-help')
if (!jobNote) fail('a job action result is not rendered as a help card')
else if (txt(jobNote.querySelector('.wa-help-title')) !== 'Why this was refused') {
  fail(`a refused job action has the wrong heading: ${txt(jobNote.querySelector('.wa-help-title'))}`)
} else if (jobNote.querySelector('.wa-raw')?.getAttribute('data-tip') !== 'klas\u00f6r yok') {
  fail('the raw job-action wording is not a tooltip label')
}
stub.state.jobFailure = null

// ===========================================================================
// 4c) The review desk (Your review station): ONE draft at a time; the first document opens read-only;
//     Approve is two-step (the first call only arms), Reject needs a reason, the script's own output
//     is kept beside the English sentence, and an empty or failed read has its own surface.
// ===========================================================================
const folio = await mount('en', { tab: 'Folio', openConfig: false })
let candCard = folioDesk(folio.host)
if (!candCard) fail('the review desk (Your review station detail) is missing')
for (const title of ['Source review', 'Automation map']) {
  if ([...folio.host.querySelectorAll('h1')].some(h => txt(h).trim() === title)) fail(`the per-view title "${title}" is back`)
}
if (folio.host.querySelectorAll('.wa-metro-detail').length !== 1 || folio.host.querySelector('.pa-log, .wa-hb-row, #wa-sec-jobs')) {
  fail('the review desk rendered another detail\'s content')
}
if (txt(candCard).includes('wiki sources the session harvest drafted — nothing enters the wiki until you approve it')) {
  fail('the redundant candidates paragraph remains')
}
// ONE DRAFT AT A TIME: kind chip, `1 of N`, title, one-sentence summary, `Will be saved as <path>`,
// Approve / Reject / Later. The 2.3.x index list (one row per candidate) is gone.
if (candCard?.querySelectorAll('.wa-pend, .fl-item').length) fail('the 2.3.x Folio index list is back (the desk shows one draft at a time)')
if (draftCount(candCard) !== 3 || deskPosition(candCard).at !== 1) fail(`the desk is not on 1 of 3: ${JSON.stringify(deskPosition(candCard))}`)
{
  const first = candidates()[0]
  const kind = { new: 'New page', update: 'Update', retire: 'Retire' }[first.kind]
  must(txt(candCard), [kind, first.summary, 'Will be saved as', first.target, 'Approve', 'Reject', 'Later'], 'the first draft on the desk')
  const disclosure = [...(candCard?.querySelectorAll('details') || [])]
    .find(d => /Show the change and the evidence/.test(txt(d.querySelector(':scope > summary'))))
  if (!disclosure) fail('the desk lost `Show the change and the evidence` (the CandidateDetail disclosure)')
  else if (disclosure.open) fail('`Show the change and the evidence` is open by default')
  else await click(disclosure.querySelector(':scope > summary'), 0)
}
const defaultCandidate = candidates()[0]
const defaultReads = stub.calls.gets.filter(path => path.startsWith('/candidates/show'))
const defaultPath = `/candidates/show?ref=${encodeURIComponent(defaultCandidate.ref)}`
if (defaultReads.length !== 1 || defaultReads[0] !== defaultPath) {
  fail(`opening the review desk must read exactly the first candidate detail once: ${JSON.stringify(defaultReads)}`)
}
if (deskRef(candCard) !== defaultCandidate.ref) {
  fail(`opening the desk did not show the first draft: ${deskRef(candCard)}`)
}
const candDetail = () => candCard
if (candCard?.querySelectorAll('.wa-pend-detail').length > 1
  || !matchingDocument(candDetail(), candidateDetail(defaultCandidate.ref))
  || !faithfulProposal(candDetail(), candidateDetail(defaultCandidate.ref))) {
  fail('opening Folio did not display the first candidate document matching its requested ref')
}
const candPosts = () => stub.calls.posts.filter(x => ['/candidates/act', '/owner/decision'].includes(x.path))
if (candPosts().length || stub.calls.posts.length) fail('opening the review desk called a candidate action or posted a write')
must(txt(candDetail()), ['Proposed change', 'Reason & evidence',
  'Format', 'Passes the house format', 'Evidence', 'ev-0928-rules', 'a new file', 'Approve', 'Reject'],
  'candidate detail')
const proposal = candDetail()?.querySelector('.fl-proposal')
if (proposal?.getAttribute('aria-label') !== 'Diff against the current source'
  || proposal?.getAttribute('tabindex') !== '0') fail('the readable proposal lost its named, keyboard-focusable diff surface')
if (!candDetail()?.querySelector('.fl-original pre.wa-mono[data-slot="panel-block"]')) {
  fail('the original diff is not retained in a code body (PanelBlock)')
}
const original = candDetail()?.querySelector('details.fl-original')
if (!original || original.open || txt(original.querySelector('summary')) !== 'As written') {
  fail('the original diff must start behind a closed, named native disclosure')
}
// jsdom textContent includes closed details: opening the actual summary, not CSS, proves access.
const postsBeforeDisclosure = stub.calls.posts.length
await click(original?.querySelector('summary'), 0)
const originalCopy = original?.querySelector('[data-copy]')
const defaultDiff = candidateDetail(defaultCandidate.ref).diff.join('\n')
if (!original?.open || rawDiff(candDetail()) !== defaultDiff
  || originalCopy?.getAttribute('data-copy') !== defaultDiff
  || !originalCopy?.getAttribute('aria-label') || originalCopy?.disabled
  || original?.querySelector('.wa-raw')?.getAttribute('data-tip') !== defaultDiff) {
  fail('opening the original disclosure did not expose the exact original diff and labelled Copy payload')
}
await click(originalCopy, 0)
await click(original?.querySelector('summary'), 0)
if (original?.open || stub.calls.posts.length !== postsBeforeDisclosure) fail('original diff disclosure or Copy posted a write or failed to close')
if (deskRef(candCard) !== defaultCandidate.ref) fail('the disclosure round trip moved the desk off its draft')
must(txt(candDetail()), ['approval required', 'raw/sources', 'model credits', 'decided in the 28.09 session'],
  'candidate approval gate and decision context')
const readsBeforeReason = stub.calls.gets.length
const postsBeforeReason = stub.calls.posts.length
await click(btn(candDetail()?.querySelector('.fl-views'), 'Reason & evidence'), 0)
if (candDetail()?.querySelector('.fl-proposal') || !candDetail()?.querySelector('.fl-reason')
  || txt(candDetail()?.querySelector('.fl-views [aria-pressed="true"]')) !== 'Reason & evidence'
  || candDetail()?.querySelector('.fl-reason p')?.textContent !== candidateDetail(defaultCandidate.ref).candidate.why
  || candDetail()?.querySelector('.fl-reason p.wa-mono')?.textContent !== 'ev-0928-rules'
  || candDetail()?.dataset.candidateRef !== defaultCandidate.ref) {
  fail('Reason & evidence did not expose the selected response\'s exact explanation and evidence read-only')
}
await click(btn(candDetail()?.querySelector('.fl-views'), 'Proposed change'), 0)
if (txt(candDetail()?.querySelector('.fl-views [aria-pressed="true"]')) !== 'Proposed change'
  || !matchingDocument(candDetail(), candidateDetail(defaultCandidate.ref))
  || !faithfulProposal(candDetail(), candidateDetail(defaultCandidate.ref))
  || candDetail()?.querySelector('details.fl-original')?.open
  || stub.calls.gets.length !== readsBeforeReason || stub.calls.posts.length !== postsBeforeReason) {
  fail('the reason/proposal round trip lost the document or issued a read or write')
}
// APPROVE, TWO-STEP: the first click asks the backend, which only arms; nothing is written until the
// confirmation is accepted, and the confirmation says it writes raw/sources and costs model usage.
await click(btn(candDetail(), 'Approve'), 120)
const candArmed = () => candCard.querySelector('[data-slot="confirm-dialog"]')
if (!candArmed()) fail('Approve did not open a confirmation — one click must not write into the wiki')
if (candPosts().length !== 1 || candPosts()[0].body?.confirm !== false
  || candPosts()[0].path !== '/owner/decision'
  || candPosts()[0].body?.review_digest !== candidateDetail(defaultCandidate.ref).review_digest) {
  fail(`the first Approve was not an unconfirmed request: ${JSON.stringify(candPosts().map(x => x.body))}`)
}
must(txt(candArmed()), ['raw/sources', 'ingest', 'model usage'], 'approve confirmation')
await click(btn(candArmed(), 'Cancel'), 60)
if (candArmed()) fail('Cancel did not close the approve confirmation')
if (candPosts().length !== 1) fail('Cancel reached the backend')
if (draftCount(candCard) !== 3) fail('a cancelled approve removed the draft')
await click(btn(candDetail(), 'Approve'), 120)
stub.state.candAct = () => ({ ok: false, retryable: true,
  reason: 'Owner operation timed out; retry the same confirmation to inspect or finish that operation.' })
await click(candArmed().querySelector('[data-slot="confirm-confirm"]'), 160)
if (!candArmed()) fail('a timed-out owner operation discarded its exact request instead of allowing a same-operation retry')
const timedOutBody = candPosts().at(-1).body
stub.state.candAct = () => { throw new Error('Synthetic connection loss after dispatch') }
await click(candArmed().querySelector('[data-slot="confirm-confirm"]'), 160)
if (!candArmed()) throw new Error('connection loss discarded the already-dispatched owner request')
stub.state.candAct = null
await click(candArmed().querySelector('[data-slot="confirm-confirm"]'), 160)
const confirmed = candPosts().filter(x => x.body?.confirm === true)
if (confirmed.length !== 3 || confirmed.some(x => JSON.stringify(x.body) !== JSON.stringify(timedOutBody))
  || confirmed[0].path !== '/owner/decision' || !confirmed[0].body?.request_id
  || confirmed[0].body?.review_digest !== candidateDetail(defaultCandidate.ref).review_digest
  || confirmed[0].body?.ref !== '20260928-213958/team-glossary') {
  fail(`the confirmed approve did not reach the backend once: ${JSON.stringify(confirmed.map(x => x.body))}`)
}
if (!txt(candCard).includes('candidate approved')) fail('the approve did not report back')
if (!txt(candCard).includes('OK new 2026-09-28-team-glossary.md applied')) {
  fail('the engine output of the approve is not kept')
}
if (draftCount(candCard) !== 2) fail(`the approved draft is still counted: ${draftCount(candCard)}`)
// REJECT NEEDS A REASON: the send button stays disabled on an empty field, the reason travels.
candCard = await reopenDesk(folio.host)
await gotoDraft(candCard, candidates()[1].ref)
// House-format problems disable approval locally; even a dispatched click cannot call the action API.
const invalidApprove = btn(candDetail(), 'Approve')
if (!invalidApprove?.disabled) fail('a candidate with format problems can be approved')
const postsBeforeInvalid = candPosts().length
await click(invalidApprove, 40)
if (candPosts().length !== postsBeforeInvalid) fail('format-blocked approval called /candidates/act')
await click(btn(candDetail(), 'Reject'), 60)
const whyField = candDetail()?.querySelector('input')
if (!whyField) fail('Reject did not open a reason field')
const sendReject = () => btn(candDetail(), 'Reject candidate')
if (!sendReject()?.disabled) fail('a reject can be sent with no reason')
await setField(whyField, 'duplicate of the structure page')
if (sendReject()?.disabled) fail('a reject with a reason cannot be sent')
must(txt(candDetail()), ['contains [[wikilinks]]', 'replaces the current file'], 'update candidate detail')
await click(sendReject(), 160)
const rejects = candPosts().filter(x => x.body?.action === 'reject')
if (rejects.length !== 1 || rejects[0].body?.reason !== 'duplicate of the structure page') {
  fail(`the reject did not carry its reason: ${JSON.stringify(rejects.map(x => x.body))}`)
}
if (typeof rejects[0].body?.review_digest !== 'string' || 'unreviewable' in rejects[0].body) {
  fail('a reviewed reject did not carry its displayed digest')
}
if (!txt(candCard).includes('candidate rejected')) fail('the reject did not report back')
if (draftCount(candCard) !== 1) fail('the rejected draft is still counted')
// A REFUSAL keeps the script's own text in the raw block beside the English sentence.
stub.state.candRefuse = true
candCard = await reopenDesk(folio.host)
await click(btn(candDetail(), 'Approve'), 120)
if (!txt(candCard).includes('the engine refused to approve this candidate')) {
  fail('an engine refusal is not printed')
}
const refusedRaw = candCard.querySelector('.wa-live .wa-raw')
if (!refusedRaw || !txt(refusedRaw).includes('!! refused: format: contains [[wikilinks]]')) {
  fail('an engine refusal dropped the script output')
}
if (candArmed()) fail('a refused approve still armed the confirmation')
stub.state.candRefuse = false
await settle(80)
// AN UNREVIEWABLE CANDIDATE (the engine refuses its review) can still leave the queue: approval
// stays off, the reject carries its reason and says there is no displayed digest.
stub.state.candShowError = 'the candidates could not be read: exit 1: !! refused: Required target base hash is missing, malformed or stale'
candCard = await reopenDesk(folio.host)
if (!btn(candDetail(), 'Approve')?.disabled) fail('an unreviewable candidate can be approved')
await click(btn(candDetail(), 'Reject'), 60)
const staleWhy = candDetail()?.querySelector('input')
if (!staleWhy) fail('an unreviewable candidate cannot be rejected')
await setField(staleWhy, 'stale legacy draft')
const rejectsBeforeStale = candPosts().length
await click(sendReject(), 160)
const staleRejects = candPosts().slice(rejectsBeforeStale)
if (staleRejects.length !== 1 || staleRejects[0].body?.unreviewable !== true
  || 'review_digest' in staleRejects[0].body || staleRejects[0].body?.reason !== 'stale legacy draft') {
  fail(`an unreviewable reject was not sent as one: ${JSON.stringify(staleRejects.map(x => x.body))}`)
}
if (draftCount(candCard) !== 0 || btn(candCard, 'Approve')) fail('the rejected unreviewable draft is still on the desk')
stub.state.candShowError = null
await settle(80)
if (folio.errors.size) fail(`the review desk threw: ${[...folio.errors].join(' | ')}`)
await act(async () => folio.unmount())
stub.state.recoverable = [{ request_id: 'a'.repeat(64), ref: 'run/interrupted', kind: 'update', target: 'approved-only.md', state: 'applying' }]
const recoveryFrame = await mount('en', { tab: 'Folio', openConfig: false })
const recoveryCard = () => document.querySelector('[data-recovery-list]')
if (!recoveryCard()) throw new Error('Review has no server-owned interrupted-approval list')
must(txt(recoveryCard()), ['Interrupted approvals', 'run/interrupted', 'approved-only.md'], 'recovery list')
const countRecoveryPosts = () => stub.calls.posts.filter(x => x.path === '/owner/recover')
if (countRecoveryPosts().length) throw new Error('Recovery auto-applied on mount')
stub.state.recoverAct = () => ({ ok: false, reason: 'Conflicting newer content was preserved' })
await click(btn(recoveryCard(), 'Resume'), 160)
if (!txt(recoveryCard()).includes('Conflicting newer content') || !btn(recoveryCard(), 'Resume')) throw new Error('Recovery refusal hid the error or removed retry')
stub.state.recoverAct = null
await click(btn(recoveryCard(), 'Resume'), 160)
const recoveryPosts = countRecoveryPosts()
if (recoveryPosts.length !== 2 || recoveryPosts.some(x => JSON.stringify(x.body) !== JSON.stringify({ request_id: 'a'.repeat(64) }))) throw new Error('Recovery changed the approved identity or sent client owner/content claims')
if (txt(recoveryCard()).includes('run/interrupted')) throw new Error('Completed operation stayed in unfinished list')
await act(async () => recoveryFrame.unmount())

// OWNER SETUP: while no owner is bound, Review shows what turning it on changes instead of a 403,
// never asks for interrupted approvals, and sends only the shown plan digest after a second click.
stub.state.recoverable = []
await settle(120)
stub.state.ownerSetup = { ok: true, active: false, ready: false, code_changed: false, owner: 'local_owner',
  job: { id: 'job-h', name: 'Wiki Session Harvest', schedule: '30 21 * * *' }, plan_digest: 'e'.repeat(64) }
const setupFrame = await mount('en', { tab: 'Folio', openConfig: false })
const setupCard = () => document.querySelector('[data-owner-setup]')
if (setupCard()?.getAttribute('data-owner-setup') !== 'off') throw new Error('Review hid that owner approval is off')
must(txt(setupCard()), ['Owner approval is off', 'this computer\'s Hermes session', 'Wiki Session Harvest (30 21 * * *)',
  'wiki drafting tools only', 'one restart'], 'owner setup card')
if (document.querySelector('[data-recovery-list]')) throw new Error('An unbound owner still shows an interrupted-approvals error')
if (!stub.calls.gets.includes('/owner/activation') || stub.calls.gets.includes('/owner/recoverable')) {
  throw new Error('Review asked for interrupted approvals before an owner was bound')
}
const setupPosts = () => stub.calls.posts.filter(x => x.path === '/owner/activation')
await click(btn(setupCard(), 'Turn on owner approval'), 60)
if (setupPosts().length) throw new Error('Owner setup was applied by the first click')
await click(btn(setupCard(), 'Cancel'), 60)
if (btn(setupCard(), 'Confirm and turn on')) throw new Error('Cancel left the owner setup armed')
await click(btn(setupCard(), 'Turn on owner approval'), 60)
await click(btn(setupCard(), 'Confirm and turn on'), 200)
if (setupPosts().length !== 1 || JSON.stringify(setupPosts()[0].body) !== JSON.stringify({ confirm: true, plan_digest: 'e'.repeat(64) })) {
  throw new Error(`Owner setup sent more than the shown plan: ${JSON.stringify(setupPosts().map(x => x.body))}`)
}
must(txt(setupCard()), ['Restart the background service to finish', 'Owner approval is on', 'A task running right now is stopped'],
  'owner setup restart state')
if (document.querySelector('[data-recovery-list]') || stub.calls.gets.includes('/owner/recoverable')) {
  throw new Error('Review asked for interrupted approvals before the runtime was ready')
}
await click(btn(setupCard(), 'Restart background service'), 60)
if (stub.host.restartCalls !== 0) throw new Error('The background service restarted on the first click')
await click(btn(setupCard(), 'Cancel'), 60)
if (btn(setupCard(), 'Restart now')) throw new Error('Cancel left the restart armed')
await click(btn(setupCard(), 'Restart background service'), 60)
stub.host.onRestart = () => { stub.state.ownerSetup = { ...stub.state.ownerSetup, ready: true }; return { ok: true, pid: 1, name: 'gateway-restart' } }
await click(btn(setupCard(), 'Restart now'), 200)
if (stub.host.restartCalls !== 1) throw new Error(`Restart now sent ${stub.host.restartCalls} restarts`)
await settle(5600)
must(txt(setupCard()), ['Owner approval is ready.'], 'owner setup after the service restarted')
stub.host.onRestart = null
await act(async () => setupFrame.unmount())
stub.state.ownerSetup = { ...stub.state.ownerSetup, active: false, code_changed: true }
stub.state.ownerActivate = () => ({ ok: false, reason: 'Engine settings belong to another profile' })
const changedFrame = await mount('en', { tab: 'Folio', openConfig: false })
must(txt(setupCard()), ['Wiki Automation was updated'], 'owner setup after a plugin update')
await click(btn(setupCard(), 'Turn on owner approval'), 60)
await click(btn(setupCard(), 'Confirm and turn on'), 200)
must(txt(setupCard()), ['Engine settings belong to another profile', 'Turn on owner approval'], 'refused owner setup keeps retry')
await act(async () => changedFrame.unmount())
stub.state.ownerSetup = null
stub.state.ownerActivate = null

// Mixed changes and whitespace are response fixtures, never mutations of the production source.
const projectionCandidates = candidates()
const richText = `  Literal **markdown**, [[link]], <script>not executable</script> & Ω\t${'evidence '.repeat(90)}  `
const projectionPayloads = projectionCandidates.map(candidate => candidateDetail(candidate.ref))
projectionPayloads[0].diff = [
  `--- current/${projectionCandidates[0].target}`, `+++ candidate/${projectionCandidates[0].target}`,
  '@@ -1,3 +1,8 @@', '-# Removed title', ' # Actual context title', '+# Later added title',
  '+## Decisions', '-old decision', ' unchanged decision', `+${richText}`, '+',
  '+###### Sixth-level heading', '+####### Not a heading', '\\ No newline at end of file',
  '+++counter', '---- separator', '+<img src="missing" onerror="globalThis.projectionExecuted = true">',
  '+<script>globalThis.projectionExecuted = true</script>', '+++ body header literal', '--- body separator',
  '@@ literal, not a hunk', '@@ -7 +9 @@ trailing section heading', ' '
]
projectionPayloads[1].diff = ['--- current/fallback.md', '+++ candidate/fallback.md', '@@ -1 +1 @@',
  '-# Removed title only', '+Fallback paragraph without an H1']
projectionPayloads[2].diff = ['--- current/retired.md', '+++ candidate/retired.md', '@@ -0,0 +1 @@',
  `+# ${projectionCandidates[2].summary}`]
const projected = await mount('en', { tab: 'Folio', openConfig: false, candidates: projectionCandidates,
  candShow: ref => projectionPayloads.find(payload => payload.ref === ref) })
const projectedDesk = () => folioDesk(projected.host)
const projectedDetail = () => projectedDesk()?.querySelector('#wa-review-document') || projectedDesk()
const explicitRows = [
  ['removed', '-', true, 'Removed title'], ['context', '·', true, 'Actual context title'],
  ['added', '+', true, 'Later added title'], ['added', '+', true, 'Decisions'],
  ['removed', '-', false, 'old decision'], ['context', '·', false, 'unchanged decision'],
  ['added', '+', false, richText], ['added', '+', false, '\u00a0'],
  ['added', '+', true, 'Sixth-level heading'], ['added', '+', false, '####### Not a heading'],
  ['context', '·', false, '\\ No newline at end of file'],
  ['added', '+', false, '++counter'], ['removed', '-', false, '--- separator'],
  ['added', '+', false, '<img src="missing" onerror="globalThis.projectionExecuted = true">'],
  ['added', '+', false, '<script>globalThis.projectionExecuted = true</script>'],
  ['added', '+', false, '++ body header literal'], ['removed', '-', false, '-- body separator'],
  ['context', '·', false, '@@ literal, not a hunk'], ['context', '·', false, '\u00a0']
].map(([change, sign, heading, text]) => ({ change, sign, hiddenSign: null, heading, text }))
if (JSON.stringify(proposalRows(projectedDetail())) !== JSON.stringify(explicitRows)
  || projectedDetail()?.querySelector('.fl-document-head h2')?.textContent !== 'Actual context title'
  || projectedDetail()?.querySelector('script, img')) {
  fail('readable proposal changed signs, line order, heading levels, literal text, whitespace or blank lines')
}
// jsdom can check typography and structure, not pixel clipping or native closed-details visibility.
for (const text of projectedDetail()?.querySelectorAll('.fl-line-text, .fl-line-heading') || []) {
  const style = dom.window.getComputedStyle(text)
  const leading = dom.window.getComputedStyle(text.closest('.fl-line')).lineHeight
  if (parseFloat(style.fontSize) < 13 || !Number.isFinite(parseFloat(style.fontSize))
    || parseFloat(leading) < 1.6 || !Number.isFinite(parseFloat(leading))
    || text.closest('pre, .wa-mono')
    || text.classList.contains('fl-line-text') && style.whiteSpace !== 'pre-wrap') {
    fail('the readable proposal lost its prose type size, line spacing or whitespace-preserving text')
  }
}
for (const [index, payload] of projectionPayloads.entries()) {
  if (index) await gotoDraft(projectedDesk(), payload.ref)
  if (!matchingDocument(projectedDetail(), payload) || !faithfulProposal(projectedDetail(), payload)) {
    fail(`projection ${payload.ref}: title, summary, destination, raw diff or readable changes differ from the response`)
  }
  const disclosure = projectedDetail()?.querySelector('details.fl-original')
  if (!disclosure || disclosure.open) fail(`projection ${payload.ref}: original diff did not start closed`)
  await click(disclosure?.querySelector('summary'), 0)
  const copy = disclosure?.querySelector('[data-copy]')
  if (!disclosure?.open || rawDiff(projectedDetail()) !== payload.diff.join('\n')
    || copy?.getAttribute('data-copy') !== payload.diff.join('\n') || !copy?.getAttribute('aria-label')
    || copy?.disabled || disclosure?.querySelector('.wa-raw')?.getAttribute('data-tip') !== payload.diff.join('\n')) {
    fail(`projection ${payload.ref}: disclosed original/Copy was truncated or rewritten`)
  }
  await click(copy, 0)
  await click(disclosure?.querySelector('summary'), 0)
  if (disclosure?.open) fail(`projection ${payload.ref}: original disclosure did not close`)
}
if (stub.calls.posts.length) fail('readable projection, disclosure, Copy or candidate selection posted a write')
if (projected.errors.size) fail(`readable projection threw: ${[...projected.errors].join(' | ')}`)
await act(async () => projected.unmount())

// Actual out-of-order detail responses: the final row owns the document AND its action ref.
const deferred = () => {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}
// Keep both racing documents format-valid so the action-ref lock still exercises real approval.
// The invalid update remains covered by the format and decision-switch tests, without altering its detail.
const [raceFirst, raceInvalid, raceFinal] = candidates()
const raceCandidates = [raceFirst, raceFinal, raceInvalid]
const firstRef = raceCandidates[0].ref
const finalRef = raceCandidates[1].ref
// Distinct actual headings expose stale title regressions as well as wrong-ref documents.
const racePayload = ref => {
  const payload = candidateDetail(ref)
  return { ...payload, diff: payload.diff.map(line => line === '+# Team glossary'
    ? `+# ${ref === firstRef ? 'First rules draft' : 'Final intake retirement'}` : line) }
}
const firstRead = deferred()
const finalRead = deferred()
const detailReads = []
const race = await mount('en', { tab: 'Folio', openConfig: false, candidates: raceCandidates, candShow: ref => {
  detailReads.push(ref)
  return ref === firstRef ? firstRead.promise : finalRead.promise
} })
const raceDesk = () => folioDesk(race.host)
const raceDetail = () => raceDesk()
if (detailReads.length !== 1 || detailReads[0] !== firstRef
  || stub.calls.gets.filter(path => path.startsWith('/candidates/show')).join('|')
    !== `/candidates/show?ref=${encodeURIComponent(firstRef)}`) {
  fail('opening the race desk did not issue exactly one read-only detail request for the first candidate')
}
if (deskPosition(raceDesk()).at !== 1 || draftCount(raceDesk()) !== 3) {
  fail(`the pending default detail is not draft 1 of 3: ${JSON.stringify(deskPosition(raceDesk()))}`)
}
if (stub.calls.posts.length) fail('opening the race desk posted an action or write')
await click(btn(raceDesk(), 'Later'), 0)
if (detailReads.join('|') !== `${firstRef}|${finalRef}`) fail('the default draft and one Later did not issue exactly two independent detail requests')
if (deskPosition(raceDesk()).at !== 2) {
  fail('Later did not move the desk to the second draft while the first read was pending')
}
if (btn(raceDetail(), 'Approve') && !btn(raceDetail(), 'Approve').disabled) fail('the desk offers approval while the shown draft is unresolved')
if (deskRef(raceDetail()) || raceDetail()?.querySelector('.fl-document-head, .fl-proposal')) {
  fail('an unresolved detail claimed a matching ref or retained a previous document')
}
const pendingPosts = stub.calls.posts.length
if (btn(raceDetail(), 'Approve')) await click(btn(raceDetail(), 'Approve'), 0)
if (stub.calls.posts.length !== pendingPosts) fail('an unresolved selected document posted an approval')
await act(async () => { finalRead.resolve(racePayload(finalRef)); await finalRead.promise })
await settle(0)
must(txt(raceDetail()), [raceCandidates[1].target, `+++ candidate/${raceCandidates[1].target}`], 'final selected candidate detail')
if (deskRef(raceDesk()) !== finalRef
  || !matchingDocument(raceDetail(), racePayload(finalRef))
  || !faithfulProposal(raceDetail(), racePayload(finalRef))) {
  fail('the second detail response did not display the selected second candidate document')
}
await act(async () => { firstRead.resolve(racePayload(firstRef)); await firstRead.promise })
await settle(0)
if (deskRef(raceDesk()) !== finalRef
  || !matchingDocument(raceDetail(), racePayload(finalRef))
  || !faithfulProposal(raceDetail(), racePayload(finalRef))
  || txt(raceDetail()).includes(`+++ candidate/${raceCandidates[0].target}`)) {
  fail('a late detail response replaced the final selected candidate document')
}
if (detailReads.join('|') !== `${firstRef}|${finalRef}` || stub.calls.posts.length) {
  fail('resolving the selection race issued an extra detail read or posted an action or write')
}
await click(btn(raceDetail(), 'Approve'), 80)
const racePosts = () => stub.calls.posts.filter(call => ['/candidates/act', '/owner/decision'].includes(call.path))
if (racePosts().length !== 1 || racePosts()[0].body?.ref !== finalRef || racePosts()[0].body?.confirm !== false) {
  fail(`approval after a detail race targeted the wrong candidate: ${JSON.stringify(racePosts())}`)
}
await click(btn(raceDesk().querySelector('[data-slot="confirm-dialog"]'), 'Cancel'), 40)

// A candidate disappears while its dry-run is in flight: the delayed reply cannot arm a write.
const staleApproval = deferred()
stub.state.candAct = () => staleApproval.promise
await click(btn(raceDetail(), 'Approve'), 0)
const beforeDisappearance = racePosts().length
if (beforeDisappearance !== 2) fail('the disappearance test did not start an approval dry-run')
stub.state.candList = []
await click(refreshButton(race.host) || (refreshButton(race.host) || btn(race.host, 'Refresh')), 80)
if (deskRef(raceDesk()) || btn(raceDesk(), 'Approve')) fail('a disappeared shown draft kept its document or approval')
await act(async () => {
  staleApproval.resolve({ ok: false, ref: finalRef, action: 'approve', needs_confirm: true, request_id: 'valid-late-owner-fixture', review_digest: 'a'.repeat(64),
    reason: 'approval writes raw/sources and costs model usage', output: '[dry-run] stale candidate' })
  await staleApproval.promise
})
await settle(0)
if (raceDesk()?.querySelector('[data-slot="confirm-dialog"]') || btn(raceDesk(), 'Approve')) {
  fail('a disappeared candidate can still arm or confirm approval')
}
if (racePosts().length !== beforeDisappearance || racePosts().some(call => call.body?.confirm === true)) {
  fail('a disappeared candidate posted a confirmed approval')
}
stub.state.candAct = null
stub.state.candShow = null
if (race.errors.size) fail(`candidate race/disappearance threw: ${[...race.errors].join(' | ')}`)
await act(async () => race.unmount())

// Retain the real kit confirm action, not a detached DOM click (React no longer dispatches those).
// A dialog can retain its callback after Cancel or a same-ref queue refresh; only the CURRENT
// confirmation token may write, even when the refreshed document has the exact same candidate ref.
const retainConfirm = desk => {
  const button = desk.querySelector('[data-slot="confirm-confirm"]')
  const propsKey = button && Object.keys(button).find(key => key.startsWith('__reactProps$'))
  const callback = propsKey && button[propsKey]?.onClick
  if (typeof callback !== 'function') throw new Error('could not retain the rendered kit confirmation callback')
  return callback
}
// A refused read is shown as the backend's own sentence, not as the transport's wrapper and JSON.
{
  const ipc = await mount('en', { tab: 'Folio', openConfig: false, folioRest: path => {
    if (path === '/automation') return automation()
    if (path === '/candidates') return { ok: true, candidates: candidates() }
    throw new Error('Error invoking remote method \'hermes:api\': Error: 403: {"detail":"No explicit owner binding exists for this profile"}')
  } })
  await settle(0)
  const shown = txt(ipc.host.querySelector('[data-recovery-list]'))
  if (!shown.includes('No explicit owner binding exists for this profile (HTTP 403)')
    || /invoking remote method|\{"detail"/.test(shown)) {
    fail(`a refused read shows the raw transport error: ${shown.slice(0, 200)}`)
  }
}
{
  const v = await mount('en', { tab: 'Folio', openConfig: false, folioRest: path => {
    if (path === '/automation') return automation()
    if (path === '/candidates') return { ok: true, candidates: candidates() }
    throw new Error('422: {"detail":[{"loc":["body","request_id"],"msg":"field required","type":"missing"}]}\n')
  } })
  await settle(0)
  const said = txt(v.host.querySelector('[data-recovery-list]'))
  if (!said.includes('field required (HTTP 422)') || said.includes('{"detail"')) {
    fail(`a validation refusal shows raw JSON: ${said.slice(0, 160)}`)
  }
}
// LEAN: the line and the review desk carry only what the reader acts on; a refusal is one line, raw text on demand.
{
  const lean = await mount('en', { openConfig: false, engineStatus: engineStatus('existing_unverified'),
    jobs: { roles: [], orphans: [], ok: false, available: false, error: refusal, reason: refusal,
      mutation_available: false },
    runs: { ok: false, available: false, error: refusal, reason: refusal } })
  await settle(150)
  const said = txt(lean.host)
  for (const gone of ['See what connects', 'Configuration · not live flow', 'Reads conversation windows',
    'Read the proposal, its reason']) {
    if (said.includes(gone)) fail(`lean: Nexus still says "${gone}"`)
  }
  const banner = lean.host.querySelector('[data-engine-banner]')
  if (!/not taken over/i.test(txt(banner))) fail(`lean: an unverified engine has no takeover banner: "${txt(banner)}"`)
  const jumps = []
  const realJump = window.HTMLElement.prototype.scrollIntoView
  window.HTMLElement.prototype.scrollIntoView = function () {
    jumps.push({ id: this.id, open: Boolean(detailOf(lean.host, 'settings')) })
  }
  try { await click(banner?.querySelector('button'), 150) } finally {
    window.HTMLElement.prototype.scrollIntoView = realJump
  }
  if (!detailOf(lean.host, 'settings')?.querySelector('#wa-sec-install')) fail('lean: the takeover button does not open Settings at the engine card')
  if (opener(lean.host, 'settings')?.getAttribute('aria-pressed') !== 'true') fail('lean: Settings is open but not pressed after the takeover jump')
  if (!jumps.some(j => j.id === 'wa-sec-install' && j.open)) {
    fail(`lean: the takeover button scrolls before Settings is open: ${JSON.stringify(jumps)}`)
  }
  const fails = [...lean.host.querySelectorAll('.wa-fail')]
  if (fails.length < 1) fail(`lean: the refused job read is not a compact failure (${fails.length})`)
  for (const box of lean.host.querySelectorAll('.wa-fail .wa-raw')) {
    if (!box.closest('details')) fail('lean: a refused read prints its raw text in the open')
  }
  const planned = await mount('en', { openConfig: false, engineStatus: engineStatus('prepared') })
  await settle(150)
  if (!planned.host.querySelector('[data-engine-banner]')) fail('lean: a previewed but uninstalled engine has no banner')
  const kept = await mount('en', { openConfig: false, engineStatus: engineStatus('installed_with_existing_jobs') })
  await settle(150)
  if (kept.host.querySelector('[data-engine-banner]')) fail('lean: a taken-over engine still shows the takeover banner')
  stub.state.recoverable = []
  const folio = await mount('en', { tab: 'Folio', openConfig: false })
  await settle(200)
  if (txt(folio.host).includes('What is proposed. Why it belongs')) fail('lean: the review desk still carries the Folio subtitle')
  if (folio.host.querySelector('[data-recovery-list]')) fail('lean: an empty interrupted-approvals list still takes a box')
  const fcss = [...folio.host.ownerDocument.querySelectorAll('style')].map(x => x.textContent).join('\n')
  const h2 = /\.fl-document-head h2\{font-size:(\d+)px/.exec(fcss)
  if (!h2 || Number(h2[1]) > 18) fail(`lean: the proposal title is ${h2?.[1]}px`)
  if (/\.fl-item\{height:146px/.test(fcss)) fail('lean: queue items keep a fixed 146px height')
}
// SEC-3: retain the real callback across SDK switches and same-ref scope re-entry.
for (const [axis, changed] of [['profile', 'other'], ['connectionId', 'remote-b'], ['cwd', '/srv/other']]) {
  let contextRead = null
  const probe = await mount('en', { tab: 'Folio', openConfig: false, folioRest: path => {
    if (path === '/automation') return contextRead?.promise || automation()
    if (path === '/candidates') return { ok: true, candidates: candidates() }
    return { ok: true, operations: [] }
  } })
  await click(btn(folioDesk(probe.host), 'Approve'), 0)
  const retained = retainConfirm(folioDesk(probe.host))
  contextRead = deferred()
  const previous = stub.host.state[axis].get()
  await act(async () => {
    stub.host.state[axis].set(changed)
    await retained()
  })
  if (probe.host.querySelector('[data-slot="confirm-dialog"], .fl-item, .fl-proposal')) fail(`SEC-3 ${axis}: stale review remained before fresh context GET`)
  if (candPosts().length !== 1) fail(`SEC-3 ${axis}: retained confirmation crossed SDK scope`)
  await act(async () => { contextRead.resolve(automation()); await contextRead.promise })
  await settle(0)
  if (!probe.host.querySelector('.fl-proposal')) fail(`SEC-3 ${axis}: fresh context did not reload review`)
  await act(async () => { stub.host.state[axis].set(previous) })
  await settle(0)
  await click(btn(folioDesk(probe.host), 'Approve'), 0)
  const before = candPosts().length
  await act(async () => { await retained() })
  if (candPosts().length !== before || !probe.host.querySelector('[data-slot="confirm-dialog"]')) fail(`SEC-3 ${axis}: old confirmation rebound to same-ref re-entry`)
  await act(async () => probe.unmount())
}

// SEC-3: rejection carries the exact displayed digest; a refreshed review never rebinds a retained send.
const rejectionDigest = 'd'.repeat(64)
const rejectionScope = await mount('en', { tab: 'Folio', openConfig: false,
  candShow: ref => ({ ...candidateDetail(ref), review_digest: rejectionDigest }) })
await click(btn(folioDesk(rejectionScope.host), 'Reject'), 0)
await setField(folioDesk(rejectionScope.host)?.querySelector('input'), 'displayed decision')
const retainClick = button => {
  const key = button && Object.keys(button).find(key => key.startsWith('__reactProps$'))
  const callback = key && button[key]?.onClick
  if (typeof callback !== 'function') throw new Error('could not retain the real rendered click callback')
  return callback
}
const staleReject = retainClick(btn(folioDesk(rejectionScope.host), 'Reject candidate'))
await click((refreshButton(rejectionScope.host) || btn(rejectionScope.host, 'Refresh')), 0)
await act(async () => { await staleReject() })
if (candPosts().length) fail('SEC-3 rejection: retained send rebound after same-ref refresh')
await click(btn(folioDesk(rejectionScope.host), 'Reject'), 0)
await setField(folioDesk(rejectionScope.host)?.querySelector('input'), 'fresh displayed decision')
await click(btn(folioDesk(rejectionScope.host), 'Reject candidate'), 0)
const rejected = candPosts().at(-1)
if (rejected?.path !== '/candidates/act' || rejected.body.review_digest !== rejectionDigest
  || rejected.body.reason !== 'fresh displayed decision') fail('SEC-3 rejection: exact displayed review_digest was not sent')
await act(async () => rejectionScope.unmount())

// SEC-3: recovery must consult the current inventory, not its retained render's idle snapshot.
let recoveryContext = null
let recoveryRows = [{ request_id: 'b'.repeat(64), ref: 'run/approved', kind: 'new', target: 'approved.md', state: 'applying' }]
const recoveryScope = await mount('en', { tab: 'Folio', openConfig: false, folioRest: path => {
  if (path === '/automation') return recoveryContext?.promise || automation()
  if (path === '/candidates') return { ok: true, candidates: candidates() }
  return { ok: true, operations: [...recoveryRows] }
} })
const retainedResume = retainClick(btn(recoveryScope.host.querySelector('[data-recovery-list]'), 'Resume'))
recoveryContext = deferred()
await click((refreshButton(recoveryScope.host) || btn(recoveryScope.host, 'Refresh')), 0)
await act(async () => { await retainedResume() })
if (stub.calls.posts.length) fail('SEC-3 recovery: retained callback bypassed pending context read')
await act(async () => { recoveryContext.resolve(automation()); await recoveryContext.promise })
await settle(0)
await act(async () => { await retainedResume() })
if (stub.calls.posts.length) fail('SEC-3 recovery: old inventory callback rebound after refresh')
const currentResume = retainClick(btn(recoveryScope.host.querySelector('[data-recovery-list]'), 'Resume'))
stub.state.recoverAct = () => { recoveryRows = []; return { ok: true } }
await act(async () => { await currentResume() })
await settle(0)
await act(async () => { await currentResume() })
if (stub.calls.posts.length !== 1 || stub.calls.posts[0].body.request_id !== 'b'.repeat(64)) fail('SEC-3 recovery: fresh request was not single-use')
stub.state.recoverAct = null
await act(async () => recoveryScope.unmount())

// SEC-3: a successful HTTP read is not a verified project context.
for (const invalid of [
  { ...automation(), available: false },
  { ...automation(), settings: { ...automation().settings, project_root: '' } },
  { ...automation(), settings: { ...automation().settings, project: { ok: false, id: 'auto-id' } } },
  { ...automation(), settings: { ...automation().settings, project: { ok: true, id: '' } } }
]) {
  const probe = await mount('en', { tab: 'Folio', openConfig: false, folioRest: path => {
    if (path === '/automation') return invalid
    if (path === '/candidates') return { ok: true, candidates: candidates() }
    return { ok: true, operations: [{ request_id: '9'.repeat(64), ref: 'run/approved', target: 'approved.md', kind: 'new', state: 'applying' }] }
  } })
  // The line reads its candidate count before the station opens; recoverable belongs only to the desk.
  if (deskRef(folioDesk(probe.host)) || probe.host.querySelector('[data-recovery-list]')
    || stub.calls.gets.includes('/owner/recoverable')) {
    fail('SEC-3 project validation: unverifiable context admitted review or recovery ' + JSON.stringify({
      visible: Boolean(deskRef(folioDesk(probe.host)) || probe.host.querySelector('[data-recovery-list]')), gets: stub.calls.gets }))
  }
  await act(async () => probe.unmount())
}

// SEC-3: the request guard is synchronous; React's next render is not the security boundary.
{
  let contextRead = null
  const probe = await mount('en', { tab: 'Folio', openConfig: false, folioRest: path => {
    if (path === '/automation') return contextRead?.promise || automation()
    if (path === '/candidates') return { ok: true, candidates: candidates() }
    return { ok: true, operations: [{ request_id: '9'.repeat(64), ref: 'run/approved', target: 'approved.md', kind: 'new', state: 'applying' }] }
  } })
  await click(btn(folioDesk(probe.host), 'Approve'), 0)
  const confirm = retainConfirm(folioDesk(probe.host))
  const resume = retainClick(btn(probe.host.querySelector('[data-recovery-list]'), 'Resume'))
  const refresh = retainClick((refreshButton(probe.host) || btn(probe.host, 'Refresh')))
  contextRead = deferred()
  const before = stub.calls.posts.length
  await act(async () => { refresh(); await confirm(); await resume() })
  if (stub.calls.posts.length !== before) fail('SEC-3 synchronous guard: retained decision bypassed pending read before React render')
  await act(async () => { contextRead.resolve(automation()); await contextRead.promise })
  await act(async () => probe.unmount())
}

// SEC-3: retained rejection, selection and recovery callbacks cannot cross a scope or re-enter it.
for (const [axis, changed] of [['profile', 'reject-profile'], ['connectionId', 'reject-remote'], ['cwd', '/srv/reject-project']]) {
  const operation = { request_id: 'e'.repeat(64), ref: 'run/approved', kind: 'update', target: 'approved.md', state: 'applying' }
  const probe = await mount('en', { tab: 'Folio', openConfig: false, folioRest: path => {
    if (path === '/automation') return automation()
    if (path === '/candidates') return { ok: true, candidates: candidates() }
    return { ok: true, operations: [operation] }
  } })
  const oldSelect = retainClick(btn(folioDesk(probe.host), 'Later'))
  const oldResume = retainClick(btn(probe.host.querySelector('[data-recovery-list]'), 'Resume'))
  await click(btn(folioDesk(probe.host), 'Reject'), 0)
  await setField(folioDesk(probe.host)?.querySelector('input'), 'reason from old scope')
  const oldReject = retainClick(btn(folioDesk(probe.host), 'Reject candidate'))
  const previous = stub.host.state[axis].get()
  await act(async () => {
    stub.host.state[axis].set(changed)
    await oldReject(); await oldResume(); await oldSelect()
  })
  if (stub.calls.posts.length || folioDesk(probe.host)?.querySelector('input')) fail(`SEC-3 ${axis}: old rejection/recovery survived switch`)
  await act(async () => { stub.host.state[axis].set(previous) })
  const reads = stub.calls.gets.length
  await act(async () => { await oldReject(); await oldResume(); await oldSelect() })
  if (stub.calls.posts.length || stub.calls.gets.length !== reads) fail(`SEC-3 ${axis}: old action/selection callback rebound on re-entry`)
  await act(async () => probe.unmount())
}

// SEC-3: old deferred detail/decision/recovery replies must not publish state or refresh the new scope.
for (const kind of ['detail', 'prepare', 'approve', 'reject', 'recover']) {
  const oldResult = deferred()
  let oldScope = true
  const operation = { request_id: 'f'.repeat(64), ref: 'run/approved', target: 'approved.md', kind: 'new', state: 'applying' }
  const probe = await mount('en', { tab: 'Folio', openConfig: false,
    candShow: ref => oldScope && kind === 'detail' ? oldResult.promise : candidateDetail(ref),
    candAct: body => oldScope && (kind !== 'approve' || body.confirm) ? oldResult.promise
      : { ok: false, needs_confirm: true, request_id: 'current-scope-request', review_digest: candidateDetail(body.ref).review_digest },
    folioRest: path => path === '/automation' ? automation() : path === '/candidates'
      ? { ok: true, candidates: candidates() } : { ok: true, operations: [operation] } })
  if (kind === 'prepare' || kind === 'approve') {
    await click(btn(folioDesk(probe.host), 'Approve'), 0)
    if (kind === 'approve') await click(probe.host.querySelector('[data-slot="confirm-confirm"]'), 0)
  } else if (kind === 'reject') {
    await click(btn(folioDesk(probe.host), 'Reject'), 0)
    await setField(folioDesk(probe.host)?.querySelector('input'), 'old scope rejection')
    await click(btn(folioDesk(probe.host), 'Reject candidate'), 0)
  } else if (kind === 'recover') {
    stub.state.recoverAct = () => oldResult.promise
    await click(btn(probe.host.querySelector('[data-recovery-list]'), 'Resume'), 0)
  }
  const expectedPosts = kind === 'detail' ? 0 : kind === 'approve' ? 2 : 1
  if (stub.calls.posts.length !== expectedPosts) throw new Error(`SEC-3 ${kind}: deferred setup did not dispatch expected requests`)
  oldScope = false
  await act(async () => { stub.host.state.profile.set(`new-${kind}`) })
  await click(btn(folioDesk(probe.host), 'Approve'), 0)
  if (!probe.host.querySelector('[data-slot="confirm-dialog"]')) throw new Error(`SEC-3 ${kind}: fresh scope could not prepare review`)
  const currentConfirm = retainConfirm(folioDesk(probe.host))
  const gets = stub.calls.gets.length
  const posts = stub.calls.posts.length
  await act(async () => {
    oldResult.resolve(kind === 'detail' ? { ...candidateDetail(firstRef), diff: ['+# OLD DEFERRED DETAIL'] }
      : { ok: true, output: 'OLD DEFERRED DECISION', needs_confirm: kind === 'prepare', request_id: 'old-request', review_digest: 'a'.repeat(64) })
    await oldResult.promise
  })
  if (stub.calls.gets.length !== gets || stub.calls.posts.length !== posts
    || !probe.host.querySelector('[data-slot="confirm-dialog"]')
    || retainConfirm(folioDesk(probe.host)) !== currentConfirm
    || txt(probe.host).includes('OLD DEFERRED')) fail(`SEC-3 ${kind}: old deferred reply contaminated fresh scope`)
  stub.state.recoverAct = null
  await act(async () => probe.unmount())
}

for (const invalidation of ['cancel', 'same-ref refresh', 'same-ref refresh then new confirmation']) {
  const retained = await mount('en', { tab: 'Folio', openConfig: false })
  const desk = folioDesk(retained.host)
  const detail = () => desk
  const dialog = () => desk.querySelector('[data-slot="confirm-dialog"]')
  await click(btn(detail(), 'Approve'), 80)
  const oldConfirm = retainConfirm(desk)
  if (candPosts().length !== 1 || candPosts()[0].body?.ref !== firstRef
    || candPosts()[0].body?.confirm !== false) fail(`${invalidation}: did not dry-run the first candidate`)
  if (invalidation === 'cancel') {
    await click(btn(dialog(), 'Cancel'), 40)
  } else {
    const readsBefore = stub.calls.gets.filter(path => path === '/candidates').length
    // A fresh list object, unchanged refs: disappearance/selection guards cannot mask the token bug.
    stub.state.candList = candidates()
    await click((refreshButton(retained.host) || btn(retained.host, 'Refresh')), 80)
    if (stub.calls.gets.filter(path => path === '/candidates').length !== readsBefore + 1) {
      fail(`${invalidation}: did not re-read the queue exactly once`)
    }
  }
  if (dialog()) fail(`${invalidation}: did not close the old confirmation`)
  if (draftCount(desk) !== 3 || deskRef(desk) !== firstRef
    || !matchingDocument(detail(), candidateDetail(firstRef))
    || !faithfulProposal(detail(), candidateDetail(firstRef))
    || btn(detail(), 'Approve')?.disabled !== false) {
    fail(`${invalidation}: no longer displays the same actionable candidate`)
  }
  const rearmBeforeReplay = invalidation === 'same-ref refresh then new confirmation'
  if (rearmBeforeReplay) await click(btn(detail(), 'Approve'), 80)
  const newConfirm = rearmBeforeReplay ? retainConfirm(desk) : null
  const postsBeforeReplay = stub.calls.posts.length
  await act(async () => { await oldConfirm() })
  await settle(0)
  if (stub.calls.posts.length !== postsBeforeReplay) fail(`${invalidation}: stale confirmation callback posted a write`)
  if (rearmBeforeReplay ? !dialog() : Boolean(dialog())) {
    fail(`${invalidation}: stale callback changed the current confirmation`)
  }
  if (!rearmBeforeReplay) await click(btn(detail(), 'Approve'), 80)
  if (!dialog()) {
    fail(`${invalidation}: could not arm the new confirmation`)
    await act(async () => retained.unmount())
    continue
  }
  const currentConfirm = newConfirm || retainConfirm(desk)
  if (currentConfirm === oldConfirm) fail(`${invalidation}: rearming reused the stale callback`)
  // Replay twice in one turn, then once after success: a current token must be single-use.
  await act(async () => { await Promise.all([currentConfirm(), currentConfirm()]) })
  await settle(80)
  const postsAfterSuccess = stub.calls.posts.length
  await act(async () => { await currentConfirm(); await oldConfirm() })
  await settle(0)
  const writes = candPosts().filter(call => call.body?.confirm === true)
  if (writes.length !== 1 || writes[0].body?.ref !== firstRef || writes[0].path !== '/owner/decision' || !writes[0].body?.request_id
    || candPosts().length !== 3 || stub.calls.posts.length !== postsAfterSuccess) {
    fail(`${invalidation}: the new confirmation did not approve exactly once: ${JSON.stringify(candPosts())}`)
  }
  if (dialog() || draftCount(desk) !== 2
    || !txt(desk).includes('candidate approved')) fail(`${invalidation}: valid new confirmation did not succeed`)
  if (retained.errors.size) fail(`${invalidation} threw: ${[...retained.errors].join(' | ')}`)
  await act(async () => retained.unmount())
}

// Refresh invalidates an in-flight dry-run even when the selected candidate survives unchanged.
const refreshedDryRun = deferred()
const refreshDuringApproval = await mount('en', { tab: 'Folio', openConfig: false,
  candAct: () => refreshedDryRun.promise })
const refreshedDesk = folioDesk(refreshDuringApproval.host)
const refreshedDetail = () => refreshedDesk
await click(btn(refreshedDetail(), 'Approve'), 0)
if (candPosts().length !== 1 || candPosts()[0].body?.ref !== firstRef
  || candPosts()[0].body?.confirm !== false) fail('same-ref dry-run refresh did not start an unconfirmed approval')
const readsBeforeDryRunRefresh = stub.calls.gets.filter(path => path === '/candidates').length
stub.state.candList = candidates()
await click((refreshButton(refreshDuringApproval.host) || btn(refreshDuringApproval.host, 'Refresh')), 80)
if (stub.calls.gets.filter(path => path === '/candidates').length !== readsBeforeDryRunRefresh + 1
  || draftCount(refreshedDesk) !== 3 || deskRef(refreshedDesk) !== firstRef) {
  fail('same-ref dry-run refresh did not refresh and keep the desk on the same draft')
}
await act(async () => {
  refreshedDryRun.resolve({ ok: false, ref: firstRef, action: 'approve', needs_confirm: true, request_id: 'valid-late-owner-fixture', review_digest: 'a'.repeat(64),
    reason: 'approval writes raw/sources and costs model usage', output: '[dry-run] before queue refresh' })
  await refreshedDryRun.promise
})
await settle(0)
if (refreshedDesk.querySelector('[data-slot="confirm-dialog"]')) fail('late dry-run after a same-ref queue refresh rearmed confirmation')
if (candPosts().length !== 1 || stub.calls.posts.length !== 1) fail('late dry-run after queue refresh posted another action')
if (btn(refreshedDetail(), 'Approve')?.disabled !== false
  || !matchingDocument(refreshedDetail(), candidateDetail(firstRef))
  || !faithfulProposal(refreshedDetail(), candidateDetail(firstRef))) {
  fail('same-ref dry-run refresh did not retain the actionable matching document')
}
stub.state.candAct = null
await click(btn(refreshedDetail(), 'Approve'), 80)
await click(refreshedDesk.querySelector('[data-slot="confirm-confirm"]'), 120)
const refreshedWrites = candPosts().filter(call => call.body?.confirm === true)
if (candPosts().length !== 3 || refreshedWrites.length !== 1 || refreshedWrites[0].body?.ref !== firstRef
  || draftCount(refreshedDesk) !== 2 || !txt(refreshedDesk).includes('candidate approved')) {
  fail('a fresh approval after an invalidated late dry-run did not succeed exactly once')
}
if (refreshDuringApproval.errors.size) fail(`same-ref dry-run refresh threw: ${[...refreshDuringApproval.errors].join(' | ')}`)
await act(async () => refreshDuringApproval.unmount())

// A harvest's corrected resubmission: the desk names it a correction, an older pending draft points at
// the newer one, and a draft the engine cannot apply says why instead of failing with a bare error.
{
  const resubmitted = [
    { ref: '20261016-213034/own-plugins', kind: 'new', target: '2026-10-16-own-plugins.md', summary: 'First draft',
      superseded_by: '20261016-213034/own-plugins-v2' },
    { ref: '20261016-213034/own-plugins-v2', kind: 'new', target: '2026-10-16-own-plugins.md', summary: 'Corrected draft',
      corrects: '20261016-213034/own-plugins-earlier' },
    { ref: '20261016-213034/stale', kind: 'new', target: '2026-10-16-stale.md', summary: 'Stale draft',
      blocked: 'raw/sources/2026-10-16-stale.md already exists and is not the unchanged file an earlier approved draft wrote' }
  ]
  const candShow = ref => {
    const row = resubmitted.find(r => r.ref === ref)
    return { ...candidateDetail(candidates()[0].ref), ref, corrects: row.corrects || null,
      target_exists: Boolean(row.corrects), candidate: { kind: 'new', target: row.target, summary: row.summary, why: 'w', evidence_ids: [] } }
  }
  const resubmission = await mount('en', { openConfig: false, candidates: resubmitted.map(row => ({ ...row })), candShow })
  await openDetail(resubmission.host, 'review')
  const rdesk = detailOf(resubmission.host, 'review')
  must(txt(rdesk), ['A newer draft of this source is waiting (own-plugins-v2). Approve that one and reject this one.'],
    'older pending draft points at the newer one')
  await gotoDraft(rdesk, '20261016-213034/own-plugins-v2')
  must(txt(rdesk), ['Correction', 'Corrects the version you approved earlier (own-plugins-earlier).'], 'correction draft')
  if (rdesk.querySelector('.wa-desk-kind')?.getAttribute('data-kind') !== 'correction') fail('a correction is badged as a new page')
  await gotoDraft(rdesk, '20261016-213034/stale')
  must(txt(rdesk), ['This draft cannot be applied:', 'not the unchanged file an earlier approved draft wrote'], 'blocked draft')
  if (resubmission.errors.size) fail(`resubmitted drafts threw: ${[...resubmission.errors].join(' | ')}`)
  await act(async () => resubmission.unmount())
}

// Selection changes invalidate the old confirmation and rejection reason, not just the document.
const decisionSwitch = await mount('en', { tab: 'Folio', openConfig: false })
const decisionDesk = folioDesk(decisionSwitch.host)
const decisionDetail = () => decisionDesk
if (deskRef(decisionDesk) !== candidates()[0].ref) fail('the decision-switch desk does not start on the first draft')
await click(btn(decisionDetail(), 'Approve'), 80)
if (!decisionDesk.querySelector('[data-slot="confirm-dialog"]')) fail('the selection-switch test did not arm approval')
await click(btn(decisionDetail()?.querySelector('.fl-views'), 'Reason & evidence'), 0)
await click(btn(decisionDesk, 'Later'), 80)
if (decisionDesk.querySelector('[data-slot="confirm-dialog"]')) fail('a candidate switch retained the previous approval confirmation')
if (txt(decisionDetail()?.querySelector('.fl-views [aria-pressed="true"]')) !== 'Proposed change'
  || decisionDetail()?.querySelector('.fl-reason')
  || !matchingDocument(decisionDetail(), candidateDetail(candidates()[1].ref))
  || !faithfulProposal(decisionDetail(), candidateDetail(candidates()[1].ref))) {
  fail('switching candidates did not reset to the matching new proposal')
}
const switchApprove = btn(decisionDetail(), 'Approve')
if (!switchApprove?.disabled) fail('switching to a format-invalid candidate enabled approval')
await click(switchApprove, 0)
if (candPosts().length !== 1) fail('switching candidates reused the previous approval action')
await click(btn(decisionDetail(), 'Reject'), 40)
await setField(decisionDetail().querySelector('input'), 'reason belonging only to the update')
await click(btn(decisionDetail()?.querySelector('.fl-views'), 'Reason & evidence'), 0)
await click(btn(decisionDesk, 'Later'), 80)
if (txt(decisionDetail()?.querySelector('.fl-views [aria-pressed="true"]')) !== 'Proposed change'
  || !matchingDocument(decisionDetail(), candidateDetail(finalRef))
  || !faithfulProposal(decisionDetail(), candidateDetail(finalRef))) fail('a second candidate switch retained another candidate\'s projection')
if (decisionDetail().querySelector('input') || btn(decisionDetail(), 'Reject candidate')) {
  fail('switching candidates retained another candidate\'s rejection reason or decision')
}
await click(btn(decisionDetail(), 'Approve'), 80)
await click(decisionDesk.querySelector('[data-slot="confirm-confirm"]'), 120)
const switchConfirmed = candPosts().filter(call => call.body?.confirm === true)
if (switchConfirmed.length !== 1 || switchConfirmed[0].body?.ref !== finalRef
  || switchConfirmed[0].path !== '/owner/decision' || !switchConfirmed[0].body?.request_id) fail('a switched decision confirmed approval for a mismatched ref')
if (decisionSwitch.errors.size) fail(`candidate decision switching threw: ${[...decisionSwitch.errors].join(' | ')}`)
await act(async () => decisionSwitch.unmount())

// A digest-less response and a mismatched prepared digest must never authorize a confirmation.
for (const protocolFault of ['missing digest', 'mismatched prepared digest']) {
  const invalidProtocol = await mount('en', { tab: 'Folio', openConfig: false,
    candShow: ref => ({ ...candidateDetail(ref), ...(protocolFault === 'missing digest' ? { review_digest: undefined } : {}) }),
    candAct: () => ({ ok: false, needs_confirm: true, request_id: 'wrong-revision-owner-fixture', review_digest: 'f'.repeat(64) }) })
  const desk = folioDesk(invalidProtocol.host)
  const postCount = stub.calls.posts.length
  await click(btn(desk, 'Approve'), 80)
  if (protocolFault === 'missing digest' && stub.calls.posts.length !== postCount) fail('digest-less review called the owner authority')
  if (desk.querySelector('[data-slot="confirm-dialog"]')) fail(`${protocolFault}: an invalid review armed confirmation`)
  if (!txt(desk).includes('Refresh and review again')) fail(`${protocolFault}: refusal did not explain the required re-review`)
  await act(async () => invalidProtocol.unmount())
}

// EMPTY, FAILED LIST, FAILED DETAIL: check the Your review station first, then the review desk.
const noCands = await mount('en', { candidates: [] })
if (noCands.host.querySelector('[data-wa-station="review"]')?.dataset.state !== 'ok') fail('no drafts is not a calm (ok) review station')
if (/Read failed/.test(txt(noCands.host.querySelector('[data-wa-station="review"]')))) fail('an empty review read looks failed')
await selectTab(noCands.host, 'Folio')
const emptyCand = folioDesk(noCands.host)
if (emptyCand?.querySelectorAll('.place-items-center').length !== 1) {
  fail('no candidates is not ONE neutral EmptyState')
}
must(txt(emptyCand), ['no candidate waiting', 'the nightly session harvest drafts new ones here'], 'no candidates')
if (deskRef(emptyCand) || btn(emptyCand, 'Approve')) {
  fail('an empty review desk still renders a draft or approval')
}
await act(async () => noCands.unmount())
const candDown = await mount('en', { candidatesPayload: { ok: false, candidates: [],
  error: 'the candidates could not be read: exit 2: harvest exploded' } })
if (candDown.host.querySelector('[data-wa-station="review"]')?.dataset.state !== 'bad') fail('a failed drafts read is not a bad review station')
if (candDown.host.querySelector('.wa-metro-bar')?.dataset.alert !== 'read-failed') fail('a failed drafts read is not the read-failed alert')
if (/Good service/i.test(txt(candDown.host))) fail('"Good service" while the drafts read failed')
await selectTab(candDown.host, 'Folio')
const downCand = candDown.host.querySelector('[data-slot="error-state"]')?.closest('.wa-help')
if (!txt(downCand).includes('could not read the candidates') || !txt(downCand).includes('harvest exploded')) {
  fail(`a failed candidates read lost the backend error: ${txt(downCand).slice(0, 160)}`)
}
if (candDown.host.querySelector('.place-items-center')) fail('a failed candidates read renders as an empty list')
if (btn(candDown.host, 'Approve')) fail('a failed drafts read offers approval')
await act(async () => candDown.unmount())
const candThrow = await mount('en', { throwOn: '/candidates' })
if (candThrow.host.querySelector('[data-wa-station="review"]')?.dataset.state !== 'bad') fail('an unreachable drafts route is not a bad review station')
if (/Good service/i.test(txt(candThrow.host))) fail('"Good service" while the drafts route is unreachable')
await selectTab(candThrow.host, 'Folio')
if (!txt(candThrow.host).includes('backend unreachable')) fail('an unreachable candidates route lost its error')
if (btn(candThrow.host, 'Approve')) fail('an unreachable drafts route offers approval')
await act(async () => candThrow.unmount())
stub.state.throwOn = null
const showDown = await mount('en')
must(txt(showDown.host.querySelector('[data-wa-station="review"]')), ['3'], 'detail-failure review station count')
stub.state.candShowError = 'the candidates could not be read: exit 1: !! refused: candidate not found'
await selectTab(showDown.host, 'Folio')
const showCard = folioDesk(showDown.host)
if (!txt(showCard).includes('could not read this candidate') || !txt(showCard).includes('candidate not found')) {
  fail(`a failed candidate detail lost the backend error: ${txt(showCard).slice(0, 160)}`)
}
if (btn(showCard, 'Approve') && !btn(showCard, 'Approve').disabled) fail('Approve is offered without a detail')
stub.state.candShowError = null
await act(async () => showDown.unmount())
for (const view of [noCands, candDown, candThrow, showDown]) {
  if (view.errors.size) fail(`the candidates views threw: ${[...view.errors].join(' | ')}`)
}

console.log('SEC-3 exercised — actual SDK connection/profile/cwd epochs · exact rejection digest · retained decision/selection/recovery callbacks · synchronous guards · deferred detail/prepare/approve/reject/recovery results; no mount mutations or persistent client storage')

// ===========================================================================
// 5) Write surface: cron history untouched, no language route
// ===========================================================================
// ONE SURFACE AT A TIME: a refusal for the draft closes the copy/mirror confirmation, so the card never
// asks "Yes, take it" beside "Why this was refused" for the same path.
await click(btn(rootCard, 'Scan for candidates'), 80)
await click([...rootCard.querySelectorAll('.wa-cand')].find(b => txt(b).includes('SAME ID')), 80)
if (!rootCard.querySelector('.wa-confirm')) fail('the same-id candidate did not arm the confirmation')
if (rootCard.querySelector('.wa-help')) fail('the copy/mirror confirmation is shown beside a second message card')
stub.state.checker.validate = 'wiki/ klas\u00f6r\u00fc yok'
await click(btn(rootCard, 'Verify'), 80)
if (rootCard.querySelector('.wa-confirm')) {
  fail('a refused verification left the copy/mirror confirmation open for the same path')
}
stub.state.checker.validate = null
if ([...rootCard.querySelectorAll('button')].filter(b => txt(b) === 'Choose folder…').length !== 1) {
  fail('"Choose folder…" is offered twice in the root card')
}
await settle(120)

const allowed = new Set(['/automation/validate', '/automation/derive', '/automation/settings',
  '/automation/scan_root', '/jobs/act', '/jobs/preview', '/candidates/act'])
for (const x of stub.calls.posts) {
  if (!allowed.has(x.path)) fail(`unexpected write route: ${x.path}`)
}
for (const x of stub.calls.gets) {
  if (!(x.startsWith('/automation') || x.startsWith('/runs') || x.startsWith('/jobs')
    || x.startsWith('/candidates') || x.startsWith('/health/jobs') || x === '/harvest/status'
    || x === '/owner/recoverable' || x === '/owner/activation' || x === '/engine/status' || x === '/wiki/map')) {
    fail(`unexpected read route: ${x}`)
  }
}

// ===========================================================================
// 6) Refresh really re-reads
// ===========================================================================
const before = stub.calls.gets.length
await click(refreshButton(p.host), 80)
if (stub.calls.gets.length <= before) fail('the refresh button did not re-read the data')
for (const route of ['/automation', '/runs', '/jobs', '/candidates', '/harvest/status']) {
  if (!stub.calls.gets.slice(before).some(x => x.startsWith(route))) {
    fail(`the refresh button did not re-read ${route}`)
  }
}

// ===========================================================================
// 6b) REMOVED in 2.5.0: the Recent-runs card with its heartbeat strip and its 3/10/25 range
//     (Docs/metro-contract.md § Removed). The run history lives once, in History (render_health.mjs).
//     What stays: no runs at all is not a failure and invents no result.
// ===========================================================================
const noRuns = await mount('en', { runs: { ok: true, limit: 3, jobs: [] }, openConfig: false })
if (['harvest-failed', 'read-failed'].includes(noRuns.host.querySelector('.wa-metro-bar')?.dataset.alert)) {
  fail('no recorded run reads as a failure')
}
if (/0 of 0|0%/.test(txt(await openDetail(noRuns.host, 'harvest')))) fail('no recorded run reads as a 0% result')
if (noRuns.host.querySelector('.wa-hb-row, .wa-hb-bar, .wa-hb-note')) fail('the removed heartbeat strip is back')
await act(async () => noRuns.unmount())

const partial = await mount('en')
const partialInstall = cardByTitle(partial.host, 'Engine and files')
if (!partialInstall?.querySelector('[data-tip="missing: install.py"]')
  || /Task Scheduler|Registered/.test(txt(partialInstall))) {
  fail(`the install reading does not name the missing script (or names Task Scheduler): ${txt(partialInstall)}`)
}
const unverified = automation()
unverified.settings = { ...unverified.settings, project: { ok: false, reason: 'wiki/ klas\u00f6r\u00fc yok',
  reason_source: 'checker' } }
const unverifiedRoot = await mount('en', { automation: unverified })
if (unverifiedRoot.host.querySelector('.wa-metro-bar')?.dataset.alert === 'good' || /Good service/i.test(txt(unverifiedRoot.host))) {
  fail('an unverified root reads as good service')
}
if (!detailOf(unverifiedRoot.host, 'settings')) fail('Settings did not open on the unverified root')
const unverifiedCard = cardByTitle(unverifiedRoot.host, 'Wiki folder')
if (/Verified/.test(txt(unverifiedCard))) fail('an unverified root is presented as verified')
await settle(120)

// ===========================================================================
// 7) Language: one bundle, app-locale driven, no picker, no raw key
// ===========================================================================
for (const appLocale of ['tr', 'ja']) {
  const other = await mount(appLocale)
  if (other.host.querySelector('.wa-lang, .wa-lang-btn, [class*="lang"]')) {
    fail(`a language picker appeared under the ${appLocale} app locale`)
  }
  if (stub.calls.registered.length !== 1 || stub.calls.registered[0].locales.join('|') !== 'en') {
    fail(`the ${appLocale} run did not register exactly one 'en' bundle`)
  }
  const card = cardByTitle(other.host, 'Wiki folder') || cards(other.host)[0]
  must(txt(card), ['Project root', 'Choose folder…', 'Verify', 'Save', 'Scan for candidates'],
    `root card under ${appLocale}`)
  must(txt(cardByTitle(other.host, 'Engine and files')), ['Settings file', 'Scripts', '3 of 4'],
    `install card under ${appLocale}`)
  if (RAW_KEY.test(txt(other.host))) fail(`a raw key reached the screen under ${appLocale}`)
  if (other.errors.size) fail(`the panel threw under ${appLocale}: ${[...other.errors].join(' | ')}`)
}

// ===========================================================================
// 8) No root set: discovery still runs and the scan folder can be picked
// ===========================================================================
const base = automation()
const noRoot = await mount('en', { automation: { ...base,
  settings: { ...base.settings, project_root: null, project: { ok: false, id: null, pages: 0,
                                                              reason: 'no project root chosen' } } } })
const nr = cardByTitle(noRoot.host, 'Wiki folder') || cards(noRoot.host)[0]
if (!btn(nr, 'Choose scan folder…')) fail('the "Choose scan folder…" button is missing while no root is set')
await click(btn(nr, 'Scan for candidates'), 80)
const nrReq = stub.calls.gets.filter(x => x.startsWith('/automation/candidates')).at(-1)
if (nrReq !== '/automation/candidates') fail(`the scan sent a root while none is set: ${nrReq}`)
// Picking the scan folder: the folder of the picked FILE is saved, then the scan runs there.
stub.state.pickResult = '/srv/other/scan/.llm-wiki/project.json'
await click(btn(nr, 'Choose scan folder…'), 80)
const sr = stub.calls.posts.filter(x => x.path === '/automation/scan_root').at(-1)
if (!sr || sr.body.path !== '/srv/other/scan') fail(`the scan root was saved wrong: ${JSON.stringify(sr)}`)
must(txt(nr), ['scan root saved: /srv/other/scan'], 'scan root message')
stub.state.pickResult = '/srv/wiki/.llm-wiki/project.json'
await settle(120)

// MISSING INSTALL: with no package on the machine the panel shows an OPEN error (no silent empty card).
const miss = await mount('en', { automation: {
  audit_dir: '/srv/audit', available: false, settings: null, scripts: {}, jobs: null,
  error: 'automation folder not found'
} })
const missCard = cardByTitle(miss.host, 'Wiki folder')
if (must(txt(missCard), ['automation folder not found'], 'missing package')) {
  const heads = [...miss.host.querySelectorAll('.wa-head, .g-panel-head')].map(h => txt(h))
  fail(`missing-package view: headings ${JSON.stringify(heads)} `
    + `| panel errors: ${[...miss.errors].join(' | ') || 'none'}`)
}
if (RAW_KEY.test(txt(miss.host))) fail('a raw key appeared in the missing-package view')

// ===========================================================================
// 9) The external checker's text: English on screen, the raw wording kept beside it
// ===========================================================================
// `~/.llmwiki-audit/wikiconfig.py` answers in TURKISH. Every known reason must appear in English,
// taken from the panel's own `en` bundle with the paths and numbers intact, and its raw wording must
// stay reachable (detail block + tooltip): the text is never silently replaced or dropped.
const CHECK_REASONS = [
  { raw: 'klasör yok', en: 'top-level folder not found' },
  { raw: '.llm-wiki/project.json yok — bu klasör bir wiki kökü değil',
    en: 'no .llm-wiki/project.json — this folder is not a wiki root' },
  { raw: '.llm-wiki/project.json okunamadı', en: '.llm-wiki/project.json could not be read' },
  { raw: 'wiki/ klasörü yok', en: 'no wiki/ folder' },
  { raw: 'wiki/ boş ya da kimlik eksik', en: 'wiki/ is empty or the project id is missing' },
  { raw: 'tarama kökü yok: /srv/nowhere', en: 'scan root not found: /srv/nowhere' },
  { raw: 'tarama kökü belirsiz — bir klasör seç', en: 'scan root unknown — pick a folder' },
  { raw: 'proje kökü seçilmemiş', en: 'project root not chosen' },
  { raw: 'proje kökü seçilmemiş (/srv/audit/settings.json)',
    en: 'project root not chosen (/srv/audit/settings.json)' },
  { raw: 'proje kökü bulunamadı: C:/wiki', en: 'project root not found: C:/wiki' },
  { raw: 'yol gerekli', en: 'a path is required' },
  { raw: 'seçilen yolun üstünde .llm-wiki/project.json yok — wiki klasörünün İÇİNDEN bir dosya seç',
    en: 'no .llm-wiki/project.json above the picked path — pick a file INSIDE the wiki folder' }
]
const cm = await mount('en')
const cmCard = cardByTitle(cm.host, 'Wiki folder') || cards(cm.host)[0]
const cmInput = cmCard.querySelector('input')
const cmMsg = () => cmCard.querySelector('[data-tone]:not(.wa-badge)')
const cmRaw = () => cmCard.querySelector('.wa-raw')
for (const c of CHECK_REASONS) {
  stub.state.checker.validate = c.raw
  await setField(cmInput, '/srv/elsewhere')
  await click(btn(cmCard, 'Verify'), 60)
  const line = cmMsg()
  if (!line || !txt(line).includes(c.en)) {
    fail(`check reason not shown in English: ${JSON.stringify(c.raw)} -> `
      + `${line ? txt(line) : 'no message'}`)
  } else if (txt(line).includes(c.raw)) {
    fail(`the raw checker text was printed as the message: ${txt(line)}`)
  }
  const detail = cmRaw()
  if (!detail) {
    fail(`the raw checker text is not kept beside its English reading: ${JSON.stringify(c.raw)}`)
  } else {
    if (!txt(detail).includes(c.raw)) fail(`the detail block lost the raw text: ${txt(detail)}`)
    if (detail.getAttribute('data-tip') !== c.raw) {
      fail(`the tooltip lost the raw text: ${JSON.stringify(detail.getAttribute('data-tip'))}`)
    }
  }
}
// UNRECOGNIZED: the raw text plus ONE neutral label — no invented translation.
const UNKNOWN = 'öngörülemeyen çıktı: /srv/unknown'
stub.state.checker.validate = UNKNOWN
await setField(cmInput, '/srv/elsewhere')
await click(btn(cmCard, 'Verify'), 60)
if (!txt(cmMsg()).includes('Unrecognized check output')) {
  fail(`an unrecognized check reason did not fall back to the neutral label: ${txt(cmMsg())}`)
}
if (txt(cmMsg()).includes('öngörülemeyen')) fail('an unrecognized reason was printed as the message')
if (!cmRaw() || !txt(cmRaw()).includes(UNKNOWN)) fail('the raw text of an unrecognized reason was dropped')
if (cmRaw() && cmRaw().getAttribute('data-tip') !== UNKNOWN) {
  fail('an unrecognized reason has no raw tooltip')
}
// Each route that can carry a checker reason maps it: derive · candidates · scan root · save.
stub.state.checker.validate = null
stub.state.checker.derive = 'yol gerekli'
await click(btn(cmCard, 'Choose folder…'), 60)
if (!txt(cmMsg()).includes('a path is required')) fail('the derive reason was not mapped')
if (!cmRaw()) fail('the derive raw text was dropped')
stub.state.checker.derive = null
stub.state.checker.candidates = 'tarama kökü yok: /srv/nowhere'
await click(btn(cmCard, 'Scan for candidates'), 60)
if (!txt(cmMsg()).includes('scan root not found: /srv/nowhere')) fail('the scan reason was not mapped')
stub.state.checker.candidates = null
stub.state.checker.settings = 'klasör yok'
await setField(cmInput, '/srv/elsewhere')
await click(btn(cmCard, 'Save'), 60)
if (!txt(cmMsg()).includes('top-level folder not found')) fail('the save reason was not mapped')
if (!cmRaw()) fail('the save raw text was dropped')
stub.state.checker.settings = null
// BACKEND REASON: already English, printed as it arrived — no second reading, no raw duplicate.
await setField(cmInput, '/srv/elsewhere')
await click(btn(cmCard, 'Verify'), 60)
if (!txt(cmMsg()).includes('the folder is not a verified wiki root')) {
  fail(`a backend reason was not printed as it arrived: ${txt(cmMsg())}`)
}
if (cmRaw()) fail('a raw detail block appeared for an English backend reason')
if (cm.errors.size) fail(`the panel threw on a checker reason: ${[...cm.errors].join(' | ')}`)
const base3 = automation()
const cmRootless = await mount('en', { automation: { ...base3, settings: { ...base3.settings,
  project_root: null, project: { ok: false, id: null, pages: 0, reason: 'proje kökü seçilmemiş' } } } })
const cmNrCard = cardByTitle(cmRootless.host, 'Wiki folder') || cards(cmRootless.host)[0]
stub.state.checker.scanRoot = 'klasör yok'
await click(btn(cmNrCard, 'Choose scan folder…'), 120)
if (!txt(cmNrCard.querySelector('[data-tone]:not(.wa-badge)')).includes('top-level folder not found')) {
  fail('the scan-root reason was not mapped')
}
if (!cmNrCard.querySelector('.wa-raw')) fail('the scan-root raw text was dropped')
stub.state.checker.scanRoot = null
await settle(120)

// ===========================================================================
// 10) The reference pass: one code language, copyable code, a help card for a reason,
//     quiet secondary actions, ONE icon-button shape
// ===========================================================================
const ref = await mount('en')
const refCard = cardByTitle(ref.host, 'Wiki folder') || cards(ref.host)[0]
const refInput = refCard.querySelector('input')
const CHECK_RAW = 'wiki/ klasörü yok'
const shape = el => {
  const s = dom.window.getComputedStyle(el)
  return `${s.fontFamily}|${s.fontSize}|${s.lineHeight}`
}
// ONE CODE LANGUAGE: the root path, the candidate paths, the raw check body and the run
// stamps/durations share a single family/size/leading. A second mono shape reads as a second kind
// of content, which is how a path stopped looking like the code it is.
const monoShape = shape(ref.host.querySelector('.wa-mono'))
const shapes = [...new Set([...ref.host.querySelectorAll('.wa-mono')].map(shape))]
if (shapes.length !== 1) fail(`the code/data language is not one: ${shapes.join(' / ')}`)
if (!/mono/i.test(monoShape)) fail(`the shared code language is not monospaced: ${monoShape}`)
// ICON BUTTONS: one shape — the kit's `icon-sm`, circular, and never a bare glyph.
const icons = [...ref.host.querySelectorAll('.wa-icon-btn')]
if (!icons.length) fail('no icon button carries the shared icon shape')
for (const ic of icons) {
  if (ic.getAttribute('data-size') !== 'icon-sm') {
    fail(`an icon button is not the shared icon-sm size: ${ic.getAttribute('data-size')}`)
  }
  if (!ic.getAttribute('aria-label')) fail(`an icon button carries no aria-label: ${ic.outerHTML.slice(0, 90)}`)
  if (dom.window.getComputedStyle(ic).borderRadius !== '9999px') fail('an icon button is not circular')
}
// SECONDARY ACTIONS SHARE ONE SECONDARY SHAPE (outline); the write stays the one filled primary.
const variantOf = el => (el ? el.getAttribute('data-variant') : null)
for (const label of ['Choose folder…', 'Verify', 'Scan for candidates']) {
  const b = btn(refCard, label)
  if (!b) fail(`the ${label} button is missing`)
  else if (variantOf(b) !== 'outline') fail(`${label} is not a secondary action: ${variantOf(b)}`)
}
if (variantOf(btn(refCard, 'Save')) !== 'default') fail('Save is no longer the filled action')
const filled = [...refCard.querySelectorAll('.wa-inline button[data-variant="default"]')].map(txt)
if (filled.length !== 1) fail(`the action row must carry exactly ONE primary: ${JSON.stringify(filled)}`)
const rowLabels = [...refCard.querySelectorAll('.wa-inline button')].map(txt)
if (rowLabels[rowLabels.length - 1] !== 'Save') fail(`the primary must end the action row: ${JSON.stringify(rowLabels)}`)
// A REFUSAL CARRYING THE CHECKER'S OWN TEXT IS A HELP CARD: heading + the one sentence + the raw
// wording in a code body + the action that helps.
stub.state.checker.validate = CHECK_RAW
await setField(refInput, '/srv/elsewhere')
await click(btn(refCard, 'Verify'), 80)
const help = refCard.querySelector('.wa-help')
if (!help) fail('a refused verification is not a help card')
const helpTitle = txt(refCard.querySelector('.wa-help-title'))
if (helpTitle !== 'Why this was refused') fail(`the help card heading is wrong: ${helpTitle}`)
const lines = help ? help.querySelectorAll('[data-tone]') : []
if (lines.length !== 1) fail(`the help card carries ${lines.length} reason lines (expected one)`)
else if (!txt(lines[0]).includes('no wiki/ folder')) fail(`the help card lost the reason: ${txt(lines[0])}`)
const codeBody = help ? help.querySelector('.wa-raw pre') : null
if (!codeBody) fail('the raw check text is not in a code body')
else {
  if (txt(codeBody) !== CHECK_RAW) fail(`the code body is not the raw text alone: ${txt(codeBody)}`)
  if (!String(codeBody.className).includes('wa-mono')) fail('the code body is outside the shared code language')
}
if (help && !txt(help).includes('As written')) fail('the code body has no caption')
// COPYABLE: both code surfaces hand the kit's copy affordance the right payload, labelled.
const copies = [...refCard.querySelectorAll('[data-copy]')]
const payloads = copies.map(c => c.getAttribute('data-copy'))
if (copies.length !== 2) fail(`the path and the raw text must both be copyable: ${copies.length} button(s)`)
if (!payloads.includes(VALID_ROOT)) fail(`the saved root path is not offered for copying: ${JSON.stringify(payloads)}`)
if (payloads.includes('/srv/elsewhere')) fail('the Project root copy button hands out an unsaved draft')
if (!payloads.includes(CHECK_RAW)) fail(`the raw text is not offered for copying: ${JSON.stringify(payloads)}`)
for (const c of copies) if (!c.getAttribute('aria-label')) fail('a copy button carries no aria-label')
// The action sits beside a refusal and really reopens the picker.
const helpAct = refCard.querySelector('.wa-help-act')
if (!helpAct) fail('a refusal with the checker wording offers no action')
else {
  if (variantOf(helpAct) !== 'outline') fail(`the help action is not secondary: ${variantOf(helpAct)}`)
  const picked = stub.state.pickCalls.length
  await click(helpAct, 80)
  if (stub.state.pickCalls.length <= picked) fail('the help action does not reopen the picker')
}
// A PLAIN RESULT: the same card, no raw block and no action.
stub.state.checker.validate = null
await setField(refInput, '/srv/wiki')
await click(btn(refCard, 'Verify'), 80)
if (refCard.querySelector('.wa-help-act')) fail('a plain result still offers the refusal action')
if (txt(refCard.querySelector('.wa-help-title')) !== 'Result') {
  fail(`a plain result has the wrong heading: ${txt(refCard.querySelector('.wa-help-title'))}`)
}
// A BACKEND reason (already English, no raw wording) gets no raw block and no action either.
await setField(refInput, '/srv/elsewhere')
await click(btn(refCard, 'Verify'), 80)
if (refCard.querySelector('.wa-raw')) fail('a backend reason grew a raw block')
if (refCard.querySelector('.wa-help-act')) fail('a backend reason offered the checker action')
if (ref.errors.size) fail(`the reference pass threw: ${[...ref.errors].join(' | ')}`)
await settle(120)

// ===========================================================================
// 10) A FAILED READ: the generic sentence AND the error the backend returned
// ===========================================================================
// The panel printed "could not read the automation state" and threw the error away — the one string a
// bug report can search for. It now sits in a code body under the same `as written` caption as the
// checker's wording, with the copy affordance beside it.
const dead = await mount('en', { throwOn: '/automation' })
const deadCard = cardByTitle(dead.host, 'Wiki folder') || cards(dead.host)[0]
must(txt(deadCard), ['could not read the automation state'], 'failed read sentence')
const deadRaw = deadCard.querySelector('.wa-raw')
if (!deadRaw) fail('a failed read dropped the error text the backend returned')
else {
  const deadBody = txt(deadRaw.querySelector('pre'))
  if (!deadBody.includes('backend unreachable (500) on /automation')) {
    fail(`the failure detail lost the error: ${deadBody}`)
  }
  if (deadRaw.getAttribute('data-tip') !== deadBody) fail('the error text is not a tooltip label')
  if (!deadRaw.querySelector('[data-copy]')) fail('the error text is not copyable')
}
// A read that failed must not leave a spinner turning: nothing is loading, and the card that
// depends on the same payload says why instead of spinning forever.
if (dead.host.querySelector('[data-loader]')) {
  fail('a failed read left a spinner turning although nothing is loading')
}
const deadInstall = cardByTitle(dead.host, 'Engine and files')
if (!deadInstall || !txt(deadInstall).includes('could not read the automation state')) {
  fail('the install card does not report the failed read it depends on')
}
const deadJobs = cardByTitle(dead.host, 'Scheduled jobs')
if (!deadJobs || !txt(deadJobs).includes('Wiki Auto-Commit')) {
  fail('a failed read in one card took an untouched card down')
}
if (dead.errors.size) fail(`the failure view threw: ${[...dead.errors].join(' | ')}`)
await settle(120)

// ===========================================================================
// 11) Round-2 review: numbers, error shapes, stale data, a11y and copy
// ===========================================================================
const beatRuns = (msList, status = 'completed') => ({ ok: true, limit: 10, jobs: [
  { role: 'autocommit', job_id: 'aaa', name: 'Wiki Auto-Commit', live: true,
    runs: msList.map((ms, i) => ({ at: `2026-09-1${i}T10:00:00+03:00`, status, status_label: 'Completed',
      delivery: 'suppressed', delivery_label: 'Silent', ms, error_preview: null })).reverse() }] })
// The heartbeat notes (slow run, median, counted noun) went with the heartbeat strip (removed in 2.5.0).
// NO ROLES / A FAILED /jobs READ: never "0 of 0 jobs live", never a green chip, the reason is shown.
const jobsDown = await mount('en', { jobs: { ok: false, roles: [], orphans: [],
  reason: 'the scheduled jobs could not be read: store exploded' } })
const downCard = cardByTitle(jobsDown.host, 'Scheduled jobs')
if (!txt(downCard).includes('store exploded') || txt(downCard).includes('0 of 0')) {
  fail(`a failed /jobs read renders as an empty job list: ${txt(downCard).slice(0, 140)}`)
}
if (!jobsDown.host.querySelector('.wa-metro-map[data-unread="1"]')) fail('a failed job store still draws the line as if the timetable were known')
if (jobsDown.host.querySelector('.wa-metro-bar')?.dataset.alert !== 'read-failed') fail('a failed job store is not the read-failed alert')
if (/Good service/i.test(txt(jobsDown.host))) fail('"Good service" while the job store read failed')
// NOTHING WRONG: no "0 missing" / "0 failed" chip.
const clean = automation()
clean.scripts = { 'a.py': true, 'b.py': true }
const allGood = await mount('en', { automation: clean, runs: beatRuns([100, 120]) })
const completeInstall = cardByTitle(allGood.host, 'Engine and files')
if (!completeInstall?.querySelector('[data-tip="nothing missing"]') || !txt(completeInstall).includes('2 of 2')) {
  fail('the retained install reading does not report all scripts present')
}
// A11Y: every station, branch and header opener is a named, keyboard-operable toggle (aria-pressed).
const allNodes = [...allGood.host.querySelectorAll('[data-wa-station], [data-wa-line], [data-wa-nav]')]
if (allNodes.length !== harvestStatus().agents.length + 3 + 2) fail(`the Metro openers are missing: ${allNodes.length}`)
for (const node of allNodes) {
  if (node.tagName !== 'BUTTON' || !txt(node).trim() || !node.getAttribute('aria-label')
    || !['true', 'false'].includes(node.getAttribute('aria-pressed'))) {
    fail(`a Metro opener is not a named keyboard-operable toggle: ${node.outerHTML.slice(0, 120)}`); break
  }
}
if (/the store has held runs since/.test(txt(allGood.host))) {
  fail('the gauge claims the oldest run shown is when the store began')
}
// STALE DATA: a refresh that fails keeps the last reading AND says so (the read-failed alert keeps the
// backend's error; the stations keep their words).
const stale = await mount('en')
const staleWords = txt(stale.host.querySelector('[data-wa-station="harvest"]'))
stub.state.throwOn = '/runs'
await click(refreshButton(stale.host), 80)
const staleBar = stale.host.querySelector('.wa-metro-bar')
if (staleBar?.dataset.alert !== 'read-failed' || !txt(staleBar).includes('backend unreachable')) {
  fail(`a failed refresh is invisible behind the stale data: ${staleBar?.dataset.alert} ${txt(staleBar).slice(0, 120)}`)
}
if (!txt(stale.host.querySelector('[data-wa-station="harvest"]')).trim() || !staleWords) fail('a failed refresh threw the last reading away')
stub.state.throwOn = null
await openDetail(stale.host, 'settings')
// BUSY: an action in flight is announced, not only prefixed.
const liveRegion = cardByTitle(stale.host, 'Wiki folder')
if (!liveRegion.querySelector('[aria-live="polite"]')) {
  fail('the root card has no live region for its messages')
}
// ROUND 4 heartbeat pills (running/unknown are not completed) went with the heartbeat strip; the live
// station tests above keep 'running is not completed'.
// ROUND 4 — an unreadable job store is an error, not every job deleted.
const unreadStore = runs()
unreadStore.error = 'the scheduled jobs (cron/jobs.json) could not be read: Expecting value'
unreadStore.jobs = unreadStore.jobs.map(j => ({ ...j, live: null }))
const storeDown = await mount('en', { runs: unreadStore, openConfig: false })
if (/Deleted job/.test(txt(storeDown.host))) fail('an unreadable job store marks every job deleted')
const storeHarvest = txt(await openDetail(storeDown.host, 'harvest')) + txt(storeDown.host.querySelector('.wa-metro-bar'))
if (!storeHarvest.includes('cron/jobs.json) could not be read')) {
  fail(`an unreadable job store is not reported: ${storeHarvest.slice(0, 160)}`)
}
if (/Good service/i.test(txt(storeDown.host))) fail('"Good service" while the job store is unreadable')
// Source-state failure is explicit, not an empty healthy line; no branch is ever fabricated.
const lineIds = view => [...view.host.querySelectorAll('[data-wa-line]')].map(n => n.dataset.waLine).join('|')
const noAdapters = await mount('en', { harvest: { ok: true, agents: [] }, openConfig: false })
must(txt(noAdapters.host.querySelector('.wa-metro-map')), ['No adapters reported'], 'empty adapter status')
if (lineIds(noAdapters)) fail('an empty status fabricated branch lines')
if (!noAdapters.host.querySelector('[data-wa-station="harvest"]') || !noAdapters.host.querySelector('[data-wa-station="review"]')) {
  fail('an empty adapter list removed the independent stations')
}
const statusFailed = await mount('en', { harvest: { ok: false, error: 'harvest config unreadable', agents: [] }, openConfig: false })
must(txt(statusFailed.host.querySelector('.wa-metro')), ['harvest config unreadable'], 'failed adapter status')
if (statusFailed.host.querySelector('.wa-metro-bar')?.dataset.alert !== 'read-failed') fail('a failed adapter status is not the read-failed alert')
if (lineIds(statusFailed)) fail('a failed status fabricated branch lines')
const statusMissing = await mount('en', { throwOn: '/harvest/status', openConfig: false })
must(txt(statusMissing.host.querySelector('.wa-metro')), ['backend unreachable'], 'missing adapter endpoint')
if (!statusMissing.host.querySelector('[data-wa-station="harvest"]') || !statusMissing.host.querySelector('[data-wa-station="review"]')) {
  fail('a missing status endpoint took the independent stations down')
}
stub.state.throwOn = null
// A later adapter failure keeps the exact last reading and announces staleness, then recovers.
const sourceStale = await mount('en', { openConfig: false })
const priorSourceIds = lineIds(sourceStale)
await openDetail(sourceStale.host, 'line:codex')
const priorCursor = txt(detailOf(sourceStale.host, 'line:codex'))
stub.state.harvestPayload = { ok: false, error: 'source refresh failed', agents: [] }
await click(refreshButton(sourceStale.host), 80)
must(txt(sourceStale.host.querySelector('.wa-metro')), ['source refresh failed'], 'stale source refresh')
if (lineIds(sourceStale) !== priorSourceIds || txt(detailOf(sourceStale.host, 'line:codex')) !== priorCursor) {
  fail('a failed refresh discarded branch facts or the open branch detail')
}
stub.state.harvestPayload = { ok: true, agents: [{ id: 'codex', enabled: true, found: true, cursor: 'recovered-cursor' }] }
await click(refreshButton(sourceStale.host), 80)
must(txt(detailOf(sourceStale.host, 'line:codex')), ['recovered-cursor'], 'recovered adapter cursor')
if (txt(sourceStale.host.querySelector('.wa-metro')).includes('source refresh failed')) fail('the stale source notice survived a successful refresh')
stub.state.harvestPayload = { ok: true, agents: [] }
await click(refreshButton(sourceStale.host), 80)
if (detailOf(sourceStale.host, 'line:codex') || sourceStale.host.querySelector('[data-wa-line][aria-pressed="true"]')) {
  fail('removing the open adapter left its branch detail open')
}
// Harvest station state is the session-harvest role, not another job or an invented healthy default.
for (const [change, expected, state] of [[{ state: 'paused' }, 'Paused', 'paused'], [{ impl_ok: false }, 'Missing target', 'bad'],
  [{ live: false }, 'Not created', null]]) {
  const jobState = jobsState()
  Object.assign(jobState.session_harvest, change)
  const collectorState = await mount('en', { jobs: jobsView(jobState), openConfig: false })
  const station = collectorState.host.querySelector('[data-wa-station="harvest"]')
  if (state && station?.dataset.state !== state) fail(`harvest ${expected}: the station is data-state=${station?.dataset.state}, expected ${state}`)
  if (station?.dataset.state === 'ok') fail(`harvest ${expected}: the station reads ok`)
  must(txt(station) + txt(await openDetail(collectorState.host, 'harvest')), [expected], `harvest ${expected}`)
  if (collectorState.errors.size) fail(`harvest ${expected} threw: ${[...collectorState.errors].join(' | ')}`)
}
const invalidTargetJobs = jobsView(jobsState())
invalidTargetJobs.roles.find(r => r.role === 'session_harvest').target.root_ok = false
const invalidCollector = await mount('en', { jobs: invalidTargetJobs, openConfig: false })
must(txt(invalidCollector.host.querySelector('[data-wa-station="harvest"]')) + txt(await openDetail(invalidCollector.host, 'harvest')),
  ['Not verified'], 'unverified harvest target')
// Exercise the actual 60-second source callback without waiting a minute or replacing its response.
const originalSetInterval = globalThis.setInterval
const sourceTicks = []
let polledSource
try {
  globalThis.setInterval = (fn, ms, ...rest) => {
    if (ms === 60000) sourceTicks.push(fn)
    return originalSetInterval(fn, ms, ...rest)
  }
  polledSource = await mount('en', { openConfig: false })
} finally { globalThis.setInterval = originalSetInterval }
await settle(80)
const sourceReads = stub.calls.gets.filter(path => path === '/harvest/status').length
if (!sourceTicks.length) fail('the line does not poll its readings every 60 seconds')
else {
  const tickAll = async () => { await act(async () => { for (const tick of sourceTicks) await tick() }); await settle(80) }
  stub.state.harvestPayload = { ok: true, agents: [{ id: 'custom-agent', enabled: true, found: false, cursor: 'custom-cursor' }] }
  await tickAll()
  await settle(80)
  if (stub.calls.gets.filter(path => path === '/harvest/status').length <= sourceReads) {
    fail('the timed source poll did not re-read /harvest/status')
  }
  const customNode = polledSource.host.querySelector('[data-wa-line="custom-agent"]')
  must(txt(customNode), ['custom-agent'], 'unknown adapter identity')
  if (customNode?.dataset.state !== 'missing') fail(`an adapter whose folder is not found is data-state=${customNode?.dataset.state}`)
  if (lineIds(polledSource) !== 'custom-agent') fail('the source poll fabricated unreported adapters')
  must(txt(await openDetail(polledSource.host, 'line:custom-agent')), ['custom-cursor'], 'timed source cursor')
  for (const id of ['constructor', '__proto__']) {
    stub.state.harvestPayload = { ok: true, agents: [{ id, enabled: true, found: true, cursor: `cursor-${id}` }] }
    await tickAll()
    const node = polledSource.host.querySelector(`[data-wa-line="${id}"]`)
    must(txt(node), [id], `prototype-named adapter ${id}`)
    if (node?.dataset.state !== 'ok') fail(`prototype-named adapter ${id} is data-state=${node?.dataset.state}`)
    must(txt(await openDetail(polledSource.host, `line:${id}`)), [id, `cursor-${id}`], `prototype-named branch detail ${id}`)
  }
}
for (const view of [jobsDown, allGood, stale, storeDown, partial,
  noAdapters, statusFailed, statusMissing, sourceStale, invalidCollector, polledSource]) {
  if (view.errors.size) fail(`the round-2 views threw: ${[...view.errors].join(' | ')}`)
}

if (problems.length) {
  console.error(`\nrender check FAILED — ${problems.length} problem(s)`)
  process.exitCode = 1
  return
}
console.log('render check OK — registration (page + sidebar) · ONE Metro view (no tab strip, no per-view title, '
  + 'no Nexus map/inspector/wires, no heartbeat strip, no lower queue; History / Settings / station / branch details '
  + 'toggled by aria-pressed, one at a time, folded by a second press) · branch lines = backend adapter facts '
  + '(ok/missing/off/run, cursor, honesty note) · Harvest station live only for an active session-harvest run · '
  + 'read-failed alert keeps the backend reason and never says Good service · Settings holds root · install · jobs · '
  + 'the four engine job roles (closed native job disclosures, 52px summaries, independent zero-request open/close, unchanged expanded controls, explicit disclosure opening before actions; the agent job marked, never created or deleted here) · '
  + 'the review desk (one draft at a time, k of N, Later by identity, actual Markdown heading with summary fallback, faithful readable changes and accessible signs, literal HTML/Markdown and whitespace preserved, exact original diff/Copy behind a closed native disclosure, read-only reason/evidence and projection resets, immediate first-document selection with exactly one read and no writes, selected detail only, distinct-heading out-of-order detail race, disappearing candidate and format approval gates, retained confirmation callbacks invalidated by cancellation or same-ref refresh/rearming, single-use current confirmation, late dry-run refresh invalidation, Approve two-step, Reject with its '
  + 'reason, the engine output kept, one EmptyState, a failed read keeping its error) · root selection '
  + '(ctx.os.pickOpenPath, a cancelled pick is no silent success) · verification · save GATE '
  + '(an invalid root never reads as saved) · candidate scan (counters, SearchField filter, '
  + 'copy/mirror confirmation) · root write surface /automation/* only; staged engine lifecycle /engine/* only · '
  + 'the run log lives once, in History · refresh · one English '
  + 'bundle with no language picker, no raw key and no native title= · external check reasons '
  + 'mapped to English with the raw text kept in the PanelBlock detail block and the Tip label (an '
  + 'unknown one falls back to one neutral label, a backend reason is printed as it arrived) · a '
  + 'failed read that keeps the error the backend returned · a job result as a help card · the schedule '
  + 'as a sentence with its cron beside it, next/last run and a late/missed flag · the visual schedule editor '
  + '(six modes to cron and back, unrepresentable cron kept in Custom, a live backend preview, the '
  + 'refusal shown) · the retired Task Scheduler gone · the '
  + 'reference pass (ONE mono shape across every code/data element, the raw wording in a code body '
  + 'under its caption, both code surfaces copyable through the kit with the right payload, a '
  + 'refusal as a help card with a heading and an action, quiet secondary actions, one circular '
  + 'aria-labelled icon-button shape)')

}

try {
  await runChecks()
} finally {
  // Each fixture owns its mounted roots: unmount to run effect/subscription cleanup, then close jsdom.
  await act(async () => {
    for (const [root, host] of mountedPanels) {
      root.unmount()
      host.remove()
    }
  })
  mountedPanels.clear()
  dom.window.close()
}
