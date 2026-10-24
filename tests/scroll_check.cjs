/**
 * Wiki Automation panel — THE SCROLL GATE: is every card reachable in a short pane?
 *
 * Why this exists: the panel root is `display:grid` inside a pane of FIXED height. A grid's `auto`
 * rows are compressed to fit a definite container, so when the pane was shorter than the panel every
 * card overflowed its own row, `.wa-card{overflow:hidden}` clipped the content inside it, and —
 * because the tracks were clamped to the pane — the root's scrollHeight equalled its clientHeight.
 * The panel showed NO scrollbar and its bottom card could not be reached at all: 6 elements sat below
 * a 760 px pane, 14 below 620 px, 60 below 220 px. `grid-auto-rows:max-content` on the root makes
 * every row its content's height, which is what turns the root's `overflow:auto` into a real scroll.
 *
 * Measured in the app's own engine (jsdom has no layout engine, so `render_check.mjs` cannot see it):
 *   clipped  -> an element cuts its own content and offers no scrollable descendant
 *   spill    -> an element overflows and NO scroll container up to the pane can reach the rest
 *   clipX    -> text wider than its box with no ellipsis
 *   cutBelow -> a leaf sits below the pane bottom and no scroll container reaches it
 * ...at a series of forced pane HEIGHTS (and pane widths as well with PROBE_WIDTHS).
 *
 * Usage: <electron> scroll_check.cjs [preview-metro-<state>.html] [frameSelector] [heights csv] [out.json] [--inject=<mode>]
 *        <electron> scroll_check.cjs preview-metro-history-log.html   (the History detail open)
 *        PROBE_WIDTHS=352,390,660 <electron> scroll_check.cjs     (narrow panes as well)
 * Build the pages first:  cd tests && node preview.mjs   (LIVE pages; the gate waits for data-wa-ready)
 *
 * Negative controls: `--inject=no-root-scroll` and `--inject=detail-grows` must each exit 1 on a page
 * with an open detail. The 1.6.0 control (`.wa-root` without `grid-auto-rows:max-content`) is kept only
 * as the audit rule `scroll flow` and its canary.
 */
const { app, BrowserWindow } = require('electron')
const fs = require('fs')
const path = require('path')

const flags = process.argv.slice(2).filter(a => a.startsWith('--'))
const [htmlArg, selArg, heightsArg, outArg] = process.argv.slice(2).filter(a => !a.startsWith('--'))
const INJECT = (flags.find(f => f.startsWith('--inject=')) || '').split('=')[1] || ''
// Negative controls. Each mode is appended to the page as a style rule and must make this gate exit 1.
//   no-root-scroll  -> the Metro root (and the reused roots inside a detail) stop scrolling: the detail
//                      under the map is cut at the pane's bottom
//   detail-grows    -> the Metro root loses its own scroll and grows to its content: the pane clips it
// The 2.0–2.4 `tabbody-grows` control went with the tab body (Metro has no tabs).
const INJECTIONS = {
  'no-root-scroll': '.wa-metro,.wa-root,.pa-root{overflow:hidden !important}',
  'detail-grows': '.wa-metro{overflow:visible !important;height:auto !important;max-height:none !important;'
    + 'min-height:auto !important;flex:0 0 auto !important}'
}
if (INJECT && !INJECTIONS[INJECT]) {
  console.log(`SCROLL CHECK: unknown --inject=${INJECT} (known: ${Object.keys(INJECTIONS).join(', ')})`)
  process.exit(3)
}
const htmlPath = htmlArg || path.join(__dirname, 'preview-metro-wiki.html')
const FRAME_SEL = selArg || '.wa-frame'
const HEIGHTS = (heightsArg || '760,620,560,430,330,220')
  .split(',')
  .map(s => parseInt(s.trim(), 10))
  .filter(n => Number.isFinite(n) && n > 0)
const WIDTHS = (process.env.PROBE_WIDTHS || '')
  .split(',')
  .map(s => parseInt(s.trim(), 10))
  .filter(n => Number.isFinite(n) && n > 0)
const outPath = outArg || htmlPath.replace(/\.html$/, '') + '.scroll.json'

app.disableHardwareAcceleration()

