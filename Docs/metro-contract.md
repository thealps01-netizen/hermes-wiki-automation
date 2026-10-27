# Metro panel (2.5.0): design and DOM contract

This file is the shared contract for the 2.5.0 rewrite of the panel's first screen. The panel code
(`desktop/plugin.js`) and the gates (`tests/*`) are written against it. If one side needs a change
to the contract, it records the change here and says so in its report.

The owner approved the composition from rendered mocks in `Docs/directions/metro-2.5.0/m-01.png` …
`m-16.png`. The script that drew them is `mock_build.py` in the same folder. Read the PNGs before
writing code; they are the target.

## Why

The owner found 2.3.x unmanageable: four tabs (Nexus, Chronicle, Folio, Health), dozens of
sections, and no single answer to "does anything need me?". He rejected a plain settings-page
simplification as "flat, no focal point". He also rejected six other directions. He picked a
**subway line map**: everyone can read one without learning it. A direction must pass a 5-second
read by a non-programmer: every mark carries a word; there are no codes, letter badges or legends.

## Screen

One view, no tabs. Top to bottom:

1. **Header.** Book icon, `Wiki Automation`, then two buttons on the right: `History` (history icon)
   and `Settings` (gear icon). Under a narrow pane (container query, at most 640 px) the buttons
   are icon-only and keep their `aria-label`. The active one is pressed (`aria-pressed="true"`).
2. **The line.** Title `Wiki line` plus the dim subtitle `from your conversations to your wiki`.
   - Four **branch lines**, one per Wiki Harvest conversation source in `/harvest/status` order: Hermes,
     Codex, Claude Code, Antigravity. Use the adapter's own id for the hue. Hues come from host
     tokens only: `--ui-accent`, `--ui-green`, `--ui-purple`, `--ui-cyan`, falling back by index.
     The branches merge into the first station.
   - Three **stations** left to right: `Harvest` → `Your review` → `Wiki`. Each station is a
     button: a ring (the stop), the name, and two short lines of plain text. A pill above the
     stop holds the state that matters now: `next 21:30` (clock), `collecting now` (sync),
     `3 waiting` (inbox), `failed` (error).
   - The **segments** between stations are SVG paths. They are computed from
     `getBoundingClientRect` after layout and on resize (ResizeObserver on the map root), never
     hand-typed. A segment starts at the edge of a label or stop, never at its centre.
   - Under the container query the line turns vertical: the branches stack above, the stations
     run down one rail, and each station's text sits to the right of its stop (m-15).
3. **Alert bar** (at most one). It shows the most urgent thing that needs the owner, in the
   priority order below. It has a tone stripe and icon, a bold one-line title, a dim one-line
   explanation, and at most one button. Its button opens the matching detail. With nothing to
   report, the bar says `Good service on the whole line` in green (m-05). It never says that when a
   read failed.
4. **Your wiki** (2.11.0, the approved modern draft `Docs/directions/modern/overview.html`). With no
   detail open it sits under the alert bar; it also opens the Wiki detail. One card: on the left a
   label, a heading (`N pages your wiki links to do not exist yet.` or `Every page your wiki links to
   exists.`), the page count and how many changed this week, the three missing pages named most (each
   a button that picks out the pages naming it; pressed again it lets go) plus `+N more missing pages`,
   and a key; on the right a canvas sphere with one dot per page, banded by folder, lit when the page
   changed in the last 7 days, the missing pages as dashed rings outside it and the pages naming them
   in orange. With more than 12 naming pages no link curves are drawn. Dragging turns the sphere; it
   never turns by itself. Its read (`GET /wiki/map`) is not one of the reads that raise the alert bar:
   a failure shows its error inside the card.
5. **Detail panel** (at most one, under the map). It opens when a station, a branch, the alert
   button, History or Settings is clicked. It has a head strip with an icon, a title and a close
   button. Clicking the same thing again, or close, folds it. Opening a detail never moves the
   map: cards never expand in place.

## States: what each station shows

