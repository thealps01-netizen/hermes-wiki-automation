# Wiki Automation — panel notes

Why the panel and the backend are built the way they are. The code itself carries no comments, so
every decision that would otherwise sit in one lives here.

## What the panel shows

Since 2.2.0 **Map** opens first, using the approved Nexus composition from `Docs/harvest-ui-v2`.
Conversation adapters connect to Session Harvest and the review boundary. Selecting a node reveals
its inspector. A lower read-only review queue opens sources in Folio; job management and recent-run
heartbeats remain available. Project settings holds root selection and installation details. An
unverified project opens setup automatically. **Chronicle** owns the only run journal; **Health**
retains watchdog findings, freshness and diagnostic analytics. Earlier sections describe historical
surfaces; the obsolete KPI/gauge shell and its layout-specific gates were retired in 2.2.0.

### Ask Hermes opens a new chat (2.5.1)

The panel is a full page, so no chat box is on screen while it shows; 2.5.0 inserted into the
"active" composer and found none. `placeInNewChat` opens a fresh chat through the host's own door
(`host.newChat()`, which also navigates to the chat view) and writes the request into ITS box with
`host.composer.insertText('new', text, { mode: 'block' })`, retrying every 150 ms for about 6 s while
the box mounts. The `'new'` address fails closed (`apps/desktop/src/sdk/composer.ts`,
`resolveComposerAddress`), so the text can only land in that fresh draft and never in another chat.
Nothing is submitted. An older desktop without `newChat` falls back to the active box (`null`).

### History, Settings and Harvest follow their drafts (2.5.1)

2.5.0 reused the 2.3.x components as the first thing each detail showed, so History, Settings and
the Harvest station did not look like their approved drafts (m-13, m-14, m-03). 2.5.1 shows the
draft first and keeps every 2.3.x component one click behind the draft's own button: History's
`Full technical log` (JobRunsPage), Settings' `Change wiki folder` (RootCard), `Manage timetable`
(JobsCard) and the automation-files value (InstallCard). A Settings section opens by itself while it
holds the fix for a problem, so a broken job or an unverified folder is never hidden. The History list
reads the line's own 24-hour run read; `Show older runs` widens it to 7 days, then the whole history.

### Unified workspace

Nexus, Chronicle, Folio and Health are complementary views of the same plugin, not separate
automation engines. One navigation shell carries project context across the views. Project selection
and installation details stay under Project settings rather than becoming repeated setup panels.
Nexus retains the configuration map, job controls, project setup and compact heartbeat. Its review
queue opens the selected source in Folio; the heartbeat's journal shortcut opens Chronicle.
Chronicle owns the run list, filters, output/details and archive-before-clear. Its lower review queue
also opens Folio. Neither queue can approve or reject a source. Health retains diagnostic analytics
but not another copy of the run list. Folio owns source decisions with the existing engine
preview/confirm protocol, format validation, raw output and reject reason. No simulated approval
trail from the prototype is treated as backend data.

### Folio scope invalidation (SEC-3)

Folio captures the SDK's actual `host.state.connectionId`, `host.state.profile` and workspace
`host.state.cwd` values, with an in-memory epoch. SDK listeners invalidate the old review and
recovery immediately; callbacks also compare those live values synchronously, before React's next
render. Scope re-entry never revives an old callback or an old queue-navigation `initialRef`.

One read-only polling loop first obtains `/automation` in that captured SDK scope and compares the
configured project root and project ID. Only then does it read candidates and approved recovery
inventory. A project change or failed context read removes old details, confirmation, rejection
reason and recovery rows. Deferred old reads cannot replace the new scope, and an old request's
completion cannot release a newer polling ticket. A pending context/inventory read blocks decisions
synchronously, not merely through disabled buttons. No mount-triggered mutation or persistent client
storage is used.

Approval retains its exact `request_id`/`review_digest` protocol. Rejection now sends the displayed
exact `review_digest` too; it cannot reuse a reason/callback from an earlier review. Recovery sends
only the server-owned `request_id`, consults the current inventory and permits an explicit retry
following refusal. Successfully completed recovery callbacks are locally single-use. These UI guards
do not cancel a request already dispatched to the old backend and do not establish source-owner
identity; server-side session binding and atomic exact-digest enforcement remain authoritative.

`render_check.mjs` exercises retained confirmation/rejection/selection/recovery callbacks, SDK scope
re-entry, synchronous pre-render guards and deferred detail/prepare/approve/reject/recovery results.
`render_health.mjs` drives the real 60-second polling callback, failed context reads, changed project
identity, delayed old inventories and nonfirst queue navigation across a profile switch. All harness
generators run sequentially inside a copied scratch checkout, never in the shared working tree.

### Reference-faithful reading surfaces

Use the approved `Docs/harvest-ui-v2` studies for composition, with the host's theme tokens and
controls. The views share chrome but retain different information layouts:

* **Nexus:** connected adapter, Session Harvest and review-boundary nodes form a configuration map,
  with the selected node's inspector beside it and a read-only review queue below. Connectors do not
  indicate active execution or completed ingestion. Schedule and setup controls remain available.
* **Chronicle:** search and outcome controls stay visible; advanced job/date filters begin closed.
  The chronological run list is as tall as its runs and scrolls past 520 px (2.3.6; it was a fixed
  520 px box that left empty space under a short list). The adjacent summary inspector has
  `height: auto` and `min-height: 520px`, grows with its content and is not independently scrollable
  as a whole. It leads with outcome, timestamp, duration, delivery, a synopsis and recorded-duration
  comparisons. Findings, original output and run metadata remain under Technical details; long raw
  output stays in bounded boxes. Read and copy failures remain visible outside the disclosure.
  The lower read-only review queue opens Folio, including when the filtered journal has no rows.
* **Folio:** candidate index, document and decision context remain distinct. The proposed source
  preserves heading levels visually and marks added, removed and context lines; the unchanged diff
  remains under As written. The decision trail shows evidence availability, candidate rationale and
  the pending decision. It is not a completed approval history or a timestamped collection timeline:
  evidence metadata contains no collection timestamp. Format checks, evidence folders, destination
  and existing decision controls remain attached to the selected candidate.
* **Health:** the metric strip, execution timeline and job distribution are separate diagnostic
  regions. Freshness and findings remain here; the journal belongs to Chronicle and source decisions
  to Folio. Do not restore a second run list or the retired overview gauge.

### Nexus data and copy contract

The map is configuration, not live execution telemetry. Adapter names and states come from the
engine's read-only status command through `GET /harvest/status`, not a copied reader catalogue.
Enabled, directory detected and committed cursor are separate facts; none proves full collection.
A missing engine, process failure, timeout, empty output, unsupported line or duplicate adapter is
an explicit failed read. Polling retains last good data with a stale notice. It never starts harvest,
commits cursors or changes settings. The endpoint selftest covers these failures and the read-only
command shape against temporary engine fixtures.

Job names, schedules and next/last timestamps use the existing jobs response; candidate counts use
the existing review response. Selection remains consistent if an adapter disappears on refresh.
Native buttons expose selected state and inspector relationships. Review/job shortcuts move focus,
not just the scroll position; reduced-motion preferences disable smooth scrolling. Theme tokens,
the host icon set and container queries keep the surface coherent in a split pane.

Keep short operational headings, states and actions. Do not restore the overview kicker, repeated
subtitle, KPI cards, gauge or redundant list explanations. Keep failure reasons, provenance,
format checks, reject reasons, source-write/model-usage warnings, root/copy confirmation and
archive-before-clear protections. The clean preview and expanded destructive fixture are separate
states so a collapsed settings section cannot accidentally satisfy a visible-text contrast gate.

## App-managed engine installation in Project settings

The existing Install card consumes the backend lifecycle; the panel does not unpack bundles,
calculate digests, register jobs, rewrite settings, grant publication authority or implement recovery.
The engine release is the digest-verified `engine/` folder in the same unified plugin package. There
is no HTTPS publication gate or separate installer panel.

### The engine lives in the panel repository (2.8.0)

Until 2.7.2 the engine was a separate private repository, shipped here as a zip under `engine-assets/`
and installed a second time. Three version lines (engine repository, zip, installed release) kept
raising "which engine is installed?": 2.7.2 shipped engine `85688e4`, a commit on a branch never merged
into the engine's `main`, and the old engine checkout in the data folder fell behind until Watch Dog
reported its scripts as stale. The owner found moving, installing and updating the engine the main
burden, so the engine source now lives in `engine/` and the panel repository is its only home.

- `engine-release.json` is generated by `tools/engine_release.py`: `sha256` is the digest of every
  file under `engine/` (`release_digest` in `dashboard/engine_lifecycle.py`; `__pycache__` is
  skipped) and `revision` is its first 40 hex characters, so the release folder name under
  `state/wiki-automation/releases/` still fits every reader of a 40-hex revision.
  `tools/engine_release.py --check` runs in CI and in the unit suite; a changed engine byte fails it.
- Staging reads the folder with the same refusals the zip reader had: no links, hard links,
  case-colliding names, reserved or traversing names, and the same file-count and size limits.
- The install itself is unchanged: **Preview update** still prepares a plan the owner confirms, so the
  two-step install contract stays. Installing the engine automatically on a plugin update would
  remove that confirmation; it is not done without the owner's decision.
- The repository stores text as LF (`.gitattributes`); `*.cmd` keeps CRLF because `cmd.exe` misreads
  labels in an LF batch file. The digest is taken from the checked-out bytes, which this policy makes
  the same on every platform.
- The old engine history was not imported: it carried personal data (an e-mail address, machine paths
  and old screenshots). Only the tree of `85688e4` entered, with the drift check's default author removed
  (`drift.own_author` now comes only from `settings.json`; without it no skill copy is skipped for its
  author, rather than every authored copy being skipped unseen).

- On mount, the card reads `GET /engine/status`. Neither mounting, status reads nor opening Project
  settings prepares or applies anything. Missing, prepared, applying, installed-paused,
  recovery-required and unavailable states remain distinct; failed reads expose an explicit retry.
- The SDK's `ctx.os.pickOpenPath` selects one file, not a directory; it has no `properties` option.
  Initial setup asks for a file **directly inside the project folder** and keeps its containing
  folder as a local draft. Do not select `.llm-wiki/project.json` in this initial-install picker:
  that would choose `.llm-wiki`, not the project. An absolute-root input remains available when
  the native picker is unavailable. This path does not call engine-dependent root derivation,
  validation or save routes. The existing Watched root card keeps its separate backend-validated
  file/identity workflow after installation.
