/**
 * Wiki Automation panel — VISUAL MEASUREMENT (with the app's own Electron).
 *
 * Run (pages from `node preview.mjs`, one LIVE page per Metro state):
 *   <electron> tests/shot.cjs tests/preview-metro-good.html tests/metro-good-1240.png 1240
 *   <electron> tests/shot.cjs tests/preview-metro-problems.html <out.png> 1240 --frame=390   (narrow: vertical)
 *   <electron> tests/shot.cjs tests/preview-metro-wiki.html <out.png> 1240 --frame=352
 *   <electron> tests/shot.cjs tests/preview-metro-settings-setup.html <out.png> 1240          (destructive pair)
 *   <electron> tests/shot.cjs tests/preview-metro-schedule.html <out.png> 820 --scroll=jobs
 *   <electron> tests/shot.cjs tests/preview-metro-good.html <out.png> 1240 --inject=metro-wires-detached
 *   <electron> tests/shot.cjs tests/preview-metro-good.html <out.png> 1240 --inject=metro-wires-gone
 *   <electron> tests/shot.cjs tests/preview-metro-problems.html <out.png> 1240 --frame=390 --inject=metro-media-query
 *   <electron> tests/shot.cjs tests/preview-metro-settings-setup.html <out.png> 1240 --inject=wrong-token
 *   Negative controls must exit 1; normal runs must exit 0. The JSON `geometry.metro` field records the
 *   line's direction, every SVG segment (length, screen endpoints, the stop each endpoint is nearest to),
 *   the stations' and branches' boxes and any element that leaves the Metro root horizontally.
 *
 * Output: one JSON object (the measurements) on stdout + a PNG + the contrast dump
 * (`<out>.contrast.json`). The gate answers:
 *   1. Are there three cards, and do their widths fit the window (no horizontal overflow)?
 *   2. Is text CLIPPED: has any element that truncates with an ellipsis (`.wa-clip` — the install
 *      values, the root path, the run-row job name) actually fallen back to one?
 *   3. Do the install/settings values sit in the kit's `PanelMeta` (dt/dd rows) with every label
 *      and value readable, and does the runs grid drop the DURATION column in a narrow PANE instead
 *      of clipping it? With `--frame=<px>` the panel is rendered inside a frame of that width in a
 *      full-width window, so only a query that measures the PANE (`@container`) can answer it; the
 *      gate fails when the Duration column survives, and `--inject=media-query` keys the same rule
 *      back to the window and must make that FAIL (the negative control).
 *   3d. Does every short chip read as a LABEL: `Verified`, `Live`, `Completed` — not `verified`?
 *      The gate fails on a badge of three words or fewer that starts lower case (a longer badge is a
 *      note, not a chip), with `--inject=lower-chip` as the negative control that must exit 1.
 *   3c. Is the TYPE readable: is every text node at or above the kit's default badge step
 *      (10.4 px), and every card title / table label at or above 11.5 px? `--inject=tiny-type`
 *      puts a title back at 9 px and the gate must then exit 1.
 *   3b. Does every element sit INSIDE the card it lives in, and is the job row shaped as the
 *      design says: the state badge ON the job name's line (not on a line of its own) with the
 *      schedule under it? Both are measured for every card and every `.wa-job`, and both have a
 *      negative control that must exit 1 — `--inject=job-row-stack` (the badge back on its own
 *      line) and `--inject=job-acts-too-wide` (an action group wider than its card).
 *   4. Is there a native `<select>` (an unthemed list), a language picker, or — the host's own rule
 *      — any element carrying a native `title=`? There should be none of the three.
 *   5. Are the kit's controls present (the `SearchField` filtering the candidates, the
 *      `SegmentedControl` runs range) and are the input and the buttons visible, with their labels?
 *   6. The REFERENCE PASS surfaces: the help card (heading · reason · the action), the raw check
 *      wording in the kit's code body under its `as written` caption, ONE mono shape across every
 *      code/data element, the copy affordances (with the payload each was handed) and every icon
 *      button at the single shared shape — `icon-sm`, circular, `aria-label`led.
 *   7. THE WCAG CONTRAST GATE (this file is the only place with real pixels): every text node in the
 *      panel is measured — the ink (alpha-composited over the ground it really sits on) against the
 *      colours painted under it — and the WCAG 2.x ratio decides (AA: 4.5:1; 3.0:1 for large text).
 *      The classes the PANEL inks are GATED, and they exit non-zero:
 *        * `danger-ink` — the panel's destructive label (`.wa-danger`, the `Failed` / `deleted job`
 *          chips): its ink must BE the theme's alarm tone `--ui-red` (5.6:1 on the panel ground)
 *          while the KIT keeps the tone on the surface (its own `destructive` badge tint). The kit's
 *          `text-destructive` ink is the FILL of that token pair and reached only 3.72:1 here.
 *        * `danger-fill` — the filled destructive write (`[data-variant="destructive"]`, the armed
 *          second step of the copy/mirror gate): its fill must BE `--dt-destructive` and its ink
 *          `--dt-destructive-foreground` (5.04:1). The alarm tone used as a FILL is white on
 *          `--ui-red` (3.4:1) — the wrong token intent; `--inject=wrong-token` applies exactly that
 *          swap to the loaded page and the gate must then exit 1 (the negative control).
 *        * `bad-ink` — `.wa-bad` / `[data-tone="bad"]`: the panel's own failure text, the alarm tone
 *          as ink on the dark ground (5.6:1).
 *        * `reading` — every other text node whose ink is not the host's faint ladder.
 *      REPORTED / held to the 3:1 floor (measured so the numbers are on the record):
 *      `quiet` — ink under alpha 0.7, the host's faint ladder (`--ui-text-tertiary` .54 /
 *      `--ui-text-quaternary` .36, the kit's own `text-muted-foreground/50` and `/55`, the SearchField
 *      glyph): the theme and the kit own that ladder and the same numbers appear in every panel, so
 *      the numbers are printed and never gated; `primary-fill` — the kit's filled primary action (the
 *      app's `--dt-primary` + `--dt-primary-foreground` tokens, 3.4:1): the APP's own pair, not this
 *      panel's, so it is held to the 3:1 non-text/large-text floor and printed. The kit's tinted
 *      badge (`chip`) IS gated at AA: its ink is solid and it is small text like any other.
 *
 * The panel is stubbed onto the kit by `kit-stub.mjs` (whose class strings are copied from the kit
 * sources) and `preview.mjs` embeds the app's compiled stylesheet, so these numbers are the ones the
 * app shows. `<electron>` MUST be the app's own build.
 */
const path = require('node:path')
const fs = require('node:fs')
const os = require('node:os')