Data comes from endpoints the panel already calls; the one route added since 2.5.0 is the read-only
`GET /wiki/map` behind the sphere (pages with folder band, title and age in days; missing link targets
with the pages naming them, by the engine's graph rule). A missing fact is reported, not invented.

| Station | Source | ok | ask / warn / bad |
|---|---|---|---|
| Branch line | `/harvest/status` agents | `found && enabled` → solid line | `!found` → dashed grey line + `folder not found`; disabled → dashed + `off`; harvest running → the branches carry a dash pattern + `reading` |
| Harvest | `/jobs` role `harvest_night` (+ `/health/jobs` runs for running/last result) | `next HH:MM` pill + `in N h MM min` | running → `collecting now`; last run failed → red stop + `failed` pill and the job's own error text (shortened, raw text behind "Show the error"); paused → `paused` |
| Your review | `/candidates` | `0 drafts waiting` | N > 0 → blue `N waiting` pill; the station is the alert subject; unreadable list → red with the backend's error |
| Wiki | `/automation` (pages) + watchdog findings (`/health/jobs` runs / `/health/watchdog`, the existing `FINDING_MAP` English) + morning jobs (autocommit, ingest_watch, watchdog) | `N pages` / `no problems` | findings → orange stop + `N problems`; a morning job failed for a reason other than findings → red |

**Alert priority** (first match wins):
1. any read failed (the backend's own error kept);
2. engine not installed, not taken over, an engine update ready, or owner approval needs set-up;
3. harvest failed;
4. a job without a working target, or a job missing;
5. drafts waiting;
6. wiki problems (findings);
7. a paused job;
8. harvest running (blue, informational);
9. good service.

Every state that the 2.4.0 "Needs you" list knew must land on one of these rows. That list is kept
as `archive/overview-2.4.0` in git: failures, broken jobs, unreadable lists, engine takeover, every
draft, paused or missing jobs. None of these states may disappear.

## Details: where every existing surface lives

Nothing that 2.3.12 can do may be lost. **The approved drafts (`Docs/directions/metro-2.5.0/m-*.png`)
decide what each detail shows first;** a 2.3.12 component that the draft does not show stays whole
behind the draft's own button (or opens by itself while it holds the fix for a problem). Reusing a
component is never a reason to show it where the draft shows something else. The render gate checks
each detail for the draft's texts and buttons.

| Opened by | Contains (existing components) |
|---|---|
| Wiki station or wiki alert | the findings list in plain English (number, title, one-line detail; raw text behind a disclosure); `Ask Hermes to fix these`; under it, `Work done at this station every morning`: three small cards for Daily check / New sources / Saving with last and next run and a dot |
| Harvest station (m-03) | what it does (one sentence), timetable, next run, last run with duration, result and cost, `Last night` (drafts, and why the night stopped early or `everything waiting was read`; only when the night record started with that run); two buttons only: `Change time` (opens the existing ScheduleEditor) and `Pause` / `Resume` (the existing two-step job actions); no job row |
| Branch line | what it brings, collected up to (the adapter cursor), the line's own folder (`<Name> folder`) found or not; an enabled line whose folder is missing reads `On — skipped while the folder is missing; the other lines are read`; `Last night` carries what the last night read from that line; a line whose last run reported `UNREADABLE` reads `On — its history could not be read, so its conversations wait`; the honesty note "a found folder does not prove every conversation was read" only when the folder is found. A missing folder raises no alert. Lines that could not be read are named together in one `warn` alert (`<A and B> lines could not be read`), whose action opens the first. |
| Your review station or drafts alert | the review desk, **one draft at a time**: kind chip (New page / Update / Retire), `1 of N` dots with `Previous draft` / `Next draft` icon buttons beside the count (they only select, never write), title, one-sentence summary, `Will be saved as <path>`, `Approve` / `Reject` / `Later`; a draft whose detail could not be read shows that error on the card under the title, with no kind chip, Approve disabled and Reject / Later available; `Show the change and the evidence` is closed by default and holds the existing CandidateDetail. Approve keeps the existing two-step ConfirmDialog with its source-write and model-credit warning. Reject keeps its required reason. Owner set-up / recovery (OwnerSetup, RecoveryList) appears here when needed. |
| History (m-13) | head "History · last 24 hours · N runs"; one plain row per run: time, job icon + name, what it did, outcome dot + words; a lateness note when a job ran 10+ minutes after its slot; `Show older runs` (widens to 7 days, then to the whole history) and `Full technical log`, which opens the existing run history (JobRunsPage: KPIs, chart, filters, window picker, rows, drawer, archive-before-clear) |
| Settings (2.12.0) | three sections, **all always open**, none behind a button: **Wiki folder** (RootCard: the saved folder, a `Change to` row with the path field and its Choose / Verify / Save, a `Find the wiki on this PC` row with the scan), **Scheduled jobs** (JobsCard, `N of M live` at the right of the head), **Engine and files** (InstallCard: an `Engine` row with the state, the installed revision and the update action, an `Install into` row, then the installation files). Every section head carries a status chip; a section that holds a fix (wiki folder unverified, a job broken / paused / missing, engine ask, files missing) carries the accent stripe on its left edge. Rows are one grid: label + note, value, actions on the right |

**`Ask Hermes to fix these`** writes a request into a chat composer and **never sends it**. The
panel is a full page, so no composer is on screen: it calls `host.newChat()` and then
`host.composer.insertText('new', text, { mode: 'block' })` until the fresh chat's box answers
(about 6 s; the 'new' address fails closed, so the text cannot land in another chat). A desktop
without `newChat` falls back to `insertText(null, …)`. When no box answers, show
`The chat box did not open. Start a new chat, then press again.`.
The request text lists every finding in English with its raw line and asks Hermes to fix them.
It cites no path that the finding itself does not carry.

## DOM contract (the gates key on these)

```
.wa-metro                         root of the view (container-type: inline-size)
  [data-wa-nav="history"|"settings"]   header buttons, aria-pressed
  .wa-metro-map[data-dir="h"|"v"]      the line; svg.wa-metro-wires inside
    [data-wa-line="<adapter id>"][data-state="ok"|"missing"|"off"|"run"]
    [data-wa-station="harvest"|"review"|"wiki"][data-state="ok"|"ask"|"warn"|"bad"|"run"|"paused"]
        button, aria-pressed when its detail is open, aria-label = name + both text lines
  .wa-metro-bar[data-tone="ok"|"ask"|"warn"|"bad"][data-alert="<priority key>"]
  .wa-metro-detail[data-for="wiki"|"harvest"|"review"|"line:<id>"|"history"|"settings"]
  .wa-metro-skeleton               loading
  .wa-globe[data-wa-globe="ready"|"reading"|"unread"]   the sphere card
    canvas.wa-globe-canvas[role="img"][aria-label]     one dot per page
    button.wa-globe-miss[aria-pressed]                 a missing page; picks out the pages naming it
  .wa-metro-detail[data-notch]     the notch that points back at the open station or branch
```

Priority keys: `read-failed`, `engine`, `harvest-failed`, `job-broken`, `drafts`, `problems`,
`paused`, `running`, `good`.

## Hard rules

All rules from `Docs/wiki-automation-notes.md` still hold. In particular:
- host tokens only;
- 12 px text floor;
- no native `title=`;
- English UI copy through the i18n bundle;
- no comments in `plugin.js`;
- the jsx third argument is the key;
- loader-allowed imports only;
- a failed read keeps the backend error;
- two-step writes stay intact.

In addition:
- **Text and colour.**
  - Reading text stays on `--ui-text-primary` / `--ui-text-secondary`.
  - State colour goes on stops, stripes, pills and lines only.
  - WCAG AA is measured by the preview gate.
- **No ornament.** No hexagons, glows or cut corners. Lines and stops are 2 px; the cards, the alert
  bar and the details share one corner radius (`--wa-r`). The only motion allowed:
  - the 120 ms colour/opacity feedback;
  - the sphere turning while the owner drags it (never by itself);
  - the dash-offset march on the branch lines while harvest runs;
  - `prefers-reduced-motion` turns the march off.
- **Narrow pane.** At 352 px nothing overflows, and the stations stay readable.
- **Removed (do not bring back):**
  - the four tabs;
  - the Nexus map and its inspector and wire animation;
  - the heartbeat strip;
  - the Chronicle lower review queue;
  - per-view titles.

### Draft details settled in 2.5.1

- The alert bar steps aside while the detail its button opens is the open one (m-02, m-07, m-08); a bar
  that jumps into Settings stays.
- With no readable timetable the map is its title alone, `Wiki line · no timetable` (m-12); the bar says
  `The timetable could not be read` and keeps the raw error behind `Show the error`.
- The review head reads `Your review · draft k of n`; the evidence disclosure sits on the button row (m-07).
- The first Approve opens a centred dialog `Approve this draft?` naming the draft, the target path and the
  model-credit warning; the engine's own question and dry-run output stay behind `Show what the engine
  reported`. The two-step write is unchanged (m-08).
- The harvest bar reads `Harvest is reading your conversations` (m-06), `Harvest stopped at HH:MM` with
  `No drafts were written. Reason: …` (m-09); a closed line reads `<Name> line closed: folder not found`
  (m-10).
