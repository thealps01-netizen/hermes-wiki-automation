/**
 * Wiki Automation — the HEALTH tab (the former Wiki Watchdog panel) — drawn in the REAL engine (the app's own Electron = Chromium), measured, and
 * captured as a PNG.
 *
 * Why a fourth gate: jsdom (render_check) proves the structure and the contract but cannot prove a
 * PIXEL. There is no Chrome on this machine; the only way to see and measure the layout is the app's
 * own engine. The measurement matters: a cell that comes back `cut: true` means that column clips its
 * own content — the fixed-height / no-clipping contract does not hold on screen.
 *
 * The gate (exit code 1 on violation): no horizontal overflow, nothing clipped (KPI · badges · two
 * line cells · time cell), no native `title` attribute, no native `<select>`, and NO LANGUAGE PICKER
 * (neither a class match nor a TR/EN button) — the panel follows the application language and has no
 * switch of its own.
 *
 * THE DESTRUCTIVE PAIR (2.6.1). `--dt-destructive` is the FILL token: on this theme it carries the
 * same `#cf2d56` in the light and the dark palette (the `.dark` block does not override it), which is
 * 3.33–3.51:1 as reading ink on the dark surface — under AA. `--ui-red` IS overridden by `.dark`
 * (`#e75e78`) and is the token the panel's own tone map already declares for this severity. So the
 * gate measures, per painted text node, the ink and the colour really behind it (translucent
 * surfaces composited in paint order; colours read back from a canvas pixel so an `oklch()` value
 * cannot be mangled by a parser of our own) and holds TWO classes to AA (4.5:1):
 *   A. the destructive token worn as READING TEXT,
 *   B. text sitting on a FILLED destructive surface (a full-opacity `--dt-destructive` / `--ui-red`
 *      fill).
 * The full per-node dump is written beside the PNG as `<out>.contrast.json`. Negative control:
 * `WD_CONTRAST_CANARY=text|fill` injects that class' violation into the drawn page, and the gate must
 * name it and exit 1.
 *
 * Usage (from the hermes home, after generating the preview):
 *   cd plugins/wiki-automation/tests && node preview.mjs --state=history
 *   <home>/hermes-agent/apps/desktop/node_modules/electron/dist/electron.exe \
 *     plugins/wiki-automation/tests/shot_health.cjs plugins/wiki-automation/tests/preview-metro-history-log.html \
 *     plugins/wiki-automation/tests/health-560.png 560   (and 1240)
 *   Append --theme=light for a pre-load fixture copy (never a product style override).
 *   Append --frame=390 with width 1240 to measure a narrow pane in a wide window.
 *
 * Metro (2.5.0): the former Health and Chronicle views are ONE History detail (header button `History`):
 * KPIs, chart, filters, the run journal, the drawer and archive-before-clear. The page is
 * `preview-metro-history-log.html` (`node preview.mjs --state=history-log`); this gate requires the journal to
 * be there, and no tab strip anywhere.
 */
const { app, BrowserWindow } = require('electron')
const fs = require('fs')
const path = require('path')

const [htmlArg, outArg, widthArg, ...flags] = process.argv.slice(2)
const htmlPath = path.resolve(htmlArg || path.join(__dirname, 'preview-metro-history-log.html'))
const outPath = path.resolve(outArg || path.join(__dirname, 'health-560.png'))
const THEME = (flags.find(f => f.startsWith('--theme=')) || '').split('=')[1] || 'dark'
const WIDTH = Number(widthArg || 560)
const frameFlag = flags.find(f => f.startsWith('--frame='))
const FRAME = frameFlag ? Number(frameFlag.split('=')[1]) : WIDTH
if (!['dark', 'light'].includes(THEME)) throw new Error(`Unknown theme: ${THEME}`)
if (![WIDTH, FRAME].every(n => Number.isInteger(n) && n > 0)) throw new Error('Widths must be positive integer pixels')
app.disableHardwareAcceleration()