- Preview sends only `{project_root}` to `POST /engine/prepare`. The backend stages a plan; preview
  does not register jobs or switch the active engine. The returned revision, project root/id,
  code/data directories, install id, plan digest, every job role/name/schedule and activation text
  are displayed exactly. The named, keyboard-reachable plan region scrolls within 420 px, and long
  values wrap without truncation. Response-shape checks do not replace backend validation.
- Only **Install this exact plan** sends `{install_id, plan_digest, confirm:true}` to
  `POST /engine/apply`. No extra context/auth fields are added to the body. A successful HTTP
  response alone is insufficient: success must report the matching install id/revision and an
  explicit installed state. New installations require `installed_paused` and
  `activation_required:true`. The existing-job update outcome is shown separately when reported
  as `installed_with_existing_jobs` with `activation_required:true`. Both states still require
  runtime verification; retained enabled jobs are not proof that new native code is active.
- Installation does not publish sources or activate new jobs. Activation remains a separate
  Scheduled jobs action. **Discard plan** invalidates local confirmation only; it does not remove
  staged backend data or roll back an installation. Recovery-required blocks further installation
  actions and asks for journal inspection; no automatic rollback is offered.
- The host authenticated interactive app session authorizes lifecycle administration. Source-owner
  authority is neither required nor configured by these controls. SDK REST uses the ambient native
  connection/profile. Preview captures `host.state.connectionId` and `host.state.profile`; their
  listeners invalidate confirmation, and guards reread both immediately before dispatch and after
  completion. Project root/id changes, root edits, discard and unmount also invalidate stale
  callbacks/results. Switching away and back cannot revive an earlier preview. A transport retry
  in the unchanged scope reuses the same staged id/digest instead of preparing another plan.

The normal render harness uses real React/jsdom and controlled SDK/backend boundaries. Its
RED/GREEN cycles cover the mounted settings card and retained callbacks. A separate mode of that
same harness is driven by `test_actual_project_controls_confirm_against_disposable_backend`: it
clicks the actual Project controls against a temporary HTTP/FastAPI server and invokes the bundled
engine. It verifies first install and an update retaining an enabled native job, exact displayed
confirmation, four nonduplicated job records and active location readback. The request's original
root spelling is echoed separately from the engine's canonical verified root; both are bound in
the saved installation identity. This catches cross-layer contracts that fixture-only gates miss.

Run Python UI/API and Node render gates serially: they regenerate shared SDK stub/module files.
All writes are confined to disposable profile/wiki fixtures and generated test outputs. These
results prove isolated backend installation, not live deployment, installed-copy synchronization,
native activation or pixel fit. Native rendering remains a separate gate.

## Why a panel of its own (superseded in 2.0.0)

Until 1.10.0 choosing and auditing the root was kept apart from reading cron history, so one breaking
left the other standing. In practice the two panels showed the same runs twice and drifted apart; 2.0.0
merges them into one plugin with two tabs, and a failed read still only takes down its own card.

## Root and job action scope (PANEL-FINAL-SEC-1)

Root and job reads carry an immutable SDK connection/profile/cwd snapshot and a project epoch.
SDK atom listeners invalidate the epoch synchronously, before React renders; returning to the same
atom value does not revive old callbacks. Changed contexts clear drafts, scan results, validation,
copy/mirror review, armed delete, schedule editors, pending flags and result notes. Fresh automation
and job reads must finish before new mutations are actionable. Root changes also refresh the jobs
for that project without waiting for the polling interval. An unavailable or failed context read
does not authorize writes or take unrelated read-only cards down.

Every root picker, derive, verify, save, scan and scan-root continuation checks its captured scope
before dispatch and after awaiting. One pending ticket owns the whole picker/scan chain; old
completion cannot clear a newer ticket. Copy/mirror grants bind the exact draft and scope, are
consumed once, and are invalidated by editing or cancellation.

Job create, pause, resume, schedule and delete bind the rendered role/id/state/schedule facts as
well as the SDK/project scope. Replacing a job id clears armed delete and schedule editing. Delete
grants are single-use; cancellation and rearming cannot revive a retained confirmation. The
schedule debounce checks scope before its preview request and before publishing its response.
Old successes and errors cannot write new-context messages, close new controls or refresh it.

`WIKI_PANEL_SCOPE_ONLY=1 node tests/render_check.mjs` exercises the four reported retained-callback
cases and mounted React/jsdom pending, deferred, cancellation, ABA, fresh-read, changed-project,
changed-id and single-use controls. It retains the real rendered React events and uses only the
fixture API/picker. This is neither native pixel evidence nor authorization for live writes.
Existing Folio and installation guards remain unchanged; they share only the SDK snapshot helper.

## How the root is chosen

The SDK has no folder picker — it only picks a single FILE (`ctx.os.pickOpenPath`). The user therefore
picks a file INSIDE the wiki folder (`.llm-wiki/project.json` is the clear choice), the folder above it
is derived by the backend, and `wikiconfig.py validate` PROVES it. An unverified root is never saved;
the panel prints only what the backend returned — showing a failure as "saved" is forbidden.

## The save gate lives in the backend

`POST /automation/settings` validates before it writes, so the panel cannot talk itself into a save.
The panel refreshes its state only after the backend answered ok.

## Copy / mirror confirmation (two-step write)

If the new root carries the SAME project id as the current one but a different path (a local folder and
its mirror), the backend refuses silently-accepting it and answers `needs_force` with a reason. The
watchdog's "commit that never reached the mirror" comparison would otherwise compare a path with
itself and the backup watch would quietly stop meaning anything. The panel shows the question and only
sending `force: true` — the user's second, explicit click — writes it. Moving to a new PC asks nothing:
there is no current root to collide with.

## Path comparison is normalised

Candidate paths are compared with a stripped trailing separator and lower case: without it the current
root showed up as its own candidate, because of a case or slash difference, and saving would have
rewritten the root text for nothing.

## Candidate scan

The scan root comes from the settings (`scan_root` → the folder above the current root) so discovery
also works while the root is not set yet. With no root at all, the user picks the scan folder
explicitly, because there is nothing to derive it from. The scan result says how much ground it
covered ("N folders scanned", "1 folder unreadable", "scan stopped early"), so "nothing found"
never mixes with "could not scan". A `SAME ID` candidate is flagged in the list and preselects the
confirmation.

## Scan root picked from a file

The scan root must be a folder, but the picker only returns files. The folder of the picked file is
used; when that folder is hidden (`.llm-wiki`), its parent is used instead — otherwise the scan would
walk the identity folder itself and find nothing.

## Picking a file inside the wiki folder

The dialog opens on the current root's identity file (`.llm-wiki/project.json`) so the user does not
have to navigate to the right folder, and the window title stays short: a long hint did not fit a
title bar and did not say what to pick.

## Dialog filters

Two filters are offered: wiki project files (`.json`, `.md`) and all files. The user must be able to
pick a file the first filter would hide, because any file inside the folder works.

## Install card

The script count and the job count come from the backend (`info.jobs`); the Task Scheduler flag is gone
with 2.1.0 (see "Schedules a person can read"):
the panel does not compare two lists of its own, it reads one source. The "live" measure is being
defined in `cron/jobs.json` — an id still sitting in the settings whose job has been deleted does not
count as live.

## Recent runs

The two axes are read separately (`status` = how the run ended, `delivery` = whether its output
reached the user): "completed + silent" is a NORMAL run, "failed + delivered" is the real alarm.
Merging them would invert the meaning of the report. A deleted job's record is NOT dropped — it stays
visible, flagged as a deleted job. Rows are sorted across ALL jobs, newest first: the table is one
timeline, and grouping it per job put the timestamps in an order that read like a sorting bug.

## Timestamps

Today's run prints its time only; another day prints `DD.MM HH:mm` through the bundle's `wa.stampDay` key, so a
language with another day order changes it in one place. Without the date, yesterday's and
today's runs look like the same hour and the ordering looks wrong. The day is compared against the
local calendar, while the timestamp keeps its own offset.

## Duration

`claimed_at` is local (`+03:00`) while `scheduled_instant` is UTC; comparing them naively shifted the
duration by the offset, so both are normalised to aware datetimes first.

## jsx third argument is the KEY

`jsx(type, props, key)` / `jsxs(type, props, key)` — the third argument is the key, NOT children.
Children live inside `props`. Passing the children array third renders an empty element with no error
and no console warning, which is how a run row once came out blank.

## Language

Text resolves from the application language: `usePluginI18n()` inside React and `ctx.i18n.t` where a
hook cannot reach (the sidebar label is read at registration time). One English bundle is registered
through `ctx.i18n.register`; the panel carries no picker, no `lang` state and no language key of its
own. The backend keeps a single English message table behind `_tx(...)` — status and delivery labels
are resolved there and the panel prints them as they arrive, never re-translating them.

## The check's own wording is mapped, never replaced

Part of what the panel prints does NOT come from this plugin: `wikiconfig.py` answers in TURKISH
(`"klasör yok"`, `".llm-wiki/project.json okunamadı"`, `"tarama kökü yok: <yol>"`, `"proje kökü
seçilmemiş"` …) and those strings arrive as `reason`. Printing them as they came put Turkish phrasing
on an English screen; translating them silently would throw away the only text a bug report (or the
author of the external program) can search for. So the panel does both:

* `_TX_MAP` matches the known patterns and `txReason(...)` returns the English sentence from the
  panel's own `en` bundle (`wa.reason*`) with the paths and numbers intact, PLUS the raw text.
* The message line shows the English; a smaller line under it shows `as written: <raw>`, and the same
  raw text is the tooltip of both. Nothing is dropped, nothing is overwritten.
* An unknown pattern is NOT guessed at: the line reads `Unrecognized check output` and the raw text
  sits right below it.
* A reason the BACKEND built itself (its `_tx(...)` table, e.g. the copy/mirror question) is English
  already, so it is printed as it arrived and gets no second reading and no raw duplicate.
* Which is which is decided by provenance, not by guessing at the alphabet: the backend marks every
  payload it forwards from the checker with `reason_source: "checker"` (`_reason_fields`). A checker
  reason therefore never reaches the panel unmarked, and the panel never has to ask "is this
  Turkish?".
* The mapping is kept out of the two-step copy/mirror write: that question is the backend's own
  English, so the confirmation row reads exactly as before.

