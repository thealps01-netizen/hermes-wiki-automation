# Wiki Automation panel — tests

## Metro (2.5.0): one view, the gates that lock it

The panel is `../desktop/plugin.js`, its backend `../dashboard/plugin_api.py`. Since 2.5.0 it is ONE
view, the "Wiki line" (`Docs/metro-contract.md` is binding; the mocks are
`Docs/directions/metro-2.5.0/m-01.png` … `m-16.png`): a header (`History`, `Settings`), the line
(stations Harvest → Your review → Wiki, one branch line per adapter the backend reports), ONE alert
bar and at most ONE detail under the map. Every 2.3.12 component is reused inside a detail reached
by a click: Settings (RootCard, InstallCard/EngineInstall, JobsCard with ScheduleEditor and the two-step
job actions, InstallationFilesCard), History (the run history: KPIs, chart, filters, rows, drawer,
archive-before-clear), the Your review station (the review desk, ONE draft at a time; Approve keeps its
two-step ConfirmDialog and warning, Reject its required reason), the Wiki station (findings in English
and `Ask Hermes to fix these`), the Harvest station (timetable, `Change time`, Pause/Resume) and each
branch line (cursor, folder found, the honesty note).

**Removed, and the gates keep it removed:** the four tabs (`TAB_IDS`, the kit `Tabs`/`TabsTrigger`,
`role="tab"`), the Nexus map with its inspector, wires and comets, the heartbeat strip and the
Recent-runs card, the Chronicle lower review queue (`ReviewQueue`), the Folio index list (one row per
draft), per-view titles (`Automation map`, `Source review`), `openRunLog`/`setTab` navigation, and the
per-tab previews (`preview.html`, `preview-health.html`, `--tab=…`).

### What locks the contract

| Gate | Command | What it proves |
|---|---|---|
| **Metro behaviour** | `cd tests && node render_metro.mjs [<plugin.js>]` | jsdom + the real React, fed by `metro-states.mjs` (the SAME fixtures the previews paint). **M1** one `.wa-metro` view: no tab strip, no Nexus/inspector/heartbeat/lower queue, no per-view title. **M2** one fixture per contract state (good, problems, wiki, harvest, branch, running, drafts, approve, harvest-failed, branch-missing, loading, read-failed, history, settings, engine, job-broken, paused, line-off, engine-update, settings-update, draft-unreadable, history-failed, branches-missing, line-missing, harvest-lines; `notText` strings must be absent from the open detail and `runs` maps a role to its `.wa-metro-run[data-outcome]`), each mapped to its `.wa-metro-bar[data-alert]` priority key, `data-tone`, the stations' and branches' `data-state` and the open `.wa-metro-detail[data-for]`. **M3** alert priority: two simultaneous conditions per pair (read-failed > engine > harvest-failed > job-broken > drafts > problems > paused > running > good, plus an engine update under read-failed and over harvest-failed); the higher one wins, and an engine update that loses still shows its `.wa-metro-notice[data-engine-banner="update"]`. **M4** `Good service on the whole line` never shows while ANY read failed, and the failed read keeps the backend's error. **M5** every station and branch has visible words and an aria-label (no empty or code-only label). **M6** stations, branches, `History` and `Settings` toggle `aria-pressed`; a second click folds the detail; only ONE detail is open; the detail opens under the map, never inside it. **M7** `Ask Hermes to fix these` calls `host.composer.insertText(null, text, { mode: 'block' })` once, never `submit`/`setDraft`; the text lists every finding with its raw line and cites no path the findings do not carry; a `false` answer shows `Open a chat first, then press again.`. **M8** the review desk (one draft, `1 of N`, Approve two-step with its source-write/model-credit warning, Reject needs a reason, `Show the change and the evidence` closed by default; `Next draft` → `2 of 3`, `Previous draft` → `1 of 3`, Previous disabled on the first draft, no POST from either; an unreadable draft keeps Approve disabled, Reject enabled and no `.wa-desk-kind`). **M9** History (head, window picker, run rows) and Settings (RootCard, InstallCard, JobsCard). |
| **Reused components behind clicks** | `cd tests && node render_check.mjs [<plugin.js>]` | Every 2.3.12 behavioural assertion, reached by clicking first: `mount(…)` opens Settings (`openConfig`), `tab: 'Folio'` opens the Your review station, `Chronicle`/`Health` open History. The review desk tests use `Later` (by identity) instead of the old index rows; the line tests read branch `data-state` (ok/missing/off/run), the Harvest station's live `run` state (an active session-harvest run only), the read-failed alert keeping the backend reason, and the dash-offset march as the only animation (reduced motion turns it off). |
| **History detail** | `cd tests && node render_health.mjs [<plugin.js>]` | The run history inside the History detail (header button, `aria-pressed`, one detail): KPIs, freshness, the one journal, drawer, filters, archive-before-clear; the review desk's SEC-3 scope guarantees reached through the Your review station; candidate read states never block the run history or write. |
| **Static audit: removed composition** | `python audit_static.py` (`check_removed_composition`) | Fails when `TAB_IDS`, the kit `Tabs`/`TabsTrigger`, a `role: 'tab'`, `Nexus`/`nx-*`, `HeartbeatStrip`/`wa-hb-*`, a per-tab view (`AutomationTab`/`ChronicleTab`/`FolioTab`/`HealthTab`), `setTab(`/`openRunLog`, the lower queue (`ReviewQueue`/`nx-queue`) or the second run list come back, or the bundle names `Nexus`/`Chronicle`/`Folio`. |
| **Static audit: Metro contract** | `python audit_static.py` (`check_metro_contract`) | The DOM vocabulary the behaviour gates select on (`.wa-metro{container-type:inline-size}`, `data-wa-nav`/`-station`/`-line`, `data-alert`/`-tone`/`-for`/`-dir`/`-state`, `aria-pressed`, `wa-metro-map`/`-wires`/`-bar`/`-detail`/`-skeleton`), all nine priority keys, the Metro copy, segments computed from layout (`ResizeObserver` + `getBoundingClientRect`), `composer.insertText(null, …, { mode: 'block' })` and never `composer.submit`/`setDraft`. |
| **Canary** | `python canary_audit.py` | Each Metro rule has its own canaries (`removed: …` and `metro: …` in `CANARIES`): an injected `TAB_IDS`, `TabsTrigger`, `role: 'tab'`, `nx-node`, `HeartbeatStrip`, `ChronicleTab`, `setTab(`, `ReviewQueue`, `wa-run` row, a bundle string naming Nexus, and every contract anchor renamed (`.wa-metro{`, `data-wa-station`, `data-wa-line`, `data-wa-nav`, `data-alert`, `data-for`, `wa-metro-skeleton`, `wa-metro-wires`, two priority keys, two copy strings, `ResizeObserver`, `insertText`) plus an injected `composer.submit`: the audit must fail with that rule's message, then the file is restored byte for byte. Anchors are replaced at every occurrence (`_count`), so a rule cannot pass on a copy it did not see. |
| **Metro previews** | `cd tests && node preview.mjs [--state=<name>] [--glass]` | One LIVE page per Metro state: `preview-metro-<state>.html` (React UMD, `kit-stub.mjs`, the panel and the state's fixture world travel inside the page as `data:` modules behind an import map; the page drives the state's clicks and then sets `<html data-wa-ready="1">`). Live, because the SVG segments are computed from `getBoundingClientRect` after layout; a jsdom snapshot would carry zero-sized boxes. Plus `settings-setup` (refused verification + SAME-ID candidate armed + job delete armed: the destructive-contrast fixture) and `schedule` (Watch Dog editor on Weekly). Generated pages are git-ignored. |
| **Metro geometry (Electron)** | `<electron> shot.cjs preview-metro-<state>.html <out.png> <width> [--frame=<px>]` | Waits for `data-wa-ready`, then measures: the line is `data-dir="h"` in a wide pane and `"v"` at ≤ 640 px (352 and 390 px), stations in order (left → right, or top → bottom), **the SVG segments exist after layout** (≥ 2, painted, with length) and each endpoint sits on the EDGE of a stop or label (never at a centre), nothing leaves `.wa-metro` horizontally, the detail sits under the map, no tab strip; plus the unchanged WCAG contrast, type floor, chip and job-row gates. Negative controls (must exit 1): `--inject=metro-wires-detached`, `--inject=metro-wires-gone`, `--frame=390 --inject=metro-media-query` (the line keyed to the window), `--inject=wrong-token`, `job-row-stack`, `job-acts-too-wide`, `tiny-type`, `sched-no-wrap`. |
| **History geometry (Electron)** | `<electron> shot_health.cjs preview-metro-history-log.html <out.png> <pane width>` | The former Health gate, now on the History detail: it must be the open, pressed detail and carry the run journal (`WD_LAYOUT_CANARY=journal` removes the journal and must fail). |
| **Scroll / pills (Electron)** | `<electron> scroll_check.cjs preview-metro-wiki.html` · `<electron> pill_check.cjs preview-metro-drafts.html` | The Metro root scrolls; every leaf of an open detail is reachable in short panes (`PROBE_WIDTHS=352,390,660`); `--inject=no-root-scroll` and `--inject=detail-grows` must exit 1. Station pills, kit badges and `PanelMeta` values are not clipped. |

