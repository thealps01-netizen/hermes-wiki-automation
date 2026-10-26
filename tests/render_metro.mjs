/**
 * Metro (2.5.0) — the single view, rendered in jsdom with the real React and driven like a user.
 *
 * Run: cd tests && node render_metro.mjs [<plugin.js path>]   (exit code 0 = passed)
 *
 * The contract is `Docs/metro-contract.md`; the states are `metro-states.mjs` (one fixture per state,
 * shared with `preview.mjs` and the Electron gates). What this gate locks:
 *   M1. ONE view: `.wa-metro`, no tab strip (`role="tab"`, `tabs-trigger`), no Nexus / Chronicle /
 *       Folio view and no heartbeat strip (the removed composition cannot crawl back).
 *   M2. Every contract state: the alert bar's `data-alert` priority key and `data-tone`, each
 *       station's and branch line's `data-state`, the open `.wa-metro-detail[data-for]`.
 *   M3. Priority: two conditions at once, the higher key wins (pair by pair, read-failed → good).
 *   M4. `Good service on the whole line` never shows while any read failed; the failed read keeps
 *       the backend's own error.
 *   M5. Every station and branch line carries words (name + text lines), and its aria-label names it.
 *   M6. Every station, line, History and Settings toggles `aria-pressed`, opens its detail and folds
 *       it on a second click; close folds it; only ONE detail is open at a time.
 *   M7. `Ask Hermes to fix these` opens a fresh chat (`host.newChat()`, the panel is a full page with
 *       no chat box on screen) and calls `host.composer.insertText('new', text, { mode: 'block' })`
 *       until that box answers; it never submits; the text lists every finding with its raw line; a
 *       box that never answers shows `The chat box did not open. Start a new chat, then press again.`.
 *   M8. The review desk is one draft at a time (`1 of N`), Approve is two-step (the first press
 *       writes nothing confirmed and opens the dialog with the source-write / model-usage warning),
 *       Reject cannot be sent without a reason.
 *   M9. History is the m-13 list (time, job, what it did, outcome) of the last 24 hours, with
 *       `Show older runs` (re-reads a wider window) and `Full technical log` (the reused run history:
 *       KPIs, window picker, rows). Settings is the m-14 summary (wiki folder, automation files,
 *       working folder) with `Change wiki folder` and `Manage timetable`; the root, the jobs and the
 *       engine install are reached by a click (or open by themselves when they hold a fix).
 * SVG segments and the narrow (vertical) line are LAYOUT facts: `shot.cjs` measures them in Electron.
 */
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { JSDOM } from 'jsdom'
import { ADAPTERS, ASK_HERMES, COMPOSER_MISS, ERRORS, GOOD_SERVICE, PRIORITY, PRIORITY_PAIRS, PROBLEMS, STATES,
  STATIONS, drive, makeRest, target, world } from './metro-states.mjs'

const HERE_URL = new URL('.', import.meta.url)
const HERE = fileURLToPath(HERE_URL).replace(/\\/g, '/') + '/'
const SRC = process.argv.slice(2).find(a => !a.startsWith('--')) || `${HERE}../desktop/plugin.js`
const PLUGIN_ID = 'wiki-automation'
const RAW_KEY = /\b(?:wa|wd)\.[a-z][a-zA-Z.]*/

const problems = []
const fail = m => { problems.push(m); console.error('  x', m) }
let mark = 0
const ok = m => { console.log(problems.length > mark ? '  RED' : '  ok', m, problems.length > mark ? `(${problems.length - mark} problem(s))` : ''); mark = problems.length }

writeFileSync(`${HERE}sdk-metro-stub.mjs`, `
export * from './kit-stub.mjs'

const atom = initial => {
  let value = initial
  const listeners = new Set()
  return { get: () => value, listen: fn => { listeners.add(fn); return () => listeners.delete(fn) },
    set: next => { if (Object.is(next, value)) return; value = next; for (const fn of listeners) fn(next) } }
}
export const composerCalls = { insert: [], submit: [], setDraft: [], newChat: 0 }
export const composerState = { answer: true }
export const host = {
  state: { connectionId: atom('local'), profile: atom('default'), cwd: atom('/srv/wiki') },
  newChat: () => { composerCalls.newChat += 1 },
  composer: {
    insertText: (sessionId, text, opts) => {
      composerCalls.insert.push({ sessionId, text, opts })
      return Promise.resolve(composerState.answer)
    },
    submit: (sessionId, text) => { composerCalls.submit.push({ sessionId, text }); return true },
    setDraft: (sessionId, text) => { composerCalls.setDraft.push({ sessionId, text }); return true },
    focus: () => true
  }
}
const bundles = new Map()
function leaf(tree, key) {
  let node = tree
  for (const part of String(key).split('.')) {
    if (!node || typeof node !== 'object') return undefined
    node = node[part]
  }
  return node
}
export function registerBundles(id, table) { bundles.set(id, table) }
export function resolveKey(id, key, args) {
  const table = bundles.get(id) || {}
  const value = leaf(table.en, key)
  if (typeof value === 'function') return value(...args)
  return value ?? key
}
export function usePluginI18n(id) { return (key, ...args) => resolveKey(id, key, args) }
export function translateNow(key) { return key }
export function useI18n() { return { t: key => key } }
export default { host: { notify: () => {}, notifyError: () => {} }, haptic: () => {},
  relativeTime: () => '2 hours ago', EmptyState: null }
`)
writeFileSync(`${HERE}plugin-metro-under-test.mjs`,
  readFileSync(SRC, 'utf8').replace("'@hermes/plugin-sdk'", `'${HERE_URL.href}sdk-metro-stub.mjs'`))