`tests/audit_static.py` bans a `.reason` read that does not pass `txReason(<x>.reason,
<x>.reason_source, t)`, a `_TX_MAP` key that is not in the bundle, a missing raw block, a backend
reason read outside `_reason_fields` and a route that stops marking its payload;
`tests/canary_audit.py` injects each of those violations (and every other audit rule) to prove the
rules still fire.

## Why the backend reads the settings the way it does

The single resolver of the settings is `wikiconfig.py` in the automation folder. The panel calls it as
a subprocess and never reads its own copy of the rules: two resolvers would drift apart.

## Read-only, and the one write

`executions.db` is opened `mode=ro` (the scheduler writes to the same file) and nothing is written to
the cron directory. The single write is the user's explicit "Save", and it goes through
`wikiconfig.py set` — which refuses an unverified root.

## Finding the automation folder

Order: `LLMWIKI_AUDIT_DIR` → the `state/wiki-automation/location.json` record in the Hermes home →
`~/.llmwiki-audit`. The record exists because the package can be moved to another folder or disk;
without it the panel looked at `~/.llmwiki-audit`, reported "not installed" and broke the portability
promise. `install.py` writes the record.

## Loader trap

The app scans plugin source with `/(from\s*|import\s*\(\s*|import\s+)(['"])([^'"]+)\2/g` and rejects
the WHOLE plugin when a matched specifier is not `@hermes/plugin-sdk` or `react*`. It matches any
`from`/`import` token followed by a quote, so a dictionary key that ends in `from` reads as an import.
`tests/audit_static.py` re-applies the loader's own regex, so this can never be discovered first as an
empty page in the app.

## After a change

The panel source is copied by the app: seeing an edit requires closing and reopening Hermes (or
⌘K → "Reload desktop plugins").

## The panel is on the host UI kit

The panel no longer hand-rolls its controls. Buttons, badges, fields and the loading/empty/error
treatments are the app's own primitives, imported from `@hermes/plugin-sdk` (every name verified
against `apps/desktop/src/sdk/index.ts` before it was used, and against `apps/desktop/DESIGN.md` for
how it is meant to behave): `Button` (variant + size, no `h-*`/`px-*` override), `Badge` (status),
`Input` (the root path), `SearchField` (the candidate filter), `SegmentedControl` (the runs range),
`PanelSectionLabel` / `PanelMeta` / `PanelBlock` (card headers, the install rows, the raw check
text), `EmptyState` (nothing to show), `ErrorState` (a failed read), `Loader` (the first read, no
"Loading…" text), `Tip` (tooltips) and `CopyButton` (the two code surfaces, icon form).

Why it matters beyond looks: a runtime plugin is loaded from `$HERMES_HOME/desktop-plugins/` and is
NEVER scanned by Tailwind, so the kit's classes only exist because the APP compiled them. Anything
the plugin styled itself with utility classes would silently render unstyled in the app. So the
kit owns padding/colour/chrome, and the plugin's own `<style>` block keeps its page layout plus the
ONE shape the design reference names and the kit has no size for — the circular icon button
(`.wa-icon-btn`) — always from theme variables, never a literal colour.

## Why the empty-state and kind-of-`title` decisions

* A `Tip` cannot wrap a kit block. `PanelBlock` (like `PanelMeta` and `EmptyState`) takes children
  and a class name and forwards nothing else — no ref, no extra prop — so `<Tip><PanelBlock/></Tip>`
  would drop the tooltip's trigger props on the floor. The raw check text therefore lives in a host
  `div.wa-raw` that `Tip` wraps, with the kit's `PanelBlock` inside it.
* The install rows are `PanelMeta`. Its label column is the kit's inspector default (5rem), which
  truncates a noun like "Automation folder"; the plugin widens it to 7.75rem in its own CSS. The
  visual gate now fails if ANY label or value truncates, so this cannot regress unnoticed.
* Status is a `Badge` variant, not a hand-rolled pill: `success` for a verified root, `destructive`
  for a failure or a deleted job, `warn` for the SAME ID copy/mirror flag, `muted` for a normal run.
  The `.wa-badge` class stays on them only as a measuring hook.

## No native `title=` anywhere

The panel used to carry a `tipProps(...)` helper that wrote `title=` plus `aria-label` onto every
element it labelled — including the raw text of the external checker. Native titles are unstyled,
open after the OS delay (~500ms) and look nothing like the host's tips; the app itself fails any
`<button>` carrying one (`apps/desktop/src/components/ui/__tests__/no-native-title.test.ts`). Every
one of them is now the kit's `Tip` (the glyph-only refresh button keeps an `aria-label`), and
`tests/audit_static.py` refuses a `title=` in the props of any control or element — with the
FILE PICKER's `title` option exempt, because that one names the dialog window rather than styling a
tooltip. `tests/canary_audit.py` injects one back to prove the rule fires, and both harnesses assert
the rendered DOM has no `title` attribute at all.

## The candidate filter and the runs range

Two small controls were added while migrating, both from the kit and both honest about what the
backend already offered. `SearchField` filters the candidate list by path (a list that can be long
after a scan); a filter that matches nothing says so in ONE neutral `EmptyState`, never in red, and
an empty list hides the field entirely — the kit's own rule. `SegmentedControl` chooses how many
recent runs are read (3 · 10 · 25): the panel already polled `/runs?limit=3`, so the range only
makes the existing query parameter reachable, and changing it re-reads immediately.

## Scheduled jobs are managed here

The panel manages the scheduler entries that keep the watched folder current, so a job is created,
paused and removed where its state is visible instead of from a chat or a CLI.

* **Roles, not ids — read from the engine.** The roles come from the engine's `<audit dir>/jobs.json`
  (see "One job definition" below). The SCHEDULE comes from `wikiconfig.py show` (by the role's
  `schedule_key`) and falls back to the engine's `default_schedule` when the config has none.