const [pageUrl, outPng, widthArg, ...flags] = process.argv.slice(2)
// History's "Full technical log" (`preview-metro-history-log.html`) holds the former Health view; it is
// measured by the Watchdog gate it came with, kept whole in shot_health.cjs; there the width argument is the
// PANE width. The plain History list (m-13) is measured here like every other detail.
if (/preview-metro-history-log\.html$/.test(String(pageUrl || ''))) {
  require('./shot_health.cjs')
  return
}
const WIDTH = Number(widthArg || 1240)
const HEIGHT = Number((flags.find(f => f.startsWith('--height=')) || '').split('=')[1]) || 900
if (!Number.isFinite(HEIGHT) || HEIGHT < 220 || HEIGHT > 2400) throw new Error('Capture height must be between 220 and 2400 pixels')
const FRAME = Number((flags.find(f => f.startsWith('--frame=')) || '').split('=')[1]) || 0
const INJECT = (flags.find(f => f.startsWith('--inject=')) || '').split('=')[1] || ''
const THEME = (flags.find(f => f.startsWith('--theme=')) || '').split('=')[1] || 'dark'
if (!['dark', 'light'].includes(THEME)) throw new Error(`Unknown theme: ${THEME}`)
const SCROLL = (flags.find(f => f.startsWith('--scroll=')) || '').split('=')[1] || ''
const { app, BrowserWindow } = require('electron')

// NEGATIVE CONTROLS: a named swap applied to the loaded page, in memory, so the gate can be shown to
// FAIL on the very regression it exists for (and pass again without it). `wrong-token` puts the alarm
// tone back where it must not be — as a FILL (white on `--ui-red`) — and the destructive token back as
// INK (`--dt-destructive`); both destructive classes drop under AA.
const INJECTIONS = {
  'wrong-token': [
    ['background:var(--dt-destructive)', 'background:var(--ui-red)'],
    ['color:var(--ui-red)', 'color:var(--dt-destructive)']
  ],
  // PANE WIDTH: the line turns vertical by a query on the PANE (`@container`), not the window. Keyed back
  // to `@media`, a narrow pane inside a wide window keeps the horizontal line: the negative control.
  'metro-media-query': [['@container (max-width:', '@media (max-width:']],
  'job-row-stack': [
    ['.wa-job-line{display:flex;flex-wrap:wrap;align-items:center;gap:6px;min-width:0}',
     '.wa-job-line{display:flex;flex-direction:column;align-items:flex-start;gap:2px;min-width:0}']
  ],
  'tiny-type': [['.wa-sec-title{font-size:12px', '.wa-sec-title{font-size:9px']],
  'chip-nowrap': [['.wa-root .wa-badge{min-width:0;max-width:100%;white-space:normal;overflow-wrap:anywhere}', '.wa-root .wa-badge{}']],
  'lower-chip': [["ok: 'Verified'", "ok: 'verified'"]],
  'job-acts-too-wide': [
    ['.wa-job-acts{display:grid;gap:4px;align-items:center;',
     '.wa-job-acts{display:grid;gap:4px;align-items:center;width:1400px;']
  ],
  'sched-no-wrap': [
    ['grid-template-columns:repeat(auto-fit,minmax(5.5rem,1fr))}',
     'grid-template-columns:repeat(6,minmax(5.5rem,1fr))}']
  ]
}

// Geometry controls mutate ONLY the loaded DOM; fixture/source files remain untouched.
const DOM_INJECTIONS = {
  'metro-wires-detached': `(() => {
    const wires = [...document.querySelectorAll('svg.wa-metro-wires path')]
    if (!wires.length) throw new Error('metro-wires-detached: no segment')
    wires.forEach(w => w.setAttribute('d', 'M0 0 L1 1'))
    window.__waFrozen = true
  })()`,
  'metro-wires-gone': `(() => {
    const svg = document.querySelector('svg.wa-metro-wires')
    if (!svg) throw new Error('metro-wires-gone: no svg')
    svg.querySelectorAll('path, line, polyline').forEach(p => p.remove())
    window.__waFrozen = true
  })()`
}

function inject(name) {
  const rules = INJECTIONS[name]
  if (!rules) throw new Error(`unknown injection: ${name}`)
  let html = fs.readFileSync(path.resolve(pageUrl), 'utf8')
  const map = /<script type="importmap">([\s\S]*?)<\/script>/.exec(html)
  if (!map) throw new Error('injection: the page carries no import map (rebuild it with `node preview.mjs`)')
  const imports = JSON.parse(map[1]).imports
  const PREFIX = 'data:text/javascript;base64,'
  let panel = Buffer.from(imports['wa-plugin'].slice(PREFIX.length), 'base64').toString('utf8')
  const applied = []
  for (const [find, replace] of rules) {
    const hits = panel.split(find).length - 1
    if (!hits) throw new Error(`injection ${name}: no ${find} in the panel source`)
    panel = panel.split(find).join(replace)
    applied.push(`${find} → ${replace} x${hits}`)
  }
  imports['wa-plugin'] = PREFIX + Buffer.from(panel, 'utf8').toString('base64')
  html = html.replace(map[1], () => JSON.stringify({ imports }))
  const out = path.join(os.tmpdir(), `wa-contrast-inject-${name}.html`)
  fs.writeFileSync(out, html)
  console.log(`INJECTED (${name}): ${applied.join(' · ')} — ${out}`)
  return out
}

app.disableHardwareAcceleration()