const MEASURE = `(() => {
  const h = sel => {
    const el = document.querySelector(sel)
    return el ? Math.round(el.getBoundingClientRect().height) : null
  }
  const frame = document.querySelector('.wa-frame')
  const pane = document.querySelector('.wa-frame > div')
  const root = document.querySelector('.pa-root')
  const duplicateJournal = [...document.querySelectorAll('.pa-log, .pa-log-head, .pa-logwrap, '
    + '.pa-logscroll, .pa-clear-open, .pa-clear-ask, .pa-clear-note, .pa-drawer, .pa-raw, '
    + '.pa-findlist, .ch-journal, .ch-inspector-empty, .pa-selwrap[data-sel="sort"]')]
    .map(el => String(el.className || el.tagName))
  // ALIGNMENT: does the head row sit on the same x as a data row? A delta means the columns shifted.
  const rowEl = document.querySelector('.pa-log')
  const headEl = document.querySelector('.pa-log-head')
  const alignDeltas = rowEl && headEl
    ? [...headEl.children].map((h, i) => {
        const r2 = rowEl.children[i]
        return r2 ? Math.round(r2.getBoundingClientRect().x - h.getBoundingClientRect().x) : null
      })
    : null
  const kpiFigY = [...document.querySelectorAll('.pa-kpi')].map(k => Math.round(k.children[1].getBoundingClientRect().y))
  const timeCell = rowEl && rowEl.children[1]
  // COLUMN DROPPING: which columns are visible at this width?
  const visibleCols = [...document.querySelectorAll('.pa-log-head > span')]
    .filter(s => s.textContent.trim() && s.getBoundingClientRect().width > 0)
    .map(s => s.textContent.trim())
  // A cell that does not fit in two lines: line-clamp overflow grows scrollHeight (a clipping flag).
  // Cells with width 0 (a column dropped in a narrow pane) are NOT counted — they are not on screen.
  const clampedCells = [...document.querySelectorAll('.pa-log .pa-clamp')]
    .filter(c => c.getBoundingClientRect().width > 0 && c.scrollHeight > c.clientHeight + 1)
    .map(c => (c.textContent || '').slice(0, 24))
  const drawer = document.querySelector('.pa-drawer')
  const drawerBody = document.querySelector('.pa-drawer-body')
  // COLOR MEASUREMENT: the "no fixed hex" claim is read back from the screen (computed values).
  const css = (sel, prop) => {
    const el = document.querySelector(sel)
    return el ? getComputedStyle(el)[prop] : null
  }
  const colors = {
    page: css('.pa-root', 'backgroundColor'),
    sectionCard: css('.pa-sec', 'backgroundColor'),
    kpiCard: css('.pa-kpi', 'backgroundColor'),
    kpiBorder: css('.pa-kpi', 'borderTopWidth'),
    bar: css('.pa-bar:not([data-zero="1"])', 'backgroundColor'),
    badgeWarn: css('.pa-badge[data-tone="warn"]', 'color'),
    badgeWarnBorder: css('.pa-badge[data-tone="warn"]', 'borderTopColor'),
    selectBorder: css('.pa-sel', 'borderTopColor'),
    segmentOn: css('.pa-seg button[aria-pressed="true"]', 'backgroundColor')
  }
  // SELECTORS: no native select (the OS list does not follow the theme) — the measured evidence.
  const sels = [...document.querySelectorAll('.pa-selwrap')].map(w => ({
    id: w.getAttribute('data-sel'),
    h: Math.round(w.querySelector('.pa-sel').getBoundingClientRect().height),
    text: (w.querySelector('.pa-sel').textContent || '').trim(),
    open: w.querySelectorAll('.pa-pop').length > 0,
    opts: w.querySelectorAll('.pa-opt').length,
    checks: w.querySelectorAll('.pa-check').length
  }))
  const logTitle = [...document.querySelectorAll('.pa-sectitle')].pop()
  // REFERENCE PASS (2.6.0): the chip, row and tab geometry the reference files pin. Measured, not
  // assumed — one radius / one padding family for the chips, one height for the finding rows with a
  // hairline between them, one height+radius for the pill tabs, and ONE tone map behind every
  // severity surface (a tone that resolved to two variants or two colors would show up right here).
  const chips = [...document.querySelectorAll('.pa-badge')].map(b => {
    const s = getComputedStyle(b)
    return {
      r: s.borderTopLeftRadius,
      p: s.paddingTop + ' ' + s.paddingRight,
      h: Math.round(b.getBoundingClientRect().height)
    }
  })
  const findRows = [...document.querySelectorAll('.pa-findlist [data-panel-row]')].map(r => ({
    h: Math.round(r.getBoundingClientRect().height),
    sep: getComputedStyle(r).borderBottomWidth,
    fill: getComputedStyle(r).backgroundColor
  }))
  const toneMatrix = {}
  // 2.5.1: the tone map is the technical log's; the m-13 run list above it has its own dots.
  ;(document.querySelector('.wa-metro-techlog') || document).querySelectorAll('[data-tone]').forEach(el => {
    const tone = el.getAttribute('data-tone')
    if (!tone) return
    const entry = toneMatrix[tone] || (toneMatrix[tone] = { variants: [], badgeColors: [], panelColors: [] })
    if (el.getAttribute('data-slot') === 'badge') {
      const v = el.getAttribute('data-variant')
      if (entry.variants.indexOf(v) < 0) entry.variants.push(v)
      const c = getComputedStyle(el).color
      if (entry.badgeColors.indexOf(c) < 0) entry.badgeColors.push(c)
    } else {
      const c = getComputedStyle(el).backgroundColor
      if (entry.panelColors.indexOf(c) < 0) entry.panelColors.push(c)
    }
  })
  const tabs = [...document.querySelectorAll('.pa-seg button')].map(b => ({
    h: Math.round(b.getBoundingClientRect().height),
    r: getComputedStyle(b).borderTopLeftRadius
  }))
  const searchEl = document.querySelector('.pa-filters input')
  const search = searchEl
    ? {
        h: Math.round(searchEl.getBoundingClientRect().height),
        r: getComputedStyle(searchEl).borderTopLeftRadius,
        pad: getComputedStyle(searchEl).paddingLeft,
        bg: getComputedStyle(searchEl).backgroundColor
      }
    : null
  // Every Health section is the shared section card (2.3.9).
  // Keep fractional boxes for the full-span section check, not screenshot guesses.
  const box = el => {
    if (!el) return null
    const r = el.getBoundingClientRect()
    return { x: r.x, y: r.y, w: r.width, h: r.height }
  }
  const contentWidth = el => el.clientWidth - parseFloat(getComputedStyle(el).paddingLeft)
    - parseFloat(getComputedStyle(el).paddingRight)
  const queryWidth = el => {
    for (let p = el.parentElement; p; p = p.parentElement) {
      if (getComputedStyle(p).containerType.includes('size')) return contentWidth(p)
    }
    return window.innerWidth
  }
  const sections = [...document.querySelectorAll('.pa-sec')].map(s => {
    const head = s.children[0]
    const body = s.children[1]
    const cs = getComputedStyle(s)
    return {
      title: (head?.children[0]?.textContent || '').slice(0, 16),
      ...box(s),
      border: cs.borderTopWidth,
      sides: [cs.borderRightWidth, cs.borderBottomWidth, cs.borderLeftWidth],
      radius: cs.borderTopLeftRadius,
      background: cs.backgroundColor,
      headBorder: head ? getComputedStyle(head).borderBottomWidth : null,
      bodyBorder: body ? getComputedStyle(body).borderTopWidth : null
    }
  })
  const metricStrip = document.querySelector('.pa-kpis')
  const metricStyle = metricStrip && getComputedStyle(metricStrip)
  const diagnosticLabels = [...document.querySelectorAll('.pa-act-row')]
    .map(el => ({ cls: el.className, width: parseFloat(getComputedStyle(el).gridTemplateColumns),
      queryW: queryWidth(el) }))
  const metricCells = [...document.querySelectorAll('.pa-kpis > .pa-kpi')].map(el => {
    const cs = getComputedStyle(el)
    return { ...box(el), border: cs.borderTopWidth, right: cs.borderRightWidth,
      bottom: cs.borderBottomWidth, radius: cs.borderTopLeftRadius, background: cs.backgroundColor }
  })
  // --- WCAG contrast, the destructive pair --------------------------------------------------------
  // The engine hands back the value it really computed, and an oklch()/color() value comes back
  // verbatim — so the colour is PAINTED onto a 1x1 canvas and the pixel is read back: no colour
  // parser of our own, no guess. A sentinel fill in front of every paint makes a value the canvas
  // refuses DETECTABLE instead of silently reading as its predecessor.
  const cv = document.createElement('canvas')
  cv.width = 2
  cv.height = 1
  const cx = cv.getContext('2d', { willReadFrequently: true })
  const pixelAt = (v, x) => {
    cx.clearRect(x, 0, 1, 1)
    cx.fillStyle = '#010203'
    cx.fillStyle = String(v)
    cx.fillRect(x, 0, 1, 1)
    const d = cx.getImageData(x, 0, 1, 1).data
    return [d[0], d[1], d[2], d[3] / 255]
  }
  const selfCheck = pixelAt('#ff0000', 0)
  const parserOk = selfCheck[0] === 255 && selfCheck[1] === 0 && selfCheck[2] === 0
  const unparsed = []
  const rgba = (v, tag) => {
    const c = pixelAt(v, 1)
    if (c[0] === 1 && c[1] === 2 && c[2] === 3) {
      unparsed.push(String(tag === undefined ? v : tag))
      return null
    }
    return c
  }
  const lum = c => {
    const f = v => {
      const s = v / 255
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
    }
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])
  }
  const ratio = (f, b) => {
    const l1 = lum(f)
    const l2 = lum(b)
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05)
  }
  const over = (f, b) => {
    if (!f) return b
    if (!b) return f
    const a = f[3]
    return [f[0] * a + b[0] * (1 - a), f[1] * a + b[1] * (1 - a), f[2] * a + b[2] * (1 - a), 1]
  }
  // The colour really behind the glyphs: every translucent surface above the node is composited in
  // paint order down to the first opaque one.
  const bgOf = el => {
    const chain = []
    let n = el
    while (n) {
      const c = rgba(getComputedStyle(n).backgroundColor, 'bg') || [0, 0, 0, 0]
      chain.push(c)
      if (c[3] >= 0.999) break
      n = n.parentElement
    }
    const last = chain[chain.length - 1]
    const floor = last && last[3] >= 0.999 ? last : [255, 255, 255, 1]
    let acc = floor
    for (let i = chain.length - 2; i >= 0; i -= 1) acc = over(chain[i], acc)
    return acc
  }
  const same3 = (a, b) => !!a && !!b && Math.abs(a[0] - b[0]) < 0.6
    && Math.abs(a[1] - b[1]) < 0.6 && Math.abs(a[2] - b[2]) < 0.6
  // The theme tokens are read through the ENGINE, not out of the file. A token the theme stopped
  // defining makes the declaration invalid at computed-value time, so the probe INHERITS — and it
  // inherits from a wrapper pinned to a colour no theme token uses, which is what makes that
  // detectable instead of passing by luck.
  const tpw = document.createElement('span')
  tpw.style.color = 'rgb(2, 3, 4)'
  const tp = document.createElement('span')
  tpw.appendChild(tp)
  document.body.appendChild(tpw)
  const probe = name => {
    tp.style.color = ''
    tp.style.color = 'var(' + name + ')'
    return rgba(getComputedStyle(tp).color, name)
  }
  const absent = probe('--wd-token-that-does-not-exist')
  const token = name => {
    const c = probe(name)
    return c && absent && same3(c, absent) ? null : c
  }
  const TOKEN_NAMES = ['--dt-destructive', '--dt-destructive-foreground', '--ui-red',
    '--ui-text-primary', '--ui-bg-elevated']
  const TOK = {}
  TOKEN_NAMES.forEach(name => { TOK[name] = token(name) })
  const DT = TOK['--dt-destructive']
  const RED = TOK['--ui-red']
  const round3 = c => 'rgb(' + [c[0], c[1], c[2]].map(v => Math.round(v)).join(',') + ')'
  // One row per node that really paints text: its ink, the colour behind it, and the ratio between.
  const textRows = []
  const sweepRoot = document.querySelector('.wa-shell') || document.querySelector('.pa-root') || document.body
  for (const el of sweepRoot.querySelectorAll('*')) {
    if (![...el.childNodes].some(c => c.nodeType === 3 && c.textContent.trim())) continue
    const s = getComputedStyle(el)
    if (s.display === 'none' || s.visibility === 'hidden' || Number(s.opacity) === 0) continue
    const elBox = el.getBoundingClientRect()
    if (elBox.width < 1 || elBox.height < 1) continue
    const ink = rgba(s.color, 'ink')
    if (!ink || ink[3] === 0) continue
    const bg = bgOf(el)
    const px = parseFloat(s.fontSize)
    const weight = parseInt(s.fontWeight, 10) || 400
    // WCAG large text is 18pt (24 CSS px), or 14pt (~18.67 CSS px) bold.
    const large = px >= 24 || (px >= 18.67 && weight >= 700)
    const flat = bg[3] >= 0.999 ? [bg[0], bg[1], bg[2]] : null
    const value = ratio(over(ink, bg), bg)
    textRows.push({
      text: (el.textContent || '').trim().slice(0, 30),
      sel: el.tagName.toLowerCase() + (el.className ? '.' + String(el.className).split(' ')[0] : ''),
      tone: el.getAttribute('data-tone'),
      destructiveInk: same3(ink, DT),
      destructiveFill: !!flat && same3(flat, DT),
      redFill: !!flat && same3(flat, RED),
      color: round3(ink),
      inkAlpha: ink[3],
      on: round3(bg),
      font: px + 'px/' + weight,
      px,
      need: large ? 3 : 4.5,
      ratio: Math.round(value * 100) / 100,
      ok: value >= (large ? 3 : 4.5)
    })
  }
  // The TWO classes this gate exists for. Both bars are AA (4.5:1) whatever the type size: a
  // destructive tone is an alarm colour and the brief fixes 4.5 for both of them.
  const least = group => group.reduce((m, r) => (m === null || r.ratio < m ? r.ratio : m), null)
  const destructiveText = textRows.filter(r => r.destructiveInk)
  const destructiveFillText = textRows.filter(r => r.destructiveFill || r.redFill)
  const contrast = {
    parser: parserOk ? 'canvas-rgba' : 'FAILED',
    unparsed: unparsed.slice(0, 8),
    tokens: TOKEN_NAMES.map(n => n + '=' + (TOK[n] ? round3(TOK[n]) : 'UNDEFINED')).join(' · '),
    measured: textRows.length,
    destructiveToneNodes: textRows.filter(r => r.tone === 'bad').length,
    belowAA: textRows.filter(r => !r.ok).map(r => r.sel + ' [' + r.text + '] ' + r.ratio + ':1'),
    lowest: least(textRows),
    destructiveText: { count: destructiveText.length, lowest: least(destructiveText),
      nodes: destructiveText },
    destructiveFillText: { count: destructiveFillText.length, lowest: least(destructiveFillText),
      nodes: destructiveFillText },
    rows: textRows
  }
  return {
    contrast,
    theme: document.documentElement.classList.contains('dark') ? 'dark' : 'light',
    previewState: frame?.dataset.previewState || null,
    openDetail: document.querySelector('.wa-metro-detail')?.getAttribute('data-for') || null,
    historyPressed: document.querySelector('[data-wa-nav="history"]')?.getAttribute('aria-pressed') || null,
    rootView: root?.dataset.view || (root?.classList.contains('pa-health') ? 'health' : null),
    workspaceTabs: [...document.querySelectorAll('[role="tab"], [role="tablist"], [data-slot="tabs-trigger"]')]
      .map(el => el.textContent.trim()),
    duplicateJournal,
    containerType: root ? getComputedStyle(root).containerType : null,
    rootW: root ? Math.round(root.getBoundingClientRect().width) : null,
    rootContentW: root ? contentWidth(root) : null,
    layoutQueryW: root ? queryWidth(root) : null,
    rootBox: box(root),
    rootPadding: root ? getComputedStyle(root).paddingLeft : null,
    header: { size: css('.pa-title', 'fontSize'), padding: css('.pa-topbar', 'paddingTop') },
    freshnessHeight: h('.pa-fr'),
    metricStrip: metricStyle ? { ...box(metricStrip), border: metricStyle.borderTopWidth,
      radius: metricStyle.borderTopLeftRadius, queryW: queryWidth(metricStrip), cells: metricCells } : null,
    diagnosticLabels,
    diagnosticLabelWidths: diagnosticLabels.map(el => el.width),
    // The time column must not be cut: a clipped "10:22:56" is unreadable (this happened).
    timeCell: timeCell
      ? { text: timeCell.textContent, cut: timeCell.scrollWidth > timeCell.clientWidth + 1 }
      : null,
    // A native title attribute = the operating system's box (which does not follow the theme): 0.
    nativeTitles: document.querySelectorAll('[title]').length,
    alignDeltas,
    kpiFigureYs: kpiFigY,
    drawer: drawer
      ? {
          w: Math.round(drawer.getBoundingClientRect().width),
          h: Math.round(drawer.getBoundingClientRect().height),
          sections: drawer.querySelectorAll('.pa-drawer-sec').length,
          kvPairs: drawer.querySelectorAll('.pa-kv dd').length,
          rawOpen: drawer.querySelectorAll('.pa-raw').length > 0,
          // One scrolling surface: the region scrolls inside itself, not the page.
          bodyScrolls: drawerBody ? drawerBody.scrollHeight > drawerBody.clientHeight + 1 : null
        }
      : null,
    visibleCols,
    clampedCells,
    sections,
    colors,
    sels,
    nativeSelects: document.querySelectorAll('select').length,
    // LANGUAGE CONTRACT: the panel has no picker of its own — measured, not assumed.
    languagePickers: document.querySelectorAll('[class*="lang"]').length,
    languageButtons: [...document.querySelectorAll('button')]
      .filter(b => ['TR', 'EN'].includes((b.textContent || '').trim())).length,
    rawKeys: [...(document.body.innerText || '').matchAll(/\\bwd\\.[a-z][a-zA-Z0-9_.]*/g)]
      .map(m => m[0]).slice(0, 5),
    // Does the head strip overflow? The sort pill has to fit inside it.
    logTitleOverflow: logTitle ? logTitle.scrollWidth - logTitle.clientWidth : null,
    tips: document.querySelectorAll('.pa-tip').length,
    calendars: document.querySelectorAll('.pa-cal').length,
    frameW: frame ? Math.round(frame.getBoundingClientRect().width) : null,
    paneW: pane ? Math.round(pane.getBoundingClientRect().width) : null,
    horizontalOverflowPx: pane ? pane.scrollWidth - pane.clientWidth : null,
    kpiHeight: h('.pa-kpi'),
    chartHeight: h('.pa-chart'),
    logHeadHeight: h('.pa-log-head'),
    logRowHeight: h('.pa-log'),
    kpiCards: document.querySelectorAll('.pa-kpi').length,
    logRows: document.querySelectorAll('.pa-log').length,
    bars: document.querySelectorAll('.pa-bar-col').length,
    badges: document.querySelectorAll('.pa-badge').length,
    // Diagnostic badges are independent of the Chronicle list; measure every painted badge.
    cutBadges: [...document.querySelectorAll('.pa-badge')]
      .filter(b => b.getBoundingClientRect().width > 0 && b.scrollWidth > b.clientWidth + 1).length,
    clippedKpis: [...document.querySelectorAll('.pa-kpi')].filter(k => k.scrollHeight > k.clientHeight + 1).length,
    // CUT INSIDE A CARD (2.16.0). The card-level check above cannot see a caption cut by a BOX INSIDE a
    // card that is itself the right size — which is exactly what the user's red box marked: a 26px
    // label box holding one line of "RUNS WITH FINDINGS" ("RUNS WITH" on screen) and a 26px caption
    // box holding two ("no output, nothing...", cut at 18.4px). Two facts make a cut a DESIGN choice:
    // box declares a scroll (max-height + overflow auto/scroll) or it carries a line clamp. Everything
    // else that cuts is an accident. An invisible carrier is exempt: the 1px date input that only
    // holds the value for the OS picker has 9px of content in its 1px box and nothing to show.
    innerClip: [...document.querySelectorAll('.pa-root *')]
      .filter(el => {
        const cs = getComputedStyle(el)
        if (!['hidden', 'clip'].includes(cs.overflowY)) return false
        if (parseFloat(cs.opacity) === 0) return false
        if (el.scrollHeight <= el.clientHeight + 2) return false
        if (['auto', 'scroll'].includes(cs.overflowY) && cs.maxHeight !== 'none') return false
        if (cs.webkitLineClamp && cs.webkitLineClamp !== 'none') return false
        return true
      })
      .map(el => ({ cls: String(el.className || el.tagName).slice(0, 44),
                    over: el.scrollHeight - el.clientHeight,
                    text: (el.textContent || '').trim().slice(0, 34) }))
      .slice(0, 12),
    // PAINTED OUTSIDE ITS OWN BOX (2.16.0): a card shorter than its content paints over the section
    // below it. The freshness orbs left the card by 38.6 px at 466/560 and landed on the KPI row.
    spill: [...document.querySelectorAll('.pa-fr, .pa-kpi, .pa-chart, .pa-act')]
      .filter(el => el.scrollHeight > el.clientHeight + 2
        && getComputedStyle(el).overflowY === 'visible')
      .map(el => ({ cls: String(el.className || el.tagName).slice(0, 44),
                    over: el.scrollHeight - el.clientHeight,
                    h: Math.round(el.getBoundingClientRect().height) }))
      .slice(0, 12),
    // The KPI label box holds ONE line by design, so the gate states the line count it really drew.
    kpiLabels: [...document.querySelectorAll('.pa-kpi-lab')].map(el => {
      const lh = parseFloat(getComputedStyle(el).lineHeight) || 1
      return { text: (el.textContent || '').trim(),
               lines: Math.round(el.scrollHeight / lh),
               cut: el.scrollHeight > el.clientHeight + 1 }
    }),
    chips: {
      count: chips.length,
      radii: [...new Set(chips.map(c => c.r))],
      paddings: [...new Set(chips.map(c => c.p))],
      heights: [...new Set(chips.map(c => c.h))]
    },
    findRows,
    findRowHeights: [...new Set(findRows.map(r => r.h))],
    findRowSeparators: [...new Set(findRows.map(r => r.sep))],
    findRowActive: findRows.filter(r => r.fill !== 'rgba(0, 0, 0, 0)').length,
    toneMatrix,
    tabs: { heights: [...new Set(tabs.map(t => t.h))], radii: [...new Set(tabs.map(t => t.r))] },
    search,
    controlHeights: [...new Set([...document.querySelectorAll('.pa-filters .pa-dateface, '
      + '.pa-filters .pa-sel, .pa-filters input:not([type="date"])')]
      .map(el => Math.round(el.getBoundingClientRect().height)))],
    docHeight: Math.round(document.documentElement.scrollHeight)
  }
})()`