* **The write path is the app's own cron store** — `cron.jobs.create_job / pause_job / resume_job /
  remove_job`, imported by the backend inside the app process, plus
  `cron.scheduler._notify_provider_jobs_changed()` so a running scheduler notices. `jobs.json` is
  never written by hand: the store's own lock is what keeps the panel from racing the scheduler.
* **Create** uses the schedule the config carries and REFUSES without a verified wiki root — a job
  whose scripts would alert on every run is worse than no job. The id that comes back is recorded in
  the panel's own state (`state/wiki-automation/settings.json → jobs`), and that mapping is what BOTH
  views read: the runs table merges it over the audit config's older `jobs` map, and a live job is
  additionally attributed by its canonical name, so a job created here cannot end up invisible in the
  run history.
* **Remove is two-step** (arm, then confirm) and the id stays in the mapping afterwards: the job's
  rows remain in the runs table flagged `deleted job`, which is how the history keeps its meaning.
* **A job whose target is gone is an orphan.** `target.ok` is the wiki root's verification AND the
  implementation file's presence; the card names which half failed and recommends Pause, which is
  reversible. Nothing is paused or deleted automatically.
* A failed action prints the mapped sentence with the checker's own wording beside it (`txReason`
  plus the `as written` block) and never a silent no-op.

Restart note: these routes live in `dashboard/plugin_api.py`, which the app loads at boot — the JS
side reloads with the plugins, the backend needs an app restart.

## Pane width, not window width

The panel lives in a pane, so a width `@media` query answers the wrong thing: dragging the split
narrow in a wide window kept the five-column runs grid and clipped the Duration column. The panel
root is now a query container (`container-type:inline-size`) and the narrow rules are
`@container` blocks measured against the space the panel really has: `(max-width:820px)` for the runs
table and `(max-width:620px)` for the job row (see below).
The pane is not free to be any width either: the layout tree gives a page pane `minWidth: '22rem'`
(352 px), and the panel root's own padding leaves about 254 px of card. The narrow rules therefore run
to the bottom of that range — `(max-width:470px)` drops the Delivery column and `(max-width:360px)`
stacks the run row (the name on its own line, then time · status · duration, which is where the
Duration comes back after the 820 px rule had dropped it). The measurement sweeps 300 → 1240 px and
fails on any element outside its card from the host's own 352 px up; 300 px sits below that contract
and is printed (2 findings) rather than gated.
The measurement renders the panel inside a 560 px frame in a 1224 px window: the Duration column
drops (4 of 5 cells). `tests/shot.cjs --inject=media-query` keys the same rule back to the window and
the gate then FAILS on exactly that (1 violation) — the negative control, so the rule cannot quietly
become a window query again. `tests/audit_static.py` bans a width `@media` query and requires the
container declaration; `tests/canary_audit.py` injects each of the two back to prove both fire.

## A result is a note card, on every card

The jobs card printed its action result into `.wa-msgbox` — a class no rule defines, so the note
rendered as a bare line while the root card showed the same thing as a bordered card. Both now use
one treatment: a heading (`Result` · `Why this was refused` · `Note`), one sentence, and the raw
wording in a code body under its `as written` caption when the checker produced it. `.wa-msg` is
declared once (it was declared twice, and the second rule only added padding), and inside a help card
the message sits flush under its heading instead of 12 px in.

## A failed read keeps the error

`could not read the automation state` was the whole answer: the caught error was dropped. `Failure`
now takes it as `detail` and prints it in the same code body + copy affordance the checker's wording
gets. The Install card reads the same `/automation` payload, so it showed a spinner while the root
card showed the failure — it now prints the same refusal, and nothing spins when nothing is loading.

## The candidate chip says what it counts

The page count was a bare number (`12`), so the row's accessible name read as a path followed by a
stray digit. It now reads `12 pages` — the same wording the verification line uses — and the count is
plural-aware, so one page prints `1 page`.

## The job row is a name line, not a stack

The state badge was a third child of the job's text column, so every job was three lines tall
(name · schedule · badge) and the badge read as a fact separate from the job it belonged to. It is now
a sibling of the name inside `.wa-job-line` (a wrapping flex row), so a job row is: NAME with its
state badge on that line, the schedule under it, and — only when the pane is genuinely tight — the
actions on a line of their own. `.wa-job-acts` wraps rather than pushing, and the job row answers its
OWN breakpoint, `@container (max-width:620px)` (where the card hint also stops being printed), instead
of sharing the runs table's 820 px one: two surfaces, two content widths.

No query could have fixed what this pass started from. The badge on a line of its own and an action
group free to push its row out of the card are LAYOUT facts, and the panel's `@container` change only
made them visible in a pane where the wide rules had never been answered before.

## Every row is measured against the card it lives in

`tests/shot.cjs` walks every element inside every card and fails when one crosses the card's left or
right edge — the card's own `overflow` would cut it silently — and it measures each `.wa-job` row: the
state badge must OVERLAP the name's line box by at least half its own height, and it reports whether
the actions sit beside the name or under it. Overlap, not top delta: the badge is centred against a
taller text line, so comparing tops is off by a few pixels while overlap asks the question the design
actually asks. Both measurements have their own negative control — `--inject=job-row-stack` (the badge
back on its own line) and `--inject=job-acts-too-wide` (an action group wider than its card) must each
exit 1.

`tests/render_check.mjs` locks the SHAPE in jsdom (the badge is a sibling of the name inside
`.wa-job-line`, never a direct child of the text column), so the structure cannot regress in a pass
that never renders a pixel, and `tests/audit_static.py` requires the name line and its breakpoint to
exist with `tests/canary_audit.py` proving both rules fire. `--scroll=bottom` captures the bottom of
the panel, which is where the jobs card lives in a narrow pane.

## Type has a floor, and the headings are not the quietest text

Nothing in the suite measured a font size, so the smallest AND faintest text on the panel was its own
headings: the card titles and the table labels come from the kit's `PanelSectionLabel`, whose base
style is `text-[0.6rem]` (9.6 px) at 50 % of the tertiary ink — 2.25:1 on the card ground, filed by the
contrast gate under "quiet", which is reported and not gated. The panel now overrides the label it
uses: `.wa-sec-title` at 11.5 px, weight 600, `--ui-text-secondary` (about 6:1), with the card title one
step up at 12 px; its own `as written` label went from 9.5 px to 11 px; and the status, delivery and
count chips moved off the kit's `xs` step (9.6 px, meant for icon-corner counts) onto the kit's default
step (10.4 px). That is the floor. Because the titles now ink secondary, the contrast gate classifies
them as reading text and holds them to 4.5:1 like everything else — 65 gated text nodes where there
were 55, and nothing left in the panel under 10.4 px.

The measurement locks both: `tests/shot.cjs` fails on any text node under 10.4 px and on any card title
or table label under 11.5 px (`--inject=tiny-type` puts a title back at 9 px and must exit 1), while
`tests/audit_static.py` refuses a `font-size` under 11 px (12 px since 2.3.6, TYPE table included) in the panel's own stylesheet and any badge
back on the `xs` step, with `tests/canary_audit.py` proving both fire. `tests/kit-stub.mjs` had to
carry the kit's full badge scale first: with only `xs` in the stub, a badge without a `size` prop
rendered at the inherited size and the harness flattered the panel by 2.6 px.

## Counts and ids read as sentences

`12 pages` and `102 folder(s) scanned` made the reader choose the number, which is the machine's
grammar, not the UI's: the bundle now carries both forms (`12 pages` · `1 page`), and a test fails on
any `(s)` left on screen. The install row printed `3/4` for its script list — it says `3 of 4` now and
names what is missing in a tooltip. The job row printed a bare hex fragment beside the schedule
(`0 * * * * · aabb6a4c`), which reads as noise until it is labelled: it is `0 * * * * · id aabb6a4c`
now. `filter candidates`, a lower-case placeholder among sentence-case labels, is `Filter candidates`;
the deleted-job chip is `Deleted job` like its `Completed` / `Failed` siblings; and the two sentences
that had grown into riddles were rewritten — `Create uses the schedule the wiki config carries; the new
id is stored with the panel.` became `Creates the missing job with the schedule the config already
carries.`, and the copy/mirror warning no longer asks `(a copy/mirror?)` mid-sentence.

## A chip is a label

`verified` survived three passes because no rule looked at the CASE of a string. The panel printed a
lower-case chip on the same screen as the kit's `Completed` / `Failed` chips, so it read as a different
kind of thing — and it was the root's whole verification state. The status words are Capitalised now:
`Verified`, `Not verified`, `Live`, `Paused`, `Registered`, `Not registered`, and the verification line
reads `Verified · 419 pages · id auto-id`. Prose stays in sentence case — `no job id`, `the entries that
keep the watched folder current`, `job paused` are sentences, and the bundle keeps them that way.

Two locks, because the case of a string is exactly the kind of thing that drifts: `tests/shot.cjs`
fails when a kit badge of three words or fewer starts lower case (a longer badge is a note, not a chip,
so `the script watchdog.py is missing from the automation folder` is left alone — that is the honest
line between a chip and a sentence), and `tests/audit_static.py` names the status keys
(`ok`, `invalid`, `registered`, `notRegistered`, `jobLiveState`, `jobPausedState`, `verified`) and
requires each to start with a capital, with `tests/canary_audit.py` proving it fires.
`--inject=lower-chip` puts `verified` back on the chip and must exit 1.

## The pane can be 352 px wide

Measured at the host's minimum (a 352 px pane, so a 254 px card) the panel had EIGHT elements sticking
out of their cards, and `.wa-card{overflow:hidden}` clipped every one of them: a table head cell 73 px
past the edge, a delivery chip 20 px, the missing-script chip 60 px. A card is not a scroll container,
so at that width the panel lost information outright — an element that overflows and cannot be
scrolled to, which is what a user reports as a design fault.

The width sweep stopped at 660 px, and that is why three passes never saw it: the host allows 352. Two
fixes — a chip may wrap (`min-width:0;max-width:100%;white-space:normal;overflow-wrap:anywhere`,
because a chip carrying a whole sentence is not a short label), and the runs table steps down a column
and then stacks instead of clipping; the runs card's range label gives way to the segmented control
beside it, which says the same thing, rather than truncating to `Runs sh…`.

The lock sits in `shot.cjs` twice over. Every width from 352 to 1240 must leave ZERO elements outside
their card, and every box whose TEXT is wider than the box itself must declare an ellipsis: `TEXT:` in
the output, where `.wa-clip` is the one exemption (a deliberate truncation with a Tip is not a loss).
A clamped box with `nowrap` text loses its tail in silence — `getBoundingClientRect` reports the box,
which fits, while the text does not. `--inject=no-narrow-runs` switches the two narrow blocks off and
must go RED (7 violations at 352 px); `--inject=chip-nowrap` removes the wrap rule and must too.

## Motion

The plugin ships no animation and no transition of its own, so under `prefers-reduced-motion` there
is nothing left to suppress: the busy spinner is the kit `Button`'s `loading` state and the first-read
spinner is the kit `Loader`, and the app's single blanket `prefers-reduced-motion` rule already
covers both. The old local `@keyframes`/`.wa-spin` block is gone.

## Reference basis

The 1.3.0 pass dresses the (already kit-migrated) panel in two entries of the local, READ-ONLY
design-token library, pinned at `8147538b4226ae41e2487a9179e3bcc1f68e8554`. Nothing inside that tree
was edited (it is upstream; the pin and the update procedure live in `reference/README.md`):

* `reference/awesome-design-md/design-md/supabase/DESIGN.md`
* `reference/awesome-design-md/design-md/mintlify/DESIGN.md`

Both files are largely MARKETING analysis — hero bands, sky/mesh gradients, 64–96px section rhythm,
testimonial oranges, logo walls, pricing tiers. What a dense in-app panel can take from them is the
small set of product-surface values, and the density argument is the reference's own: supabase prices
a card's internal padding at 32px and a marketing section at 64–96px (`supabase/DESIGN.md:315`,
`:312-319`), while mintlify drops its DOCUMENTATION surfaces to `{spacing.xxl}` (32px) between
subsections (`mintlify/DESIGN.md:554`). A panel inside the app chrome is the documentation-dense end
of that scale, so the panel's rhythm lands on 2/4/8/12/16/24 and nothing sits at a marketing size.

### Taken (each row names the line that carries it)

| Value | Evidence | Where it lands |
|---|---|---|
| Spacing 2/4/8/12/16/24/32 | `supabase/DESIGN.md:117-125` — `spacing: xxs 2 · xs 4 · sm 8 · md 12 · lg 16 · xl 24 · xxl 32` | page gutter 24 (xl) · gap between cards 16 (lg) · card body 12/16 (md/lg) · row gaps 12 (md) · inline gaps 8 (sm) · chip/candidate gaps 4 (xs). The old 18/22/10/6px values are gone. The FIXED PIXEL LAYER is NOT rhythm and was left alone: card head 30 · run row 36 · column head 24 · candidate row 30 — that is the measured contract. |
| `code-block` behaviour: one mono language, one leading, one padding, copyable | `supabase/DESIGN.md:188-193` (`typography: {typography.code}`, `padding: 16px`), `:282` ("Code blocks use system mono (`ui-monospace`, with Menlo / Monaco / Consolas fallbacks)"), `:304` ("Mono for code") | ONE rule (`.wa-mono`: system mono · 11px · line-height 1.5) covers the root path, the candidate paths, the raw checker body and the run stamps/durations — `monoShapes` measures 1 in the visual gate. The kit's `PanelBlock` stays the block's chrome (surface, padding, radius are the host's); the panel adds only the code language. |
| copyable | the same ask names it; the mechanism is in mintlify — `copy-code-button` (`mintlify/DESIGN.md:397-402`) and `code-block-header` (`:343-348`) | The host's OWN `CopyButton` (`apps/desktop/src/sdk/index.ts:1671`), icon form, on the root path and beside the `as written` caption. Its own failure state (an X plus an error label) is why it was preferred over a hand-rolled clipboard call. |
| `pill-tag-soft` label language | `supabase/DESIGN.md:200-205` — soft surface, quiet text, `typography.micro`, padding 2px 8px | Passive metadata rides the host's soft chip: the candidate page count is the kit's `Badge variant="muted" size="xs"`. Loud chips keep their meaning (`success` / `warn` / `destructive` stay reserved for state). |
| `card-feature-light` surface hierarchy | `supabase/DESIGN.md:164-169` (card surface, 1px hairline) and `:260` ("Canvas Night Soft … slightly lifted dark for nested chrome") | page (`--ui-bg-sidebar`) → card (`--ui-bg-card` + 1px `--ui-stroke-tertiary`) → nested chrome: the card head band on the SOFTEST token (`--ui-bg-quinary`) → the host's code block inside the help card. Three levels, every one a theme variable. |
| `card-help` tone for a validation reason | `mintlify/DESIGN.md:228-232` and `:643` ("Need help?" cards: a heading, one line of why, a CTA), `:647` (a card is a heading + a description) | A message is now a bordered card on the card surface: a heading (`Why this was refused` · `Note` · `Result`), the ONE sentence reason, the raw wording under its `as written` caption, and — only for a refusal that carries the checker's own text — one action. |
| `button-ghost` for secondary actions | `mintlify/DESIGN.md:202-207` — transparent, quiet text, 8px 12px | pick · verify · scan · scan folder · cancel are `ghost`; the write keeps the filled `Button` (Save, and the confirmed "Yes, take it") as the one filled action in its row. |
| `button-icon-circular` | `mintlify/DESIGN.md:213-219` — 32px, `rounded.full`, 1px hairline, icon-only | Every icon button is the kit's `icon-sm` (32×32) with the kit's ring (`outline`) variant and an `aria-label`, in ONE shape: refresh · path copy · code copy. Measured: 3 × 32×32, radius `9999px`. |
| empty-state narrative | `mintlify/DESIGN.md:647` — a card carries a heading AND a supporting line in the quiet grey | Both `EmptyState`s carry a second line that says what to do about it ("clear the field to see the whole candidate list", "the three wiki jobs write a row here after their first run"). |

### Not taken

* Hex values, font families and radius VALUES: the panel keeps the host's theme variables and the
  kit's radii. Both reference files write their colors as literals (`#3ecf8e`, `#1c1c1c`, `#0a0a0a`);
  a runtime plugin may not.