const PREPARE = `(() => {
  const frame = document.querySelector('.wa-frame')
  if (${FRAME}) frame.style.width = ${FRAME} + 'px'
  const q = s => document.querySelector(s)
  const qa = s => [...document.querySelectorAll(s)]
  const txt = el => (el?.textContent || '').replace(/\\\\s+/g, ' ').trim()
  const cards = qa('.wa-card')
  const root = q('.wa-metro') || q('.wa-root, .pa-root')
  if (${SCROLL === 'bottom' ? 1 : 0}) {
    for (const el of [root, q('.wa-frame'), document.scrollingElement, document.documentElement,
                      document.body]) {
      if (el) el.scrollTop = el.scrollHeight
    }
    window.scrollTo(0, document.body.scrollHeight)
  }
  if (${SCROLL === 'jobs' ? 1 : 0}) {
    const target = document.querySelector('.wa-sched') || document.getElementById('wa-sec-jobs')
    if (target) target.scrollIntoView({ block: 'center' })
  }
  const clipped = el => el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).textOverflow === 'ellipsis'
  const meta = qa('.wa-kv').map(m => ({ rows: m.querySelectorAll('dd').length,
                                        labels: [...m.querySelectorAll('dt')].map(txt) }))
  const metaVals = qa('.wa-kv .wa-clip')
  const metaLabels = qa('.wa-kv dt')
  const runRows = qa('.wa-hb-row')
  const cells = runRows.length ? [...runRows[0].children] : []
  const gridCols = runRows.length ? getComputedStyle(runRows[0]).gridTemplateColumns : ''
  const hbColumns = gridCols ? gridCols.split(' ').filter(Boolean).length : 0
  const visibleCells = cells.filter(c => getComputedStyle(c).display !== 'none').length
  const clipEls = qa('.wa-clip')
  const mono = qa('.wa-mono')
  const monoStyle = mono.length ? getComputedStyle(mono[0]) : null
  const iconBtns = qa('.wa-icon-btn')
  const copies = qa('[data-copy]')
  const outOfCard = []
  const spillingText = []
  for (const card of cards) {
    const cr = card.getBoundingClientRect()
    for (const el of card.querySelectorAll('*')) {
      const r = el.getBoundingClientRect()
      if (!r.width || !r.height) continue
      const overRight = Math.round(r.right - cr.right)
      const overLeft = Math.round(cr.left - r.left)
      if (overRight > 1 || overLeft > 1) {
        const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ')
        const cs = getComputedStyle(el)
        if (!cs.textOverflow.startsWith('ellipsis') && cs.whiteSpace !== 'normal'
            && el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 0) {
          const words = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ')
          spillingText.push({
            text: words.replace(/\s+/g, ' ').trim().slice(0, 44),
            over: el.scrollWidth - el.clientWidth
          })
        }
        outOfCard.push({
          label: el.getAttribute('class') || el.tagName,
          text: own.replace(/\s+/g, ' ').trim().slice(0, 44),
          overRight, overLeft
        })
      }
    }
  }
  const jobRows = qa('.wa-job').filter(row => row.getClientRects().length).map(row => {
    const folded = row.tagName === 'DETAILS' && !row.open
    const name = row.querySelector(folded ? '.wa-job-summary > strong' : '.wa-job-name')
    const badge = row.querySelector(folded ? '.wa-job-summary-state' : '.wa-badge')
    const acts = folded ? null : row.querySelector('.wa-job-acts')
    const nr = name ? name.getBoundingClientRect() : null
    const br = badge ? badge.getBoundingClientRect() : null
    const ar = acts ? acts.getBoundingClientRect() : null
    const overlap = nr && br ? Math.min(br.bottom, nr.bottom) - Math.max(br.top, nr.top) : null
    return {
      name: txt(name),
      height: Math.round(row.getBoundingClientRect().height),
      folded,
      badgeOnNameLine: overlap === null ? null : overlap >= Math.min(nr.height, br.height) * 0.5,
      badgeOverlap: overlap === null ? null : Math.round(overlap),
      actsBelowName: nr && ar ? Math.round(ar.top - nr.top) : null,
      actsOnOwnLine: nr && ar ? ar.top >= nr.bottom : null
    }
  })
  return {
    previewState: frame?.dataset.previewState || '',
    previewAlert: frame?.dataset.previewAlert || '',
    ready: document.documentElement.dataset.waReady || '',
    readyError: document.documentElement.dataset.waError || '',
    width: innerWidth,
    frameWidth: frame ? Math.round(frame.getBoundingClientRect().width) : null,
    rootWidth: root ? Math.round(root.getBoundingClientRect().width) : null,
    cards: cards.map(c => ({ w: Math.round(c.getBoundingClientRect().width),
                             title: txt(c.querySelector('.wa-sec-title')) })),
    bodyScrollX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    metaBlocks: meta.length,
    metaRows: meta.reduce((n, m) => n + m.rows, 0),
    metaLabels: meta.flatMap(m => m.labels),
    metaValues: metaVals.length,
    metaClipped: metaVals.filter(clipped).map(txt),
    metaLabelClipped: metaLabels.filter(clipped).map(txt),
    runRows: runRows.length,
    runCells: cells.length,
    runCellsVisible: visibleCells,
    gridCols,
    hbColumns,
    tabs: qa('[role="tab"], [role="tablist"], [data-slot="tabs-trigger"]').map(txt),
    runCellClipped: cells.filter(clipped).length,
    spillingText,
    outOfCard,
    jobRows,
    visibleJobWarnings: qa('.wa-job-summary-state[data-tone="bad"]').filter(el => el.getBoundingClientRect().height > 0).length,
    truncating: clipEls.length,
    clippedText: clipEls.filter(clipped).map(txt),
    searchField: qa('.wa-cand-head input').length,
    segmentedButtons: qa('[aria-pressed]').length,
    rangeLabels: qa('[aria-pressed]').map(txt),
    nativeSelects: qa('select').length,
    languagePickers: qa('.wa-lang, .wa-lang-btn, [class*="lang"]').length,
    nativeTitles: qa('[title]').length,
    inputVisible: !!q('.wa-input, input'),
    buttons: qa('.wa-refresh, .wa-cand').map(b => txt(b)),
    allButtons: qa('button').map(b => txt(b)),
    helpCards: qa('.wa-help').length,
    helpTitle: txt(q('.wa-help-title')),
    helpAction: txt(q('.wa-help-act')),
    codeBodies: qa('.wa-raw pre').length,
    codeCaption: txt(q('.wa-code-head .wa-label')),
    monoBlocks: mono.length,
    monoFont: monoStyle ? monoStyle.fontFamily : null,
    monoSize: monoStyle ? monoStyle.fontSize : null,
    monoLeading: monoStyle ? monoStyle.lineHeight : null,
    monoShapes: [...new Set(mono.map(el => {
      const s = getComputedStyle(el)
      return s.fontFamily + '|' + s.fontSize + '|' + s.lineHeight
    }))].length,
    copyButtons: copies.length,
    copyPayloads: copies.map(c => c.getAttribute('data-copy')),
    iconButtons: iconBtns.map(b => ({ label: b.getAttribute('aria-label'),
      w: Math.round(b.getBoundingClientRect().width), h: Math.round(b.getBoundingClientRect().height),
      radius: getComputedStyle(b).borderRadius })),
    ghostButtons: qa('button[data-variant="ghost"]').map(txt),
    filledButtons: qa('button[data-variant="default"]').map(txt),
    destructiveButtons: qa('button[data-variant="destructive"]').map(txt),
    confirmRows: qa('.wa-confirm').length,
    pkgTitle: txt(q('.wa-sec-title'))
  }
})()`