const GATE = ['horizontalOverflowPx', 'cutBadges', 'clampedCells', 'clippedKpis', 'innerClip', 'spill',
  'nativeTitles', 'nativeSelects', 'languagePickers', 'languageButtons', 'rawKeys']

// The negative control for the destructive pair: each mode injects ONE class' violation into the page
// that has ALREADY been drawn, so it exercises the same measurement path and nothing else. `text`
// rebuilds the pre-2.6.1 chip exactly (the kit's destructive variant ink on its own 10% tint); `fill`
// builds the other forbidden shape (a full `--ui-red` fill under the foreground token = 3.35:1).
const CANARY = {
  text: `(() => {
    const host = document.querySelector('.pa-root')
    if (!host) return 'no host'
    const el = document.createElement('div')
    el.setAttribute('data-canary', 'destructive-as-text')
    el.style.cssText = 'font-size:10.5px;padding:4px 8px;border-radius:4px;'
      + 'color:var(--dt-destructive);'
      + 'background-color:color-mix(in srgb, var(--dt-destructive) 10%, transparent)'
    el.textContent = 'canary: destructive token worn as reading text'
    host.appendChild(el)
    return 'injected'
  })()`,
  fill: `(() => {
    const host = document.querySelector('.pa-root')
    if (!host) return 'no host'
    const el = document.createElement('div')
    el.setAttribute('data-canary', 'text-on-destructive-fill')
    el.style.cssText = 'font-size:10.5px;padding:4px 8px;border-radius:4px;'
      + 'color:var(--dt-destructive-foreground);background-color:var(--ui-red)'
    el.textContent = 'canary: reading text on a filled destructive surface'
    host.appendChild(el)
    return 'injected'
  })()`
}