* Marketing surfaces: hero bands and their gradients, section rhythm at 64–96px, the testimonial
  orange, logo walls, pricing tiers, the atmospheric depth ladder.
* Anything outside the kit: no hand-rolled control was introduced, and no second typeface.

### Decisions the reference does not cover (and why)

* **The circular icon shape is drawn by the panel** (`.wa-icon-btn{border-radius:9999px}`). The kit's
  icon sizes are square (`rounded-[4px]`); the reference names a circular icon button and the panel
  is asked for ONE icon-button form, so exactly that shape is applied — size, ring, hover and the
  rest come from the kit's `icon-sm` + `outline`. This is the one place the panel's own `<style>`
  block leaves pure layout.
* **The help card's action is gated on a refusal that carries the checker's own text.** The reference
  puts a CTA on every help card; here an action beside "Verified · 419 pages" would be noise, and
  beside a backend reason there is nothing to fix by re-picking. The card shows what the backend
  knows and nothing more.
* **The copy affordance stays icon-only**, although mintlify's own `copy-code-button` is a labelled
  caption button: a labelled copy in the code header would have been the SECOND icon-button form in
  the panel. One shape everywhere won.
* **The softest theme token stands in for the reference's nested-chrome value.** Supabase names the
  role ("slightly lifted dark for nested chrome") and a hex; the panel maps the ROLE onto
  `--ui-bg-quinary` and lets the theme decide the value.
* **Density.** The reference has no in-app spacing guidance; 16/24 (lg/xl) was chosen as the tightest
  step that still separates the three cards, and the card body sits at 12/16.
* **In the test harness**, the stub's `CopyButton` renders a placeholder glyph for the icon-only form
  (no icon set in jsdom) and exposes the payload it was handed as `data-copy`; the app draws its real
  Copy icon. Documented in `tests/README.md` so the preview cannot read as more than it is.

## Verification note

The destructive pair in the app's compiled stylesheet is `--dt-destructive` + `--dt-destructive-foreground`
(`#cf2d56` / `#fff`). `--dt-destructive` is declared ONCE and the `.dark` block does NOT override it
(only `--ui-red` moves: `#cf2d56` → `#e75e78`). That is the theme, and it is upstream — `app.asar` is
never edited here. What the panel owes is the right token for the ROLE, and that is what 1.3.1 fixed:

* **A destructive LABEL is ink.** `Failed` / `deleted job` are kit `Badge variant="destructive"`
  (`bg-destructive/10 text-destructive`), so their ink was `--dt-destructive` — the FILL of that pair
  used as reading ink: **3.48:1** on the tinted pill (3.72:1 if the oklab tint is not composited).
  They now carry `.wa-danger` and read in the alarm tone `--ui-red`: **5.25:1**, with the tone still on
  the surface (the kit keeps its destructive tint; `success`/`warn`/`destructive` stay reserved for
  state, as the reference pass decided).
* **A filled destructive WRITE is a surface.** The one destructive action the panel arms is the second
  step of the copy/mirror gate ("Yes, take it", after the backend refuses a same-id root). It is now
  `variant="destructive"` pinned to the pair at FULL alpha — `.wa-danger-fill` paints
  `background:var(--dt-destructive)` and `color:var(--dt-destructive-foreground)` — **5.04:1**
  (the kit's `dark:bg-destructive/60` scales that fill to 60% and is beaten by the panel rule; the
  gate asserts the fill IS `--dt-destructive`, so a lost override cannot pass silently). The naive
  fix — filling a chip with the tone and putting white on it — is **3.35:1** and is exactly what the
  negative control injects.
* **What did NOT change:** `.wa-bad` and its sibling `[data-tone="bad"]` already inked with
  `--ui-red` and stay at **5.6:1**; the filled *primary* action (the kit's `Save`, `--dt-primary`
  `#4a84fe` + `--dt-primary-foreground` `#fcfcfc`) stays at **3.40:1** — that pair is the APP's, the
  panel may not repaint the kit's primary action, and `render_check` pins `Save` as the filled
  `default` button. The gate therefore measures it, holds it to the 3:1 non-text/large-text floor and
  prints the number instead of pretending it passed AA.

`tests/shot.cjs` now carries the WCAG gate (real pixels, the app's own Electron): every text node in
the panel is measured — ink alpha-composited over the colours really painted under it, with the canvas
resolving `oklab()`/`oklch()` so no node is silently skipped (69 nodes, 0 unread) — and the classes the
PANEL inks are gated at AA: `danger-ink` (and its ink must BE `--ui-red`), `danger-fill` (fill
`--dt-destructive`, ink `--dt-destructive-foreground`), `bad-ink`, and every other `reading` node.
The host's faint ladder (secondary .74 / tertiary .54 / quaternary .36, the kit's own
`text-muted-foreground/50` and `/55`, 2.21–3.16:1) is printed and not gated: the theme and the kit own
it and the same numbers appear in every panel. The dump lands beside the PNG
(`panel-1240.contrast.json`). `--inject=wrong-token` swaps the two danger rules back to the wrong
token intents IN MEMORY and the gate must exit 1 — and it does: 3.35:1 for the filled destructive,
3.48:1 for the chips, 3.72:1 for the failure ink. The pre-fix panel source goes red the same way
(4 violations).

| measured on panel-1240.png (dark theme, 1224 px inner) | before | after |
|---|---|---|
| `Failed` / `deleted job` chip ink | `--dt-destructive` 3.48:1 (3.72:1 un-composited) | **`--ui-red` 5.25:1** |
| filled destructive write ("Yes, take it") | not destructive at all — the kit's filled primary, 3.40:1 | **`--dt-destructive` + white 5.04:1** |
| `.wa-bad` / `[data-tone="bad"]` ink (`3/4`, the refusal line) | `--ui-red` 5.6:1 | 5.6:1 (untouched) |
| lowest AA-gated node in the panel | — | **5.04:1** (need 4.5) |
| kit tinted badge (`Verified` · `SAME ID`) | `Failed` chip 3.48:1 | 10.74:1 · 11.26:1 |
| kit primary fill pair (`Save`) — floored at 3:1 | 3.40:1 | 3.40:1 (APP tokens, reported) |
| faint ladder (reported, never gated) | 2.21:1 | 2.21:1 |

## Why the dashboard code is shaped this way (moved out of the source)

Production files carry no comments; these reasons were written inline during the dashboard
redesign and live here instead.