// Measure rendered paths in screen coordinates, not guessed percentages or source strings.
// "Visible" means painted within the fixture content, not necessarily above its viewport fold.
// Static previews have intrinsic-height frames; body/html clipping is the capture boundary, not a card defect.
function measureFlow() {
  const q = s => document.querySelector(s)
  const qa = s => [...document.querySelectorAll(s)]
  const text = el => (el?.textContent || '').replace(/\s+/g, ' ').trim()
  const round = n => Math.round(n * 100) / 100
  const rect = el => {
    if (!el) return null
    const r = el.getBoundingClientRect()
    return Object.fromEntries(['left', 'top', 'right', 'bottom', 'width', 'height'].map(k => [k, round(r[k])]))
  }
  const paintVisible = color => !['none', 'transparent'].includes(color)
    && !(color.startsWith('rgba(') && /,\s*0(?:\.0+)?\s*\)$/.test(color))
    && !/\/\s*0(?:\.0+)?\s*\)$/.test(color)
  const painted = el => {
    if (!el || !el.getClientRects().length) return false
    for (let n = el; n; n = n.parentElement) {
      const s = getComputedStyle(n)
      if (s.display === 'none' || s.visibility !== 'visible' || Number(s.opacity) === 0) return false
    }
    const closed = el.closest('details:not([open])')
    return !closed || !!closed.querySelector(':scope > summary')?.contains(el)
  }
  const visible = el => {
    if (!painted(el)) return false
    const r = el.getBoundingClientRect()
    if (r.width <= 0 || r.height <= 0) return false
    // Scroll containers may expose below-fold content; non-scrollable clipping may not hide it.
    let scrollReachableY = false
    for (let n = el.parentElement; n && n !== document.body && n !== document.documentElement; n = n.parentElement) {
      const s = getComputedStyle(n), b = n.getBoundingClientRect()
      if (['hidden', 'clip'].includes(s.overflowX) && (r.left < b.left - 2 || r.right > b.right + 2)) return false
      if (!scrollReachableY && ['hidden', 'clip'].includes(s.overflowY)
        && (r.top < b.top - 2 || r.bottom > b.bottom + 2)) return false
      if (['auto', 'scroll'].includes(s.overflowY) && n.scrollHeight > n.clientHeight) scrollReachableY = true
    }
    return true
  }
  const inside = (a, b) => a && b && a.left >= b.left - 2 && a.right <= b.right + 2
    && a.top >= b.top - 2 && a.bottom <= b.bottom + 2
  const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y)
  const edge = (r, side) => ({ x: r[side], y: (r.top + r.bottom) / 2 })
  // Wrapping can make a card taller: attachment to its edge matters, not exact centre alignment.
  const edgeGap = (p, r, side) => distance(p, { x: r[side], y: Math.max(r.top, Math.min(r.bottom, p.y)) })
  const violations = []
  const check = (ok, why) => { if (!ok) violations.push(why) }
  const root = q('.wa-metro') || q('.wa-root'), paneWidth = root?.clientWidth || 0
  const report = { paneWidth, tolerancePx: 2, visibilityScope: 'fixture content; viewport fold excluded',
    metro: null, violations }
  const m = q('.wa-metro')
  check(!!m, 'no .wa-metro root: the panel is one Metro view')
  check(!qa('[role="tab"], [role="tablist"], [data-slot="tabs-trigger"]').length, 'a tab strip is back')
  // Loading draws the skeleton in place of the line (contract § DOM): there is no line to measure yet.
  const skeleton = m ? q('.wa-metro-skeleton') : null
  if (m && (skeleton || !q('.wa-metro-map'))) {
    check(skeleton && visible(skeleton), 'neither the line nor the loading skeleton is painted')
    report.metro = { skeleton: true, dir: null, stations: [], lines: [], segments: [], outside: [] }
  }
  // m-12: with no readable timetable the map is its title alone — nothing to lay out, nothing to cross.
  const unread = q('.wa-metro-map[data-unread="1"]')
  if (m && unread) {
    check(visible(unread), 'the line title is not painted while the timetable is unread')
    check(!q('[data-wa-station], [data-wa-line], svg.wa-metro-wires'), 'a line is drawn although the timetable is unread')
    report.metro = { unread: true, dir: null, stations: [], lines: [], segments: [], outside: [] }
  }
  if (m && !skeleton && !unread) {
    const mr = rect(m), map = q('.wa-metro-map'), svg = q('svg.wa-metro-wires')
    const narrow = paneWidth <= 640
    const stations = qa('[data-wa-station]'), lines = qa('[data-wa-line]')
    // The stop: the ring of a station / the line of a branch. The panel's own element if it names one,
    // otherwise the station box itself (an endpoint must still sit on an edge, never at a centre).
    const stopOf = el => el.querySelector('[class*="stop"], [class*="ring"], circle') || el
    const boxes = [...stations, ...lines].map(el => ({ id: el.dataset.waStation || `line:${el.dataset.waLine}`,
      el, rect: rect(el), stop: rect(stopOf(el)), label: rect(el.querySelector('[class*="name"], [class*="label"]') || el) }))
    const mt = report.metro = { dir: map?.dataset.dir || null, narrow, root: mr, map: rect(map),
      stations: boxes.filter(b => !b.id.startsWith('line:')).map(b => ({ id: b.id, rect: b.rect, visible: visible(b.el),
        state: b.el.dataset.state })),
      lines: boxes.filter(b => b.id.startsWith('line:')).map(b => ({ id: b.id, rect: b.rect, visible: visible(b.el),
        state: b.el.dataset.state })),
      segments: [], outside: [], detailInsideMap: false }
    check(visible(map), 'the line (.wa-metro-map) is not painted')
    check(mt.dir === (narrow ? 'v' : 'h') || (paneWidth > 640 && paneWidth < 700 && ['h', 'v'].includes(mt.dir)),
      `the line is data-dir=${mt.dir} in a ${paneWidth}px pane (narrow panes ≤ 640 px are vertical, wide ones horizontal)`)
    check(stations.length === 3 && mt.stations.every(st => st.visible), 'the three stations are not all painted')
    check(lines.length >= 1 && mt.lines.every(l => l.visible), 'a branch line is not painted')
    for (const b of boxes) check(inside(b.rect, mr), `${b.id} sits outside the Metro root`)
    if (narrow && mt.stations.length === 3) {
      const [h, r, w] = ['harvest', 'review', 'wiki'].map(id => mt.stations.find(st => st.id === id)?.rect)
      check(h && r && w && h.bottom <= r.top + 2 && r.bottom <= w.top + 2,
        'the vertical line does not run Harvest → Your review → Wiki down one rail')
    }
    if (!narrow && mt.stations.length === 3) {
      const [h, r, w] = ['harvest', 'review', 'wiki'].map(id => mt.stations.find(st => st.id === id)?.rect)
      check(h && r && w && h.right <= r.left + 2 && r.right <= w.left + 2,
        'the horizontal line does not run Harvest → Your review → Wiki left to right')
    }
    // SEGMENTS: SVG paths computed after layout. Each has length, is painted, and both endpoints sit on
    // the EDGE of a stop or label (within 3 px of its border), never at a stop's centre.
    const paths = svg ? [...svg.querySelectorAll('path, line, polyline')] : []
    check(painted(svg) && paths.length >= 2, `the line has ${paths.length} SVG segment(s) after layout (≥ 2 between three stations)`)
    const onEdge = (p, r) => r && p.x >= r.left - 3 && p.x <= r.right + 3 && p.y >= r.top - 3 && p.y <= r.bottom + 3
      && Math.min(Math.abs(p.x - r.left), Math.abs(p.x - r.right), Math.abs(p.y - r.top), Math.abs(p.y - r.bottom)) <= 3
    const centre = r => ({ x: (r.left + r.right) / 2, y: (r.top + r.bottom) / 2 })
    paths.forEach((wire, i) => {
      const ctm = wire.getScreenCTM(), length = wire.getTotalLength ? wire.getTotalLength() : 0, st = getComputedStyle(wire)
      const at = f => { const p = wire.getPointAtLength(length * f); return new DOMPoint(p.x, p.y).matrixTransform(ctm) }
      const ends = ctm && length > 0 ? [at(0), at(1)] : []
      const seg = { i, length: round(length), stroke: st.stroke, ends: ends.map(p => ({ x: round(p.x), y: round(p.y) })),
        attached: [], atCentre: [] }
      for (const p of ends) {
        const near = boxes.find(b => onEdge(p, b.stop) || onEdge(p, b.label) || onEdge(p, b.rect))
        seg.attached.push(near ? near.id : null)
        const hit = boxes.find(b => b.stop && b.stop.width > 4 && distance(p, centre(b.stop)) < Math.min(b.stop.width, b.stop.height) / 2 - 1)
        if (hit) seg.atCentre.push(hit.id)
      }
      mt.segments.push(seg)
      check(length > 0 && paintVisible(st.stroke) && parseFloat(st.strokeWidth) > 0 && Number(st.strokeOpacity) > 0,
        `SVG segment ${i} has no length or no painted stroke`)
      check(ends.length === 2 && seg.attached.every(Boolean), `SVG segment ${i} is detached: an endpoint sits on no stop or label edge (${JSON.stringify(seg.ends)})`)
      check(!seg.atCentre.length, `SVG segment ${i} starts at the centre of ${seg.atCentre.join(',')} (it must start at an edge)`)
    })
    // NOTHING OVERFLOWS the Metro root horizontally (a scroll container inside may hold wider content).
    for (const el of m.querySelectorAll('*')) {
      if (!painted(el)) continue
      const r = el.getBoundingClientRect()
      if (!r.width || !r.height) continue
      let scroller = false
      for (let n = el.parentElement; n && n !== m; n = n.parentElement) {
        if (['auto', 'scroll', 'hidden', 'clip'].includes(getComputedStyle(n).overflowX)) { scroller = true; break }
      }
      if (scroller) continue
      if (r.right > mr.right + 1 || r.left < mr.left - 1) {
        mt.outside.push({ el: (el.getAttribute('class') || el.tagName).toString().slice(0, 40), text: text(el).slice(0, 30),
          over: Math.round(Math.max(r.right - mr.right, mr.left - r.left)) })
      }
    }
    check(!mt.outside.length, `${mt.outside.length} element(s) leave the Metro root horizontally: `
      + mt.outside.slice(0, 4).map(o => `${o.el} [${o.text}] ${o.over}px`).join(' · '))
    const detail = q('.wa-metro-detail')
    mt.detailInsideMap = !!(detail && map && map.contains(detail))
    check(!mt.detailInsideMap, 'the detail opened inside the map (cards never expand in place)')
    if (detail) check(rect(detail).top >= rect(map).bottom - 1, 'the detail is not under the map')
  }
  return report
}
const GEOMETRY = `(${measureFlow.toString()})()`