const PROBE = `(() => {
  const FRAME_SEL = ${JSON.stringify(FRAME_SEL)};
  const WIDTHS = ${JSON.stringify(WIDTHS)};
  const HEIGHTS = ${JSON.stringify(HEIGHTS)};
  const isScrollY = o => o === 'auto' || o === 'scroll' || o === 'overlay';
  const clsOf = el => (el.className && typeof el.className === 'string')
    ? el.className.trim().split(/\\s+/).slice(0, 3).join('.') : '';
  const label = el => {
    const c = clsOf(el);
    const t = (el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 40);
    return el.tagName.toLowerCase() + (c ? '.' + c : '') + (t ? ' :: ' + t : '');
  };
  const chain = el => {
    const out = [];
    let n = el;
    while (n && out.length < 4 && n.tagName !== 'BODY') { out.push(label(n).split(' :: ')[0]); n = n.parentElement; }
    return out.join(' < ');
  };
  const scrollableDesc = el => {
    const all = el.querySelectorAll('*');
    for (const d of all) {
      const s = getComputedStyle(d);
      if ((isScrollY(s.overflowY) && d.scrollHeight - d.clientHeight > 1) ||
          (isScrollY(s.overflowX) && d.scrollWidth - d.clientWidth > 1)) return true;
    }
    return false;
  };
  const scrollableAnc = (el, stop) => {
    let n = el.parentElement;
    while (n && n !== stop) {
      const s = getComputedStyle(n);
      if (isScrollY(s.overflowY) && n.scrollHeight - n.clientHeight > 1) return true;
      n = n.parentElement;
    }
    return false;
  };
  const frames = Array.from(document.querySelectorAll(FRAME_SEL));
  const report = { html: location.pathname, frames: [], defects: [] };
  frames.forEach((frame, fi) => {
    const baseW = Math.round(frame.getBoundingClientRect().width);
    const row = { i: fi, width: baseW, runs: [] };
    const widths = WIDTHS.length ? WIDTHS : [baseW];
    widths.forEach(ww => HEIGHTS.forEach(hh => {
      frame.style.height = hh + 'px';
      frame.style.width = ww + 'px';
      frame.style.overflow = 'hidden';
      frame.style.display = 'flex';
      void frame.offsetHeight;
      const fr = frame.getBoundingClientRect();
      // Metro (2.5.0): one view; the Metro root is what scrolls (the line, the bar and the open detail).
      const inner = frame.querySelector('.wa-metro') || frame.querySelector('.wa-root, .pa-root') || frame.firstElementChild;
      const seen = new Set();
      const run = { w: ww, h: hh, contentH: inner ? inner.scrollHeight : null,
                    paneH: inner ? inner.clientHeight : null,
                    frameScrollY: inner ? inner.scrollHeight - inner.clientHeight : 0,
                    rootScrollable: inner ? isScrollY(getComputedStyle(inner).overflowY) : false,
                    defects: [], n: 0 };
      const all = frame.querySelectorAll('*');
      for (const el of all) {
        const st = getComputedStyle(el);
        if (st.display === 'none' || st.visibility === 'hidden') continue;
        // An opacity:0 control (the Health tab's 1 px native date input, opened through showPicker())
        // shows nothing, so there is nothing on it to reach.
        if (st.opacity === '0') continue;
        const r = el.getBoundingClientRect();
        if (r.width < 1 || r.height < 1) continue;
        const overY = el.scrollHeight - el.clientHeight > 1;
        const overX = el.scrollWidth - el.clientWidth > 1;
        if (!overY && !overX) continue;
        const clipY = st.overflowY === 'hidden' || st.overflowY === 'clip';
        let reason = null;
        if (overY && clipY && !isScrollY(st.overflowY)) {
          if (el === inner) { reason = null; }
          else if (!scrollableDesc(el)) reason = 'clipped';
        } else if (overY && st.overflowY === 'visible') {
          if (!scrollableAnc(el, frame) && !isScrollY(st.overflowY)) reason = 'spill';
        }
        if (!reason && overX && st.textOverflow !== 'ellipsis' && st.webkitLineClamp !== '1'
            && st.overflowX !== 'visible' && st.overflowX !== 'auto' && st.overflowX !== 'scroll') {
          reason = 'clipX';
        }
        if (!reason) continue;
        const key = reason + '|' + clsOf(el) + '|' + el.tagName;
        if (seen.has(key)) continue;
        seen.add(key);
        run.n++;
        run.defects.push({
          reason,
          el: label(el),
          chain: chain(el),
          overY: el.scrollHeight - el.clientHeight,
          overX: el.scrollWidth - el.clientWidth,
          box: Math.round(r.width) + 'x' + Math.round(r.height),
          belowFrame: Math.round(r.bottom - fr.bottom),
          belowInner: inner ? Math.round(r.bottom - inner.getBoundingClientRect().bottom) : null
        });
      }
      // Unreachable content: a leaf below the pane bottom with no scroll container between it and
      // the frame is a fact the user reports as "the panel does not scroll".
      const cut = [];
      for (const el of frame.querySelectorAll('*')) {
        const r = el.getBoundingClientRect();
        if (r.bottom <= fr.bottom + 1) continue;
        const st = getComputedStyle(el);
        if (st.position === 'absolute' || st.position === 'fixed' || st.display === 'none') continue;
        if (scrollableAnc(el, frame)) continue;
        if (el.querySelector('*')) continue;
        cut.push({ el: label(el), belowFrame: Math.round(r.bottom - fr.bottom) });
      }
      run.cutBelow = cut.length;
      run.cutSample = cut.slice(0, 4);
      const chainOf = node => {
        const out = [];
        let n = node;
        while (n && n.tagName !== 'BODY' && out.length < 5) {
          const s = getComputedStyle(n);
          out.push(n.tagName.toLowerCase() + (clsOf(n) ? '.' + clsOf(n) : '') +
            ' [ovY=' + s.overflowY + ' h=' + Math.round(n.getBoundingClientRect().height) +
            ' cl=' + n.clientHeight + ' sh=' + n.scrollHeight + ']');
          n = n.parentElement;
        }
        return out;
      };
      run.roots = chainOf(frame.firstElementChild);
      row.runs.push(run);
    }));
    frame.style.height = '';
    frame.style.width = '';
    report.frames.push(row);
  });
  return JSON.stringify(report);
})()`

