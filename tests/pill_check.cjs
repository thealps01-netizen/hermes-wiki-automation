// Are the PILLS clipped — the Metro stations' state pills (`next 21:30`, `3 waiting`, `failed`), the kit
// badges and the values inside the kit's PanelMeta rows? (A row cell alone does not see a nested pill.)
// Usage: <electron> pill_check.cjs preview-metro-drafts.html     (station pills + the review desk chips)
//        <electron> pill_check.cjs preview-metro-history-log.html    (History: run-log and drawer badges)
//        <electron> pill_check.cjs preview-metro-settings.html   (Settings: job chips, PanelMeta values)
// Exit 1 when a pill or a value is clipped, or when the page carries no pill at all (a vacuous pass).
const path = require('node:path')
const { app, BrowserWindow } = require('electron')
const [pageUrl] = process.argv.slice(2)
app.disableHardwareAcceleration()
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1240, height: 900, show: false })
  await win.loadFile(path.resolve(pageUrl))
  for (let i = 0; i < 100; i += 1) {
    if (await win.webContents.executeJavaScript('document.documentElement.dataset.waReady || ""')) break
    await new Promise(r => setTimeout(r, 100))
  }
  await new Promise(r => setTimeout(r, 300))
  const out = await win.webContents.executeJavaScript(`(() => {
    const txt = el => (el?.textContent || '').replace(/\\\\s+/g, ' ').trim()
    const pills = [...document.querySelectorAll('.wa-metro [class*="pill"], .wa-badge, [data-slot="badge"]')]
      .filter(p => p.getBoundingClientRect().width > 0)
      .map(p => ({
        text: txt(p), w: Math.round(p.getBoundingClientRect().width),
        scroll: p.scrollWidth, client: p.clientWidth,
        clipped: p.scrollWidth > p.clientWidth + 1,
        flex: getComputedStyle(p).flex
      }))
    const values = [...document.querySelectorAll('.wa-kv .wa-clip')].map(v => ({
      text: txt(v), clipped: v.scrollWidth > v.clientWidth + 1
        && getComputedStyle(v).textOverflow === 'ellipsis'
    }))
    return { tab: document.querySelector('.wa-frame')?.dataset.previewState || '', pills,
             pillsClipped: pills.filter(p => p.clipped).length,
             values, kvClipped: values.filter(v => v.clipped).length }
  })()`)
  console.log(JSON.stringify(out, null, 1))
  const red = []
  if (!out.pills.length) red.push('no pill is on screen — the check would pass for the wrong reason')
  if (out.pillsClipped) red.push(`${out.pillsClipped} pill(s) clipped`)
  if (out.kvClipped) red.push(`${out.kvClipped} PanelMeta value(s) clipped`)
  console.log(red.length ? `PILL CHECK RED (${out.tab}): ${red.join(' · ')}`
    : `PILL CHECK clean (${out.tab}): ${out.pills.length} pill(s), ${out.values.length} value(s), none clipped`)
  app.exit(red.length ? 1 : 0)
})
