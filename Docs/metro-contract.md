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
   - Four **branch lines**, one per Session Harvest adapter in `/harvest/status` order: Hermes,
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
4. **Detail panel** (at most one, under the map). It opens when a station, a branch, the alert
   button, History or Settings is clicked. It has a head strip with an icon, a title and a close
   button. Clicking the same thing again, or close, folds it. Opening a detail never moves the
   map: cards never expand in place.

## States: what each station shows

Data comes from endpoints the panel already calls. No new backend route is planned. A missing fact
is reported, not invented.

| Station | Source | ok | ask / warn / bad |
|---|---|---|---|
| Branch line | `/harvest/status` agents | `found && enabled` → solid line | `!found` → dashed grey line + `folder not found`; disabled → dashed + `off`; harvest running → the branches carry a dash pattern + `reading` |
| Harvest | `/jobs` role `session_harvest` (+ `/health/jobs` runs for running/last result) | `next HH:MM` pill + `in N h MM min` | running → `collecting now`; last run failed → red stop + `failed` pill and the job's own error text (shortened, raw text behind "Show the error"); paused → `paused` |
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
| Harvest station (m-03) | what it does (one sentence), timetable, next run, last run with duration and result; two buttons only: `Change time` (opens the existing ScheduleEditor) and `Pause` / `Resume` (the existing two-step job actions); no job row |
| Branch line | what it brings, collected up to (the adapter cursor), the line's own folder (`<Name> folder`) found or not; an enabled line whose folder is missing reads `On — skipped while the folder is missing; the other lines are read` (an engine without `--last-run` stops every line instead: `On — nothing collected while the folder is missing`); a line whose last run reported `UNREADABLE` reads `On — its history could not be read, so its conversations wait`; the honesty note "a found folder does not prove every conversation was read" only when the folder is found. A missing folder raises no alert. Lines that could not be read are named together in one `warn` alert (`<A and B> lines could not be read`), whose action opens the first; with an engine that stops every line, enabled lines with missing folders are named together in one `bad` alert (`<A and B> lines closed: folders not found`) whose action opens the engine install section. |
| Your review station or drafts alert | the review desk, **one draft at a time**: kind chip (New page / Update / Retire), `1 of N` dots with `Previous draft` / `Next draft` icon buttons beside the count (they only select, never write), title, one-sentence summary, `Will be saved as <path>`, `Approve` / `Reject` / `Later`; a draft whose detail could not be read shows that error on the card under the title, with no kind chip, Approve disabled and Reject / Later available; `Show the change and the evidence` is closed by default and holds the existing CandidateDetail. Approve keeps the existing two-step ConfirmDialog with its source-write and model-credit warning. Reject keeps its required reason. Owner set-up / recovery (OwnerSetup, RecoveryList) appears here when needed. |
| History (m-13) | head "History · last 24 hours · N runs"; one plain row per run: time, job icon + name, what it did, outcome dot + words; a lateness note when a job ran 10+ minutes after its slot; `Show older runs` (widens to 7 days, then to the whole history) and `Full technical log`, which opens the existing run history (JobRunsPage: KPIs, chart, filters, window picker, rows, drawer, archive-before-clear) |
| Settings (m-14) | three rows: Wiki folder (path + pages · checked), Automation files (`N of M in place`, opens the install section), Working folder; `Change wiki folder` opens RootCard, `Manage timetable` opens JobsCard; the install section (InstallCard, EngineInstall, InstallationFilesCard) opens from the files value. A section opens by itself while it holds a fix (wiki folder unverified, a job broken / paused / missing, engine ask, files missing) |

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
- **No ornament.** No hexagons, glows or cut corners. The only motion allowed:
  - the 120 ms colour/opacity feedback;
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