app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1700, height: 1300, show: false, webPreferences: { offscreen: false } })
  const bail = setTimeout(() => { console.log('SCROLL CHECK TIMEOUT'); app.exit(2) }, 120000)
  try {
    await win.loadFile(htmlPath)
  } catch (e) {
    console.log('SCROLL CHECK LOAD FAILED: ' + htmlPath + ' :: ' + e.message)
    clearTimeout(bail)
    app.exit(3)
    return
  }
  clearTimeout(bail)
  if (INJECT) {
    await win.webContents.executeJavaScript(`(() => { const s = document.createElement('style');
      s.textContent = ${JSON.stringify(INJECTIONS[INJECT])}; document.head.appendChild(s) })()`)
    console.log(`scroll canary '${INJECT}' injected`)
  }
  for (let i = 0; i < 100; i += 1) {
    if (await win.webContents.executeJavaScript('document.documentElement.dataset.waReady || ""')) break
    await new Promise(r => setTimeout(r, 100))
  }
  await new Promise(r => setTimeout(r, 400))
  const json = await win.webContents.executeJavaScript(PROBE)
  fs.writeFileSync(outPath, json)
  const rep = JSON.parse(json)
  if (!rep.frames.length) {
    console.log(`SCROLL CHECK: no frame matched ${FRAME_SEL}`)
    app.exit(3)
    return
  }
  let bad = 0
  for (const f of rep.frames) {
    console.log(`# frame ${f.i} (${f.width}px)`)
    for (const run of f.runs) {
      console.log(`  w=${run.w} h=${run.h}  content=${run.contentH} inner=${run.paneH} `
        + `rootScrollable=${run.rootScrollable}  defects=${run.n} cutBelow=${run.cutBelow}`)
      for (const c of run.cutSample) console.log(`     [CUT BELOW PANE +${c.belowFrame}px] ${c.el}`)
      for (const d of run.defects.slice(0, 6)) {
        console.log(`     [${d.reason}] ${d.el}  over=${d.overY}/${d.overX} box=${d.box} belowFrame=${d.belowFrame}`)
        console.log(`        via ${d.chain}`)
      }
      if (run.defects.length > 6) console.log(`     ... +${run.defects.length - 6} more`)
      if (run.h === f.runs[0].h) for (const r of run.roots) console.log(`     root> ${r}`)
      if (run.n > 0 || run.cutBelow > 0) bad++
    }
  }
  console.log('JSON: ' + outPath)
  if (bad) {
    console.log(`SCROLL CHECK FAILED — ${bad} pane size(s) hide content that cannot be scrolled to`)
    app.exit(1)
    return
  }
  const tall = rep.frames[0].runs.filter(r => r.contentH > r.paneH)
  console.log(`SCROLL CHECK clean — ${rep.frames.length} frame(s), ${rep.frames[0].runs.length} pane `
    + `size(s), 0 defects, 0 unreachable; the root scrolls where the content is taller `
    + `(${tall.length} of ${rep.frames[0].runs.length} sizes)`)
  app.exit(0)
})