const dom = new JSDOM('<!doctype html><html><body></body></html>', { pretendToBeVisual: true })
global.window = dom.window
global.document = dom.window.document
Object.defineProperty(global, 'navigator', { value: dom.window.navigator, configurable: true })
global.IS_REACT_ACT_ENVIRONMENT = true
// jsdom has no layout: a ResizeObserver that never fires is the honest stand-in (the segments are an
// Electron fact). Without it a panel that observes its map would throw on mount.
if (!dom.window.ResizeObserver) {
  dom.window.ResizeObserver = global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
}
if (!dom.window.matchMedia) {
  dom.window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {} })
}

const React = await import('react')
const { createRoot } = await import('react-dom/client')
const { act } = React.act ? React : await import('react-dom/test-utils')
// A test file runs for minutes and keeps earlier panels mounted, so their real 60-second polls would land in
// the shared call log at wall-clock-dependent moments and race every read-count assertion. Polls of a minute
// or longer never fire on their own here; a test that needs one captures its callback and calls it.
const realSetInterval = globalThis.setInterval
globalThis.setInterval = (fn, ms, ...rest) => (Number(ms) >= 60000 ? realSetInterval(() => {}, ms) : realSetInterval(fn, ms, ...rest))
const stub = await import(`${HERE_URL.href}sdk-metro-stub.mjs`)

const txt = el => (el?.textContent || '').replace(/\s+/g, ' ').trim()
const settle = (ms = 80) => act(async () => { await new Promise(r => setTimeout(r, ms)) })
const click = async (el, ms = 60) => {
  if (!el) { fail('the control to click was not found'); return }
  await act(async () => {
    el.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }))
    await new Promise(r => setTimeout(r, ms))
  })
}
const setField = async (el, value) => {
  await act(async () => {
    const proto = el.tagName === 'TEXTAREA' ? dom.window.HTMLTextAreaElement.prototype : dom.window.HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value)
    el.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
    await new Promise(r => setTimeout(r, 20))
  })
}
const api = { click }
const guard = async (label, fn) => {
  try { await fn() } catch (e) { fail(`${label}: the check could not run to the end: ${e.message}`) }
}
const buttons = (scope, label) => [...(scope?.querySelectorAll('button') || [])].filter(b => txt(b) === label
  || (b.getAttribute('aria-label') || '') === label)

let version = 0
let mounted = null
async function mount(w, opts = {}) {
  if (mounted) { await act(async () => mounted.root.unmount()); mounted.host.remove(); mounted = null }
  stub.composerCalls.insert.length = 0
  stub.composerCalls.submit.length = 0
  stub.composerCalls.setDraft.length = 0
  stub.composerCalls.newChat = 0
  stub.composerState.answer = opts.composer === undefined ? true : opts.composer
  const registrations = []
  const ctx = {
    rest: makeRest(w, opts),
    os: { pickOpenPath: () => Promise.resolve('/srv/wiki/.llm-wiki/project.json') },
    i18n: { t: (key, ...args) => stub.resolveKey(PLUGIN_ID, key, args),
      register: table => stub.registerBundles(PLUGIN_ID, table) },
    register: r => registrations.push(r)
  }
  const mod = await import(`${HERE_URL.href}plugin-metro-under-test.mjs?v=${++version}`)
  mod.default.register(ctx)
  const page = registrations.find(r => r.area === 'routes')
  if (!page) throw new Error('no page registration')
  const host = document.createElement('div')
  document.body.appendChild(host)
  const errors = []
  const root = createRoot(host, { onUncaughtError: e => errors.push(String(e?.message || e)),
    onRecoverableError: e => errors.push(String(e?.message || e)) })
  await act(async () => { root.render(React.createElement(page.render)) })
  await settle(120)
  mounted = { root, host, errors, w }
  return mounted
}

const metro = host => host.querySelector('.wa-metro')
const bar = host => host.querySelector('.wa-metro-bar')
const details = host => [...host.querySelectorAll('.wa-metro-detail')]
const station = (host, id) => host.querySelector(`[data-wa-station="${id}"]`)
const line = (host, id) => host.querySelector(`[data-wa-line="${id}"]`)
const pressedOf = el => (el?.tagName === 'BUTTON' ? el : el?.querySelector('button') || el)?.getAttribute('aria-pressed')

