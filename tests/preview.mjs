/**
 * Wiki Automation panel — LIVE preview pages, one per Metro state, for the Electron gates and for eyes.
 *
 * Why live: Metro's line segments are SVG paths computed from `getBoundingClientRect` after layout
 * (Docs/metro-contract.md § Screen). A page serialised from jsdom carries jsdom's zero-sized boxes, so a
 * static snapshot would show — and the gates would measure — segments the app never draws. Each page
 * here boots the REAL panel in the page: React's UMD build, `kit-stub.mjs` (the kit's class strings),
 * the panel source and the state's fixture world (`metro-states.mjs`) travel inside the HTML as
 * `data:` modules behind an import map, so the file opens from disk with no server and no bundler.
 * When the panel has settled after the state's clicks it sets `<html data-wa-ready="1">`.
 *
 * Colors are not copied: the app's compiled stylesheet, its theme file and its dark-mode block are
 * embedded as the app loads them (the kit styles itself with Tailwind classes compiled into the app).
 *
 * Run: cd tests && node preview.mjs [<plugin.js path>] [--state=<name>] [--glass]
 *   no --state  -> every Metro state: preview-metro-<state>.html (good, problems, wiki, harvest, branch,
 *                  running, drafts, approve, harvest-failed, branch-missing, loading, read-failed, history,
 *                  settings, …) plus the two reused-component pages below
 *   --state=settings-setup  Settings with a refused verification, the SAME-ID candidate armed (the
 *                  filled destructive copy/mirror write) and a job delete armed: the destructive-contrast
 *                  fixture the 2.3.x `preview.html` carried
 *   --state=schedule        Settings with the Watch Dog schedule editor on WEEKLY (Mon + Thu 08:15)
 * Measuring: shot.cjs / shot_health.cjs / scroll_check.cjs / pill_check.cjs (see README).
 */
import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'
import { DESKTOP_APP } from './env.mjs'
import { STATES } from './metro-states.mjs'

const HERE_URL = new URL('.', import.meta.url)
const HERE = fileURLToPath(HERE_URL).replace(/\\/g, '/') + '/'
const SRC = process.argv.slice(2).find(a => !a.startsWith('--')) || `${HERE}../desktop/plugin.js`
const THEME = `${HERE}_theme_preview.css`
const APP_STYLES = `${DESKTOP_APP}/src/styles.css`
const GLASS = process.argv.includes('--glass')
const EXTRA = ['settings-setup', 'schedule']
const ONE = (process.argv.find(a => a.startsWith('--state=')) || '').split('=')[1] || ''
if (ONE && !Object.hasOwn(STATES, ONE) && !EXTRA.includes(ONE)) {
  throw new Error(`Unknown preview state: ${ONE} (known: ${[...Object.keys(STATES), ...EXTRA].join(', ')})`)
}
const WANTED = ONE ? [ONE] : [...Object.keys(STATES), ...EXTRA]

const require = createRequire(import.meta.url)
const React = require('react')
const pkgDir = name => require.resolve(`${name}/package.json`).replace(/package\.json$/, '')
const REACT_UMD = readFileSync(`${pkgDir('react')}umd/react.production.min.js`, 'utf8')
const REACT_DOM_UMD = readFileSync(`${pkgDir('react-dom')}umd/react-dom.production.min.js`, 'utf8')

const b64 = text => `data:text/javascript;base64,${Buffer.from(text, 'utf8').toString('base64')}`
const source = name => readFileSync(`${HERE}${name}`, 'utf8')
const bare = text => text
  .replace(/'\.\/kit-stub\.mjs'/g, "'wa-kit'")
  .replace(/'\.\/fixture\.mjs'/g, "'wa-fixture'")
  .replace(/'\.\/fixture-health\.mjs'/g, "'wa-fixture-health'")
  .replace(/'\.\/metro-states\.mjs'/g, "'wa-states'")