Narrow mocks: m-15 = `preview-metro-problems.html --frame=390`, m-16 = `preview-metro-wiki.html
--frame=390`; repeat at `--frame=352`.

### Gate history

The sections below describe the 2.0–2.4 four-tab composition and its measurements; they are kept as
history. Where they name `preview.html`, `preview-health.html`, `--tab=…`, Nexus, Chronicle, Folio,
Health or the heartbeat, read the Metro equivalent above. The removed checks are listed in the
2.5.0 change of `render_check.mjs` (Nexus block → Metro line block), `render_health.mjs` (lower queue →
review desk SEC-3), `audit_static.py` (`check_tabs`/`check_single_run_view` → `check_removed_composition`
+ `check_metro_contract`) and `canary_audit.py`.

Mutation canaries run the same audit on byte-exact temporary copies, checking the originals stay
unchanged. A killed or timed-out canary cannot leave its mutation in working sources. Allow the full
run; partial output is not success. UI gates do not modify engine settings or scheduled jobs.

The panel is built from the HOST UI KIT (`Button` · `Badge` · `Input` · `SearchField` ·
`SegmentedControl` · `PanelSectionLabel` · `PanelMeta` · `PanelBlock` · `EmptyState` · `ErrorState` ·
`Loader` · `Tip`), so the harnesses stub the kit in `kit-stub.mjs` instead of the panel; see "Host UI
kit" below.

## The gates