/** M1 — the removed composition is absent from any rendered state. */
function noOldShape(host, label) {
  if (!metro(host)) fail(`${label}: no .wa-metro root`)
  if (host.querySelectorAll('.wa-metro').length > 1) fail(`${label}: more than one .wa-metro root`)
  if (host.querySelector('[role="tab"], [role="tablist"], [data-slot="tabs-trigger"], [data-slot="tabs-list"]')) {
    fail(`${label}: a tab strip is back (the four tabs were removed in 2.5.0)`)
  }
  if (host.querySelector('.nx-map, .nx-node, .nx-inspector, .nx-queue, .nx-lower, .nx-wires, .wa-hb-row, .wa-heartbeat')) {
    fail(`${label}: a Nexus node, inspector, lower queue or heartbeat strip is back`)
  }
  const words = txt(host)
  for (const gone of ['Nexus', 'Chronicle', 'Folio']) {
    if (new RegExp(`\\b${gone}\\b`).test(words)) fail(`${label}: the removed view name ${gone} is on screen`)
  }
  if (RAW_KEY.test(words)) fail(`${label}: a raw i18n key reached the screen: ${words.match(RAW_KEY)[0]}`)
  if (host.querySelector('[title]')) fail(`${label}: a native title= reached the DOM`)
  if (details(host).length > 1) fail(`${label}: ${details(host).length} details are open at once`)
}

/** M5 — every station and branch line carries words a non-programmer can read. */
function wordsOnMarks(host, label) {
  const named = [...STATIONS.map(s => [station(host, s.id), s.name, `station ${s.id}`]),
    ...ADAPTERS.map(a => [line(host, a.id), a.name, `line ${a.id}`])]
  for (const [el, name, what] of named) {
    if (!el) { fail(`${label}: ${what} is missing`); continue }
    const shown = txt(el)
    const button = el.tagName === 'BUTTON' ? el : el.querySelector('button')
    const aria = button?.getAttribute('aria-label') || ''
    if (!button) fail(`${label}: ${what} is not a button`)
    if (!shown.includes(name)) fail(`${label}: ${what} does not show its name ${JSON.stringify(name)}: ${JSON.stringify(shown)}`)
    // A station always explains itself; a healthy branch line is its name alone (m-01, contract § States),
    // and any other branch state must say what is wrong in words.
    const needsNote = what.startsWith('station') || el.dataset.state !== 'ok'
    if (needsNote && !/[A-Za-z]{3,}/.test(shown.replace(name, ''))) {
      fail(`${label}: ${what} carries no words beyond its name (a mark needs plain text): ${JSON.stringify(shown)}`)
    }
    if (!needsNote && aria.trim() === name) fail(`${label}: ${what} aria-label does not say the line is collecting`)
    if (/^[\W\d_]*$/.test(shown) || /^[A-Z]{1,2}$/.test(shown)) fail(`${label}: ${what} is a code, not words`)
    if (!aria.includes(name)) fail(`${label}: ${what} aria-label does not name it: ${JSON.stringify(aria)}`)
    if (station(host, 'harvest') === el && aria.trim() === name) fail(`${label}: ${what} aria-label lacks its text lines`)
  }
}

function expectState(name, host) {
  const s = STATES[name]
  const e = s.expect
  const label = `state ${name}${s.mock ? ` (${s.mock})` : ''}`
  noOldShape(host, label)
  const b = bar(host)
  if (e.skeleton) {
    if (!host.querySelector('.wa-metro-skeleton')) fail(`${label}: no .wa-metro-skeleton while every read is pending`)
    if (txt(host).includes(GOOD_SERVICE)) fail(`${label}: says good service before anything was read`)
    if (b && e.notAlert?.includes(b.dataset.alert)) fail(`${label}: the bar claims ${b.dataset.alert} while loading`)
    return
  }
  if (host.querySelector('.wa-metro-skeleton')) fail(`${label}: the loading skeleton stayed after the reads arrived`)
  const bars = host.querySelectorAll('.wa-metro-bar').length
  if (bars !== (e.bar ?? 1)) fail(`${label}: ${bars} alert bars (expected ${e.bar ?? 1})`)
  if (e.noMap && host.querySelector('.wa-metro-station, .wa-metro-wire, [data-wa-line]')) {
    fail(`${label}: a line is drawn although the timetable could not be read (m-12 shows the title only)`)
  }
  if (b) expectBar(b, e, label)
  stationsAndRest(host, s, e, label)
}