- **Reschedule** (`saveSchedule`): the store validates and writes, then the panel shows what came back.
- **Delete** (`removeJob`) goes through the dialog: throwing keeps it open with the reason inline
  (the dialog's own contract).
- **Heartbeat strip** (`HeartbeatStrip`): one strip per job, a bar for each run the cron store still
  holds, tallest bar = slowest run. Green is a completed run, red a failed one, orange a run at twice
  that job's median - the outlier the table below cannot show. Read-only: everything comes from the
  `/runs` payload, whose runs arrive newest first, so the strip is reversed to read oldest -> newest.
- A job whose record is gone from the scheduler must not read as healthy just because its last runs
  succeeded: the table marks it "Deleted job" and the strip's dot agrees (`quiet`).
- Each bar's label is the kit's `Tip` (a native `title=` is unstyled and ~500 ms late, and the
  panel's own gate refuses it); the tooltip carries the reading the height stands for.
- Every KPI figure is read off a payload the panel already fetches - no number stands alone.
- The refresh button RE-READS both payloads. It is not decoration: every figure on the page derives
  from those two calls, so without it a stale figure could only be fixed by a reload.
- The heartbeat gauge sits directly above the run log: the one-figure summary first, then the detail
  it summarises. Both are full-width bands - the gauge carries a legend, the log a table.
- Backend `_forget_job`: drops the panel's own memory of a job it created. The recorded id is what
  the panel points the row at; keeping it after the job is gone makes the row print an id nothing in
  the store answers to.
- Backend `_jobs_view` row: `id` is the identity the STORE answers to, so a role with no job in the
  store reports none - the panel then says "no job id" instead of naming a job that is gone. What the
  panel still has on file stays visible separately as `mapped_id`, for diagnosing a stale mapping.
- Selftest reschedule check: the expression is validated first, then written, then read back.
- The unused bundle entry `wa.hbNone` was removed: the heartbeat strip renders nothing for a job
  with no runs (`return null`), so there is no "no run yet" line to label.

## Visual pass — the Fleet Routing language (2026-09-22)

The panel already followed the reference (caps caption, dot, 26 px figure with a pill, sub-line, bar).
Fixed on that pass:
- Plurals: the jobs pill read `1 orphans`; `wa.pOrphans` is now a function (`1 orphan` / `N orphans`).
- The Slowest-run card said `4 runs in the window` in the pill and `Heartbeat` as its sub-line; the pill
  is gone and the sub-line says `across N runs` (`wa.pAcross`).
- The unused `kpis` array in the overview (built, never rendered) was removed.
- KPI card radius 8 → 10 px, the same as Fleet Routing, Approvals and Fleet Status.

## Visual pass to 9 (2026-09-22)

The judge's 7.0/10 defects, fixed in look only (no key, no handler, no request changed):
- WIKI PROJECTS FOUND: the candidate path is left-aligned beside its chips (`.wa-cand` was a centred
  kit row button and the path a `flex:1` span, so it floated mid-row and the chips hung at the far
  right). The filter is a real field: the kit `SearchField` gets `containerClassName:
  'desktop-input-chrome wa-filter'` (the app's own input chrome, 220 px, 28 px tall, full opacity).
  The stray `/` was the preview stub's stand-in for the kit's search icon; the stub now draws a
  magnifier like the app does and passes `containerClassName` through (stub-only artifact).
- Header: `.g-head` is a 3-row grid (caps · title · subtitle) and the Root/Install/Jobs/Runs chips +
  refresh sit on the TITLE row (`grid-row:2`); under 560 px they drop to their own row.
- Setup row: the Install card used to end at ~430 px beside a 750 px Watched-root card. The row now
  has ONE fixed height (`grid-template-rows:500px`, 440 px under 900 px); the right column is Install +
  Heartbeat stacked (`.g-side`), the Watched-root body and the Heartbeat body scroll inside their
  cards (`.g-fill`, themed thin scrollbars). No card grows with its content.
- Buttons: one primary (`Save`, filled, last in the row) and ONE secondary shape (`outline`) for
  Choose folder… · Scan for candidates · Choose scan folder… · Verify · Cancel and the help-card
  action. The row reads left-to-right as acquire → inspect → commit.
- KPI sub-line is one line (`.g-kpi-sub`: nowrap + ellipsis, full text in a kit `Tip`); the card is
  `grid-template-rows:auto auto auto 1fr` with the bar `align-self:end`, so all four bars share a line.
- Also: the Scheduled jobs / Recent runs heads were one long `Title · sentence` string in title
  weight; the sentence is now a tertiary hint line under the title (same bundle keys). The heartbeat
  ring's centre was painted `--ui-bg-primary`, which read as a grey disc on the card; the ring is
  now a masked conic stroke with a transparent centre.

`Choose folder…` appears twice: the action row's button and the refusal help card's action. BOTH call
the same `pick` handler (the file picker → `/automation/derive`), so the labels are correctly the
same; the second one is the help card's contextual "what helps" action and `render_check.mjs` locks
that it reopens the picker. Removing it would change behaviour — kept.

Reported, NOT changed (behaviour): `Verified` beside a refusal is a render-state bug. `rootRow` prints
`shown` (the DRAFT path when one is typed/picked) but its badge reads `project.ok`, which belongs to
the SAVED root. After a refused Verify of a draft, the kv row shows the draft path + `Verified`
(about the saved root) while the help card says the draft was refused. A fix needs a decision (badge
the draft as `Not verified`/unknown until verified, or keep the saved path in the kv row) — user approval.

Gated: `check_visual_hierarchy` in `audit_static.py` (no ghost Button, one-line KPI sub-line, chips on
`grid-row:2`, px-fixed setup row, inner scroll on the fixed cards, filter field chrome), six canaries
(56 rules). `render_check.mjs` now asserts `outline` secondaries, exactly one filled primary in the
action row and that it ends the row (was: `ghost` secondaries).

## One job definition: the engine's jobs.json (1.10.0)

The panel used to carry `dashboard/job_catalogue.json`, a second copy of the engine's job list. Two
copies drifted apart: the engine gained a fourth job (Wiki Session Harvest, an agent job at
`30 21 * * *`) and the panel went on showing three. The owner's rule is one control panel over one
versioned engine, with the panel only a VIEW. So the panel now reads `<audit dir>/jobs.json` and keeps
no definition of its own. The audit fails if a catalogue file or a reader for one comes back.

* **Field mapping.** name · kind · launcher · impl come straight from `jobs.json`. The delivery target is
  the engine `settings.json` `deliver` (default `ntfy`), because the engine installer uses that value
  for every job. For a script job, the prompt the panel stores on Create is the engine `description`,
  which is the same text the installer stores.
* **Agent jobs are the engine's.** An agent job needs its prompt file (`prompt_file`) and its gate script
  wired in, and only `install.py` does that. The panel therefore refuses `create` for `kind: agent` and
  names `python install.py`. It refuses `remove` too: a job the panel cannot re-create should not be
  deleted from it either. Pause, resume and reschedule act on the stored job and stay available.
* **Role ids.** The engine `settings.json` `jobs` map now carries all four roles. `_role_map()` reads it
  and lays the panel's own state map over it, so the panel state still wins. A job the panel created
  keeps its recorded id, and the Session Harvest id (`5ceb0986beea`), which only the engine recorded,
  resolves. Before, only the panel state was read, so the fourth role could never be live here.
* **A missing definition is a failed read.** No `jobs.json` returns `ok: false` with the path, and the
  card shows the failure card. An empty job list would read as "no jobs".

## Candidates go through the engine script only (1.10.0)

The session harvest drafts wiki source candidates under `<audit dir>/inbox/<run>/candidates/<name>/`.
`wiki_candidates.py` is the only writer from that inbox into the wiki, and it holds the rules: the
house format check, the base-hash check for updates, and copying the evidence folders. The panel
therefore never reads the inbox or writes `raw/sources` itself. The three routes shell out to the
script with `sys.executable`, the way the backend already runs `wikiconfig.py`, and pass back its JSON
or its own text.

* **Approve is two-step.** An approve writes a source into the wiki, the app ingests it, and that
  costs model usage, so one click must not do it. The first call runs `approve --dry-run`. That checks
  everything the real approve checks without writing anything, and then arms the confirmation. A
  refusal at this step (format, missing evidence, a changed base) is shown before any dialog. Only a
  second call with `confirm` runs the real approve. The pattern is the same as Delete job.
* **Reject needs a reason.** The engine records it, so the harvest's hit rate can be measured later.
  The reason is passed as one `--reason=<text>` argument, so a reason that starts with `--` cannot be
  read as a flag.
* **The ref is validated before argv.** `<run>/<name>`, each part `[A-Za-z0-9_-]` and starting with a
  letter or digit. That excludes path traversal, a third segment, and a part that begins with `-` and
  would be read as an option.
* **The script's own words are kept.** On success and on a refusal, the script's stdout/stderr come
  back as `output`. The card shows the English sentence with the script's text beside it in the same
  `as written` block every other card uses.

## One Wiki panel: the Watchdog folded in as Health (2.0.0)

The owner's rule is one control panel over one versioned engine. Two panels over the same engine meant
two run views, two backends reading the same `executions.db`, and two sets of gates that drifted. The
Wiki Watchdog panel (`plugins/wiki-watchdog`) is therefore folded into this plugin as the **Health**
tab. Its folder is retired but kept: this plugin never edits or deletes it; the owner disables it once
2.0.0 is installed.

* **Tabs.** The page is the host kit's `Tabs`: `Health` first and default (it answers "is the wiki
  healthy?", the question asked most), `Automation` beside it. Each tab keeps its own root
  (`.pa-root` / `.wa-root`) that scrolls inside the tab body, so the two keep their own styles and
  their own gates.
* **Routes.** The Watchdog backend moved in under `/health/*` so it cannot collide with this plugin's
  own `/jobs`: `GET /watchdog` → `GET /health/watchdog`, `POST /watchdog/clear` →
  `POST /health/watchdog/clear`, `GET /jobs` → `GET /health/jobs`, `GET /jobs/run` →
  `GET /health/jobs/run`, `POST /runs/archive-clear` → `POST /health/runs/archive-clear`. The archive
  folder is unchanged (`<HERMES_HOME>/backups/wiki-watchdog/`), so archives written by the old panel
  and the new tab sit side by side.
* **A view only.** Both tabs call the engine (`~/.llmwiki-audit`): the watchdog's log and the job
  definitions in `jobs.json`. Neither copies the engine's logic nor writes a wiki file.

### Surviving Watchdog notes

The full history is in `plugins/wiki-watchdog/Docs/wiki-watchdog-notes.md`. These are the rules that
still bind the Health tab:

* **The checker's line is data.** The watchdog writes Turkish finding lines. The backend classifies
  each (`_WD_RULES` → `_WD_KINDS`) and hands the panel the kind, the values read out of the line and
  the VERBATIM line. The English sentence lives in the panel's `en` bundle behind `FINDING_MAP`; the
  raw line is printed beside it under "As written", never replaced. An unmatched line gets the neutral
  "Other finding" label and its raw text — no invented translation.
* **Archive, then clear.** The only write into the scheduler's store. The rows are archived to
  `<HERMES_HOME>/backups/wiki-watchdog/runs-<stamp>.json`, the file is read back and its ids must equal
  the ids read, and only then are those ids deleted in one transaction; a count mismatch rolls back.
  The panel sends the ids it is SHOWING (a filtered log clears only the filtered set), and the first
  press only arms the confirm step.
* **Freshness is measured, not parsed.** The ring is `(now - last_run_at) / (next_run_at -
  last_run_at)` from the scheduler's own instants; a job with no next run shows an empty ring and the
  reason. Nothing parses a cadence string.
* **Timeline density.** A lane with at least as many runs as the axis has cells (24) draws as density
  cells instead of overlapping bars; the lanes box scrolls.
* **Destructive pair.** `--dt-destructive` is a fill token only; reading text in that severity uses
  `--ui-red`. `shot_health.cjs` gates both classes at AA.
* **Loader trap.** The loader's import regex has no word boundary; the audit applies it verbatim to the
  raw source, so an identifier ending in `from` followed by a quote cannot sneak in.

### One run view (the dropped duplicate)

Before 2.0.0 the runs were shown twice: the Automation "Recent runs" table (five columns: job, status,
delivery, time, duration) and the Watchdog run log. The two disagreed on filters and ranges, and a fix
to one never reached the other. The run log is the complete one (filters, search, detail drawer with
the full body, archive-then-clear), so the Automation table is removed. The Automation runs card
keeps what only it shows — the per-job heartbeat — and an **Open the run log** button that switches
to Health. `audit_static.py`'s `check_single_run_view` refuses a second run table, and its canary
proves the rule fires.

### Retired finding: page not listed in index.md

The engine's `not_indexed` check ("page not listed in index.md") was removed from the engine. LLM Wiki
0.6.12 writes only the 200 most recently updated pages into `index.md`, so on any wiki larger than that
the check could never come back clean — a permanent finding is noise. Findability is measured by the
isolated-page check (a page with no graph edge). Old log lines of that kind are still parsed, and
shown as a retired check with a neutral tone and "nothing to do", so history does not turn into
"Other finding".

### Evidence checks 8 and 9

The engine gained two checks, and the Health tab recognises both:

* **Check 8, evidence store (`evidence_store`, bad).** A stored evidence file no longer matches its
  sha256, a quoted passage is gone, or a decision names a pinned version with no evidence. Action:
  `evidence_capture.py --verify` in the engine folder.
* **Check 9, evidence staleness (`evidence_stale`, warn).** The installed LLM Wiki or Hermes version
  changed and N evidence passages no longer occur in it. Action: `evidence_capture.py --recheck`, then
  review the decisions that rest on them.

Both follow the same contract as every other kind: the count is read from the checker's line, the
English sentence comes from the bundle, and the raw line stays beside it.

## Schedules a person can read (2.1.0)

The user's words: "saat sıklık falan bu şekilde çok basit" — a cron field and five preset chips is not
a way to say *when*. The card now reads and writes schedules in hours, days and frequencies; cron is
still what the store holds, and it stays visible.

* **One translation, both directions.** `cronToSched(expr)` reads a five-field cron into a model
  `{mode, every, minute, time, days, dom, raw}`; `schedToCron(model)` writes it back; `schedHuman(t,
  expr)` goes through `cronToSched`, so the sentence on the row and the mode the editor opens in can
  never disagree. A mode only claims an expression it can write back: `*/N` with N in 5/10/15/30
  (Minutes), `M * * * *` (Hourly), `M H * * *` (Daily), `M H * * <days>` with digit days, lists and
  ranges (Weekly — `7` is read as Sunday, ranges of three or more are written back as `1-5`), `M H D * *`
  (Monthly). Everything else — named days (`MON`), month fields, steps like `*/7`, two hours
  (`0 9,17 * * *`), day-of-month *and* day-of-week, a natural phrase the store also accepts (`every
  2h`) — opens in **Custom** as written.
* **Opening never rewrites.** The editor remembers the model it opened with; while the model still
  equals it, the expression shown and offered is the ORIGINAL string, not the re-serialised one
  (`0 9 * * 7` stays `7`, `00 09 * * *` stays as written), and Save stays disabled. A save is always a
  choice the user made, and the render check proves the round trip for every live expression plus each
  mode's shape without a single `/jobs/act` call.
* **The backend is still the authority.** The editor never decides validity. It asks `POST
  /jobs/preview` (debounced 250 ms) for the next three runs, and Save still goes through `/jobs/act
  'schedule'`, which runs `cron.parse_schedule` before `cron.update_job`. A refusal shows twice by
  design: in the preview line ("the store would refuse this schedule" + the store's wording) before
  the click, and as the existing "Why this was refused" note after it, with the editor left open and
  the row unmoved.
* **The preview only reads.** It is a POST so the expression travels in a body, and nothing else:
  `_jobs_preview` calls `parse_schedule` and then `compute_next_run(parsed, anchor)` three times, each
  anchored on the previous answer. That is the SAME function the scheduler uses to set `next_run_at`
  (it anchors cron to the configured IANA zone's wall clock and handles the DST fold), so the preview
  cannot drift from what fires. No dependency was added — croniter is already the core's. The audit's
  `check_preview_read_only` refuses a store write, a job-map write or a scheduler nudge inside it, and
  the selftest compares the store's bytes before and after.
* **Time zone.** Cron times are the store's wall clock: `hermes_time.get_timezone_name()` (the profile's
  configured zone) or the server-local zone. `_store_zone()` reports `{name, offset}` on `/jobs` and on
  every preview, and the editor prints it once: "Times are in the store's time zone: Europe/Istanbul
  (UTC+03:00)". Run times on the row are printed in the offset the store wrote them in, so a job at
  09:00 reads 09:00 however the machine running the panel is set.
* **Run state is the store's, normalised once.** `_run_state(rec)` passes `next_run_at`, `last_run_at`
  and `last_status` through, and `_dispatch_flag(rec)` reads `last_dispatch.kind`, which the core stamps
  on every recurring dispatch (`_classify_dispatch_lateness`): `on_time` (within 300 s) → no flag,
  `late` (past 300 s but inside the catch-up grace, half the period clamped to 2 min–2 h) → **Late**,
  `catch_up` (past the grace: the slot was missed and the job ran once to catch up) → **Missed**.
  Anything malformed yields no flag rather than a guess. The badge's `Tip` spells it out: due time,
  start time, lateness.
* **Relative times** (`in 3 h`, `14 min ago`) are computed at render; the 60 s poll refreshes them.
  `today` / `tomorrow` / `yesterday` / `Thu 01.10` are decided in the stamp's own offset.

### The editor, laid out

A frequency `SegmentedControl` (the kit's, folded into rows by `repeat(auto-fit, minmax(5.5rem, 1fr))`
so six segments fit a 352 px pane — `--inject=sched-no-wrap` proves a fixed six-column row sticks out
of the card), then one labelled row per field: the minute steps (a second `SegmentedControl`), a
minute number, an `Input type=time`, seven day toggles (kit `Button`s with `aria-pressed`; the pressed
one takes an accent tint and ring from theme tokens), a day-of-month number with a short-month note
past 28, or the raw cron. The preview box sits under the fields (sentence · mono cron · next runs · zone,
`aria-live`), then Cancel (outline) and **Save schedule**: `--ui-text-primary` ink on a `--ui-accent`
tint with an accent ring. That closes the 2.0.0 red gate: the old `.wa-sched-save` was `--ui-accent`
INK on the drawer at 4.22:1. The kit's filled primary was tried first. It passes the gate only because
the app's `--dt-primary` pair (3.4:1) is floored at 3:1 there, so it would have moved the number under
a looser rule instead of fixing it. The tinted form is a `reading` node held to AA. The drift line (store vs config) now sits directly under the row, above the editor,
so the editor never separates a job from its own warning.

### The retired Task Scheduler

The engine stopped registering a Windows Task Scheduler task (its `scheduler_task` setting was removed
and `run_watchdog.cmd` no longer pops up): the Hermes cron store is the only scheduler. The Install
card's `Task Scheduler` row, the scripts KPI's `Task Scheduler: …` sub-line, the backend's `schtasks`
query (`_scheduler_registered`) and `run_watchdog.cmd` in the scripts-present list are gone; the KPI
sub-line now names what is missing. The selftest fails if `/automation` reports any of them again.

## Update ready, and a check that finds problems is not a failure (2.5.11)

`/engine/status` returns both the shipped revision (`selected_revision`) and the active recorded install
(`current_revision`). When the engine is installed and the two differ, the map raises the `engine` alert
with tone `ask` ("Engine update ready") and opens Settings at the install section. The panel only
compares the two ids; it never applies an update. The owner still presses `Preview update` and confirms
that exact plan, so the two-step install contract stays. An unreadable draft whose error is the 2.5.9
refusal `New source target already exists` points at that update, because the newer engine fixes it.

Watch Dog's `main()` returns 1 whenever it has findings, so the cron store records a check that found
problems as `failed`. History reads the findings first: a `watchdog` run with findings is `found N
problems` (warn), whatever its stored status. Other failed runs show their reason from the run's own
`body`; the store's status is never rewritten, and the Full technical log keeps the raw `Failed` badge.

### A harvest is judged by the engine's record, not the cron store (2.5.13)

The harvest job is an agent job: the cron store marks it `completed` when the model session ends,
whether or not the engine's run was finished. From 17 to 18 October 2026 four such runs were
`completed` while no conversation was saved. `GET /harvest/status` therefore also asks the engine
for `--last-run` (newest host-bound run: execution id, created, committed, outcome status, per-agent
report). The newest harvest job run is a failure when its execution id names an engine run that is
not committed, or when it started after the newest engine run was created (no run was made for it).
An engine without `--last-run` answers `last_run_supported: false` and the panel keeps the cron
store's word; any other bad answer is a failed read with the engine's own error.

A line's state follows what that engine does. Engine `464668b` skips a tool that is not installed
and keeps the cursor of a tool it could not read, so a missing folder is drawn and not alarmed, and
`UNREADABLE` in the last run's report makes the line `unread` with a `warn` alert. An older engine
stops every line while a folder is missing, so then the alert is `bad`, the Harvest station says it
stopped, and the action opens the engine update.

## Evidence to fetch: a finding's copy is downloaded on the owner's press (2.7.0)

The harvest job runs without network access on purpose: its input is conversation text, and a model
that could fetch could also send that text away. Before engine `9e7972d` a finding about an outside
source therefore always fell into `missing_evidence`. A draft may now carry `evidence_requests` in
`candidate.json` (a GitHub file at a commit or a public https page, plus verbatim passages), and the
review shows each address, claim and passage before anything is downloaded. `Fetch evidence` posts
`action: fetch_evidence` with the displayed `review_digest` to `/candidates/act`, which runs the
engine's `fetch-evidence`; the engine stores a copy only when every passage is in the file, and only
in the candidate's own `evidence/` folder. Approve is replaced by Fetch while `pending_evidence` is
not empty, and the engine refuses an approval then too. The fetched copy changes the review digest,
so the owner sees the stored copy before approving it. The commit id is shortened in a narrow pane
only (`@container (max-width:640px)`), because a 40-character id wrapped across five lines at 390 px.

## Approval refusal shown in the review (2.7.1)

Engine `855bf0e` reports `approval_refusal` in `show --json`: the text of the approval's own dry-run
refusal, or null. The review shows it under "This draft cannot be approved as written." and locks
Approve; a pending evidence request is shown as Fetch instead, because its refusal is only "not
fetched yet". The same source rules (`content_refusals`: a pinned version with `Evidence: none`, a
finding without evidence) refuse a draft at submission, so the harvest corrects it in its own run.
Five drafts of 2026-10-20 had passed review and were refused only at Approve; the rule was not
relaxed, its timing was moved forward.

## Installed agents for the setup check (2.7.2)

Engine `85688e4` reads `drift.agents` from `settings.json`: the agent setups installed on the machine. The
component and skill targets keep naming every agent; a tool missing from the list is dropped from them,
so its absent components raise no finding. The key is optional and its absence keeps the old
expectation (all four agents). It exists because the owner removed Claude Code and the Codex CLI on
2026-10-16 and the check reported eight missing items for them every day.

## A stale update draft is re-derived, not refused (2.9.0)

Until 2.8.2 an update draft kept only the hash of the page it was written from. When another draft for
the same page was approved first, the hash no longer matched and the draft could only be rejected. On
2026-10-22 one such draft ("wiki-watchdog repository deleted") was a full copy of the page from before
the metro-panel draft was approved; applied as written it would have deleted about 30 approved lines.
The approval was refused correctly, but the change it carried was lost until a later harvest.

The draft adapter now keeps `base.md`, the exact page the draft was written from. `list` (the panel's
queue) replays the draft's own changes against `base.md` onto the page as it is now
(`engine/source_merge.py`: units are decisions, list items, table rows, paragraphs; where both sides
changed the same units the merge runs again on their lines). The result is a new candidate beside the
original with `derived_from`; the original stays unapprovable and is hidden while its derivation waits.
A derived draft passes the same format, content and citation checks as any draft, plus one more: every
line of the current page the draft did not change survives, and every added line is one the draft
added. It has its own review digest, so an approval given to the original never covers it. A later
change re-derives from the original again. When both sides changed the same lines, or `base.md` is
missing (drafts from before 2.9.0; the before-image an applied operation kept is used when its hash
matches), nothing is derived and the queue shows why. The merge is code only; no model is called.

Replayed on copies of the real files: the 2026-10-22 draft re-derived onto today's page with no
conflict, the 30 metro lines kept, 19 changed lines all from the draft itself.

## Why a harvest run stopped, and what it cost (2.10.0)

Until 2.9.0 the plugin's turn-end hook returned silently in every case that kept a run open: the turn
failed, the final answer was not the JSON report, or a captured input was not read completely. The
panel could only say "The engine did not finish this run". Between 2026-10-17 and 10-22 nine runs
stayed open this way ($2.37 together); five of them read almost nothing (under 800 output tokens,
about $0.05 each), and nothing said why.

The plugin now records two events per bound run in `inbox/<run>/attempt.json` through the engine
(`wiki_session_harvest.py --record-attempt`): `start` (the drafting session that owns the run) and
`end` (the turn's flags, its exit reason, and the stop reason when the run cannot be finished:
`turn_failed`, `no_final_report`, `unread_input`, `outcome_refused` with the engine's own refusal).
A recording failure never changes the run. `--last-run` and `--runs` report the stop reason, or
`no_end_event` when the session ended without reporting back (its session end reason named), and
`not_recorded` for runs from before this record. Usage and cost are read read-only from the owning
profile's `state.db` session row, so the figure is Hermes' own estimate, not one made here; a missing
store is reported as an error, not guessed. The panel shows the recorded reason in place of the
generic sentence and the cost in Harvest's "Last run" row.

Measured on this machine from the session store (Hermes' estimates, 34 harvest runs that matched one
cron session, 2026-10-15 to 10-24): $24.48 in total; a nightly run that finished cost $0.19–$1.76,
about $0.24 per conversation on 2026-10-24.

## Hermes' own geometry (2.11.2)

Hermes draws its cards, menus and inputs with corners scaled by one value, `--radius-scalar` (0.2 in
the shipped stylesheet): `--radius-md` is 2 px, `--radius-lg` 2.4 px, `--radius-xl` 3.2 px. The panel
had ten literal radii of its own, from 2 to 14 px, so its cards read as a web page pasted into the app.
Every corner now names one of those tokens (cards and boxes `--radius-xl`, buttons and inner boxes
`--radius-lg`, stripes and bars `--radius-md`); the only literals left are 0, 1 px, a circle (50%)
and a pill (99 px and up), which the host also uses. `tests/audit_static.py`
(`check_host_geometry`) refuses any other literal, in CSS or in an inline `borderRadius`, and two
canaries in `tests/canary_audit.py` put a 14 px card corner and an 8 px inline corner back.

Hover and selection use the host's own row states (`--ui-row-hover-background`,
`--ui-row-active-background`, which the theme mixes from its accent), not tints mixed by the panel,
and font sizes sit on the host's steps (12, 13, 14, 16, 18, 20, 24 px).

## Version

2.10.0 — a harvest run that stops says why (recorded by the plugin, shown in the panel) and its drafting cost is reported from Hermes' session store
2.9.0 — a stale update draft is re-derived onto the page as it is now and offered for a fresh approval, instead of only being refused
2.7.2 — the setup check expects only the agents listed in `drift.agents`
2.7.1 — the approval's own refusal is shown in the review with Approve locked; the harvest meets the same check at submission
2.7.0 — Evidence to fetch: a draft names the public copy a finding needs, the owner fetches it in the review (passages verified, stored in the draft), Approve waits for every copy
2.5.13 — the harvest's own outcome (`--last-run`) decides a failed harvest · a tool that is not installed is drawn, not alarmed · a line that could not be read gets its own state and alert · missing-folder copy follows the engine in use
2.5.11 — engine update ready (revision comparison, never applied by the panel) · short engine id with the full one on hover · an unreadable draft explained on its card · Previous / Next draft · fourteen more Watch Dog finding kinds in English · a check that found problems is not a failure in History, other failed runs show their reason · branch lines name their own folder and several missing lines together · Harvest lists only the lines it reads
2.1.0 — schedules a person can read: the row leads with the schedule as a sentence (cron beside it in mono), the next run, the last run with its result and a Late/Missed flag from the store's dispatch stamp; a visual editor (Minutes · Hourly · Daily · Weekly · Monthly · Custom) with a read-only `POST /jobs/preview` of the next three runs from the core's own `compute_next_run`; unrepresentable cron kept in Custom, never rewritten; `Save schedule` on theme tokens at AA (the 4.22:1 contrast failure is gone); the retired Task Scheduler removed from the tab and the backend
2.0.0 — one Wiki panel: the Wiki Watchdog panel folded in as the Health tab (first, default) beside Automation; its backend under `/health/*`; the Automation runs table dropped for the single Health run log (the runs card keeps the heartbeat and opens Health); `not_indexed` retired; evidence checks 8 and 9 recognised
1.10.0 — the job list is the engine's `jobs.json` (four roles, the agent job marked and never created or deleted here; `dashboard/job_catalogue.json` is gone), role ids resolve from the engine settings under the panel state, and a Candidates card lists the harvest's candidates and approves (two-step, dry run first) or rejects (with a reason) them only through `wiki_candidates.py`
1.6.0 — the panel could not be scrolled (the user's red box: the job card cut its last job row and the
RECENT RUNS card sat under the window bottom with no way to reach it). `.wa-root` was `display:grid`
with `height:100%` inside a pane of FIXED height, and a grid compresses its `auto` rows to fit a
definite container: every card overflowed its own row, `.wa-card{overflow:hidden}` clipped the content
inside it, and the root's scrollHeight ended up equal to its clientHeight — there was nothing to
overflow, so `overflow:auto` never produced a scrollbar and the bottom card was unreachable. Measured
in the app's Electron: 6 elements sat below a 760 px pane and 60 below a 220 px one, and the first card
clipped 281 px of its own content at 760 px and 421 px at 220 px. One declaration on the root —
`grid-auto-rows:max-content` — makes each row its content's height: sh 1220 vs cl 758/618/558/428/328/
218, 0 defects and 0 unreachable at every pane height, and 0 at a 352 px pane (content 1475 px) and a
660 px pane (1342 px) as well. The promise has two gates: `tests/scroll_check.cjs` (new — the layout
layer jsdom cannot be: it forces pane heights and widths and fails on clipped / spill / clipX /
cutBelow content, with the pre-fix source as its negative control: exit 1, 3 defects, 6/14/31
unreachable elements) and the `scroll flow` rule in `tests/audit_static.py`, whose canary removes the
declaration and proves the rule fires (49 rules now)
1.5.4 — the pane's real minimum is 352 px and the panel lost content there: eight elements ran past
their cards and the card clipped them (a table head cell 73 px, the missing-script chip 60 px, a
delivery chip 20 px). A chip may now WRAP and the runs table steps down (Delivery dropped at 470 px,
the row stacked at 360 px, which brings the Duration back); `shot.cjs` sweeps 300 → 1240 px and gates
both an element outside its card and a box whose text is wider than the box with no ellipsis, with
`--inject=no-narrow-runs` and `--inject=chip-nowrap` as the negative controls
1.5.3 — a status chip is a LABEL: `Verified` · `Live` · `Paused` · `Registered` (they were printed in sentence case beside the kit's own `Completed`/`Failed` chips), gated both in the browser (a badge of <= 3 words must start with a capital) and statically (the status keys are named), with `--inject=lower-chip` as the negative control
1.5.2 — a type floor with teeth: card titles and table labels 11.5 px on secondary ink (they were the smallest and faintest text on the panel), the panel's own labels ≥ 11 px, status/count chips on the kit's default step (10.4 px), and the gate now fails on any text under 10.4 px or any title under 11.5 px; counts are plurals instead of `folder(s)`, the install row says `3 of 4` and names what is missing, job ids are labelled, and the copy was rewritten where it read as a riddle
1.5.1 — the job row is a name line with the badge on it (`.wa-job-line`) instead of three stacked lines, its actions wrap and answer their own `@container (max-width:620px)` breakpoint, and both are measured: every element is checked against the card it lives in, the badge's line is checked by vertical overlap, and `--inject=job-row-stack` / `--inject=job-acts-too-wide` are the negative controls
1.5.0 — pane-width layout through `@container` (the narrow rules answer the pane, not the window; the visual gate measures a 560 px frame in a wide window and its `media-query` negative control fails on the regression), one note-card treatment for job results (the undefined `wa-msgbox` is gone), a failed read keeps the error the backend returned (no card spins forever on a dead read), the candidate chip names its unit, and the static preview serves `/jobs` so the job surface is inside every measurement
1.4.0 — the three wiki jobs are managed from the panel (Create · Pause · Resume · two-step Delete against the app's own cron store, the canonical catalogue in `dashboard/job_catalogue.json`, the target check that flags an orphan and recommends a pause, one role mapping shared by the card and the runs table); the dead `/automation` job counter left the payload
1.3.1 — destructive readability: the destructive label inked with the alarm tone `--ui-red` (5.25:1) and the armed filled destructive write on the `--dt-destructive` token pair (5.04:1); both classes gated in `tests/shot.cjs`'s WCAG contrast gate with negative-control proof
1.3.0 — reference pass: supabase code/entry surfaces, mintlify help-card tone
1.2.0 — the panel is built from the host UI kit (Button · Badge · Input · SearchField · SegmentedControl · PanelSectionLabel · PanelMeta · PanelBlock · EmptyState · ErrorState · Loader · Tip), zero native `title=`, and a canary suite of 39 rules.
1.1.0 — single `en` bundle resolved from the app language (no picker, no `lang` state, no `?lang=`), comment-free production files with the rationale in this file, per-rule canary suite, external checker text mapped to English with the raw line kept.