| Gate | Command | What it proves |
|---|---|---|
| **Backend selftest** | `python ../dashboard/plugin_api.py --selftest` | The root validation gate (an OPEN error when `wikiconfig.py` is missing — no silent "ok"), automation folder resolution (`LLMWIKI_AUDIT_DIR` wins), timezone normalisation (local `+03:00` ↔ UTC), status and delivery as SEPARATE labelled axes, job ids read from the settings, name/duration/error preview from a temporary `executions.db`, and the **candidate scan against the real resolver** (three levels deep, a copy/mirror of the same id flagged, counters correct). Runs in temporary folders. |
| **Static audit** | `python audit_static.py` | Exactly ONE `en` bundle and it reaches `ctx.i18n.register`; every key the panel asks for exists in it (a missing key would print itself); no language switch left (no `tr`/`en` literal, no `lang` state, no `/settings` route); no comment or docstring in the panel or the backend; the loader's own import regex accepts the source; every `jsx` third argument is a key, not children; **no native `title=` on a control** (a tooltip is the kit's `Tip`; the file picker's dialog `title` option is the one exemption); only theme colors; the two-step copy/mirror write is intact; `_tx(...)` gets exactly the placeholders its message uses; **every external check `reason` is read through `txReason(...)`** (a bare `.reason` would put the checker's Turkish on an English screen) and every `_TX_MAP` entry exists in the bundle with the raw text still reaching a `Tip` label and a `PanelBlock` detail block; **the backend marks every checker payload with its provenance** (`_reason_fields`); the version is ONE number across `plugin.yaml` and `dashboard/manifest.json`; no undefined name. |
| **Canary (audit rules)** | `python canary_audit.py` | That each audit rule above really fires: one violation is INJECTED into the real source per rule (128 as of 2.1.0, including no job catalogue in the plugin and the two-step candidate approve), the audit must exit 1 with that rule's own message, then the file is restored byte-for-byte (sha256 unchanged) and the audit must exit 0 again. Includes the external-text rule from five sides (a bare `.reason`, a `_TX_MAP` key missing from the bundle, a raw block that stopped showing the checker's wording, a raw text that stopped being a `Tip` label, a `question` that stopped unpacking `msg.raw`) plus the backend provenance rule, plus the native-title rule (a `title:` injected into a `jsx(Button, …)` props object). |
| **Render/behaviour** | `cd tests && node render_check.mjs [<plugin.js>]` | jsdom + the real React: registration (page path + sidebar label resolved, never a raw key), SIX cards (root · install · heartbeat · scheduled jobs with the FOUR engine roles from `jobs.json`, the agent job offering no Create/Delete · candidates · recent runs), the **candidates card** (one row per pending candidate, the detail opened in the card with its diff in a code body, Approve two-step through an unconfirmed dry run, Reject only with a reason, the engine's own output kept on a refusal, one EmptyState, a failed list or detail read keeping its error),**root selection through `ctx.os.pickOpenPath`** (a cancelled pick produces no request and no silent success), verification, the **save GATE** (an unverified root never reads as saved and does not refresh), the **copy/mirror confirmation** (the same-id candidate asks, and only the confirmed click sends `force: true`), candidate scan (counters written, an empty result stays informational, not red, the `SearchField` narrows the list and a miss is ONE neutral empty state), the write surface (`/automation/*` only — the removed `/settings` language route is never called), the runs table (two separate pills, a deleted job kept, a same-day timestamp vs a dated one, newest-first across all jobs, the `SegmentedControl` range re-reading with the new limit, an empty card showing the kit's `EmptyState`), refresh, **the scheduled-jobs card** (the three roles with their schedule · id · state, the orphan
banner naming the job whose target is gone, and the actions driven through `/jobs/act`: one click on
Delete only ARMS the confirmation and sends nothing, Cancel closes it, the confirmed click sends
`confirm: true` for that role, Create and Pause round-trip through the view the backend returns, and a
REFUSED action prints the mapped sentence with the checker's `as written` wording beside it while the
row stays where it was), **no language picker in the DOM with English text under any app locale**, **not one native `title=` in the rendered DOM**, and **every external check reason** (12 known patterns + one unknown, on all five routes that can carry one) shown in English with its raw Turkish wording kept in the `PanelBlock` detail block and the `Tip` label. It also locks the **reference pass**: ONE mono shape across every `.wa-mono` element (path · candidate path · code body · stamps), the raw wording in a code body under its `as written` caption, both code surfaces **copyable through the kit** (`data-copy` carries the payload and each trigger is aria-labelled), a refusal rendered as a **help card** (heading · one sentence · the action that helps, absent for a plain result or a backend reason), **one secondary shape (`outline`) for every secondary action** with the one filled Save ending the row, and **one circular `icon-sm` aria-labelled icon-button shape**. It also locks the surfaces this pass added: a **failed read** that keeps the error the backend returned in a code body under its `as written` caption (with no spinner left turning and no untouched card taken down), a **job result printed as a help card** with the heading the tone calls for (`Result` · `Why this was refused`) beside the raw wording, the candidate chip's own unit (`12 pages`), and the **job row shape** — the state badge is a sibling of the job name inside `.wa-job-line` and never a direct child of the text column, which would draw it on a line of its own, and the panel's COPY: no count written as a machine plural (`folder(s)`), the install row saying `3 of 4`, and the job row labelling its id. |
| **Static preview** | `cd tests && node preview.mjs` | Writes `preview.html` (the app's theme file, its dark-mode block AND its compiled stylesheet `apps/desktop/dist/assets/index-*.css` are embedded; colors are never copied). The panel is driven into a candidate scan, a REFUSED verification and then a SAME-ID candidate CLICK, so the armed two-step confirm row — the panel's one filled destructive surface — is in the measured document. A refusal closes that confirmation (one surface at a time), so the click comes last; the refusal help card and its code body are covered by `render_check.mjs`. The stub also answers `/jobs` (it used to throw, so EVERY shot rendered the whole job card as a failed read) and the two-step delete is ARMED, so the roles, their state pills, the action row and the confirmation row are inside the measured document too. |
| **Visual measurement** | `<electron> shot.cjs preview.html panel-1240.png 1240` | The real Electron: card widths, horizontal overflow, the kit's `PanelMeta` rows with EVERY label and value readable (dt/dd), clipping of any truncating element (`.wa-clip`: the root path, the install values, the run-job names) and of the run-row cells, the DURATION column dropping at 820 px instead of clipping, no native `<select>`, no language picker, **no native `title=` in the DOM**, the `SearchField` and the `SegmentedControl` present, and the button labels. The reference pass is measured too: the help card and its heading/action, the code bodies and their caption, **how many distinct mono shapes** the code/data elements resolve to (must be 1), the copy affordances with the payload each was handed, every `.wa-icon-btn` with its aria-label/size/radius, and which buttons are `ghost`/filled/`destructive`. It also carries **THE WCAG CONTRAST GATE** (see below) and exits 1 on a violation. With `--frame=<px>` the same panel is measured inside a PANE of that width in a full-width window, and the gate FAILS when the DURATION column survives a narrow pane; `--frame=560 --inject=media-query` keys the rule back to the window and must go RED (the negative control for the container query). It also walks every element inside every card and FAILS when one crosses the card's edge (the card's own `overflow` would cut it silently), and it measures each `.wa-job`: the state badge must overlap the name's line box by at least half its own height, it sweeps 300 → 1240 px (the host allows a 352 px pane) and fails on any element outside its card at
any of them, on any box whose text is wider than the box itself with no ellipsis (`.wa-clip` exempt), and
it reports whether the actions sit beside the name or under it — `--inject=job-row-stack` (the badge back on its own line) and `--inject=job-acts-too-wide` (an action group wider than its card) must each exit 1. `--scroll=bottom` captures the bottom of the panel, where the jobs card lives in a narrow pane. It also GATES the type: every text node must be at or above the kit's default badge step (10.4 px) and every card title / table label at or above 11.5 px, and `--inject=tiny-type` (a title back at 9 px) must exit 1. Output: JSON + PNG + the contrast dump. |
| **Contrast (WCAG 2.x)** | `<electron> shot.cjs preview.html panel-1240.png 1240` · negative control: same command plus `--inject=wrong-token` | **Every** text node in the panel, ink alpha-composited over the colours really painted under it (the canvas resolves `oklab()`/`oklch()`, so the kit's palette colours and its translucent tints are read instead of skipped): 70 nodes, 0 unread. GATED at AA: the destructive label (`wa-danger`, and its ink must BE `--ui-red`), the filled destructive write (`[data-variant="destructive"]`, fill `--dt-destructive` + ink `--dt-destructive-foreground`), the failure ink (`.wa-bad` / `[data-tone="bad"]`) and every other `reading` node. FLOORED at 3:1 and printed: the kit's filled primary action (the APP's `--dt-primary` pair, 3.4:1 — not this panel's tokens to repaint). Printed, never gated: the host's faint ladder (secondary .74 / tertiary .54 / quaternary .36, the kit's `text-muted-foreground/50` and `/55`, 2.21–3.16:1). Dump: `<out>.contrast.json`. `--inject=wrong-token` rewrites the two danger rules to the WRONG token intents in memory and must exit 1 — 3.35:1 (white on `--ui-red`), 3.48:1 (chips), 3.72:1 (failure ink): the negative control. |
| **Pill measurement** | `<electron> pill_check.cjs preview.html` | Whether the pills NESTED inside a run row (status · delivery · "deleted job") are clipped, and whether a truncating value inside a `PanelMeta` row is. `shot.cjs` only measures a row's direct children, so this runs separately. |
| **Scroll (pane height)** | `<electron> scroll_check.cjs preview.html` | THE promise a user reports as "the panel does not scroll": every card reachable in a SHORT pane. jsdom has no layout engine (`render_check.mjs` cannot see this) and `shot.cjs` never forced a short pane, so the defect lived in the one place no gate measured. `scroll_check.cjs` forces pane HEIGHTS (760/620/560/430/330/220 px) and, with `PROBE_WIDTHS=352,660`, pane WIDTHS as well, and exits 1 on an element that cuts its own content with no scrollable descendant (`clipped`), content overflowing with no scroll container up to the pane (`spill`), text wider than its box with no ellipsis (`clipX`), or any leaf below the pane bottom that no scroll container reaches (`cutBelow`). Post-fix: content 1220 px (1475 px at a 352 px pane), 0 defects, 0 unreachable at every size. Negative control: the pre-fix source exits 1 with 3 defects and cutBelow 6/14/31 at 760/620/430 px. |

| **Render/behaviour (History detail; 2.3.x "Health + Chronicle")** | `cd tests && node render_health.mjs [<plugin.js>]` | Health's three diagnostic sections, KPIs, freshness, data honesty and shared filters/error/refresh; Chronicle's journal, selected-run inspector, separate execution/notification state, exact recorded duration snapshot, original output, findings and eight metadata pairs behind Technical details, full-body loading and copy failures, and two-step archive-before-clear with POSTed keys equal to the shown records. Health must not mount a journal, finding list, drawer or archive action. |
| **Static preview (History)** | `cd tests && node preview.mjs --state=history-log` | Writes `preview-metro-history-log.html` with the History detail open (2.3.x: `--tab=health` / `--tab=chronicle`, removed). |
| **Visual measurement (History)** | `<electron> shot_health.cjs preview-metro-history-log.html health-560.png 560` and `… health-1240.png 1240` | Separated sections, divided metrics; no overflow, clipping or spill, no native `title`/`<select>` or language picker, the run journal present in the same detail, no tab strip, and unchanged type/contrast gates. `WD_LAYOUT_CANARY=clip\|spill\|cover\|journal\|container` and `WD_CONTRAST_CANARY=text\|fill` must fail their named measurements. |

2.0.0 note on the rows above: the Automation tab no longer has a five-column runs table (the run log
lives once, in Health), so the runs-table parts of the render/shot/pill descriptions and the 1.x
measurements below are history. `render_check.mjs` now asserts the runs card carries the heartbeat and
**Open the run log**, and the static audit's `check_single_run_view` (with its canary) refuses a second
run table.

History variants of the Electron gates: `<electron> pill_check.cjs preview-metro-history-log.html` and
`<electron> scroll_check.cjs preview-metro-history-log.html`.

### 2.1.0: the schedule editor and the run state

| Gate | Command | What it proves |
|---|---|---|
| **Render/behaviour (schedule)** | `cd tests && node render_check.mjs` | The job row leads with the schedule as a SENTENCE (`Every day at 09:00`) with the raw cron after it in `.wa-mono` behind a `Tip`; the next run and the last run as a local time plus a distance (`tomorrow 09:00 · in 22 h`, `yesterday 11:00 · 24 h ago`), with `OK` / `Failed` on the last run, and a `Late` / `Missed` flag whose `Tip` gives due · start · lateness. A paused job that never ran says `none while paused` / `not run yet`, and a job with no store record prints no run times. **Editor:** every mode → cron (`*/15`, `*/30`, `0 *`, `5 *`, `0 9 * * *`, `0 9 * * 1`, `15 8 * * 1,4`, `15 8 * * 1-5`, `0 3 1 * *`, `0 3 15 * *`, weekends `0 3 * * 0,6`) with its sentence; cron → mode round trip for the four live expressions and each mode's shape, never rewritten on open (`0 9 * * 7`, `00 09 * * *` stay as written) and Save disabled until something changes; 7 unrepresentable expressions (`0 9,17 * * *`, `*/7`, a month field, dom+dow, `MON`, `every 2h`) open in Custom unchanged with the "kept as written" note and a `Custom schedule` row; the preview line re-asks `/jobs/preview` on every change and lists three runs; a refused expression shows the refusal in the preview AND, on Save, the existing "Why this was refused" note with the editor left open and the row unmoved; a failed preview read keeps its error; the store's time zone is printed once; Weekly with no day cannot be saved; Save is the kit's filled primary; no native `title=`; opening the editor 16 times sends no `/jobs/act`. Also: no `Task Scheduler` anywhere on the tab and the scripts KPI naming the missing script. |
| **Backend selftest (schedule)** | `PYTHONPATH=<core> <core venv python> ../dashboard/plugin_api.py --selftest` | Against a temporary cron store: `/jobs` carries `next_run_at` equal to what the reschedule returned; a job that never ran has no last run, status or flag; a stamped run gives `last_run_at`, `last_status` and `dispatch.flag = missed` for `catch_up` (with its lateness), `late` for `late`, none for `on_time`, none for four malformed stamps; the zone is `{name, offset ±HH:MM}`. `POST /jobs/preview`: `30 21 * * *` → three runs, each at 21:30 in the store zone, 24 h apart, the first in the future; `*/15` → 900 s apart; `not a cron expression` → `ok: false` with the store's refusal and no runs; blank and missing → refused; the store's `jobs.json` bytes are identical before and after. `/automation` no longer reports `run_watchdog.cmd`, `scheduler_task` or `scheduler_registered`. |
| **Static audit + canary (schedule)** | `python audit_static.py` · `python canary_audit.py` | `check_preview_read_only`: `_jobs_preview` / `jobs_preview_route` may not call `update_job`/`create_job`/`remove_job`/`pause_job`/`resume_job`/`save_jobs`/`trigger_job`/`_write_job_map`/`_forget_job`/`_notify_scheduler`, and must call the core's `cron.compute_next_run`; `/jobs/preview` is the one POST listed as read-only. Canaries: an injected `update_job`, an injected `_notify_scheduler`, the core call removed, the route renamed, the new `OK` / `Missed` chips in lower case, and `.wa-sched-save` inked with `--ui-accent` again (`check_schedule_save_ink`) — each fires. `contract_core.py` checks `compute_next_run` against the core. |
| **Schedule preview** | `cd tests && node preview.mjs --state=schedule` | Writes `preview-schedule.html` with the Watch Dog editor OPEN in **Weekly** (Mon + Thu, 08:15) and its preview answered (`15 8 * * 1,4`, three runs); exits 1 if that state is not reached. |
| **Visual measurement (schedule)** | `<electron> shot.cjs preview-schedule.html schedule-<w>.png <w> --scroll=jobs` for 560 · 820 · 1240, plus `--frame=352` | The same WCAG / type / out-of-card / chip gates over the editor. `--scroll=jobs` centres the editor for the screenshot. Negative control: `--inject=sched-no-wrap` (the frequency control forced to one six-column row) must exit 1 with the segments past the card edge (at 560 and at a 352 px pane). `--inject=job-acts-too-wide` was re-pointed at the grid rule (the old flex selector matched nothing, so it only failed by throwing). |

The red gate this release closes: `.wa-sched-save` ("Save schedule", `--ui-accent` ink on the drawer)
measured **4.22:1** in the 2.0.0 schedule preview at all three widths. It is now a kit `Button`
inked `--ui-text-primary` on a `--ui-accent` tint (theme tokens only). The gate classes it as a
`reading` node, so it is held to AA 4.5:1 rather than the 3:1 floor of the app's filled primary, and
it passes.

A second pre-existing blind spot found while re-running the negative controls on 2.0.0: `--frame=560
--inject=media-query` exits **0** (it prints "did NOT go red"). The heartbeat rule it rekeys lives at
470 px, so a 558 px panel never crosses it. The control fires at a pane under 470 px: `--frame=440
--inject=media-query` exits 1 ("the heartbeat row kept 3 columns in a 438px panel inside a 1224px
window"). Use that form.

### Backend selftest needs the core on the path

`plugin_api.py --selftest` imports the core's `cron` package. Run it with the core's interpreter and the
core checkout on `PYTHONPATH`, or it fails with `the cron store could not be imported`:

```bash
PYTHONPATH="$HERMES_AGENT_DIR" "$HERMES_AGENT_DIR/venv/Scripts/python.exe" ../dashboard/plugin_api.py --selftest
```

### The static audit and the release gate against an isolated HERMES_HOME

`audit_static.py`, `canary_audit.py` and `release_gate.py` compare the installed desktop copy
(`$HERMES_HOME/desktop-plugins/wiki-automation/plugin.js`) with `desktop/plugin.js`. On a branch that is
not installed yet, point `HERMES_HOME` at an empty folder: the sync check is then a printed note, not a
failure, and every other rule still runs.

```bash
HERMES_HOME=<empty folder> python audit_static.py
HERMES_HOME=<empty folder> python canary_audit.py
HERMES_HOME=<empty folder> python release_gate.py
```

Electron: the app's OWN Electron is used —
`<hermes-agent>/apps/desktop/node_modules/electron/dist/electron.exe`. The scripts never hardcode a
path; the caller passes it, so moving the package to another PC changes only the command line.

## Host UI kit (and the stub)

`desktop/plugin.js` imports its controls from `@hermes/plugin-sdk`, which exists only inside the app.
Both harnesses rewrite that one import to a stub, and `kit-stub.mjs` is what those stubs re-export
(`export * from './kit-stub.mjs'`):

* **DOM contract** — `Button`/`RowButton` render a real `<button>`, `Input`/`SearchField` a real
  `<input>` (so the harness types into it and dispatches React's own `input` event), `PanelMeta` a
  `<dl>` of `dt`/`dd`, `PanelBlock` a `<pre>`, and `Tip` NOTHING but the child it wraps, with the
  label copied onto the child as `data-tip`. That last one is deliberate: the app puts a tip's label
  in a portalled bubble and never a native `title=`, so `data-tip` on the trigger is exactly what the
  render check can assert and what `shot.cjs` cross-checks (`nativeTitles: 0`).
* **`Button` also mirrors the kit's own `data-variant` / `data-size`** (the real component writes
  both), which is how the harness proves a secondary action is really quiet (`ghost`) and that every
  icon button uses the one shared size. `CopyButton` resolves its payload internally, so the stub
  exposes it as `data-copy` on the trigger — the same deliberate hook as `data-tip` — and, for the
  icon-only form, renders a PLACEHOLDER glyph in the `size-3.5` box the app's own Copy icon fills:
  the stub has no icon set, and without it the affordance would render as an empty circle in the
  preview. The app draws its real icon; nothing else about the button differs.
* **Visual contract** — the class strings are copied verbatim from the kit sources
  (`apps/desktop/src/components/ui/*`, `app/overlays/panel.tsx`) and `preview.mjs` embeds the app's
  compiled stylesheet, because a RUNTIME plugin is never scanned by Tailwind: utility classes written
  in plugin code would simply not exist in the app. Without both halves the visual gate would measure
  a UI the app never shows.
* The stub concatenates classes instead of running `cn()`/tailwind-merge, so a conflicting utility
  (one radius on an icon button) can resolve by stylesheet order. No gate measures that.

## Last measurement (2026-09-18, version 1.3.1)

The numbers below are the ones the current panel produces; the "before" column of the layout table is
the 1.2.0 panel (so the reference pass can be checked against what it replaced), and the "before"
column of the contrast table is the 1.3.0 panel. All go through the same three commands.

| Metric (window 1240 → inner 1224) | before | after |
|---|---|---|
| card width (all four cards) | 1154 px | **1142 px** |
| horizontal overflow | 0 | 0 |
| runs grid (`gridTemplateColumns`) | `72px 716px 108px 120px 72px` | **`72px 696px 108px 120px 72px`** |
| run rows / cells (Duration visible) | 4 / 5 | 4 / 5 |
| truncating elements (`.wa-clip`) / clipped | 11 / 0 | **10 / 0** |
| `PanelMeta` blocks / rows / clipped labels / clipped values | 2 / 6 / 0 / 0 | **2 / 5 / 0 / 0** |
| `SearchField` · `SegmentedControl` (`3 10 25`) | 1 · 3 | 1 · 3 |
| native `<select>` · language pickers · `nativeTitles` | 0 · 0 · 0 | 0 · 0 · 0 |
| **distinct mono shapes** (`monoShapes`) | — (one `font-size`, no leading) | **1** — `ui-monospace, SFMono-Regular, Menlo, Consolas, monospace` · 11 px · 16.5 px, 11 elements |
| **help card** | — | 1 · heading `Why this was refused` · action `Choose folder…` |
| **code bodies / caption** | — | 1 · `as written` |
| **copy affordances / payloads** | — | 2 · `["/srv/other-wiki", "wiki/ klasörü yok"]` |
| **icon buttons** (label · size · radius) | — | 3 × (`Refresh` · `Copy` · `Copy`, 32×32, `9999px`) |
| **buttons** ghost / filled / destructive | all secondary | (2026-09-22: now `outline`, see the notes' Visual pass to 9) ghost `Choose folder… · Verify · Scan for candidates · Choose folder… · Cancel` · filled `Save` · **destructive `Yes, take it`** (the armed two-step write) |
| **confirm rows** (the armed copy/mirror step) | — | 1 |

804 px (window 820): card width **722 px** (was 734) · horizontal overflow 0 · **4 cells — DURATION
DROPS, not clipped** · grid **`64px 382px 104px 110px`** (was `64px 400px 104px 110px`) · clipped
cells 0 · clipped labels 0 · `nativeTitles` 0 · language pickers 0 · `monoShapes` 1 · the same three
icon buttons at 32×32/`9999px` · the contrast gate GREEN with 34 AA-gated nodes.

Pills: 9 pills, 0 clipped (status · delivery · "deleted job"), flex `0 0 auto`; 5 `PanelMeta` values,
0 clipped (`kvClipped` 0) — unchanged by the reference pass, which is the point: the pills and the
values are the panel's own measured surface and it moved under them not at all.

### Contrast (the two destructive classes, 1.3.1)

| node (dark theme, `panel-1240.png`) | before (1.3.0) | after (1.3.1) | gate |
|---|---|---|---|
| `Failed` / `deleted job` chip ink | `--dt-destructive` `#cf2d56` → **3.48:1** (3.72:1 with the oklab tint un-composited) | **`--ui-red` `#e75e78` → 5.25:1** | `danger-ink`, AA 4.5, ink must BE `--ui-red` |
| filled destructive write ("Yes, take it") | not destructive — the kit's filled primary `#fcfcfc` on `#4a84fe` → 3.40:1 | **`--dt-destructive` `#cf2d56` + `--dt-destructive-foreground` `#fff` → 5.04:1** | `danger-fill`, AA 4.5 + token identity |
| `.wa-bad` / `[data-tone="bad"]` (`3/4`, the refusal line) | `--ui-red` 5.6:1 | 5.6:1 (untouched) | `bad-ink`, AA 4.5 |
| lowest AA-gated node in the panel | — | **5.04:1** (need 4.5) | — |
| kit tinted badges (`Verified` · `SAME ID`) | (`Failed` = a kit chip at 3.48:1) | 10.74:1 · 11.26:1 | `chip`, AA 4.5 |
| kit primary fill pair (`Save`) | 3.40:1 | 3.40:1 (the APP's `--dt-primary` tokens, reported) | `primary-fill`, 3:1 floor |
| faint ladder (tertiary/quaternary + `text-muted-foreground/50`, `/55`) | 2.21–3.16:1 | 2.21–3.16:1 | printed, never gated |

Negative controls (both must be RED, and are): `--inject=wrong-token` → exit 1 with 8 violations
(3.35:1 filled destructive, 3.48:1 chips, 3.72:1 failure ink, plus the two token-identity lines); the
1.3.0 panel source through the same gate → exit 1 with 4 violations (the two 3.48:1 chips and the two
"no destructive label / filled destructive write on screen" lines).

## Last measurement (2026-09-20, version 1.5.4)

`cd tests && node preview.mjs` then `<electron> shot.cjs preview.html <out.png> <width>`. The pane
column is the same command with `--frame=660` — a 612 px card inside a 1224 px window — and
`--scroll=bottom` captures the bottom of the panel at either width. The pane the host actually allows
is 352 px (`minWidth: '22rem'` in the layout tree), so the sweep below runs 300 → 1240 px and the gate
fails at ANY of them on an element outside its card or on a box whose text is wider than the box with
no ellipsis. The 1.3.1 table above is history: it was taken before the job card was inside the
measured document.

| Metric | window 1240 (inner 1224) | 660 px pane in that window |
|---|---|---|
| cards / card width / `bodyScrollX` | 4 / 1142 px / 0 | 4 / 562 px / 0 |
| runs grid | `72px 696px 108px 120px 72px` · 5 of 5 cells · Duration **visible** | `64px 222px 104px 110px` · **4 of 5 cells · Duration dropped** |
| truncating elements (`.wa-clip`) / clipped | 16 / 0 | 16 / 0 |
| run cells clipped · `.wa-clip` in a `PanelMeta` row clipped | 0 · 0 | 0 · 0 |
| `PanelMeta` blocks / rows / clipped labels / clipped values | 2 / 5 / 0 / 0 | 2 / 5 / 0 / 0 |
| **text nodes · smallest · under the 10.4 px floor · titles under 11.5 px** | **89 · 10.4 px · 0 · 0** | **82 · 10.4 px · 0 · 0** |
| `SearchField` · `SegmentedControl` · native `<select>` · language pickers · `nativeTitles` | 1 · 3 · 0 · 0 · 0 | 1 · 3 · 0 · 0 · 0 |
| distinct mono shapes / mono elements | 1 / 14 | 1 / 14 |
| help cards · code bodies · copy affordances · confirm rows | 1 · 1 · 2 · 2 | 1 · 1 · 2 · 2 |
| icon buttons | 3 × (`Refresh` · `Copy` · `Copy`, 32×32, `9999px`) | 3 ×, same shape |
| elements crossing their card's edge | **0** | **0** |
| job rows (name line · state badge · the actions' line) | badge/name overlap **12 px** on the name line, actions BESIDE the name — both live rows; the not-live row carries no state badge | overlap **12 px** on the name line, actions **ON THEIR OWN LINE** 45 px under the name — all 3 rows |
| jobs surface on screen | 3 rows (`Pause job` · `Delete job` · `Create job`), the orphan banner, the armed delete confirmation | same, each action row under its job |
| chips (kit badges) · of label length · starting lower case | 16 · 16 · **0** | 16 · 16 · **0** |
| contrast | 89 text nodes, 0 unread, **65 AA-gated**, reading 52 / quiet 23, lowest **5.04:1** (`Yes, take it`) | 82 text nodes, **60 AA-gated**, reading 47 / quiet 21, lowest **5.04:1** |

Both columns are the proof that the narrow rules measure the PANE: the window is 1224 px wide in both
runs and only the container width changed. The job row answers its own 620 px breakpoint — at a 612 px
card the actions move under the row, at an 818 px card they stay beside it. The type column is the
readability floor: the chips sit ON it (10.4 px, the kit's default badge step) and the card titles one
step above it (11.5 px), which is why 12 more nodes are inside the contrast gate than before the pass.

Negative controls, all RED as required: `--frame=560 --inject=media-query` (the pane gate, 1
violation), `--inject=job-row-stack` (the badge back on a line of its own, 2 violations),
`--inject=job-acts-too-wide` (an action group wider than its card: 13 out-of-card violations plus the
wrapped badge), `--inject=tiny-type` (a card title back at 9 px: 12 violations), `--inject=lower-chip` (the
`Verified` chip back in sentence case: 1 violation) and `--inject=wrong-token` (the
destructive-token swap), `--inject=chip-nowrap` (the chip's wrap rule removed: 1 out-of-card
violation at 352 px) and `--inject=no-narrow-runs` (the two narrow runs blocks switched off: 7
violations at 352 px, 5 at 400).

`pill_check.cjs`: 9 pills, 0 clipped, all `flex: 0 0 auto`; 5 `PanelMeta` values, `kvClipped` 0.
`canary_audit.py`: 48 rules, each fires on its own injected violation and the source comes back byte
for byte — the ones these passes added are the pane query (a width `@media` query is back), the query
container (`container-type:inline-size` gone), the job row's own breakpoint, its name line, a failed
read that stopped carrying the backend's error, a class with no rule (`wa-msgbox`), a font size under
the floor, and a badge back on the kit's `xs` step.

### The pane sweep (the host allows 352 px)

| pane · window 1224 | card | runs grid | cells · Duration | out of card | AA-gated | text past its box |
|---|---|---|---|---|---|---|
| **352 (host minimum)** | 254 px | `56px minmax(0,1fr) 96px` · **stacked** | 4 · **visible** | **0** | 63 | 0 |
| 400 | 302 px | `56px minmax(0,1fr) 96px` · stacked | 4 · visible | **0** | 63 | 0 |
| 470 | 372 px | `56px 170px 96px` | 3 · dropped | **0** | 59 | 0 |
| 560 | 462 px | `56px 260px 96px` | 3 · dropped | **0** | 59 | 0 |
| 660 | 562 px | `64px 222px 104px 110px` | 4 · dropped | **0** | 60 | 0 |
| 1000 | 902 px | `72px 456px 108px 120px 72px` | 5 · **visible** | **0** | 65 | 0 |
| 1240 (window) | 1142 px | `72px 696px 108px 120px 72px` | 5 · visible | **0** | 65 | 0 |

A stacked row has room for the Duration on its second line; the 470-560 band keeps the 820 px rule and
drops it. The gate's floor is the host's own 352 px: 300 px is below the contract (the layout tree will
not make a page pane narrower) and is measured and printed rather than gated — it still carries 2
findings, the copy button and its icon, in a head with no line left to wrap onto.

## The scroll pass (2026-09-21, version 1.6.0 — the user's red box on the jobs card)

The panel could not be scrolled. Reported against the live app: the SCHEDULED JOBS card cut its last
job row and the RECENT RUNS card sat half under the window bottom with no way to reach it.

Cause — `display:grid` on the root with `height:100%` inside a pane of FIXED height. A grid compresses
its `auto` rows to fit a definite container, so in a pane shorter than the panel every card overflowed
its own row, `.wa-card{overflow:hidden}` clipped the content inside it, and the root's scrollHeight
ended up equal to its clientHeight: there was nothing to overflow, so `overflow:auto` never produced a
scrollbar and the bottom card was unreachable.

Fix — one declaration on the root: `grid-auto-rows:max-content` (each row is its content's height).

> **2.0.0: this negative control no longer fires.** The Tabs wrapper (`.wa-tabbody>*{flex:1 1 auto;
> min-height:0}`) gives `.wa-root` a definite height from a flex parent, and the root keeps its rows
> at content height with or without `grid-auto-rows:max-content`. Measured: the preview with that
> declaration stripped exits 0 (0 defects, 0 unreachable at all six heights). The declaration and its
> audit rule stay (a root rendered outside the Tabs would need it). `scroll_check.cjs` now carries its
> own injected negative controls, which fire on both tabs:
>
> | control | what it breaks | `preview.html` | `preview-health.html` |
> |---|---|---|---|
> | `--inject=no-root-scroll` | the tab root stops scrolling (`overflow:hidden`) | exit 1, 6 of 6 heights | exit 1, 6 of 6 heights (cutBelow 94 at 760 px, 309 at 220 px) |
> | `--inject=tabbody-grows` | the tab body loses `min-height:0` and grows past the pane | exit 1, 6 of 6 heights | exit 1, 6 of 6 heights (3 defects, cutBelow 94 / 309) |

| pane height · `.wa-frame` | before: root | before: unreachable below the pane | after: root | after: unreachable |
|---|---|---|---|---|
| 760 px | sh 758 = cl 758 | 6 elements | sh **1220** vs cl 758 | **0** |
| 620 px | sh 618 = cl 618 | 14 | sh 1220 vs cl 618 | **0** |
| 560 px | sh 558 = cl 558 | 17 | sh 1220 vs cl 558 | **0** |
| 430 px | sh 428 = cl 428 | 31 | sh 1220 vs cl 428 | **0** |
| 330 px | sh 328 = cl 328 | 43 | sh 1220 vs cl 328 | **0** |
| 220 px | sh 218 = cl 218 | 60 | sh 1220 vs cl 218 | **0** |

Both columns are the SAME measured document (the panel's own preview, the app's Electron). The before
column carries 3 defect records as well — the first card clipping 281 px of its own content at 760 px
and 421 px at 220 px, plus two icon glyphs spilling 2 px and 6 px — and the fix clears all three. At a
352 px pane (the host's minimum) the content is 1475 px and still 0 defects / 0 unreachable; at 660 px
it is 1342 px.

Gated in two places, because the promise has two halves: `scroll_check.cjs` measures the pane (the
layout layer jsdom cannot be), and the `scroll flow` rule in `audit_static.py` refuses a root without
`grid-auto-rows:max-content` or without `overflow:auto`. The pre-fix source is the negative control
for BOTH: the check exits 1 with 3 defects and 6/14/31 unreachable elements, and its canary in
`canary_audit.py` removes the declaration and proves the audit rule fires.

## Language contract

* The panel calls `usePluginI18n('wiki-automation')` inside React and `ctx.i18n.t('wa.title')` where a
  hook cannot reach (the sidebar label is read at `register` time).
* `ctx.i18n.register({ en: { wa: { … } } })` — ONE bundle, nested, because the app translator resolves
  keys by DOT-PATH (`wa.title` = `bundle['wa']['title']`). A flat `'wa.title'` key would resolve
  nowhere: the panel would show raw keys while the bundle looked correct.
* The backend keeps one English message table behind `_tx(...)`; status and delivery labels are
  resolved there and the panel prints them as they arrive.
* `tests/fixture.mjs` builds its timestamps RELATIVE to today: a fixture pinned to a fixed date turns
  the "same day prints the time only" rule into a failure the next day.

## External check text (the checker is not this plugin)

`GET/POST /automation*` forwards what `~/.llmwiki-audit/wikiconfig.py` answers, and that program
speaks TURKISH: `"klasör yok"`, `"wiki/ boş ya da kimlik eksik"`, `"tarama kökü yok: <yol>"` and so
on. The English panel therefore maps it, in its OWN `en` bundle — the external program is never
touched, and its wording is never thrown away:

* `_TX_MAP` in `plugin.js` maps each known pattern to a bundle key. `txReason(raw, source, t)` returns
  `{ text, raw, known }`: the English sentence (from `wa.reason*` / `wa.checkUnrecognized`), the raw
  text as it arrived, and whether the pattern was recognised.
* A KNOWN pattern shows the English sentence with the paths and numbers intact (`"tarama kökü yok:
  /srv/nowhere"` → `scan root not found: /srv/nowhere`; `"proje kökü seçilmemiş (<path>)"` →
  `project root not chosen (<path>)`).
* The RAW text stays reachable: `question` unpacks it off the message, the kit's `Tip` carries it as
  its label on the message line and on the `.wa-raw` block, and the block itself prints it (the kit's
  `PanelBlock`) as `as written: …` — SHOWN BESIDE its English reading, never silently replaced.
* An UNRECOGNIZED pattern prints the raw text plus exactly ONE neutral label (`Unrecognized check
  output`). No invented translation.
* A reason the BACKEND resolved itself (its own `_tx(...)` table, e.g. the copy/mirror question) is
  already English and is printed as it arrived — no second reading, no duplicate raw block.
* Provenance is what makes this possible: the backend marks every checker payload with
  `reason_source: 'checker'` through `_reason_fields(...)`, so the panel knows which strings need
  mapping. A checker reason never leaves the API unmarked.
* The rule is enforced, not hoped for: `audit_static.py` refuses a `.reason` read that does not go
  through `txReason(<x>.reason, <x>.reason_source, t)`, a `_TX_MAP` entry whose bundle key does not
  exist, a raw block that stopped showing the checker's wording, a raw text that stopped being a `Tip`
  label, a `question` that stopped unpacking `msg.raw`, a backend `reason` read outside
  `_reason_fields`, and a route that stopped marking its payload. `canary_audit.py` proves each of
  those fires.
* The mapping does NOT touch the two-step copy/mirror write: the question the backend sends there is
  its own English and reaches the confirmation row unchanged.

## Known limits

* `render_check.mjs` ends with `process.exit(0)`: the panel's polling timers stay open and the process
  would otherwise hang after printing OK.
* The panel source is COPIED by the app: after a change, close and reopen Hermes (or ⌘K → "Reload
  desktop plugins") to see it.
* `jsdom` / `react` / `react-dom` are dev dependencies of this folder (`package.json`,
  `node_modules`); run `npm install` here if they are missing.
* The kit stub carries COPIED class strings, so a kit restyle is not reflected here until the copy is
  refreshed; the behaviour gates never depend on them, the visual ones do.