function expectBar(b, e, label) {
  if (!PRIORITY.includes(b.dataset.alert)) fail(`${label}: data-alert ${JSON.stringify(b.dataset.alert)} is not a priority key`)
  if (!['ok', 'ask', 'warn', 'bad'].includes(b.dataset.tone)) fail(`${label}: data-tone ${JSON.stringify(b.dataset.tone)}`)
  if (e.alert && b.dataset.alert !== e.alert) fail(`${label}: data-alert is ${b.dataset.alert}, expected ${e.alert}`)
  if (e.notAlert?.includes(b.dataset.alert)) fail(`${label}: data-alert must not be ${b.dataset.alert}`)
  if (e.tone && b.dataset.tone !== e.tone) fail(`${label}: data-tone is ${b.dataset.tone}, expected ${e.tone}`)
  if ((b.dataset.alert === 'good') !== txt(b).includes(GOOD_SERVICE)) {
    fail(`${label}: "${GOOD_SERVICE}" and data-alert="good" disagree: ${JSON.stringify(txt(b))}`)
  }
  if (b.querySelectorAll('button').length > 1) fail(`${label}: the alert bar has more than one button`)
}

function stationsAndRest(host, s, e, label) {
  for (const [id, want] of Object.entries(e.stations || {})) {
    const got = station(host, id)?.dataset.state
    if (got !== want) fail(`${label}: station ${id} data-state=${got}, expected ${want}`)
  }
  for (const [id, want] of Object.entries(e.lines || {})) {
    const got = line(host, id)?.dataset.state
    if (got !== want) fail(`${label}: line ${id} data-state=${got}, expected ${want}`)
  }
  for (const words of e.text || []) if (!txt(host).includes(words)) fail(`${label}: missing text ${JSON.stringify(words)}`)
  if (e.noGood && txt(host).includes(GOOD_SERVICE)) fail(`${label}: good service shown while a read failed`)
  const open = details(host)
  const scope = open[0] || host
  for (const words of e.notText || []) {
    if (txt(scope).includes(words)) fail(`${label}: ${open[0] ? 'the open detail' : 'the panel'} says ${JSON.stringify(words)}`)
  }
  for (const [role, want] of Object.entries(e.runs || {})) {
    const got = scope.querySelector(`.wa-metro-run[data-role="${role}"]`)?.dataset.outcome
    if (got !== want) fail(`${label}: run ${role} data-outcome=${got}, expected ${want}`)
  }
  if (e.detail) {
    if (open.length !== 1 || open[0].dataset.for !== e.detail) {
      fail(`${label}: open detail is ${open.map(d => d.dataset.for).join(',') || 'none'}, expected ${e.detail}`)
    }
    const opener = target(host, s.open)
    if (pressedOf(opener) !== 'true') fail(`${label}: ${s.open} is not aria-pressed while its detail is open`)
  } else if (open.length) fail(`${label}: a detail is open without a click: ${open[0].dataset.for}`)
  if (e.dialog) {
    const dialog = host.querySelector('[role="dialog"]')
    if (!dialog) fail(`${label}: Approve did not open its confirmation dialog`)
    const words = txt(dialog)
    if (!/raw\/sources/.test(words) || !/model usage|credit/i.test(words)) {
      fail(`${label}: the approve dialog lost its source-write and model-usage warning: ${JSON.stringify(words)}`)
    }
    const confirmed = mounted.w.calls.posts.filter(p => ['/candidates/act', '/owner/decision'].includes(p.path) && p.body?.confirm)
    if (confirmed.length) fail(`${label}: the first Approve sent a confirmed write`)
  }
  if (!e.noMap) wordsOnMarks(host, label)
}

// ── M1 · M2 · M5 — one fixture per contract state ──────────────────────────────────────────────
mark = problems.length; console.log('M2 contract states')
for (const name of Object.keys(STATES)) {
  const w = world(STATES[name].conditions)
  const { host, errors } = await mount(w)
  await drive(name, host, api).catch(e => fail(`state ${name}: ${e.message}`))
  await settle(60)
  expectState(name, host)
  for (const e of errors) fail(`state ${name}: React error ${e}`)
}
ok(`${Object.keys(STATES).length} states rendered and checked`)

// ── M3 — two conditions at once: the higher priority wins ─────────────────────────────────────
mark = problems.length; console.log('M3 alert priority')
for (const [winner, loser, conditions] of PRIORITY_PAIRS) {
  if (PRIORITY.indexOf(winner) >= PRIORITY.indexOf(loser)) fail(`fixture: ${winner} is not above ${loser}`)
  const { host } = await mount(world(conditions))
  const got = bar(host)?.dataset.alert
  if (got !== winner) fail(`priority: ${winner} + ${loser} → data-alert=${got}, expected ${winner}`)
  if (conditions.engineUpdate && winner !== 'engine'
    && !host.querySelector('.wa-metro-notice[data-engine-banner="update"]')) {
    fail(`priority: ${winner} + an engine update shows no "Engine update ready" notice`)
  }
}
ok(`${PRIORITY_PAIRS.length} priority pairs`)