// The negative control for the two layout classes: `clip` rebuilds the cut caption (two lines in a
// one-line box) and `spill` rebuilds the card whose content leaves it. Both are injected into the page
// that has ALREADY been drawn, so the same measurement path runs.
const LAYOUT_CANARY = {
  clip: `(() => {
    const card = document.querySelector('.pa-kpi')
    if (!card) return 'no KPI card'
    const el = document.createElement('div')
    el.setAttribute('data-canary', 'cut-caption')
    el.style.cssText = 'height:14px;overflow:hidden;font-size:10.5px;line-height:13px'
    el.textContent = 'canary caption that needs two lines to be readable'
    card.appendChild(el)
    return 'injected'
  })()`,
  journal: `(() => {
    const rows = document.querySelectorAll('.pa-log, .pa-logwrap')
    if (!rows.length) return 'no journal'
    rows.forEach(el => el.remove())
    return 'injected'
  })()`,
  container: `(() => {
    const style = document.querySelector('.pa-root style')
    if (!style || !style.textContent.includes('@container')) return 'no container rules'
    style.textContent = style.textContent.replaceAll('@container', '@media')
    return 'injected'
  })()`,
  spill: `(() => {
    const host = document.querySelector('.pa-root')
    if (!host) return 'no host'
    const el = document.createElement('div')
    el.setAttribute('data-canary', 'spilling-card')
    el.className = 'pa-kpi'
    el.style.cssText = 'min-height:112px;height:112px;overflow:visible;display:flex;'
      + 'flex-direction:column;padding:9px 10px'
    const lab = document.createElement('div')
    lab.textContent = 'canary'
    const tall = document.createElement('div')
    tall.style.cssText = 'height:200px;flex:0 0 auto'
    tall.textContent = 'canary content taller than its card'
    el.appendChild(lab)
    el.appendChild(tall)
    host.appendChild(el)
    return 'injected'
  })()`
}