const reactNames = Object.keys(React).filter(k => /^[A-Za-z_$][\w$]*$/.test(k) && k !== 'default')
const MODULES = {
  react: `const R = window.React\nexport default R\nexport const { ${reactNames.join(', ')} } = R\n`,
  'react/jsx-runtime': [
    "import R from 'react'",
    'export const Fragment = R.Fragment',
    'export function jsx(type, props, key) { return R.createElement(type, key === undefined ? props : { ...props, key }) }',
    'export const jsxs = jsx'
  ].join('\n'),
  'react-dom/client': 'export const createRoot = (...a) => window.ReactDOM.createRoot(...a)\n',
  'node:url': "export function fileURLToPath() { throw new Error('no file URL inside a preview page') }\n",
  'wa-kit': source('kit-stub.mjs'),
  'wa-fixture': bare(source('fixture.mjs')),
  'wa-fixture-health': bare(source('fixture-health.mjs')),
  'wa-states': bare(source('metro-states.mjs')),
  '@hermes/plugin-sdk': `
export * from 'wa-kit'
const atom = value => ({ get: () => value, listen: () => () => {} })
export const composerCalls = { insert: [], submit: [] }
export const host = {
  state: { connectionId: atom('local'), profile: atom('default'), cwd: atom('/srv/wiki') },
  composer: {
    insertText: (sessionId, text, opts) => { composerCalls.insert.push({ sessionId, text, opts }); return Promise.resolve(true) },
    submit: (sessionId, text) => { composerCalls.submit.push({ sessionId, text }); return true },
    setDraft: () => true, focus: () => true
  }
}
const bundles = new Map()
const leaf = (tree, key) => String(key).split('.').reduce((n, p) => (n && typeof n === 'object' ? n[p] : undefined), tree)
export function registerBundles(id, table) { bundles.set(id, table) }
export function resolveKey(id, key, args) {
  const value = leaf((bundles.get(id) || {}).en, key)
  return typeof value === 'function' ? value(...args) : value ?? key
}
export function usePluginI18n(id) { return (key, ...args) => resolveKey(id, key, args) }
export function translateNow(key) { return key }
export function useI18n() { return { t: key => key } }
export default { host: { notify: () => {}, notifyError: () => {} }, haptic: () => {}, relativeTime: () => '2 hours ago' }
`,
  'wa-plugin': readFileSync(SRC, 'utf8')
}
const IMPORT_MAP = JSON.stringify({ imports: Object.fromEntries(Object.entries(MODULES).map(([k, v]) => [k, b64(v)])) })

// The state's clicks run IN the page, through React, exactly like a user's; the reused-component pages
// add the flows the 2.3.x preview ran on the Automation tab (now inside Settings).
const boot = state => `
import React from 'react'
import { createRoot } from 'react-dom/client'
import plugin from 'wa-plugin'
import * as sdk from '@hermes/plugin-sdk'
import { STATES, drive, makeRest, target, world } from 'wa-states'
const STATE = ${JSON.stringify(state)}
const wait = ms => new Promise(r => setTimeout(r, ms))
const click = async (el, ms = 80) => {
  if (!el) throw new Error('preview: a control to press is missing')
  el.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  await wait(ms)
}
const type = async (el, value) => {
  if (!el) throw new Error('preview: a field to type into is missing')
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, value)
  el.dispatchEvent(new Event('input', { bubbles: true }))
  await wait(40)
}
const byText = (scope, label, exact = true) => [...scope.querySelectorAll('button')]
  .find(b => exact ? (b.textContent || '').trim() === label : (b.textContent || '').includes(label))
const extra = ${JSON.stringify(EXTRA)}
const conditions = STATES[STATE]?.conditions || (STATE === 'settings-setup' ? { jobBroken: true } : {})
const w = world(conditions)
const registrations = []
plugin.register({
  rest: makeRest(w),
  os: { pickOpenPath: () => Promise.resolve('/srv/wiki/.llm-wiki/project.json') },
  i18n: { register: table => sdk.registerBundles(plugin.id, table), t: (key, ...a) => sdk.resolveKey(plugin.id, key, a) },
  register: r => registrations.push(r)
})
const page = registrations.find(r => r.area === 'routes')
const host = document.querySelector('.wa-frame')
try {
  if (!page) throw new Error('no page registration')
  createRoot(host).render(React.createElement(page.render))
  await wait(STATE === 'loading' ? 400 : 250)
  if (!extra.includes(STATE)) await drive(STATE, host, { click })
  if (STATE === 'settings-setup' || STATE === 'schedule') {
    await click(target(host, 'settings'), 200)
  }
  if (STATE === 'settings-setup') {
    const scan = byText(host, 'Scan for candidates', false)
    if (scan) await click(scan)
    const verify = byText(host, 'Verify')
    if (verify) await click(verify)
    const cand = host.querySelector('.wa-cand')
    if (cand) await click(cand)
    const del = byText(host, 'Delete job')
    if (del) await click(del)
  }
  if (STATE === 'schedule') {
    const row = [...host.querySelectorAll('.wa-job')].find(el => (el.textContent || '').includes('Watch Dog'))
    if (row?.tagName === 'DETAILS') row.open = true
    await click([...(row?.querySelectorAll('button') || [])].find(b => (b.textContent || '').trim() === 'Schedule'))
    const ed = () => host.querySelector('.wa-sched')
    await click([...(ed()?.querySelectorAll('.wa-sched-freq button') || [])].find(b => (b.textContent || '').trim() === 'Weekly'))
    await click([...ed().querySelectorAll('.wa-day')].find(b => (b.textContent || '').trim() === 'Thu'))
    await type(ed().querySelector('.wa-sched-time'), '08:15')
    await wait(500)
  }
  await wait(200)
  document.documentElement.dataset.waReady = '1'
} catch (e) {
  document.documentElement.dataset.waReady = 'error'
  document.documentElement.dataset.waError = String(e && e.message || e)
  console.error(e)
}
`