// ── M4 — good service never while a read failed ───────────────────────────────────────────────
mark = problems.length; console.log('M4 failed reads')
for (const path of ['/jobs', '/candidates', '/harvest/status', '/automation', '/health/jobs', '/health/watchdog',
  '/engine/status']) {
  for (const mode of ['answer', 'throw']) {
    const w = world(mode === 'answer' ? { readFailed: path } : {})
    const { host } = await mount(w, mode === 'throw' ? { throwOn: path } : {})
    if (!w.calls.gets.some(p => p.split('?')[0] === path)) {
      console.log(`  - ${path}: the panel does not read it on its first screen (skipped)`)
      break
    }
    const label = `read ${path} (${mode})`
    const b = bar(host)
    if (b?.dataset.alert !== 'read-failed') fail(`${label}: data-alert=${b?.dataset.alert}, expected read-failed`)
    if (b?.dataset.tone !== 'bad') fail(`${label}: data-tone=${b?.dataset.tone}, expected bad`)
    if (txt(host).includes(GOOD_SERVICE)) fail(`${label}: "${GOOD_SERVICE}" shown while a read failed`)
    let words = txt(host)
    if (!words.includes(ERRORS[path])) {
      const act = b?.querySelector('button')
      if (act) { await click(act); words = txt(host) }
    }
    if (!words.includes(ERRORS[path])) fail(`${label}: the backend error is not kept: ${JSON.stringify(ERRORS[path])}`)
  }
}

// ── M6 — aria-pressed toggles, a second click folds, one detail at a time ─────────────────────
mark = problems.length; console.log('M6 details')
await guard('M6', async () => {
  const w = world({ drafts: 2, problems: true })
  const { host } = await mount(w)
  const openers = [...STATIONS.map(s => s.id), ...ADAPTERS.map(a => `line:${a.id}`), 'history', 'settings']
  let previous = null
  for (const what of openers) {
    const el = target(host, what)
    if (!el) { fail(`toggle: ${what} has no control`); continue }
    if (pressedOf(el) !== 'false') fail(`toggle: ${what} must start aria-pressed="false" (got ${pressedOf(el)})`)
    const mapBefore = host.querySelector('.wa-metro-map')
    await click(el)
    const open = details(host)
    if (open.length !== 1 || open[0].dataset.for !== what) {
      fail(`toggle: ${what} opened ${open.map(d => d.dataset.for).join(',') || 'nothing'}`)
    }
    if (pressedOf(target(host, what)) !== 'true') fail(`toggle: ${what} is not aria-pressed="true" when open`)
    if (previous && pressedOf(target(host, previous)) !== 'false') fail(`toggle: ${previous} stayed pressed after ${what}`)
    if (host.querySelector('.wa-metro-map') !== mapBefore) fail(`toggle: opening ${what} re-mounted the map`)
    if (open[0] && host.querySelector('.wa-metro-map')?.contains(open[0])) fail(`toggle: ${what} expanded inside the map`)
    previous = what
  }
  const last = openers.at(-1)
  await click(target(host, last))
  if (details(host).length) fail(`toggle: a second click on ${last} did not fold its detail`)
  if (pressedOf(target(host, last)) !== 'false') fail(`toggle: ${last} stayed pressed after folding`)
  await click(target(host, 'wiki'))
  const close = details(host)[0]?.querySelector('button[aria-label^="Close"], button[aria-label*="close" i]')
  if (!close) fail('toggle: the detail head has no close button (aria-label "Close …")')
  else {
    await click(close)
    if (details(host).length) fail('toggle: the close button did not fold the detail')
    if (pressedOf(target(host, 'wiki')) !== 'false') fail('toggle: wiki stayed pressed after close')
  }
  const alertButton = bar(host)?.querySelector('button')
  if (!alertButton) fail('toggle: the drafts alert has no button')
  else {
    await click(alertButton)
    if (details(host)[0]?.dataset.for !== 'review') fail(`toggle: the drafts alert opened ${details(host)[0]?.dataset.for}`)
  }
  const nav = ['history', 'settings'].map(id => host.querySelector(`[data-wa-nav="${id}"]`))
  for (const el of nav) {
    if (!el?.getAttribute('aria-label')) fail(`header: ${el?.dataset.waNav || 'a nav button'} has no aria-label`)
  }
})