app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: WIDTH + 40, height: 1400, show: false,
    webPreferences: { javascript: true, backgroundThrottling: false } })
  try {
    win.webContents.on('render-process-gone', (e, d) => console.error('[renderer gone]', JSON.stringify(d)))
    let fixture = htmlPath
    if (THEME === 'light') {
      const html = fs.readFileSync(fixture, 'utf8')
      if (!html.includes('<html class="dark"')) throw new Error('The fixture has no explicit theme class')
      const dir = path.join(path.dirname(fixture), '.cache')
      fs.mkdirSync(dir, { recursive: true })
      fixture = path.join(dir, `light-${path.basename(fixture)}`)
      fs.writeFileSync(fixture, html.replace('<html class="dark"', '<html class=""'))
    }
    await win.loadFile(fixture)
    for (let i = 0; i < 100; i += 1) {
      if (await win.webContents.executeJavaScript('document.documentElement.dataset.waReady || ""')) break
      await new Promise(r => setTimeout(r, 100))
    }
    // Third argument: frame width (px); --frame tests a separate pane inside that wide window.
    await win.webContents.insertCSS(`.wa-frame{width:${FRAME}px !important}`)
    await new Promise(r => setTimeout(r, 400))
    const canaryMode = String(process.env.WD_CONTRAST_CANARY || '').trim()
    if (canaryMode) {
      if (!CANARY[canaryMode]) {
        console.error(`unknown WD_CONTRAST_CANARY mode: ${canaryMode} (use text|fill)`)
        app.exit(1)
        return
      }
      const injected = await win.webContents.executeJavaScript(CANARY[canaryMode])
      console.log(`contrast canary '${canaryMode}' injected: ${injected}`)
      await new Promise(r => setTimeout(r, 150))
    }
    const layoutMode = String(process.env.WD_LAYOUT_CANARY || '').trim()
    if (layoutMode) {
      if (!LAYOUT_CANARY[layoutMode]) {
        console.error(`unknown WD_LAYOUT_CANARY mode: ${layoutMode} (use clip|spill|journal|container)`)
        app.exit(1)
        return
      }
      const injected = await win.webContents.executeJavaScript(LAYOUT_CANARY[layoutMode])
      console.log(`layout canary '${layoutMode}' injected: ${injected}`)
      await new Promise(r => setTimeout(r, 150))
    }
    // The window shrinks to its content so the PNG holds no empty space.
    const docHeight = await win.webContents.executeJavaScript('document.documentElement.scrollHeight')
    win.setContentSize(WIDTH + 40, Math.min(1600, docHeight + 20))
    await new Promise(r => setTimeout(r, 300))
    // Measure the settled page. Since 2.3.9 every block of a view rises in (480 ms, staggered), and a
    // canary appended to the page gets the same entry: measured at once, it was still transparent and
    // the contrast canary went unseen. Looping animations never finish and are not waited for.
    await win.webContents.executeJavaScript(`Promise.race([
      Promise.all(document.getAnimations()
        .filter(a => a.effect && a.effect.getComputedTiming().endTime !== Infinity)
        .map(a => a.finished.catch(() => null))),
      new Promise(r => setTimeout(r, 5000))])`)
    const measurement = await win.webContents.executeJavaScript(MEASURE)
    const image = await win.webContents.capturePage()
    fs.writeFileSync(outPath, image.toPNG())
    // The measurement is kept beside the PNG: the dump is the evidence, the PNG is the picture. The
    // per-node contrast table is written before the gate runs, so a RED run still leaves its numbers.
    const contrastPath = outPath.replace(/\.png$/i, '.contrast.json')
    fs.writeFileSync(contrastPath, JSON.stringify(measurement.contrast || {}, null, 1))
    console.log(JSON.stringify(measurement, null, 1))
    // MOTION MEASUREMENT (after the PNG): does the drawer really SLIDE? There is no React in a static
    // HTML but the CSS transition is driven by a DOM attribute, so intermediate widths during
    // EXIT_MS mean the animation plays (an instant 0 means there is no transition).
    const motion = await win.webContents.executeJavaScript(`(async () => {
      const wrap = document.querySelector('.pa-logwrap')
      const drawer = document.querySelector('.pa-drawer')
      const list = document.querySelector('.pa-logscroll')
      if (!wrap || !drawer || !list) return { animated: null }
      // 1) IS THE LEFT SIDE FIXED: hiding the drawer must NOT change the list width (an overlay, not
      //    a squeeze). Equal means the list is unaffected by the drawer.
      const listWith = Math.round(list.getBoundingClientRect().width)
      drawer.style.display = 'none'
      const listWithout = Math.round(list.getBoundingClientRect().width)
      drawer.style.display = ''
      // 2) SLIDING IN FROM THE RIGHT: push the drawer out (data-in="0"), then open it and sample its
      //    LEFT edge — decreasing values mean it really slides leftwards.
      drawer.setAttribute('data-in', '0')
      await new Promise(r => setTimeout(r, 60))
      const leftClosed = Math.round(drawer.getBoundingClientRect().left)
      const leftSamples = []
      drawer.setAttribute('data-in', '1')
      for (let i = 0; i < 6; i += 1) {
        await new Promise(r => setTimeout(r, 40))
        leftSamples.push(Math.round(drawer.getBoundingClientRect().left))
      }
      const leftOpen = Math.round(drawer.getBoundingClientRect().left)
      const bar = document.querySelector('.pa-kindbar')
      return {
        listWithDrawer: listWith,
        listWithoutDrawer: listWithout,
        listUnaffectedByDrawer: listWith === listWithout,
        leftClosed,
        leftSamples,
        leftOpen,
        slideAnimated: new Set(leftSamples).size > 2,
        slideLeftward: leftSamples.every((v, i) => i === 0 ? v <= leftClosed : v <= leftSamples[i - 1]),
        drawerTransition: getComputedStyle(drawer).transitionProperty,
        drawerDuration: getComputedStyle(drawer).transitionDuration,
        kindBarAnimation: bar ? getComputedStyle(bar).animationName : null,
        kindBarWidth: bar ? bar.style.width : null
      }
    })()`)
    console.log(JSON.stringify({ motion }, null, 1))
    console.log(`png: ${outPath}`)
    const bad = GATE.filter(k => {
      const v = measurement[k]
      return Array.isArray(v) ? v.length > 0 : Number(v) > 0
    })
    if (measurement.timeCell && measurement.timeCell.cut) bad.push('timeCell.cut')
    if (measurement.theme !== THEME) bad.push(`theme: expected ${THEME}, measured ${measurement.theme}`)
    // Metro (2.5.1): the run history is History's "Full technical log", opened by the header's History button.
    if (measurement.previewState !== 'history-log' || measurement.openDetail !== 'history'
        || measurement.historyPressed !== 'true') bad.push('the History detail is not the open, pressed detail')
    if (measurement.workspaceTabs.length) bad.push('a tab strip is back: ' + measurement.workspaceTabs.join('|'))
    // 2.3.x split the journal (Chronicle) from the diagnostics (Health) and this gate proved the journal's
    // ABSENCE here. Metro puts the whole run history in ONE detail, so the journal must now be PRESENT.
    if (!measurement.duplicateJournal.some(cls => /pa-log/.test(String(cls)))) {
      bad.push('the History detail carries no run journal rows (.pa-log)')
    }
    if (measurement.containerType !== 'inline-size') bad.push('Health has no inline-size container')
    if (!measurement.diagnosticLabels.length) bad.push('diagnostic label columns are missing')
    for (const label of measurement.diagnosticLabels) {
      const expected = label.queryW <= 560 ? 96 : 160
      if (!Number.isFinite(label.width) || Math.abs(label.width - expected) > 1) {
        bad.push(`diagnostic label columns: ${label.cls} ${label.width}px; expected ${expected}px `
          + `in a ${label.queryW}px query container`)
      }
    }
    if (!measurement.paneW || measurement.frameW !== FRAME) bad.push('diagnostic frame/pane is missing or has the wrong width')
    // History (2.5.0) holds the three diagnostic sections and, under them, the one run journal.
    const order = ['Freshness', 'Run flow', 'Activity by job', 'Run journal']
    if (measurement.sections.length !== order.length
        || measurement.sections.some((s, i) => !s.title.startsWith(order[i]))) {
      bad.push('the three diagnostic sections and the run journal are missing, duplicated or out of order')
    }
    // Run flow spans the scope: every day from the oldest run in scope to today, 12 to 31 days.
    if (measurement.kpiCards !== 5 || measurement.bars < 12 || measurement.bars > 31
        || !measurement.diagnosticLabels.length) {
      bad.push('diagnostic KPI/flow/activity fixture content is missing')
    }
    const near = (a, b) => Number.isFinite(a) && Number.isFinite(b) && Math.abs(a - b) <= 1
    const [freshness, flow, activity] = measurement.sections
    // Since 2.3.9 every section in every view is the same card: 1 px border on all sides, 8 px radius,
    // the shared pane surface, and a full-width rule under its title.
    for (const section of measurement.sections) {
      if (section.border !== '1px' || section.radius !== '8px'
          || section.headBorder !== '1px' || section.bodyBorder !== '0px'
          || section.sides.join('/') !== '1px/1px/1px'
          || section.background === 'rgba(0, 0, 0, 0)') {
        bad.push('diagnostic section surface geometry: ' + JSON.stringify(section))
      }
    }
    for (const section of [freshness, flow, activity]) {
      if (!section || !near(section.w, measurement.rootContentW)
          || !near(section.x, measurement.rootBox.x + parseFloat(measurement.rootPadding))) {
        bad.push('diagnostic full-span section geometry: ' + JSON.stringify(section))
      }
    }
    // 2.5.0: the History detail's head names the view; the per-view title is gone (contract § Removed).
    if (measurement.header.size !== null
        || measurement.header.padding !== (measurement.layoutQueryW <= 560 ? '20px' : '28px')) {
      bad.push('diagnostic header geometry: ' + JSON.stringify(measurement.header))
    }
    for (const [key, floor] of [['kpiHeight', 86], ['freshnessHeight', 122], ['chartHeight', 60]]) {
      if (!Number.isFinite(measurement[key]) || measurement[key] < floor) {
        bad.push(`diagnostic height floor: ${key}=${measurement[key]}px < ${floor}px`)
      }
    }
    const strip = measurement.metricStrip
    if (!strip || strip.border !== '1px' || strip.radius !== '8px' || strip.cells.length !== 5
        || !near(strip.w, measurement.rootContentW)) {
      bad.push('diagnostic metric strip geometry: ' + JSON.stringify(strip))
    } else {
      const narrow = strip.queryW <= 560
      strip.cells.forEach((cell, i) => {
        const expectedRight = narrow ? (i < 4 && i % 2 === 0 ? '1px' : '0px') : (i < 4 ? '1px' : '0px')
        if (cell.border !== '0px' || cell.radius !== '0px' || cell.background !== 'rgba(0, 0, 0, 0)'
            || cell.right !== expectedRight || cell.bottom !== (narrow && i < 4 ? '1px' : '0px')
            || cell.h < 86
            || !near(cell.w, (strip.w - 2) / (narrow ? i === 4 ? 1 : 2 : 5))
            || !near(cell.y, strip.cells[narrow ? i - i % 2 : 0].y)) {
          bad.push('diagnostic divided metric geometry: ' + JSON.stringify({ i, narrow, cell }))
        }
      })
    }
    // REFERENCE GEOMETRY: one chip radius/padding family, one tab height+radius, and every tone
    // resolving to a single variant and a single color — the tone map is a map, not a scatter.
    const mixed = []
    if (measurement.chips.radii.length > 1) mixed.push('chip radii ' + measurement.chips.radii.join('/'))
    if (measurement.chips.paddings.length > 1) mixed.push('chip paddings ' + measurement.chips.paddings.join('/'))
    // Finding geometry/selection belongs to Chronicle (render_health.mjs + shot.cjs), not Health.
    // duplicateJournal above rejects even an empty finding list or unpainted drawer here.
    if (measurement.tabs.heights.length > 1) mixed.push('tab heights ' + measurement.tabs.heights.join('/'))
    if (measurement.tabs.radii.length > 1) mixed.push('tab radii ' + measurement.tabs.radii.join('/'))
    // Date/job/search controls form one field family; presets are separate 30px buttons.
    // Their wrapper can be 65px when the narrow pane lays the presets out on two rows.
    if (measurement.tabs.heights.join('/') !== '30' || measurement.tabs.radii.join('/') !== '4px') {
      mixed.push('preset geometry ' + JSON.stringify(measurement.tabs))
    }
    if ((measurement.controlHeights || []).length !== 1
        || ![28, 30].includes(measurement.controlHeights[0])) {
      mixed.push('filter field heights ' + (measurement.controlHeights || []).join('/'))
    }
    Object.keys(measurement.toneMatrix).forEach(tone => {
      const entry = measurement.toneMatrix[tone]
      if (entry.variants.length > 1) mixed.push('tone ' + tone + ' variants ' + entry.variants.join('/'))
      if (entry.badgeColors.length > 1) mixed.push('tone ' + tone + ' chip colors ' + entry.badgeColors.join('/'))
      if (entry.panelColors.length > 1) mixed.push('tone ' + tone + ' panel colors ' + entry.panelColors.join('/'))
    })
    if (mixed.length) bad.push('reference geometry: ' + mixed.join(' · '))
    const cutLabels = (measurement.kpiLabels || []).filter(l => l.cut)
    if (cutLabels.length) bad.push('KPI labels are cut: ' + cutLabels.map(l => l.text).join('/'))
    if (measurement.innerClip?.length) {
      bad.push('content is cut inside its own box: '
        + measurement.innerClip.map(c => `${c.cls} +${c.over}px "${c.text}"`).join(' · '))
    }
    if (measurement.spill?.length) {
      bad.push('a card paints outside its own box: '
        + measurement.spill.map(c => `${c.cls} +${c.over}px (h${c.h})`).join(' · '))
    }
    // THE DESTRUCTIVE PAIR (2.6.1). Two classes, both held to AA (4.5:1) whatever the type size.
    const ct = measurement.contrast || { rows: [] }
    const ctRed = []
    if (!measurement.contrast) ctRed.push('the contrast dump is missing')
    if (ct.parser !== 'canvas-rgba') ctRed.push('the colour parser failed its own self-check')
    if (!ct.measured) ctRed.push('no painted text node was measured')
    if (ct.unparsed && ct.unparsed.length) ctRed.push('unparsed colours: ' + ct.unparsed.join(' · '))
    // Match the shared pixel gate's floors: faint theme ladder >= 3:1, reading text >= AA.
    // Alarm text/fills are NEVER quiet exemptions: both destructive classes retain 4.5:1.
    for (const row of ct.rows || []) {
      const alarm = row.tone === 'bad' || row.destructiveInk || row.destructiveFill || row.redFill
      const need = alarm ? 4.5 : row.inkAlpha < 0.7 ? 3 : row.need
      if (row.ratio < need) ctRed.push(`${row.sel} [${row.text}] ${row.ratio}:1 on ${row.on} < ${need}:1`)
      if (row.px < 10.4) bad.push(`type: ${row.sel} [${row.text}] ${row.px}px < 10.4px`)
    }
    // Diagnostic scope can contain no failures. Absence is valid; unsafe alarm ink/fill, if present,
    // remains held to the SAME 4.5:1 bar below. Canary runs independently prove both paths still fire.
    const DT_TEXT = ct.destructiveText || { nodes: [] }
    const DT_FILL = ct.destructiveFillText || { nodes: [] }
    for (const row of DT_TEXT.nodes || []) {
      if (row.ratio < 4.5) {
        ctRed.push(`destructive token worn as reading text: .${row.sel} [${row.text}] ${row.ratio}:1 `
          + `on ${row.on} < 4.5:1`)
      }
    }
    for (const row of DT_FILL.nodes || []) {
      if (row.ratio < 4.5) {
        ctRed.push(`reading text on a filled destructive surface: .${row.sel} [${row.text}] `
          + `${row.ratio}:1 on ${row.on} < 4.5:1`)
      }
    }
    if (ctRed.length) bad.push('contrast: ' + ctRed.join(' · '))
    if (bad.length) {
      console.error(`MEASUREMENT FAILED: ${bad.map(k => Object.hasOwn(measurement, k)
        ? `${k}=${JSON.stringify(measurement[k])}` : k).join(' · ')}`)
      app.exit(1)
      return
    }
    console.log(`gate OK: overflow 0 · clipped 0 (badges/KPI/cells/time) · nativeTitles 0 · nativeSelects 0 · `
      + `languagePickers 0 · languageButtons 0 · rawKeys 0 · language contract measured`)
    console.log(`contrast: parser ${ct.parser} · ${ct.measured} text nodes measured · lowest ${ct.lowest}:1 · `
      + `below AA ${ct.belowAA.length} · class A (destructive as reading text) ${DT_TEXT.count} node(s), `
      + `lowest ${DT_TEXT.lowest === null ? 'n/a' : DT_TEXT.lowest + ':1'} · class B (text on a filled `
      + `destructive surface) ${DT_FILL.count} node(s), lowest ${DT_FILL.lowest === null ? 'n/a' : DT_FILL.lowest + ':1'}`)
    console.log(`contrast tokens: ${ct.tokens}`)
    console.log(`reference geometry: chip radius ${measurement.chips.radii.join('/')} · chip padding `
      + `${measurement.chips.paddings.join('/')} · journal/drawer absent (Chronicle-owned) · `
      + `tabs ${measurement.tabs.heights.join('/')} px `
      + `${measurement.tabs.radii.join('/')} · search ${measurement.search ? measurement.search.h : '—'} px `
      + `${measurement.search ? measurement.search.r : ''} · tones ${Object.keys(measurement.toneMatrix).join('/')}`)
    app.exit(0)
  } catch (err) {
    console.error(`measurement failed: ${err && err.message}`)
    app.exit(1)
  }
})