const APP_CSS_DIR = `${DESKTOP_APP}/dist/assets`
const newest = pattern => {
  try {
    return readdirSync(APP_CSS_DIR).filter(name => pattern.test(name))
      .map(name => ({ name, at: statSync(`${APP_CSS_DIR}/${name}`).mtimeMs })).sort((a, b) => b.at - a.at)[0]?.name
  } catch (e) {
    return undefined
  }
}
const APP_CSS_FILES = [newest(/^index-.*\.css$/), newest(/^tooltip-.*\.css$/)].filter(Boolean)
const appCss = APP_CSS_FILES.map(name => readFileSync(`${APP_CSS_DIR}/${name}`, 'utf8')).join('\n')
  .replace(/url\((\.\/codicon-[^)?]+)(?:\?[^)]*)?\)/g, (_match, asset) =>
    `url(data:font/ttf;base64,${readFileSync(`${APP_CSS_DIR}/${asset}`).toString('base64')})`)
if (!appCss) {
  console.log(`note: no compiled app stylesheet in ${APP_CSS_DIR} — the kit components will render unstyled`)
}
const appStyles = (() => { try { return readFileSync(APP_STYLES, 'utf8') } catch (e) { return '' } })()
const glassBlock = (() => {
  const a = appStyles.indexOf('/* ── Window glass')
  const b = appStyles.indexOf('/* Clear mode (native window opacity)')
  return a >= 0 && b > a ? appStyles.slice(a, b) : ''
})()
const theme = readFileSync(THEME, 'utf8')
const darkBlock = (() => {
  const start = appStyles.indexOf(':root.dark {')
  if (start < 0) return ''
  let depth = 0
  let i = appStyles.indexOf('{', start)
  for (; i < appStyles.length; i += 1) {
    if (appStyles[i] === '{') depth += 1
    else if (appStyles[i] === '}') { depth -= 1; if (depth === 0) break }
  }
  return appStyles.slice(start, i + 1)
})()
const DARK_SEEDS = darkBlock
  ? ':root.dark { --theme-background-seed: #0d1117; --theme-sidebar-seed: #010409; --theme-card-seed: #010409;'
    + ' --theme-elevated-seed: #161b22; --theme-bubble-seed: #07162c; --theme-foreground: #e6edf3;'
    + ' --theme-midground: #4a84fe; --theme-primary: #4a84fe; --theme-warm: #4a84fe; --theme-secondary: #1d2e4f;'
    + ' --theme-accent-soft: #17243a; --theme-mix-chrome: 74%; --theme-mix-sidebar: 100%; --theme-mix-card: 38%;'
    + ' --theme-mix-elevated: 46%; }'
  : ''

const pageOf = state => `<!doctype html>
<html class="dark" lang="en"${GLASS ? ' data-hermes-glass="" style="--translucency-glass-keep: 55%"' : ''}>
<head><meta charset="utf-8"><title>Wiki Automation — Metro preview · ${state}</title>
<style>${appCss}</style>
<style>${theme}</style>
<style>${darkBlock}</style>
<style>${DARK_SEEDS}</style>
<style>
  body { margin: 0; padding: 16px; background: var(--ui-surface-background); color: var(--ui-text-primary); }
  *, *::before, *::after { box-sizing: border-box; }
  .wa-frame { width: 100%; border: 1px solid var(--ui-stroke-primary); border-radius: 10px; overflow: hidden;
              display: flex; }
  :root[data-hermes-glass] { background-image: repeating-linear-gradient(135deg, #3b5b8c 0 40px,
              #8c3b5b 40px 80px, #3b8c6a 80px 120px) !important; }
  .wa-frame > div { flex: 1; min-width: 0; }
</style>
${GLASS ? `<style>${glassBlock}</style>` : ''}
<script>${REACT_UMD}</script>
<script>${REACT_DOM_UMD}</script>
<script type="importmap">${IMPORT_MAP}</script>
</head>
<body>
<div class="wa-frame" data-preview-state="${state}" data-preview-mock="${STATES[state]?.mock || ''}"
  data-preview-alert="${STATES[state]?.expect?.alert || ''}"></div>
<script type="module">${boot(state)}</script>
</body>
</html>
`

for (const state of WANTED) {
  const out = `preview-metro-${state}${GLASS ? '-glass' : ''}.html`
  const html = pageOf(state)
  writeFileSync(`${HERE}${out}`, html)
  console.log(`${out} written (${html.length} bytes) — app stylesheet ${APP_CSS_FILES.join(', ') || 'NOT FOUND'}`)
}
process.exit(0)