// ── M7 — Ask Hermes: insert, never submit ─────────────────────────────────────────────────────
mark = problems.length; console.log('M7 composer')
for (const answer of [true, false]) {
  const { host } = await mount(world({ problems: true }), { composer: answer })
  await click(target(host, 'wiki'))
  const detail = details(host)[0]
  const askBtn = buttons(detail, ASK_HERMES)[0]
  if (!askBtn) { fail(`composer: no "${ASK_HERMES}" button in the wiki detail`); continue }
  for (const f of PROBLEMS) {
    if (!txt(detail).includes(f.title) && !txt(detail).includes(f.en || '')) {
      fail(`composer: the wiki detail does not list the finding ${JSON.stringify(f.title)} in English`)
    }
  }
  await click(askBtn, answer ? 400 : 7000)
  const calls = stub.composerCalls
  if (calls.submit.length) fail('composer: the panel SUBMITTED to the chat (it must only insert)')
  if (calls.setDraft.length) fail('composer: the panel replaced the draft (it must insert)')
  if (calls.newChat !== 1) fail(`composer: newChat called ${calls.newChat} times (the page has no chat box of its own)`)
  if (answer && calls.insert.length !== 1) fail(`composer: insertText called ${calls.insert.length} times`)
  if (!answer && calls.insert.length < 2) fail('composer: a box that did not answer yet was not asked again')
  if (calls.insert.some(c => c.sessionId !== 'new')) fail('composer: an insert went to another chat than the new one')
  const call = calls.insert[0]
  if (call) {
    if (call.sessionId !== 'new') fail(`composer: insertText session is ${JSON.stringify(call.sessionId)}, expected 'new'`)
    if (call.opts?.mode !== 'block') fail(`composer: insertText mode is ${JSON.stringify(call.opts?.mode)}, expected block`)
    for (const f of PROBLEMS) {
      if (!call.text.includes(f.raw)) fail(`composer: the request lacks the raw line of ${f.kind}`)
    }
    if (!/fix/i.test(call.text)) fail('composer: the request does not ask Hermes to fix the findings')
    const paths = call.text.match(/(?:[A-Za-z]:)?\/[\w.-]+(?:\/[\w.-]+)+/g) || []
    for (const p of paths) {
      if (!PROBLEMS.some(f => f.raw.includes(p))) fail(`composer: the request cites a path no finding carries: ${p}`)
    }
  }
  const miss = txt(host).includes(COMPOSER_MISS)
  if (answer && miss) fail('composer: the "open a chat" note shows although the insert succeeded')
  if (!answer && !miss) fail(`composer: a false insert does not show "${COMPOSER_MISS}"`)
}

// ── M8 — the review desk ─────────────────────────────────────────────────────────────────────
mark = problems.length; console.log('M8 review desk')
await guard('M8', async () => {
  const w = world({ drafts: 3 })
  const { host } = await mount(w)
  await click(target(host, 'review'))
  const desk = () => details(host).find(d => d.dataset.for === 'review')
  if (!txt(desk()).includes('1 of 3')) fail('review: the desk does not say "1 of 3"')
  if (buttons(desk(), 'Approve').length !== 1) fail(`review: ${buttons(desk(), 'Approve').length} Approve buttons (one draft at a time)`)
  for (const label of ['Reject', 'Later']) if (buttons(desk(), label).length !== 1) fail(`review: no single ${label} button`)
  const first = w.candidates[0]
  if (!txt(desk()).includes(first.target)) fail('review: "Will be saved as <path>" does not name the draft target')
  const nav = label => desk()?.querySelector(`button[aria-label="${label}"]`)
  if (!nav('Previous draft') || !nav('Next draft')) fail('review: the desk has no Previous / Next draft buttons')
  else {
    if (!nav('Previous draft').disabled) fail('review: Previous draft is enabled on the first draft')
    const postsBefore = w.calls.posts.length
    await click(nav('Next draft'))
    if (!txt(desk()).includes('2 of 3')) fail('review: Next draft did not move to "2 of 3"')
    await click(nav('Previous draft'))
    if (!txt(desk()).includes('1 of 3')) fail('review: Previous draft did not move back to "1 of 3"')
    if (w.calls.posts.length !== postsBefore) fail('review: Previous / Next sent a request that writes')
  }
  const evidence = [...(desk()?.querySelectorAll('details') || [])].find(d => /Show the change and the evidence/.test(txt(d.querySelector('summary'))))
  if (!evidence) fail('review: "Show the change and the evidence" disclosure is missing')
  else if (evidence.open) fail('review: "Show the change and the evidence" is open by default')
  await click(buttons(desk(), 'Later')[0])
  if (!txt(desk()).includes('2 of 3')) fail('review: Later did not move to the next draft')
  // The fixture's update draft carries a format problem, so its Approve must stay locked; the retire draft is clean.
  if (!buttons(desk(), 'Approve')[0]?.disabled) fail('review: a draft with format problems can be approved')
  await click(buttons(desk(), 'Later')[0])
  if (!txt(desk()).includes('3 of 3')) fail('review: Later did not move to the third draft')
  await click(buttons(desk(), 'Approve')[0], 160)
  const unconfirmed = w.calls.posts.filter(p => ['/candidates/act', '/owner/decision'].includes(p.path))
  if (unconfirmed.some(p => p.body?.confirm)) fail('review: the first Approve was a confirmed write')
  const dialog = host.querySelector('[role="dialog"]')
  if (!dialog) fail('review: Approve did not open the ConfirmDialog')
  else {
    if (!/raw\/sources/.test(txt(dialog)) || !/model usage|credit/i.test(txt(dialog))) {
      fail('review: the ConfirmDialog lost its source-write and model-usage warning')
    }
    await click(dialog.querySelector('[data-slot="confirm-confirm"]'), 200)
    const confirmed = w.calls.posts.filter(p => ['/candidates/act', '/owner/decision'].includes(p.path) && p.body?.confirm)
    if (confirmed.length !== 1) fail(`review: confirming sent ${confirmed.length} confirmed writes`)
  }
  await settle(120)
  const rejectBtn = buttons(desk(), 'Reject')[0]
  await click(rejectBtn)
  const reason = desk()?.querySelector('textarea, input[type="text"], input:not([type])')
  const send = () => [...(desk()?.querySelectorAll('button') || [])].find(b => /^(Reject|Send|Confirm reject)/.test(txt(b)) && b !== rejectBtn)
    || buttons(desk(), 'Reject')[0]
  if (!reason) fail('review: Reject asks for no reason')
  else {
    const posts = w.calls.posts.length
    if (send() && !send().disabled) await click(send())
    if (w.calls.posts.slice(posts).some(p => p.body?.action === 'reject' && !String(p.body?.reason || '').trim())) {
      fail('review: a reject was sent without a reason')
    }
    await setField(reason, 'duplicates an existing page')
    if (send()?.disabled) fail('review: the reject stays disabled with a reason typed')
  }
})