// Every text node, ink over the ground it sits on, WCAG 2.x. Chromium prints a theme token as
// rgb()/color(srgb ...) and a Tailwind palette colour as oklab()/oklch(); the canvas resolves the
// latter (painted over black and over white, which also recovers the alpha) so NO text node is
// silently skipped.
const CONTRAST = `(() => {
  const FLOOR = 3
  const parseColor = value => {
    const v = String(value || '').trim()
    if (v.startsWith('rgb(') || v.startsWith('rgba(')) {
      const parts = v.slice(v.indexOf('(') + 1, v.indexOf(')')).split(',').map(p => Number(p.trim()))
      return Number.isFinite(parts[0]) && Number.isFinite(parts[1]) && Number.isFinite(parts[2])
        ? { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1 } : null
    }
    if (v.startsWith('color(')) {
      const body = v.slice(v.indexOf('(') + 1, v.indexOf(')')).split('/')
      const chans = body[0].trim().replace('srgb', '').trim().split(' ').map(Number)
      const tail = body[1] === undefined ? '' : body[1].trim()
      const alpha = tail === '' ? 1 : (tail.endsWith('%') ? Number(tail.slice(0, -1)) / 100 : Number(tail))
      return chans.length === 3 && chans.every(Number.isFinite) && Number.isFinite(alpha)
        ? { r: chans[0] * 255, g: chans[1] * 255, b: chans[2] * 255, a: alpha } : null
    }
    return null
  }
  const canvas = document.createElement('canvas')
  canvas.width = 1
  canvas.height = 1
  const cx = canvas.getContext('2d')
  const onBase = (base, css) => {
    cx.fillStyle = base
    cx.fillRect(0, 0, 1, 1)
    cx.fillStyle = css
    cx.fillRect(0, 0, 1, 1)
    const d = cx.getImageData(0, 0, 1, 1).data
    return { r: d[0], g: d[1], b: d[2] }
  }
  const resolved = css => {
    const black = onBase('#000000', css)
    const white = onBase('#ffffff', css)
    const lost = 1 - ((white.r - black.r) + (white.g - black.g) + (white.b - black.b)) / 765
    if (!(lost > 0)) return { r: 0, g: 0, b: 0, a: 0 }
    return { r: black.r / lost, g: black.g / lost, b: black.b / lost, a: lost }
  }
  const inkOf = css => parseColor(css) || resolved(css)
  const over = (top, base) => ({ r: top.r * top.a + base.r * (1 - top.a),
                                 g: top.g * top.a + base.g * (1 - top.a),
                                 b: top.b * top.a + base.b * (1 - top.a), a: 1 })
  const fillUnder = el => {
    const stack = []
    for (let n = el; n; n = n.parentElement) {
      const c = inkOf(getComputedStyle(n).backgroundColor)
      if (c && c.a > 0) { stack.push(c); if (c.a >= 0.999) break }
    }
    let base = { r: 255, g: 255, b: 255, a: 1 }
    let used = 0
    if (stack.length && stack[stack.length - 1].a >= 0.999) { base = stack[stack.length - 1]; used = 1 }
    for (let i = stack.length - 1 - used; i >= 0; i -= 1) base = over(stack[i], base)
    return base
  }
  const paintUnder = el => {
    for (let n = el; n; n = n.parentElement) {
      const c = inkOf(getComputedStyle(n).backgroundColor)
      if (c && c.a > 0) return c
    }
    return null
  }
  const chan = c => { const s = c / 255; return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4) }
  const lum = c => 0.2126 * chan(c.r) + 0.7152 * chan(c.g) + 0.0722 * chan(c.b)
  const ratio = (f, b) => Math.round(((Math.max(lum(f), lum(b)) + 0.05) / (Math.min(lum(f), lum(b)) + 0.05)) * 100) / 100
  const rgbText = c => c ? 'rgb(' + Math.round(c.r) + ', ' + Math.round(c.g) + ', ' + Math.round(c.b) + ')' : '—'
  const same = (a, b, tol) => Boolean(a && b) && Math.abs(a.r - b.r) <= tol && Math.abs(a.g - b.g) <= tol
    && Math.abs(a.b - b.b) <= tol && Math.abs((a.a === undefined ? 1 : a.a) - (b.a === undefined ? 1 : b.a)) <= 0.02
  const probeEl = document.createElement('span')
  document.body.appendChild(probeEl)
  const token = name => {
    probeEl.style.color = ''
    probeEl.style.color = 'var(' + name + ')'
    return inkOf(getComputedStyle(probeEl).color)
  }
  const TOKEN_NAMES = ['--ui-text-primary', '--ui-text-secondary', '--ui-text-tertiary',
    '--ui-text-quaternary', '--ui-red', '--ui-green', '--ui-yellow', '--ui-blue',
    '--dt-primary', '--dt-primary-foreground', '--dt-destructive', '--dt-destructive-foreground']
  const TOKENS = {}
  for (const name of TOKEN_NAMES) TOKENS[name] = token(name)
  // The panel keeps the alarm hue in light mode but mixes its ink toward the foreground for AA.
  probeEl.style.color = document.documentElement.classList.contains('dark')
    ? 'var(--ui-red)' : 'color-mix(in srgb,var(--ui-red) 65%,var(--ui-text-primary))'
  TOKENS['--panel-danger-ink'] = inkOf(getComputedStyle(probeEl).color)
  probeEl.remove()
  const LADDER = ['--ui-text-secondary', '--ui-text-tertiary', '--ui-text-quaternary']
  const READING_ALPHA = 0.7
  const FLOORED = ['quiet', 'primary-fill']
  const root = document.querySelector('.wa-root') || document.body
  const rows = []
  const unparsed = []
  for (const el of [root, ...root.querySelectorAll('*')]) {
    const own = [...el.childNodes].filter(n => n.nodeType === 3 && (n.nodeValue || '').trim())
      .map(n => n.nodeValue.trim()).join(' ')
    if (!own) continue
    const cs = getComputedStyle(el)
    if (cs.visibility === 'hidden' || cs.display === 'none' || !el.getClientRects().length) continue
    const closed = el.closest('details:not([open])')
    if (closed && !closed.querySelector(':scope > summary')?.contains(el)) continue
    const ink = inkOf(cs.color)
    const cls = (el.getAttribute('class') || '').split(' ').filter(Boolean)
    const label = cls.find(c => c.startsWith('wa-')) || cls.slice(0, 2).join('.') || el.tagName.toLowerCase()
    if (!ink) { unparsed.push(label + ' [' + own.slice(0, 22) + '] ' + cs.color); continue }
    if (ink.a === 0) continue
    const bg = fillUnder(el)
    const paint = paintUnder(el)
    const seen = ink.a >= 0.999 ? ink : over(ink, bg)
    const px = parseFloat(cs.fontSize)
    const bold = parseInt(cs.fontWeight, 10) >= 700
    const large = px >= 18.7 || (px >= 14 && bold)
    const base = large ? 3 : 4.5
    const variant = el.getAttribute('data-variant')
    const tone = el.getAttribute('data-tone')
    let klass = 'reading'
    if (variant === 'destructive') klass = 'danger-fill'
    else if (cls.includes('wa-danger')) klass = 'danger-ink'
    else if (cls.includes('wa-bad') || tone === 'bad') klass = 'bad-ink'
    else if (ink.a < READING_ALPHA) klass = 'quiet'
    else if (same(paint, TOKENS['--dt-primary'], 1)) klass = 'primary-fill'
    else if (el.getAttribute('data-slot') === 'badge') klass = 'chip'
    const measured = ratio(seen, bg)
    const need = FLOORED.includes(klass) ? FLOOR : base
    rows.push({
      sel: label, text: own.slice(0, 22), tag: el.tagName.toLowerCase(), variant, tone,
      ink: rgbText(ink), inkAlpha: Math.round(ink.a * 100) / 100, fill: rgbText(bg),
      paint: paint ? rgbText(paint) : null, paintAlpha: paint ? Math.round(paint.a * 100) / 100 : null,
      px, weight: String(cs.fontWeight), large, need, ratio: measured, klass,
      slot: el.getAttribute('data-slot'), words: own.trim() ? own.trim().split(/\s+/).length : 0,
      pass: klass === 'quiet' ? null : measured >= need
    })
  }
  rows.sort((a, b) => a.ratio - b.ratio)
  const of = name => rows.filter(r => r.klass === name)
  const gated = rows.filter(r => r.pass !== null)
  const aaGated = rows.filter(r => r.pass !== null && !FLOORED.includes(r.klass))
  const floored = rows.filter(r => FLOORED.includes(r.klass) && r.klass !== 'quiet')
  const dangerInk = of('danger-ink')
  const dangerFill = of('danger-fill')
  const badInk = of('bad-ink')
  return {
    rows,
    count: rows.length,
    classes: {
      gated: gated.length,
      aaGated: aaGated.length,
      dangerInk: dangerInk.length,
      dangerFill: dangerFill.length,
      badInk: badInk.length,
      reading: of('reading').length,
      quiet: of('quiet').length,
      chip: of('chip').length,
      primaryFill: of('primary-fill').length
    },
    violations: gated.filter(r => r.pass === false),
    unparsed,
    floor: FLOOR,
    lowestGated: aaGated.length ? aaGated[0] : null,
    lowestFloored: floored.length ? floored[0] : null,
    lowestQuiet: of('quiet')[0] || null,
    lowestChip: of('chip')[0] || null,
    lowestPrimaryFill: of('primary-fill')[0] || null,
    tokens: TOKENS,
    ladder: LADDER.map(name => ({ name, ink: rgbText(TOKENS[name]),
      alpha: TOKENS[name] ? Math.round(TOKENS[name].a * 100) / 100 : null })),
    dangerInkRows: dangerInk.map(r => ({ text: r.text, ratio: r.ratio, ink: r.ink, fill: r.fill })),
    dangerFillRows: dangerFill.map(r => ({ text: r.text, ratio: r.ratio, ink: r.ink, fill: r.fill })),
    badInkRows: badInk.map(r => ({ text: r.text, ratio: r.ratio, ink: r.ink, fill: r.fill })),
    dangerInkIsTone: dangerInk.length > 0
      && dangerInk.every(r => r.ink === rgbText(TOKENS['--panel-danger-ink'])),
    dangerFillIsTokenPair: dangerFill.length > 0
      && dangerFill.every(r => r.fill === rgbText(TOKENS['--dt-destructive'])
        && r.ink === rgbText(TOKENS['--dt-destructive-foreground']))
  }
})()`

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    width: WIDTH, height: HEIGHT, show: false, backgroundColor: '#0d1117',
    webPreferences: { offscreen: false, backgroundThrottling: false }
  })
  let fixture = path.resolve(INJECT && !DOM_INJECTIONS[INJECT] ? inject(INJECT) : pageUrl)
  if (THEME === 'light') {
    const html = fs.readFileSync(fixture, 'utf8')
    if (!html.includes('<html class="dark"')) throw new Error('The fixture has no explicit theme class')
    const dir = path.join(path.dirname(fixture), '.cache')
    fs.mkdirSync(dir, { recursive: true })
    const light = path.join(dir, `light-${path.basename(fixture)}`)
    fs.writeFileSync(light, html.replace('<html class="dark"', '<html class=""'))
    fixture = light
  }
  await win.loadFile(fixture)


  // The page is LIVE (preview.mjs): it boots the panel, runs the state's clicks and then marks
  // <html data-wa-ready>. Measuring before that would measure an empty frame.
  for (let i = 0; i < 100; i += 1) {
    const ready = await win.webContents.executeJavaScript('document.documentElement.dataset.waReady || ""')
    if (ready) break
    await new Promise(r => setTimeout(r, 100))
  }
  await win.webContents.executeJavaScript(`new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))`)
  // Narrow the pane BEFORE the settle wait: the line re-measures its wires on a ResizeObserver tick, as it does
  // when the owner resizes the real pane. Narrowing inside PREPARE would measure before that tick could run.
  if (FRAME) {
    await win.webContents.executeJavaScript(`document.querySelector('.wa-frame').style.width = '${FRAME}px'`)
    await win.webContents.executeJavaScript(`new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))`)
  }
  await new Promise(r => setTimeout(r, 300))
  // Measure the settled panel; looping animations (the harvest march, a busy spinner) never finish and
  // are not waited for.
  await win.webContents.executeJavaScript(`Promise.race([
    Promise.all(document.getAnimations()
      .filter(a => a.effect && a.effect.getComputedTiming().endTime !== Infinity)
      .map(a => a.finished.catch(() => null))),
    new Promise(r => setTimeout(r, 5000))])`)
  if (DOM_INJECTIONS[INJECT]) {
    await win.webContents.executeJavaScript(DOM_INJECTIONS[INJECT])
    console.log(`INJECTED (${INJECT}): loaded DOM only; no fixture/source write`)
  }

  const out = await win.webContents.executeJavaScript(PREPARE)
  out.geometry = await win.webContents.executeJavaScript(GEOMETRY)
  out.contrast = await win.webContents.executeJavaScript(CONTRAST)
  out.contrast.injected = INJECT || null

  if (outPng) {
    // A hidden window may hand back its last painted frame; force a fresh paint of the narrowed layout first.
    win.webContents.invalidate()
    await win.webContents.executeJavaScript(`new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))`)
    await new Promise(r => setTimeout(r, 150))
    const img = await win.webContents.capturePage()
    fs.writeFileSync(path.resolve(outPng), img.toPNG())
    out.png = path.resolve(outPng)
    out.pngBytes = fs.statSync(path.resolve(outPng)).size
  }
  console.log(JSON.stringify(out, null, 2))

  // ── THE WCAG CONTRAST GATE ──────────────────────────────────────────────────────────────────────
  const ct = out.contrast
  const contrastPath = (outPng ? path.resolve(outPng) : path.resolve('shot.png')).replace(/\.png$/i, '.contrast.json')
  fs.writeFileSync(contrastPath, JSON.stringify(ct, null, 1))
  const mark = row => row.pass === null ? 'REPORT' : (row.pass ? 'PASS' : 'FAIL')
  console.log('CONTRAST — every text node, ink composited over the ground it sits on (WCAG 2.x ratio):')
  for (const row of ct.rows) {
    console.log(`  ${String(row.ratio).padStart(6)}:1 need ${row.need} ${mark(row).padEnd(6)}`
      + ` ${row.klass.padEnd(12)} .${row.sel} [${row.text}] ${row.px}px/${row.weight}`
      + ` ink ${row.ink} a${row.inkAlpha} on ${row.fill}`)
  }
  console.log(`CONTRAST SUMMARY: ${ct.count} text nodes · AA-gated ${ct.classes.aaGated} · danger ink `
    + `${ct.classes.dangerInk} · filled destructive ${ct.classes.dangerFill} · failure ink ${ct.classes.badInk}`
    + ` · reading ${ct.classes.reading} · at the ${ct.floor}:1 floor: kit tinted badges ${ct.classes.chip} +`
    + ` kit primary fill ${ct.classes.primaryFill} · reported only: faint ladder ${ct.classes.quiet}`)
  const lowest = ct.lowestGated
  console.log(`  LOWEST AA-GATED RATIO: ${lowest ? `${lowest.ratio}:1 need ${lowest.need} .${lowest.sel}`
    + ` [${lowest.text}] ${lowest.px}px/${lowest.weight} (${lowest.ink} on ${lowest.fill})` : 'no AA-gated node'}`)
  console.log(`  destructive label ink: ${ct.dangerInkRows.map(r => `${r.ratio}:1 [${r.text}] ${r.ink}`).join(' · ') || '—'}`
    + ` → is --ui-red (${rgbFind(ct, '--ui-red')}): ${ct.dangerInkIsTone}`)
  console.log(`  filled destructive: ${ct.dangerFillRows.map(r => `${r.ratio}:1 [${r.text}] ${r.ink} on ${r.fill}`).join(' · ') || '—'}`
    + ` → is --dt-destructive fill + --dt-destructive-foreground ink: ${ct.dangerFillIsTokenPair}`)
  console.log(`  failure ink (.wa-bad / data-tone=bad): ${ct.badInkRows.map(r => `${r.ratio}:1 [${r.text}]`).join(' · ') || '—'}`)
  console.log(`  at the ${ct.floor}:1 floor — lowest kit tinted badge ${ct.lowestChip ? `${ct.lowestChip.ratio}:1 .${ct.lowestChip.sel} [${ct.lowestChip.text}]` : '—'}`
    + ` · kit primary fill pair ${ct.lowestPrimaryFill ? `${ct.lowestPrimaryFill.ratio}:1 .${ct.lowestPrimaryFill.sel}`
      + ` [${ct.lowestPrimaryFill.text}]` : '—'}`
    + ` (the app's own --dt-primary/--dt-primary-foreground tokens, not this panel's pair)`)
  console.log(`  reported only — the faint ladder (${ct.ladder.map(l => `${l.name} a${l.alpha}`).join(' · ')}),`
    + ` lowest ${ct.lowestQuiet ? `${ct.lowestQuiet.ratio}:1 .${ct.lowestQuiet.sel} [${ct.lowestQuiet.text}]` : '—'}`
    + `: the theme/kit own that ladder and the same numbers appear in every panel`)
  console.log(`  contrast dump: ${contrastPath}`)

  const red = out.geometry.violations.map(why => `geometry: ${why}`)
  const mt = out.geometry.metro
  console.log(`  METRO GEOMETRY: pane ${out.geometry.paneWidth}px · line ${mt?.dir || 'absent'}`
    + ` · stations ${mt?.stations.length || 0} · branches ${mt?.lines.length || 0} · SVG segments ${mt?.segments.length || 0}`
    + ` · out of root ${mt?.outside.length || 0} · violations ${out.geometry.violations.length}`)
  if (out.ready !== '1') red.push(`the live page did not settle (${out.ready || 'no data-wa-ready'}${out.readyError ? `: ${out.readyError}` : ''})`)
  for (const row of ct.violations) {
    red.push(`contrast ${row.ratio}:1 < ${row.need}:1 for .${row.sel} [${row.text}] ${row.px}px/${row.weight}`
      + ` (${row.klass}) ink ${row.ink} a${row.inkAlpha} on ${row.fill}`)
  }
  if (out.bodyScrollX > 1) red.push(`horizontal overflow: ${out.bodyScrollX}px`)
  if (!ct.count) red.push('no text node was measured (the contrast dump is missing)')
  for (const line of ct.unparsed) red.push(`a text node's ink could not be read (${line})`)
  // The destructive-contrast fixture moved with its components: Settings, with the SAME-ID candidate
  // armed (filled destructive write), a job delete armed and a job without its script (failure ink).
  const setupFixture = out.previewState === 'settings-setup'
  if (setupFixture && !ct.classes.dangerInk && !out.visibleJobWarnings) {
    red.push('no destructive label or supporting-job attention warning is on screen')
  }
  if (out.previewState === 'settings-jobs'
      && (out.jobRows.length !== 4 || out.jobRows.some(row => !row.folded || row.height < 52 || row.height > 90))) {
    red.push('Settings must begin with the four scheduled jobs as compact native disclosures')
  }
  if (ct.classes.dangerInk && !ct.dangerInkIsTone) red.push(`the destructive label ink does not follow the panel tone contract: ${ct.dangerInkRows.map(r => r.ink).join(' | ')}`)
  if (setupFixture && !ct.classes.dangerFill) red.push('no filled destructive write is on screen (the armed copy/mirror step vanished)')
  if (ct.classes.dangerFill && !ct.dangerFillIsTokenPair) red.push(`the filled destructive write is not the --dt-destructive fill + --dt-destructive-foreground ink pair: ${ct.dangerFillRows.map(r => r.ink + ' on ' + r.fill).join(' | ')}`)
  if (setupFixture && !ct.classes.badInk) red.push('the panel failure ink (.wa-bad / data-tone="bad") is not on screen')
  if (out.tabs.length) red.push(`a tab strip is back: ${out.tabs.join('|')} (the four tabs were removed in 2.5.0)`)
  // PANE WIDTH (only with `--frame`): a narrow pane inside a WIDE window. Only a query that measures the
  // pane (`@container`) can turn the line vertical here; `--inject=metro-media-query` must go red.
  if (FRAME) {
    console.log(`  PANE: frame ${out.frameWidth}px (panel ${out.rootWidth}px) inside a ${out.width}px window — line ${mt?.dir}`)
    if (out.rootWidth <= 640 && mt?.dir !== 'v' && !mt?.skeleton && !mt?.unread) {
      red.push(`the line stayed ${mt?.dir || 'absent'} in a ${out.rootWidth}px pane inside a ${out.width}px window — `
        + 'the layout is keyed to the window, not to the pane')
    }
  }
  for (const row of out.jobRows) {
    console.log(`  JOB ROW: "${row.name}" ${row.height}px tall · badge/name overlap `
      + `${row.badgeOverlap === null ? '—' : `${row.badgeOverlap}px`} · actions `
      + `${row.actsBelowName === null ? '—' : `${row.actsBelowName}px`} below the name`)
  }
  console.log(`  CARDS: ${out.cards.length} · out of card ${out.outOfCard.length} · job rows `
    + `${out.jobRows.length} (badge on the name line ${out.jobRows.filter(r => r.badgeOnNameLine).length}, `
    + `actions on their own line ${out.jobRows.filter(r => r.actsOnOwnLine).length})`)
  console.log(`  TEXT: ${out.spillingText.length} box(es) whose text is wider than the box, with no ellipsis`)
  for (const item of out.spillingText) {
    console.log(`    ! "${item.text}" — ${item.over}px of text past its own box`)
    red.push(`"${item.text}" has ${item.over}px of text wider than its own box and no ellipsis: the tail sits outside the box, and nothing scrolls to it`)
  }
  for (const item of out.outOfCard) {
    red.push(`${item.label} sticks out of its card (${item.overRight > 1
      ? `${item.overRight}px past the right edge` : `${item.overLeft}px past the left edge`})`)
  }
  for (const row of out.jobRows) {
    if (row.badgeOnNameLine === false) {
      red.push(`the job row "${row.name}" puts its state badge on a line of its own — a job row is the `
        + 'name with the badge on that line and the schedule under it')
    }
  }
  const FLOOR = 10.4
  const tiny = ct.rows.filter(r => r.px > 0 && r.px < FLOOR)
  const smallTitles = ct.rows.filter(r => (r.sel || '').includes('wa-sec-title')
    && r.px > 0 && r.px < 11.5)
  console.log(`  TYPE: ${ct.rows.length} text node(s) · floor ${FLOOR}px · below it ${tiny.length} `
    + `· smallest ${Math.min(...ct.rows.map(r => r.px || 99)).toFixed(1)}px`
    + ` · card titles/labels under 11.5px ${smallTitles.length}`)
  for (const row of tiny) {
    red.push(`text is ${row.px}px, under the ${FLOOR}px floor [${row.text}] .${row.sel}`)
  }
  for (const row of smallTitles) {
    red.push(`a card title / table label is ${row.px}px, under the 11.5px floor [${row.text}] .${row.sel}`)
  }
  // A status chip is a label, not a sentence: short badge text starts with a capital. A badge long
  // enough to be a sentence (`the script watchdog.py is missing…`) is a note and is exempt.
  const CHIP_WORDS = 3
  const badges = ct.rows.filter(r => r.slot === 'badge')
  const shortChips = badges.filter(r => r.words > 0 && r.words <= CHIP_WORDS)
  const lowercaseChips = shortChips.filter(r => /^[a-z]/.test(r.text))
  console.log(`  CHIPS: ${badges.length} kit badge(s) · ${shortChips.length} of label length `
    + `(<= ${CHIP_WORDS} words) · starting lower case ${lowercaseChips.length}`)
  for (const row of lowercaseChips) {
    red.push(`the chip "${row.text}" starts lower case — a short chip is a LABEL (Verified · Live · `
      + 'Completed), and a sentence belongs in the card\'s hint line')
  }
  for (const line of red) console.error(`SHOT GATE RED: ${line}`)
  if (red.length) {
    console.error(`SHOT GATE: RED (${red.length} violation(s))${INJECT ? ` — injection ${INJECT}` : ''}`)
    app.exit(1)
    return
  }
  console.log(`SHOT GATE: GREEN — ${ct.classes.aaGated} AA-gated text node(s) at or above AA;`
    + ` alarm ink matches the ${THEME === 'light' ? 'light-theme mix' : '--ui-red'} contract;`
    + ` filled destructive ${ct.classes.dangerFill ? 'token pair verified' : 'absent in this fixture'};`
    + ` ${ct.classes.chip + ct.classes.primaryFill} kit node(s) at or above the ${ct.floor}:1 floor;`
    + ` no text node unread${INJECT ? ` — injection ${INJECT} did NOT go red (the gate is blind)` : ''}`)
  app.exit(0)
}).catch(e => { console.error('ERROR:', e); app.exit(1) })

function rgbFind(ct, name) {
  const c = ct.tokens[name]
  return c ? `rgb(${Math.round(c.r)}, ${Math.round(c.g)}, ${Math.round(c.b)})` : '—'
}