await guard('M8 unreadable draft', async () => {
  const w = world({ drafts: 3, unreadableDraft: true, engineUpdate: true })
  const { host } = await mount(w)
  await click(target(host, 'review'))
  await settle(60)
  const desk = details(host).find(d => d.dataset.for === 'review')
  const card = desk?.querySelector('article')
  if (!txt(card).includes('This draft could not be read')) fail('review: the unreadable draft does not say so on its card')
  if (!buttons(desk, 'Approve')[0]?.disabled) fail('review: an unreadable draft can be approved')
  if (buttons(desk, 'Reject')[0]?.disabled !== false) fail('review: an unreadable draft cannot be rejected')
  if (card?.querySelector('.wa-desk-kind')) fail('review: an unreadable draft still shows a kind chip')
})

await guard('M8 draft approval would refuse', async () => {
  const w = world({ drafts: 1, refusal: true })
  const { host } = await mount(w)
  await click(target(host, 'review'))
  await settle(60)
  const desk = details(host).find(d => d.dataset.for === 'review')
  if (!txt(desk).includes('This draft cannot be approved as written')) fail('review: the approval refusal is not shown before Approve')
  if (!buttons(desk, 'Approve')[0]?.disabled) fail('review: a draft that approval refuses can be approved')
  if (buttons(desk, 'Reject')[0]?.disabled !== false) fail('review: a draft that approval refuses cannot be rejected')
})

// ── M9 — History and Settings hold the reused components ──────────────────────────────────────
mark = problems.length; console.log('M9 history and settings')
await guard('M9', async () => {
  const { host } = await mount(world({ richHistory: true }))
  await click(target(host, 'history'))
  const h = details(host)[0]
  if (!/History/.test(txt(h?.querySelector('h2, h3, [class*="head"]')))) fail('history: the detail head is not "History …"')
  if (!/History · last 24 hours · \d+ runs?/.test(txt(h?.querySelector('h2')))) fail(`history: the head is not "History · last 24 hours · N runs": ${txt(h?.querySelector('h2'))}`)
  const runRows = h?.querySelectorAll('.wa-metro-run') || []
  if (!runRows.length) fail('history: no run rows (time · job · what it did · outcome)')
  for (const row of runRows) {
    if (!row.querySelector('.wa-metro-run-at') || !row.querySelector('.wa-metro-run-what strong')
      || !txt(row.querySelector('.wa-metro-run-out'))) fail(`history: a run row lacks its time, job or outcome: ${txt(row)}`)
  }
  if (h?.querySelector('.pa-root')) fail('history: the technical log is open before it is asked for')
  if (buttons(h, 'Show older runs').length !== 1) fail('history: no "Show older runs" button')
  if (buttons(h, 'Full technical log').length !== 1) fail('history: no "Full technical log" button')
  const w0 = mounted.w.calls.gets.length
  await click(buttons(h, 'Show older runs')[0], 120)
  if (!mounted.w.calls.gets.slice(w0).some(g => /\/health\/jobs\?window=7d/.test(g))) fail('history: "Show older runs" did not read the last 7 days')
  if (!/History · last 7 days/.test(txt(details(host)[0]?.querySelector('h2')))) fail('history: the head did not move to the last 7 days')
  await click(buttons(details(host)[0], 'Full technical log')[0], 160)
  const full = details(host)[0]
  if (!full?.querySelector('[aria-pressed], [data-slot="segmented-control"]')) fail('history: the technical log has no window picker')
  if (!full?.querySelector('.pa-root, .pa-log, [data-run-id], .pa-row')) fail('history: the technical log shows no run rows')
  await click(target(host, 'settings'))
  const s = details(host)[0]
  if (s?.dataset.for !== 'settings') fail('settings: the detail did not switch to settings')
  for (const label of ['Wiki folder', 'Automation files', 'Working folder']) {
    if (!txt(s).includes(label)) fail(`settings: the summary lacks "${label}"`)
  }
  for (const label of ['Change wiki folder', 'Manage timetable']) {
    if (buttons(s, label).length !== 1) fail(`settings: no "${label}" button`)
  }
  const shownSec = id => { const el = s?.querySelector(`[data-sec="${id}"]`); return Boolean(el) && !el.hidden }
  if (shownSec('root') || shownSec('jobs') || shownSec('install')) fail('settings: a section is open on a healthy line before its button is pressed')
  await click(buttons(s, 'Manage timetable')[0])
  if (!shownSec('jobs') || !s?.querySelector('[data-sec="jobs"] .wa-job')) fail('settings: "Manage timetable" did not open the scheduled jobs (JobsCard)')
  await click(buttons(s, 'Change wiki folder')[0])
  if (!shownSec('root') || !/Wiki folder|wiki folder|project root|Root/i.test(txt(s.querySelector('[data-sec="root"]')))) fail('settings: "Change wiki folder" did not open the RootCard')
  await click(s?.querySelector('.wa-metro-linkbtn'))
  if (!shownSec('install') || !/engine|Engine/.test(txt(s.querySelector('[data-sec="install"]')))) fail('settings: the automation files value did not open the engine install (InstallCard)')
})

// ── M10 — the sphere (2.11.0): home and Wiki detail, its read never raises the alert bar ─────────
mark = problems.length; console.log('M10 the sphere')
await guard('M10', async () => {
  const globe = host => host.querySelector('.wa-globe')
  let { host } = await mount(world({}))
  if (globe(host)?.dataset.waGlobe !== 'ready') fail(`sphere: the healthy home screen shows no ready sphere: ${globe(host)?.dataset.waGlobe}`)
  if (!/Every page your wiki links to exists\./.test(txt(globe(host)))) fail('sphere: the healthy wiki does not say every linked page exists')
  if (!/334 pages · \d+ changed this week/.test(txt(globe(host)))) fail(`sphere: the page count is not read from /wiki/map: ${txt(globe(host))}`)
  const canvas = globe(host)?.querySelector('canvas.wa-globe-canvas[role="img"]')
  if (!/sphere of 334 dots/.test(canvas?.getAttribute('aria-label') || '')) fail('sphere: the canvas is not a labelled image of every page')
  await click(station(host, 'harvest'))
  if (globe(host)) fail('sphere: it stays on screen while another detail is open')
  ;({ host } = await mount(world({ problems: true })))
  const miss = [...(globe(host)?.querySelectorAll('button.wa-globe-miss') || [])]
  if (miss.length !== 3) fail(`sphere: ${miss.length} missing-page buttons, expected 3`)
  if (!/3 pages your wiki links to do not exist yet\./.test(txt(globe(host)))) fail('sphere: the missing-page heading is wrong')
  if (!/4 pages name them\./.test(txt(globe(host)))) fail('sphere: the naming-page count is wrong')
  if (!txt(miss[0]).includes('hermes-standing-behaviour-rules') || !/named by 2 pages/.test(txt(miss[0]))) fail(`sphere: the first missing page is wrong: ${txt(miss[0])}`)
  if (miss[0]?.getAttribute('aria-pressed') !== 'false') fail('sphere: a missing page is not a pressable button')
  await click(miss[0])
  if (globe(host)?.querySelector('button.wa-globe-miss')?.getAttribute('aria-pressed') !== 'true') fail('sphere: pressing a missing page does not pick it out')
  await click(globe(host)?.querySelector('button.wa-globe-miss'))
  if (globe(host)?.querySelector('button.wa-globe-miss')?.getAttribute('aria-pressed') !== 'false') fail('sphere: a second press does not let go')
  await click(station(host, 'wiki'))
  if (!details(host)[0]?.querySelector('.wa-metro-dbody > .wa-globe[data-wa-globe="ready"]')) fail('sphere: the Wiki detail does not open with the sphere')
  if (host.querySelectorAll('.wa-globe').length !== 1) fail('sphere: more than one sphere on screen')
  ;({ host } = await mount(world({ readFailed: ['/wiki/map'] })))
  if (globe(host)?.dataset.waGlobe !== 'unread') fail('sphere: a failed /wiki/map read is not shown inside its card')
  if (!txt(globe(host)).includes('read failed: /wiki/map')) fail('sphere: the failed read lost the backend error')
  if (bar(host)?.dataset.alert !== 'good') fail(`sphere: a failed /wiki/map read raised the alert bar: ${bar(host)?.dataset.alert}`)
})

if (mounted) { await act(async () => mounted.root.unmount()); mounted = null }
if (problems.length) {
  console.error(`METRO RENDER: ${problems.length} problem(s)`)
  process.exit(1)
}
console.log('METRO RENDER: passed — one view, every contract state, priority pairs, failed reads, details, '
  + 'composer insert-only, review desk two-step, history and settings reached by a click')
process.exit(0)
