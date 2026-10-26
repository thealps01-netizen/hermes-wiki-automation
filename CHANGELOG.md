# Changelog

Notable changes to the Wiki Automation panel. The version is carried in three places — `plugin.yaml`,
`dashboard/manifest.json` and the top heading below — and the static audit fails when they disagree.

## 2.11.0

Engine `280c5db`. A new nightly job, Wiki Harvest, reads conversations one at a time.

### Added
* **Wiki Harvest (installed paused).** A script-only job at 21:30 that reads every conversation
  changed since its last run one by one (Hermes except `tool` sessions, Codex, Claude Code,
  Antigravity), keeps what each one said in a ledger, and merges the new decisions, findings and
  articles into at most one draft per wiki page. Drafts appear in Review as before; nothing reaches
  the wiki without the owner's approval. A night has a cost cap (10 USD) and a time limit (45 min);
  what a night does not reach waits for the next. A page that already has a draft in Review is not
  drafted again until that draft is decided. The night's report is kept in `harvest-nights/<night>/`.
  The job is created paused: switch it on and pause Wiki Session Harvest in the panel. Wiki Session
  Harvest stays installed, because the approval system is bound to that agent job.

### Fixed
* **The harvest cost note** said about $0.24 per conversation; the packed harvest's cost is mostly
  fixed per run (about $0.85 a night plus $0.003 per conversation), so the per-conversation figure
  only reflected how few conversations that night held.

## 2.10.0

Engine `d03321b`. A harvest run that stops says why, and its cost is reported.

### Fixed
* **"The engine did not finish this run" without a reason.** When the drafting turn failed, its final
  answer was not the required report, or a conversation was not read completely, the run stayed open
  and nothing said which. The plugin now records each run's drafting session and how its turn ended;
  the panel shows that reason ("2 of 7 captured inputs were not read completely…", "The drafting turn
  failed…", or the engine's own refusal) instead of the generic sentence.

### Added
* **What a harvest run cost.** Harvest's "Last run" row shows Hermes' own cost estimate for the
  drafting session, read from the profile's session store. `wiki_session_harvest.py --runs` lists
  every run with its stop reason and cost.

## 2.9.0

Engine `37ab0df`. A stale update draft is re-derived instead of only refused.

### Changed
* **A draft written before another approval is rewritten onto the page as it is now.** When two
  drafts updated the same source page and one was approved first, the other could only be rejected,
  and its change was lost until a later harvest. A draft now keeps the page it was written from; the
  review queue replays only that draft's own changes onto the current page and offers the result as a
  new draft ("Rewritten onto the page as it is now, from an older draft"), which needs its own
  approval. Every line the draft did not change is checked to survive. When both changed the same
  lines, the queue says so and nothing is rewritten. No model is called.

## 2.8.2

Engine `d8bb46f`. The agent-setup check no longer expects Serena.

### Fixed
* **The setup check reported Serena as missing after it was uninstalled.** Serena was removed from
  every agent on this machine, and the check still expected it in Hermes, so Watch Dog showed
  "bileşen eksik: serena -> hermes" every day. Serena is no longer an expected component, and the
  `--deep` probe no longer looks for it; honey and the LLM Wiki MCP server are still checked.

## 2.8.1

Engine `b6b4382`.

### Fixed
* **Commands in engine reports point at the engine.** Watch Dog, Auto-Commit and Ingest Watch printed
  commands such as `python <data folder>/wiki_audit.py`, but the data folder holds state only; the
  scripts live in the installed engine release. The commands now name the release folder, and a test
  refuses any printed command that names a script in the data folder.

## 2.8.0

Engine `28a7a9b`: engine `85688e4`, now kept in this repository, with its README updated for that home
and the drift check's built-in author removed. Installing and updating it works as before
(**Preview update**, then confirm the plan).

### Changed
* **The engine ships inside the panel.** Its source is the `engine/` folder of this repository instead of
  a zip built from a separate repository, so one version line names the panel and its engine together.
  `engine-release.json` pins the folder's content digest; `tools/engine_release.py` writes it and CI
  checks it. The zip under `engine-assets/` is gone.
* **The agent-setup check has no built-in author.** `drift.own_author` in `settings.json` names the
  owner whose skill copies are checked; without it no copy is skipped for its author.

## 2.7.2

Engine `85688e4`. The agent-setup check no longer expects tools you have uninstalled.

### Fixed
* **The setup check reported Codex and Claude Code after they were removed.** It expected honey, the
  LLM Wiki MCP server, Serena and two skills in every agent, so an uninstalled tool showed as eight
  "missing" items every day, with nothing that could clear them. `settings.json` may now list the
  installed agents in `drift.agents` (for example `["hermes", "antigravity"]`); a tool left out is
  not expected, the listed ones are still checked, and without the key every agent is expected as
  before.

## 2.7.1

Engine `855bf0e`. A draft that cannot be approved says so before you press Approve.

### Fixed
* **Approve refused a draft that the review showed as fine.** The wiki refuses a decision that
  carries a version number (for example "Released as 4.4.0") with `Evidence: none`, because nothing
  could re-check that claim after an upgrade. That check ran only when you pressed Approve, so five
  harvest drafts looked approvable and were then refused. The review now runs the approval's own
  checks and shows the reason with Approve locked. The harvest meets the same check when it submits a
  draft and has to correct the draft first, and its instructions now say that a release number of
  your own project is history to leave out of the decision. The rule itself is unchanged.

## 2.7.0

Engine `9e7972d`. A finding about an outside source can now reach the wiki with its evidence, fetched
only when you ask for it.

### Added
* **Evidence to fetch, in Your review.** The nightly harvest has no internet access, so a finding
  about a tool, paper or repository used to be left out for lack of a stored copy. A draft can now
  name the public copy it needs (a GitHub file at a commit, or a public https page) together with
  the exact passages that copy must contain. The review shows each address, the claim it backs and
  the passages. Nothing is downloaded until you press **Fetch evidence**; a copy is kept only when
  every passage is in the downloaded file, and it lands in the draft, not in the wiki. Approve
  appears once every requested copy is fetched, so the stored copy is reviewed before it is written.
  Local files, plain http, IP addresses, private hosts and addresses with credentials are refused.

## 2.6.1

Engine `45d7e1c`. The wiki's daily auto-commit no longer leaves the installed engine looking modified.

### Fixed
* **"Installed code release is dirty" after the morning auto-commit.** Auto-Commit runs the engine's
  own pre-commit hook on the wiki, and that hook's Python wrote a bytecode cache
  (`__pycache__/wikiconfig.*.pyc`) into the installed engine folder. The panel checks that folder
  file by file against its installation record, so the Wiki line showed "The timetable could not be
  read" with a 409 refusal, although no engine file had changed. The hook now runs without writing
  bytecode. The check itself is unchanged: a cache file in the engine folder is code Python may load.

## 2.6.0

A wording slip in the drafting model's final reply no longer leaves a finished harvest uncommitted.

### Fixed
* **The harvest is finished by what was submitted, not by what the model says it submitted.** The
  drafting job ends with a JSON reply, and the run was completed only when that reply had exactly the
  expected fields and listed exactly the candidates on disk. On 19 Oct the model misspelled one field
  and listed a candidate the engine had refused, so a run whose every conversation had been read and
  whose four drafts had been written stayed uncommitted, and its conversations were queued again. The
  candidate list now comes from the submissions the engine accepted; the reply only has to be a JSON
  object, its `owner_report` is the morning report and its other fields are ignored except the missing
  evidence list. Every conversation must still be read in full before a run completes.

## 2.5.13

Engine `464668b`. A tool that is not installed no longer stops the Session Harvest, and the panel
says when a harvest was not finished even though its job reported success.

### Fixed
* **Harvest runs without Codex or Claude Code.** Since engine `22a0f71` the collector treated an
  enabled agent whose folder is missing as a failed run, and the drafting step refused every such
  run, so on a PC without one of those tools nothing was collected or drafted from any agent. The
  engine now skips an agent that is not installed and collects the others. An agent whose history
  exists but cannot be read keeps its cursor, so its conversations wait for a later run while the
  others are completed.
* **A harvest the engine did not finish is a failed harvest.** The cron store recorded those runs as
  completed. The panel now reads the engine's own record of its newest run (`--last-run`, read-only,
  through `GET /harvest/status`): when the newest harvest job run has no completed engine run, the
  Harvest station and the alert say no drafts were written and that the conversations wait.
* **Missing-folder copy matches the engine.** `The other lines still run` was shown while the engine
  stopped every line. With this engine a missing folder is drawn on its line and needs no alert; a
  line whose history could not be read is drawn in orange with its own alert. With an older engine
  the alert says it stops every line and points to the engine update.

Engine `c35059b`. Nothing in the repository or the shipped engine names one person's machine.

### Changed
* **The engine ships no personal data.** The dated installation report that carried one PC's user
  name, home folder, wiki folder and project id is gone from the archive. The engine's
  personal-defaults test now scans every shipped file, documents and tests included, for a concrete
  user home path or the author's wiki name; `wiki_ingest_watch.py` no longer quotes real project ids.
* **Design history trimmed to what the contract uses.** The rejected design directions under
  `Docs/directions/` (mock-ups, their build scripts and third-party reference screenshots) are no
  longer in the repository; `Docs/directions/metro-2.5.0/` stays because `Docs/metro-contract.md`
  binds to it. In those approved drafts, real wiki page names and folder paths are blurred, and the
  draft builder uses example names.
* **Example data.** The review-desk fixture uses an example draft (`Team glossary`) instead of a real
  wiki page; the README screenshot is regenerated from it.

## 2.5.11

Engine unchanged (`c6fd419`). Fixes from a live check of the panel.

### Fixed
* **An engine update is announced.** When the installed engine is older than the one this plugin
  ships, the map says `Engine update ready` (both short ids) and opens Settings at the install
  section. Nothing changes until the owner previews the update and confirms that exact plan.
* **Settings shows the engine id short.** The installed block prints the first 7 characters, with
  the full id on hover; the plan preview keeps every value exact. The existing-jobs note now says
  plainly that the new engine is proven by its next runs in History.
* **An unreadable draft says so on its card.** The error is shown under the title instead of only
  inside the closed disclosure, with no kind chip; Approve stays off, Reject and Later work. When an
  engine update is ready and the error is `New source target already exists`, the card says the
  update fixes it.
* **Previous / Next draft.** Two buttons beside `k of N` move between drafts without writing.
* **Fourteen more Watch Dog findings in English.** Control files, the project file, a re-registered
  folder, stale index entries, unsplit ingest output, MCP access off, uncommitted changes, a crashed
  setup check, unread or compressed Codex sessions and old engine copies no longer show as "Other
  finding"; the raw line stays beside the English.
* **A check that found problems is not a failure.** History shows the Daily check as `found N
  problems` even though its run is stored as failed (Watch Dog exits 1 when it finds something).
  Other failed runs show their reason, with the full text behind `Show the error`.
* **Branch lines name their own folder.** The detail says `<Name> folder`; a missing folder reads
  `On — nothing collected while the folder is missing` and drops the "found folder" note. Several
  missing lines are named together in one alert, and Harvest's "What it does" lists only the lines
  it can read.

## 2.5.10

Engine `c6fd419`. The engine still carried the original author's own setup, so another installation
reported problems it did not have: a missing `onedrive` and `github` mirror every day, a comparison
of that author's agent skills and plugins, and a morning report always written in Turkish.

### Changed
* **Mirrors are the wiki's own git remotes.** Auto-Commit and Watch Dog check every remote of the
  wiki repository, the same ones its post-commit hook pushes to. `settings.json` → `mirrors` can
  name only some of them, and `[]` turns the mirror check off. A wiki without remotes has no mirror
  finding.
* **The agent-setup check is opt-in.** Watch Dog runs `drift_check.py` only when `settings.json`
  declares `drift.expect`; that check describes one installation's own skills and plugins.
* **The morning report follows the owner's language**, the one the owner writes in the harvested
  conversations, instead of always Turkish. The update refreshes the drafting job's prompt; its
  schedule, on/off state and history stay as they are.
* No job ids of another installation are built into the defaults, and printed lines say
  "Wiki watchdog", "wiki auto-commit" and "wiki ingest watch" without the author's wiki name.

## 2.5.9

Engine `d01faac`. The nightly harvest can send a corrected copy of a new source as a second draft.
After the first draft was approved, opening the second one showed only "New source target already
exists", and the wiki kept the first, less accurate text.

### Fixed
* **A corrected resubmission becomes a correction.** When a newer draft writes the same file that an
  earlier approved draft added, and nobody has changed that file since, Review shows it with a
  **Correction** badge and the changes against the text you approved. Approving it replaces that file.
  An older draft, an identical one, or a file that has been edited since is not applied; Review says
  why and that the draft should be rejected.
* **Two waiting drafts for one file.** The older one now says that a newer draft is waiting, so the
  newer one is approved and the older one rejected.

## 2.5.8

Engine `54b14f7`. The daily wiki auto-commit had refused every run since 11 Oct and still reported
success, so wiki changes piled up uncommitted for five days.

### Fixed
* **The daily auto-commit commits again.** The engine installs its own pre-commit hook in the wiki
  (link-form clean-up) and the auto-commit then refused to run next to any pre-commit hook. It now
  recognizes the engine's own hook byte for byte, runs it before the commit is assembled, and commits
  without running hooks a second time. A hook that is not the engine's, or an edited copy of it, is
  still refused as before.
* **Uncommitted wiki changes are a Watch Dog finding.** When wiki changes have waited longer than
  26 hours, Watch Dog reports how many and quotes the auto-commit's last output. This catches every
  reason the commit can stop, not only this one; the auto-commit's own messages reach only a local file.

## 2.5.7

Engine `728f74b` (unchanged). After turning on owner approval, Review kept saying "Restart Hermes to
finish" and showed a red "could not read interrupted approvals" error, even after the app was restarted.

### Fixed
* **Owner approval finishes from the panel.** Approvals need the background service (the gateway that
  runs scheduled tasks) to restart, and restarting the app does not restart it. The card now names the
  background service and has a **Restart background service** button, confirmed with a second click. It
  uses the app's own gateway restart, waits until approval is ready and then says so; if approval is
  still not ready after two minutes it says that instead.
* **No red error while approval is still starting.** Review no longer asks for interrupted approvals
  before the background service has loaded owner approval; that request could only fail.

## 2.5.6

Engine `728f74b`. Updating from 2.5.4 to 2.5.5 stopped at preview with "Legacy or customized drafting job
requires a separate reviewed migration", although nobody had edited the job.

### Fixed
* **Updates no longer stop on the engine's own job settings.** Two settings the engine writes into its own
  tasks went stale on their own: the drafting instructions, when a release ships new ones, and the Python a
  script task runs with, when Hermes moves to another Python. Either one made every later update refuse. An
  update now replaces such a setting when it is exactly what an earlier installation wrote, and keeps the
  task's schedule, on/off state and history. A setting changed by hand is still refused, as before. The
  update preview names each task whose setting will be replaced.
* **Watch Dog on Python before 3.14.** The check for the zstd decoder crashed instead of reporting it missing.

## 2.5.5

Engine `0b27bc5`. Wiki sources lost their research results because the harvest kept decisions only.

### Changed
* **Sources keep verified findings.** The session harvest now drafts verified findings — facts about an
  outside tool, product, paper, price or technique, or our own measurement — next to decisions, in an optional
  `## Findings` section. A finding whose evidence copy is not retained is listed as missing evidence instead
  of entering the source.

### Added
* **Findings need evidence.** Approving a candidate is refused when a new or changed finding has no retained
  evidence (our own measurement may say `none (measurement: …)`). A finding that names a pinned version needs
  a pinned copy, the same rule decisions already had.

## 2.5.4

Engine `04d8b67`. The session harvest skipped most Codex conversations, and nothing warned when an agent ran an older copy of the engine.

### Fixed
* **Codex conversations missing from the harvest.** Codex stores older conversations compressed
  (`.jsonl.zst`). The harvest read only uncompressed files, so 314 of 318 Codex session files were skipped
  without any error. It now reads both forms, and a conversation stored in both forms is read once. On a
  Python without the zstd decoder (before 3.14) the harvest stops with an error instead of skipping.

### Added
* **Watch Dog: harvest reader coverage.** Reports Codex session files the harvest does not read, so a new
  file form shows up in the Health tab instead of becoming a silent gap.
* **Watch Dog: older engine copies.** Reports scripts in the automation data folder that differ from the
  installed engine. Such a copy can lack a gate the installed engine enforces: an older `wiki_candidates.py`
  there applied a candidate that the installed engine refuses to apply from the command line.

## 2.5.3

Engine `6436a9f`. A Watch Dog run could lock the panel, and the Watch Dog turned red after every Hermes skill edit.

### Fixed
* **Panel locked after a Watch Dog run.** The Watch Dog started its agent-setup check in a way that let Python
  write a cache file (`__pycache__/wikiconfig.cpython-314.pyc`) into the installed engine folder. The panel
  checks that folder file by file, so it then refused to work with "Installed code release is dirty or lacks
  verified file identity". Every Python process the engine starts now runs without writing cache files, so the
  folder stays exactly as installed.
* **Red Watch Dog after editing a skill.** The owner retired the comparison of one skill's copies across Hermes,
  Codex, Claude and Antigravity; those copies are no longer kept in step. A skill that points to a missing
  reference file is still reported.

### Tests
* Engine: `tests/test_release_stays_clean.py`, `tests/test_drift_check.py`.

## 2.5.2

Engine `bebabf7`. The daily watchdog had stopped reporting two things correctly after Hermes started running
engine scripts with its bundled Python 3.14.

### Fixed
* **Wednesday crash.** The page-count check and the alerts history took the date from the Windows console; on a
  Turkish system "Çar" could not be decoded, so every Wednesday the check crashed and that day's findings were
  missing from History. The time now comes from Python, in the same `DD.MM.YYYY HH:MM:SS` shape.
* **"drift_check ayrıntı vermedi".** The agent-setup check could not read Hermes' `config.yaml` without PyYAML and
  died before its verdict. It now reads the file through Hermes' own Python and lists the real differences; if the
  checker itself crashes, the finding says so with its error line.

### Tests
* Engine: `tests/test_watchdog.py`, `tests/test_drift_check.py`.

## 2.5.1

2.5.0 showed the reused 2.3.x components first in three details, so History, Settings and the Harvest station
did not look like their approved drafts, and `Ask Hermes to fix these` did nothing on the full-page panel. 2.5.1
makes every screen follow its draft (`Docs/directions/metro-2.5.0/m-01.png` … `m-16.png`); every 2.3.x surface is
still one click away.

### Fixed
* **Ask Hermes to fix these** opens a new chat and writes the request into its box. It never sends it; the text
  can only land in that new chat. The full-page panel has no chat box of its own, so 2.5.0 found nowhere to write.
* **History (m-13)** is a plain list: time, job, what it did, outcome, and a note when the morning jobs ran late.
  `Show older runs` widens it to 7 days, then the whole history; `Full technical log` opens the former run history.
* **Settings (m-14)** is three rows: wiki folder, automation files, working folder. `Change wiki folder`,
  `Manage timetable` and the files value open the former cards; a card opens by itself while it holds a fix.
* **Harvest (m-03)** has two buttons, `Change time` and `Pause`, instead of the job row.
* **Review (m-07)** reads `draft k of n`; **Approve (m-08)** asks in a centred dialog with the path and the
  model-credit warning, still in two steps; the engine's own words sit behind `Show what the engine reported`.
* **Alerts (m-06, m-09, m-10, m-12)** use the drafts' words; with an unreadable timetable no line is drawn and the
  raw error sits behind `Show the error`. The bar steps aside while the detail it opens is open.

### Tests
* The render gate checks each detail for its draft's texts and buttons; the Ask Hermes check asserts the new chat.

## 2.5.0

The panel is one screen: a line map. The four views (Nexus, Chronicle, Folio, Health) asked the owner to learn
where each answer lived and had no single answer to "does anything need me?". The map reads like a subway line:
four conversation sources run into Harvest, then Your review, then the Wiki. One bar under it names the most
urgent thing that needs the owner, or says the whole line is in good service. Every surface of 2.3.12 is still
reachable: click a station, a line, History or Settings and its detail opens under the map.

### Changed
* **One Metro view replaces the four tabs.** Stations and lines carry their state in words, never in codes.
  The alert bar follows one priority order: a failed read, the engine, a failed harvest, a broken job, drafts
  waiting, wiki problems, a paused job, a running harvest, good service. It never says good service while a read
  failed, and a failed read keeps the backend's own error.
* **Review is one draft at a time** with Approve, Reject and Later. Approve keeps its two steps and its warning;
  Reject still needs a reason. The change and its evidence stay one click away.
* **Wiki problems in plain English**, with "Ask Hermes to fix these", which writes the request into the chat box
  and never sends it.
* History holds the run history; Settings holds the wiki folder, the engine, the scheduled jobs and the
  installation files.

### Removed
* The tab strip, the Nexus map and inspector, the heartbeat strip, the lower review queue and per-view titles.

### Tests
* New `render_metro.mjs` locks every contract state, the alert priority, one detail at a time and the composer
  insert. The static audit fails if the old composition returns. Every new rule has a canary.
* The CI job limit is 45 minutes. Windows was cancelled at 20 minutes mid-canary.

## 2.3.12

Session Harvest can update existing wiki pages again. Its drafting instructions say an unchanged decision keeps its evidence citations, but the drafting step was refused any evidence id, and 37 of the 38 live sources cite evidence. Every update was therefore impossible: on 2026-10-12 a new decision for the Hermes Desktop Panels source was refused twice ("Evidence citations, including retained evidence, are not available through this adapter").

### Fixed
* **An update may keep the evidence its page already cites** (engine `0bad565`). Only ids the exact current page cites (its base hash must match the live file) and that have a retained record are admitted. New evidence, evidence on a new page, a stale base and unrecorded ids are still refused before anything is written; review and approval checks are unchanged.

### Tests
* Engine `test_draft_adapter`: an update keeping its page's evidence is admitted and reviewable; new evidence, a new page, a stale base, mismatched citations and an unrecorded id are refused with nothing written.

## 2.3.11

Drafting no longer stalls on a backlog. With approvals off for days, the conversations waiting for Session Harvest grew to 532,585 characters; one run handed all of them to the drafting step, its context was compacted while reading, and it correctly refused to draft from partial reads ("The run context was compacted twice while reading"). Because the run did not complete, the next one would have been larger still, so no candidate could arrive again.

### Fixed
* **Each run reads at most 250,000 characters** (engine `62d1a44`; `harvest.max_run_chars` in the engine settings changes it). Conversations are taken oldest first and whole; the rest wait for the next run. A single conversation larger than the budget is read in time order across runs. Nothing is skipped or read twice: the engine records which conversations a run already read. On 2026-10-12's backlog this gives three runs of 243k, 214k and 187k characters, none splitting a conversation.

### Tests
* Engine `test_harvest_lifecycle`: a backlog is packed by whole conversation within the budget; an oversized conversation is read across runs with every message exactly once and later conversations after it.

## 2.3.10

Approvals work again, and the review queue can be emptied. On every installation Review answered "No explicit owner binding exists for this profile (HTTP 403)" and no candidate could be approved: approval needs a bound owner, and no installer, panel or engine step ever wrote one. The drafting job stayed paused for the same reason ("owner activation required"), so no new candidates arrived. Separately, three queued candidates could not even be opened ("Actual source citations must match evidence_ids exactly").

### Fixed
* **Turn on owner approval from Review:** while no owner is bound, Review shows what turning it on changes (who approves: this computer's Hermes session in this profile, or the signed-in account; which job drafts; one Hermes restart) and asks twice. The panel derives the owner from the verified host session, never from the request; cron and service callers are refused. The engine writes the binding, pins the loaded guard code and creates the decision authority; the panel turns on the drafting and runtime-check switches. After a plugin update the card says so and asks once more. Interrupted approvals are read only once an owner is bound, so the 403 banner is gone.
* **Placeholder notes are not citations:** the engine (now `6a36472`) read dates and hyphenated words inside `Evidence: none (...)` notes as evidence ids, also when the note wrapped onto a second line. A complete `none (...)` note is now ignored; an unbalanced one still fails review.
* **An unreviewable candidate can be rejected:** when the engine refuses a candidate's review (stale base, citation mismatch, older metadata), Reject stays available. The backend re-checks that the review is still refused before rejecting without a digest; approval stays off.

### Tests
* Engine: `test_owner_decisions` (activation binding, refusals, re-activation keeps the authority), `test_evidence_identifier_policy` (wrapped, mixed and nested notes; unbalanced notes fail closed). Panel: `test_owner_broker` (setup route: session-derived owner, plan digest, refusal leaves host settings untouched, cron refused; unreviewable rejection), `test_runtime_probe` (setup through the real route against the real engine and host plugin loader, then a confirmed approval), `render_check.mjs` (setup card, two-step confirm, refusal, unreviewable reject).

## 2.3.9

The four views (Nexus, Chronicle, Folio, Health) open and draw the same way. The owner saw them as fed "from different places": one view slid in slowly, another appeared at once, and some row lines stopped short while others ran the whole box. Measured on 2.3.7: Nexus played 17 entry animations over 1.6 s, Health 35 over 1.5 s (ring fill, bar growth, counting figures), Folio 3, Chronicle none; in-card lines ran edge to edge in the jobs list but stopped 14-24 px short in the review queue, run detail, Folio panes and Nexus node cards, in two different colours.

### Changed
* **One entry motion:** every view's blocks rise in the same way (480 ms, 60 ms apart, all settled by 0.8 s); Chronicle now enters like the rest. The map's arriving nodes and drawing wires, Health's ring fill, growing bars and counting figures are gone; the loops that report a live state (the flow comet, the live core's orbit, the busy spinner) stay. Reduced motion switches all of it off.
* **One surface:** the four views share one set of surface tokens and one section card (same border, 8 px radius, surface and top highlight). Health's Run flow and Activity by job are cards like the rest; the side panes in Folio and Chronicle share one pane colour.
* **One line rule:** every divider inside a card or pane runs the full width of that box, in one colour, with the text keeping its place. This includes the findings list under a run's Technical details. The tab bar's line runs the full window width like the header's.

### Tests
* `tests/audit_static.py` reads all three stylesheets for hand-timed motion and for reduced-motion coverage (it used to read only the Chronicle/Health one); `tests/canary_audit.py` proves both rules fire in the Nexus and shell stylesheets. `render_check.mjs` asserts the shared entry exists and that no view plays its own entry choreography; `render_health.mjs` asserts Health no longer animates its bars, ring or figures.

## 2.3.8

### Fixed
* **Folio's notice band sits 24 px above its card, like every other gap:** it sat 36 px above it. The cause was an empty screen-reader announcement box (`aria-live`) that still took a grid row; the same box added 8 px under the Nexus engine and schedule cards. An empty announcement box now leaves the layout and keeps its place for assistive technology; it returns the moment a message fills it.
* **`hermes plugins doctor` is clean:** `plugin.yaml` now lists the three tools and six hooks the plugin registers (doctor warned about all nine on every check). `tests/test_manifest_registrations.py` runs Hermes' own doctor and fails on any finding.

### Tests
* **Nexus visual gate (`shot.cjs`) green again:** it measured 900 ms after load while the map's entry brings cards and wires in for about 1.6 s, so it reported the review card hidden and every wire disconnected. It now waits for finite animations to finish, and reads a wire's dashes in the path's own units: a source that feeds Harvest is solid, one that does not is dashed (the panel's rule since the wires started showing which sources feed Harvest). Negative controls (`nx-wire-detached`, `nx-lower-hidden`) still fail it.
* **Health visual gate (`shot_health.cjs`) green again:** it still expected the five sections and 112 px KPI cards from before 2.3.4's lean panel. It now measures the three sections, the 86 px KPI floor and a run flow of 12 to 31 days; its checks for the removed timeline and distribution (including the `cover` layout canary) are gone. The clip, spill, journal, container and both contrast canaries still fail it.
* `tests/audit_static.py` and `tests/canary_audit.py` hold the empty-announcement-box rule.

## 2.3.7

Nexus speaks one visual language. The sections below the automation map were flat lists on the bare page while the map above them was a framed card; the owner compared the two and found the jobs list unfinished beside the map.

### Changed
* **Selected node, Ready for review, Scheduled jobs, Recent runs and Project settings are cards like the map:** the same surface, border, radius and 18 px inner gutter, a 52 px head with the title on the left and its count or control on the right. Project settings opens and closes from its card head.
* **Job rows carry framed glyphs** like the map's nodes and the review queue.
* **The jobs count sits in the card head** instead of a badge on its own line between two hairlines.

### Fixed
* **Paused jobs were counted as live:** with the harvest job paused the panel said "4 of 4 jobs live". It now says "3 of 4 jobs live · 1 paused".
* The map's column labels (Conversations · Harvest · Review) now sit exactly over their cards; they were 8–10 px off.
* A long job name no longer pushes the harvest card's "Paused" state onto a second line.
* "last failure" in Recent runs starts with a capital letter.

## 2.3.6

Polish on the 2.3.5 layout: the four views (Nexus, Chronicle, Folio, Health), their sections and their order are unchanged. Every view was checked at a real pane size (1040×760 and 560×760) and scrolled to its last line.

### Fixed
* **Health:** in a pane shorter than the page, the Freshness card and the KPI strip were squeezed to a 23 px sliver with their content hidden, and the page did not scroll. Rows now take their content's height and the page scrolls.
* **Page bottoms:** Chronicle ended with its card on the pane's bottom edge and Health had no space under its legend; every view now ends with 28–32 px of space under its last line.
* **Chronicle:** the run list was a fixed 520 px box even with five runs, leaving a large empty area; it is now as tall as its runs and scrolls past 520 px.
* **One left edge:** Nexus and Folio started at 28 px, Chronicle and Health at 24 px, the Folio recovery banner 14 px further in and Recent runs 12 px further in. All content now sits on one 28 px gutter (20 px in a pane of 470 px or less).
* **Buttons that looked like text:** outline buttons (Manage jobs, Open the run log, Project, folder pickers) and the job actions (Pause, Schedule, Delete, Create in installation) now have a visible border; Delete is marked red.
* **Readability:** the smallest text is 12 px (it was 10.5–11 px in 50+ places, including the host's badges, raw-output boxes, detail lists and segmented controls). Detail labels (Project root, Settings file…) measured 2.35:1 contrast; every view now measures at least 4.88:1 on the owner's theme (WCAG AA is 4.5:1).
* **Sentences shown as shouting labels:** two hints in Project settings were set in upper-case label style; they are plain sentences now. Stand-alone status lines start with a capital letter.
* **Repetition:** Folio's queue footer repeated the document's "Draft · approval required"; the open job repeated its own name; Recent runs carried a "Heartbeat" caption under its own heading. Each now appears once.
* **Job rows:** the schedule column moved per row with the width of the state text; it is now one fixed column. "no job id" reads "No job ID".
* Recent runs explains its bars correctly: "One bar per recorded run; a taller bar ran longer."

### Tests
* The type floor in `tests/audit_static.py` is 12 px and covers the TYPE table; `tests/canary_audit.py` proves both rules fire.

## 2.3.5

### Fixed
* **Job buttons work again:** Pause, Resume, Schedule and Delete had been switched off since 2.3.0 because a panel write could race the scheduler. Each change now verifies that the job belongs to this engine installation, takes Hermes' own cron store lock, re-reads the job and refuses with "the job changed since this page read it" unless the job still matches what the page showed, then calls Hermes' own pause/resume/update/remove and reads the result back. Session Harvest can be turned on from the panel.
* **Create goes through the installation:** Create in installation opens Project settings at the engine card; its reviewed plan creates the missing job paused, with the provenance the panel checks. The panel never writes a new native job itself.
* Delete (script jobs only, after the confirmation) also removes the job from the engine and panel mappings, so the list stays readable and offers Create again.

## 2.3.4

### Fixed
* **Engine takeover no longer refused on a Hermes home with a differently-cased folder:** "Preview update" checked every file name in the engine archive against the Hermes home folder itself, so a home holding `Docs` refused the archive's `docs/` with "Release path case collision" (seen four times on a real install). Archive names are now checked for safe spelling only; the real path checks still run where the files are written (`state/wiki-automation/releases/`). Verified on a copy of a real home: the old module refuses, the fixed one plans and installs (three jobs adopted in place, Session Harvest paused).

### Changed
* **Less on screen, each surface one job:** Health keeps freshness, the KPI figures, the run flow and activity by job. The run timeline and job distribution cards are gone (activity by job now carries each job's run count, so the same counts are no longer drawn three times). KPI cards lose their caption line (the explanation stays in the card's tooltip), the title bar loses its subtitle, the legend keeps the colour key only, and section metadata is one short phrase ("last 12 days").
* **Run flow covers the scope:** the chart spans every day from the oldest run in scope to today (12 days minimum, 31 maximum), so its total equals the runs shown ("50 runs · peak 29.09"); before, runs older than 12 days were counted on the KPI card but missing from the chart.
* **Compact journal:** a Chronicle run is one 52 px row (64 px narrow) with a one-line preview; the explanation sentence under the journal is gone.
* **Nexus and Folio:** subtitles, the map caption, the inspector's description, the queue hint and the empty "interrupted approvals" box are gone. Folio's proposal title is 18 px across the document column (it was 28 px held to 17 characters, five lines tall), spacing is tighter and the decision column is wider.
* **Failed reads in one line:** a refused or failed read is a single line with the backend's own reason; the raw text and its copy button sit behind "Details" instead of filling a card.
* **Engine takeover is visible:** while the existing engine is not yet taken over (including a previewed but uninstalled plan), an installation was interrupted, or no engine is installed, Nexus shows one banner with an Open button that unfolds Project settings and then scrolls to the engine card. The banner keeps its state while the same project's status is re-read, and disappears once the takeover is installed.
* **Activity counts say what they count:** counts are marked `≈` when the server capped the trend read, and the card reads "· all runs" while a filter narrows the rest of Health (activity is not filtered).
* **Deleted-job runs stay one row:** the "Historical job" marker sits on the job-name line instead of a third line that overflowed the compact row.

## 2.3.3

### Fixed
* **Run timeline:** runs reached the grouping newest first, so every run of a job collapsed into one mark at the right edge ("10:36:21 ×13") stamped with the newest clock. Marks are now one per run (runs closer than 2.6 % of the axis still share one), in time order; only the newest mark in a lane shows its clock (the newest run's, also when runs share the mark), the rest on hover and to assistive technology, over a hairline instead of a filled band.
* **Activity by job:** a fixed box showed two of four jobs and hid the rest behind a scroll; four rows now fit. A window longer than a day names the day on its axis and in every cell tooltip ("28.09 08:26"), and the window reads in days ("last 12 days · 13 h buckets") instead of hours ("last 299h").
* **Window translucency:** the panel painted its own opaque field, so Hermes' Glass setting never reached it. The panel field now wears the app's page surface token, which Hermes makes transparent under Glass and tints with the Tint slider; raised cards keep their fills as the app's own pages do. The preview gains `--glass`.
* **Refused reads in plain words:** a transport error is shown as the backend's own sentence ("No explicit owner binding exists for this profile (HTTP 403)") instead of "Error invoking remote method 'hermes:api': Error: 403: {\"detail\": …}". Validation refusals list their messages.

## 2.3.2

### Added
* **Motion that carries a fact:** on the map, wires draw in and show which sources feed Session Harvest (lit = enabled and folder found, dotted = not feeding). Selecting a source sends one pulse along its wire. The collector orbits and its wires flow only while the newest Harvest run is active, less than three hours old and confirmed by a readable job record; the state then says Running and the caption "Harvest run in progress". Sections, KPIs, the success ring and the run-flow bars animate in on Health. Every animation is off when the system asks for reduced motion.

### Fixed
* **Run output matching:** Hermes names a run's output file when it saves it, at the end of the run. Each run now takes the file saved nearest its finish time, so long runs keep their own output, back-to-back runs no longer swap bodies (even when delivery outlasts the gap) and a run still in progress shows no body. On a real 50-run history every run now has its own output (27 had none before).
* **Silent and Findings counts:** output files without a separator (empty output, script failure) are read without their header, so empty runs count as Silent and failure output stays visible. Agent jobs show their reply (read through Hermes' character frame) or, after a failed run, their error, never their prompt; their bullet lists are no longer counted as watchdog findings. The real history now reads Silent 14 and Findings 13 (was 26 and 2).
* **Activity, all time:** the "all" window draws activity across the whole history instead of "0 of 4 jobs ran".
* **Refused reads are not facts:** when the job or run store refuses to answer (an engine installed before the panel), the map shows the failure with its reason instead of "no schedule in the config", "not run yet" or "no run recorded yet".
* **Boundary copy:** "No automatic publishing" became "Harvest drafts wait for your approval". The Auto-Commit job does commit the wiki, and its Git hook pushes to the configured mirrors.
* **First load:** the engine card no longer announces "Project or app context changed" before anything was previewed.
* **Run timeline:** the right-hand time names the newest run and sits at its position on the axis.

## 2.3.1

### Fixed
* **Pre-panel engine upgrade:** an engine installed by the earlier `install.py` no longer locks the panel with "Active installation has no matching verified release record". Status reports it as an existing, not-yet-verified installation, and **Preview update** prepares an exact plan. Jobs that still have the exact shape `install.py` created are adopted in place with their IDs, schedules and history. Script jobs keep their on/off state; only ownership, working folder and interpreter are recorded, and they run the new launcher from their next scheduled run. The earlier Session Harvest job gets the new drafting prompt and tools and is paused until the owner turns it on. A customized job is refused at preview, before anything is written.
* **Stale preview:** if a job or setting changes between preview and confirm, the engine refuses before journaling anything and the panel records the plan as stale instead of demanding recovery; preview again.
* **Engine pin:** the bundled engine is committed revision `a51c0b310f3c35d2491ec25870cbe92373a6ebc6`, verified against its committed Git blobs.

## 2.3.0

### Added
* **App-managed engine installation:** one digest-verified offline engine bundle, an exact-plan preview and separate confirmation in Project settings. Code releases and mutable data remain separate. New jobs start paused; installation does not grant content-owner authority.
* **Approved interrupted-install recovery:** the same verified administrator can review the original plan in a fresh application session and explicitly confirm a single-use, 300-second recovery review. Legacy, unapproved and changed-release plans are refused without adoption or migration.

### Changed
* **Native job management is read-only:** Create, Pause, Resume, Schedule and Delete are unavailable until the host supports atomic expected-record ownership validation. The backend refuses these actions before native store loading; verified role listing and read-only schedule preview remain.
* **Engine pin:** the bundled engine is committed revision `ec4f8b1ce3eb1d282caa45a3ed6bc5d3fb17dee7`, verified against its committed Git blobs. No remote release or live installation is implied by this local package.

### Fixed
* Captured owner files, secondary recaptures and staged/unstaged Git selections survive workflow interruption without silent overwrite or shared-index reset.
* Citation identifiers beginning with `none` remain valid; pinned-version decisions cannot hide a missing-evidence field behind later unrelated prose.
* Installation and recovery bind strict native task snapshots, script interpreters, paths and current-state digests before writes; unsupported SQLite WAL inspection refuses without sidecar creation or conversion.
* Retained UI callbacks cannot mutate a replacement SDK scope or discard a newer review. Ordinary refresh preserves unchanged drafts/reviews; the host's ambient null connection remains supported.
* Render harnesses unmount and close timers naturally. The existing static scanner recognizes the configuration subprocess wrapper and its mutation canary proves the rule fires.

### Verification boundaries
* Source and the real extracted engine archive pass 242 methods each; panel passes 106, with one POSIX-only skip per full suite. Independent whole-branch reviews and all 136 static mutation canaries pass.
* Real host-source SDK/HTTP tests cover install, update and process-death recovery with the actual pinned bundle. Fixture Electron measurements are not live deployment, external OAuth or physical-owner-click proof.
* Search measurements are source-mirror retrieval observations, not certified semantic answer quality, embedding gain or cost savings. Existing external-writer/CAS, power-loss and manually deleted archive limits remain explicit.

## 2.2.0

### Changed
* **Shared workspace shell:** Nexus opens first, Chronicle owns the run journal, Folio owns source review, and Health retains diagnostic analytics without a second journal. Navigation and project context share one shell. Existing APIs and action gates remain the source of truth.
* **Nexus map:** Map is the default tab. The connected configuration map follows the approved `Docs/harvest-ui-v2` composition: conversation adapters connect to Session Harvest and the review boundary; selection opens the adapter or job inspector. A lower read-only review queue opens sources in Folio. Schedule, run times and candidate counts use backend data, not prototype constants.
* **Concise workspace:** removed the overview kicker, subtitle, duplicate KPI/gauge surfaces and redundant list explanations. Project selection and install details live under Project settings; unverified projects open setup automatically.
* **Chronicle:** search and outcome filtering stay visible; advanced job/date filters are closed by default. The spaced journal retains a fixed 520 px scrolling list and a lower read-only queue that opens Folio. Its summary-first inspector grows with content from a 520 px minimum rather than scrolling as a whole, with recorded-duration comparisons. Findings, original output and run metadata remain under Technical details in bounded technical boxes; read and copy failures stay outside that disclosure.
* **Folio:** separates the document, review index and evidence context, with heading hierarchy, readable change lines and the unchanged original diff under As written. The decision trail presents evidence, candidate rationale and the pending decision, not an invented timestamped approval history; evidence collection timestamps are not supplied by the backend. Approval and rejection retain their existing gates.
* **Health:** separates the metric strip, execution timeline and job distribution. Freshness and diagnostic analytics stay here; the run journal and source decisions stay in Chronicle and Folio.
* **Accessible navigation:** native buttons expose selected state and inspector relationships; review and job shortcuts move focus to their target. Narrow panes reflow the map; reduced-motion preferences are respected.

### Added
* **`GET /harvest/status`** delegates to the engine's read-only `--status`. Enabled state, directory detection and committed cursor stay distinct. Missing, failed, empty, malformed and duplicate output fail visibly; no collection, cursor commit or configuration write is performed.
* **Visual fixtures:** separate clean Map and expanded setup states, plus theme and graph-containment coverage. Standalone previews embed the host's icon font rather than depending on its asset paths.

### Fixed
* Unknown adapter IDs retain their literal display name, including names that match object prototype properties.
* Read-only status calls disable Python import-cache writes. Mutation canaries and release-gate canaries use a shared isolated source tree, so interruption cannot leave a test mutation in working code.
* The Health timeline used the static-children helper for a single child, producing React warnings.
* Test-only `source-map-js` is updated to 1.2.2 for GHSA-68fv-2mgg-jv7q; no runtime dependency is added.

## 2.1.0

A real scheduling experience on the Automation tab's **Scheduled jobs** card, instead of a bare cron field.

### Added
* **Human-readable schedules:** every job row leads with the schedule as a sentence (`Every day at 09:00`, `Every 30 minutes`, `Weekdays at 21:30`, `Mondays and Thursdays at 08:15`, `Every hour at :05`, `Day 1 of every month at 03:00`). The raw cron stays beside it in mono, with the kit's `Tip`. An expression with no visual form reads `Custom schedule`, never a guessed sentence.
* **Run state on the row:** the next run (local time and `in 3 h`), the last run (time, `4 h ago`) with an `OK` / `Failed` / `Delivery failed` badge, and a `Late` or `Missed` badge when the store's dispatch stamp says the last start was late (`late`) or a catch-up after a missed slot (`catch_up`). The badge's `Tip` gives the due time, the start time and how late it was. A paused job says `none while paused`; a job that never ran says `not run yet`.
* **Visual schedule editor:** **Schedule** opens a frequency control (Minutes · Hourly · Daily · Weekly · Monthly · Custom) with the fields each mode needs: every 5/10/15/30 min, the minute past the hour, a time field, Mon–Sun day toggles, the day of the month, or the raw cron (Custom, the old behaviour). The current cron opens in its own mode; anything the modes cannot represent opens in Custom exactly as written and is never rewritten on open. **Save schedule** stays disabled until something changes.
* **Live preview:** the editor shows the sentence, the cron it will save and the next three runs, asked of the backend. The store's time zone is shown once. A schedule the store would refuse shows the refusal before Save.
* **`POST /jobs/preview`** (read-only): validates with the core's `cron.parse_schedule` and returns the next three runs from the core's own `cron.compute_next_run`, or the refusal. It writes nothing: no store write, no job map, no scheduler nudge.
* **`GET /jobs`** now carries `next_run_at`, `last_run_at`, `last_status` and a normalised `dispatch` (`{flag: late|missed, scheduled_at, dispatched_at, lateness_seconds}`) per role, and the store's `timezone`.

### Removed
* **The Task Scheduler row and KPI sub-line.** The engine no longer registers a Windows Task Scheduler task (`scheduler_task` left its settings; `run_watchdog.cmd` no longer exists). The backend's `schtasks` query and `scheduler_task` / `scheduler_registered` fields are gone, and `run_watchdog.cmd` left the scripts-present list. The scripts KPI now names the missing script(s) or says `nothing missing`.
* The five preset chips and the bare cron field (their job is the editor's Minutes/Hourly/Daily modes and Custom).

### Fixed
* **Contrast:** `Save schedule` was `--ui-accent` text on the drawer at 4.22:1 (under AA). It is now a kit `Button` inked `--ui-text-primary` on a `--ui-accent` tint with an accent ring (theme tokens only), measured as a reading node at AA, and the schedule preview's contrast gate is green at 560, 820 and 1240 px.
* `shot.cjs --inject=job-acts-too-wide` matched a selector that no longer existed (the action group became a grid), so the control only "fired" by throwing. It now targets the grid rule and fails on the measured overflow.

### Gates
* `render_check.mjs`: every mode → cron, cron → mode round trip for the four live expressions and each mode's shape, unrepresentable cron kept in Custom and never saved on open, the preview line following each change, the refusal shown in the preview and in the job note, a failed preview read keeping its error, the time zone shown once, the row sentence + mono cron + Tip, next/last run, OK/Failed badges, Late/Missed flags with their Tips, no native `title=`, and the Task Scheduler gone.
* Backend selftest: the new `/jobs` fields against a temporary cron store (never ran → none; a stamped run → last run, result, `missed`; `late`; `on_time` → no flag; malformed stamps → no flag), the zone, and `/jobs/preview` (three runs at the right wall-clock time and spacing, an invalid expression refused, empty refused, and the store's bytes unchanged afterwards).
* Static audit: `check_preview_read_only` (the preview may not call a store write, the job map or the scheduler nudge, and must ask the core's `compute_next_run`) with four canaries, `check_schedule_save_ink` (Save schedule never inked with the accent again) with its canary, plus capital-letter canaries for the new chips. `contract_core.py` covers `compute_next_run`.
* `preview.mjs --state=schedule` now opens the editor in Weekly (Mon + Thu 08:15) with its preview; `shot.cjs --scroll=jobs` centres it, and `--inject=sched-no-wrap` is the negative control for the frequency control folding in a narrow pane.

## 2.0.0

One Wiki panel. The separate Wiki Watchdog panel is folded into this plugin as the **Health** tab, next to **Automation**. The run log exists once.

### Changed
* **Two tabs:** the page is built on the host kit's `Tabs`. **Health** is the first tab and the default; **Automation** holds the cards that were the whole panel before. The Watchdog cards (findings, KPIs, freshness, timeline, run log, detail drawer) moved into Health unchanged.
* **Routes renamed** (the Watchdog backend now lives in this plugin, under `/health/*`):

  | Before (wiki-watchdog) | Now (wiki-automation) |
  |---|---|
  | `GET /watchdog` | `GET /health/watchdog` |
  | `POST /watchdog/clear` | `POST /health/watchdog/clear` |
  | `GET /jobs` | `GET /health/jobs` |
  | `GET /jobs/run` | `GET /health/jobs/run` |
  | `POST /runs/archive-clear` | `POST /health/runs/archive-clear` |

  The archive folder is unchanged: `<HERMES_HOME>/backups/wiki-watchdog/`. This plugin's own `GET /jobs`, `POST /jobs/act` and `GET /runs` keep their paths.
* **The panel is a view:** it calls the engine (`~/.llmwiki-audit`) and never copies its logic or writes wiki files. Job definitions live only in the engine's `jobs.json`.

### Removed
* **The duplicate run table:** the Automation tab's five-column Recent runs table is gone. Runs are shown only in the Health run log (filters, search, detail drawer, full body, archive-then-clear). The Automation runs card keeps the per-job heartbeat and gains an **Open the run log** button that switches to Health. The static audit's `check_single_run_view` rule and its canary keep a second run table from coming back.
* **Retired finding `not_indexed`:** the engine no longer reports "page not listed in index.md". LLM Wiki 0.6.12 lists only the 200 most recently updated pages in `index.md`, so that check could never come back clean. Findability is measured by the isolated-page check. Old log lines of that kind are still parsed and labelled as a retired check, with nothing to do.

### Added
* **Evidence findings:** the engine's check 8, the evidence store (`evidence_store`, bad), and check 9, evidence staleness against the installed LLM Wiki / Hermes version (`evidence_stale`, warn), are recognised, mapped to English with the checker's line kept beside them, and each names the `evidence_capture.py` step that helps.

### Gates
* The Watchdog gates are merged: `tests/render_health.mjs` (jsdom, the Health tab), the Watchdog audit rules and canaries inside `audit_static.py` / `canary_audit.py`, the Health backend selftest inside `plugin_api.py --selftest`, and `tests/shot_health.cjs` (Electron, 560 and 1240 px). `node preview.mjs --tab=health` writes `preview-health.html`; `pill_check.cjs` and `scroll_check.cjs` run on both previews. CI now runs `render_health.mjs` beside `render_check.mjs`.
* `scroll_check.cjs` has a negative control that still fires under the Tabs wrapper: `--inject=no-root-scroll` (see `tests/README.md`).

### Wiki Watchdog panel
* `plugins/wiki-watchdog` is retired but kept: this release does not touch or delete it. Disable it once this version is installed, so the two panels do not both show the run log.

## 1.10.0

One job definition, and a Candidates card. The panel reads the engine instead of keeping its own copy.

### Changed
* **Jobs come from the engine:** the job list is `<audit dir>/jobs.json` (name, kind, launcher, implementation, schedule key and default schedule, description), the engine's single definition. `dashboard/job_catalogue.json` is deleted. The delivery target comes from the engine `settings.json` (`deliver`, default `ntfy`), and a script job's prompt is its `description`. The panel now shows the fourth job, **Wiki Session Harvest** (`30 21 * * *`), with an `Agent` chip.
* **Agent jobs belong to the engine:** `install.py` creates them, because they need their prompt file and gate script. `/jobs/act` refuses `create` and `remove` for `kind: agent` and names `python install.py`. Pause, resume and reschedule still work, as they do for script jobs. The card offers no Create or Delete on an agent row.
* **Role ids:** the engine settings `jobs` map (autocommit, ingest_watch, watchdog, session_harvest) now resolves the roles. The panel's own state map is laid over it and still wins, so a job the panel created keeps its recorded id.
* A missing or unreadable `jobs.json` is a failed read that names the file. It never shows as an empty job list.

### Added
* **Candidates card:** one row per pending candidate from the session harvest, each with a kind chip (New · Update · Retire), the target file and the summary. Clicking a row opens the detail in the same card: target, format check, evidence folders, why, and the unified diff in a code body. Approve and Reject follow the detail. With nothing pending, the card shows one neutral EmptyState. A failed read keeps the backend's error, like every other card.
* **Routes:** `GET /candidates` (`wiki_candidates.py list --json`), `GET /candidates/show?ref=<run>/<name>` (`show --json`) and `POST /candidates/act` `{ref, action: approve|reject, confirm, reason}`. All three shell out to the engine script under the audit dir with the backend's own Python, the same way the backend already runs `wikiconfig.py`. The plugin never writes a wiki file itself.
* **Approve is two-step:** the first call runs `approve --dry-run` and only arms the confirmation. The confirmation says that approving writes the source into the wiki's `raw/sources` and that the app will ingest it, which costs model usage. Only a second call with `confirm` writes. **Reject needs a reason**, which is passed to the script as one `--reason=` argument. A ref must be `<run>/<name>`, each part `[A-Za-z0-9_-]` starting with a letter or digit, before it reaches the script. The script's own output is returned as `output` and shown under the result.

### Gates
* The selftest runs against a temporary engine (a four-role `jobs.json` and a stub `wiki_candidates.py` that logs its argv). It proves the agent create and remove are refused, the engine settings map resolves a role, the unconfirmed approve is only a dry run, a malformed ref never reaches the script, and a reject without a reason never runs. It does not touch the real inbox.
* The static audit gains two rules: **no job catalogue in the plugin, the job list is the engine's** and **the approve is two-step and candidates go through the engine script only**. There are 12 new canaries. The version canary now reads the manifest's own version instead of a pinned one.
* The render check expects six cards, four job roles (the agent row has no Create or Delete) and the whole candidates flow (open, arm, cancel, confirm, reject with a reason, engine refusal with its output, empty, failed list, failed detail).

## 1.9.11

Panel surfaces take their colours from shared theme tokens. No behaviour change.

### Style
* **Theme tokens:** the root is transparent and the cards read `--hx-card`, `--hx-field`, `--hx-raised` and `--hx-line`, defined once on the panel root from the app's `--ui-*` colours. The panel now matches the Wiki Watchdog panel and the app surface behind it.

## 1.9.10

Wiki Auto-Commit description: the link repair is gone. No code change.

### Copy
* **Wiki Auto-Commit:** the LINK REPAIR sentence and the `OK link repair` output line are removed. LLM Wiki v0.6.12 counts a page's frontmatter `related:` entries as graph edges (upstream commit b726bd16), so the daily repair that gave isolated pages body links was retired from `wiki_autocommit.py`; `wiki_link_repair.py` is archived under `~/.llmwiki-audit/backups/`.
* A job keeps the prompt it was created with, so the existing Wiki Auto-Commit job still shows the old description until its prompt is updated or the job is re-created.

## 1.9.9

Job descriptions for the once-a-day schedule. No code change.

### Copy
* **Wiki Ingest Watch:** the escalation text described the old 30-minute cadence ("older than 20 minutes" rescans, "older than 45 minutes" alarms), which a job that runs once a day can never follow. It now says what a daily run does: a file younger than 10 minutes is in flight, any other finding earns one rescan the first time it is seen, and it becomes an alarm only when the next day's run still finds it.
* **Wiki Auto-Commit:** the description now covers the link repair that runs in the same idle window and is committed on its own.
* **Watch Dog:** the list of checks now includes a source whose body still holds `---FILE:` blocks (an ingest that was never split into pages).
* These texts are what Create stores as a job's prompt. Jobs that already exist keep the text they were created with until the job is re-created.

## 1.9.8

Fourth blind review: three correctness fixes.

### Fixes
* **Project root row showed the draft:** typing a path into the root input rewrote the "Project root" row (and its copy button) as if that path were already saved. The row now always shows the saved root with its own verdict; the draft stays in the input, and a verified/refused draft gets its own badge beside the input.
* **Running runs counted as completed:** the Heartbeat pill, the legend and the gauge counted every run that was not failed as completed, so a running or unknown run read as done. Only finished-OK runs count as completed now; the rest are shown as "N not finished" and the pill is neutral while they are pending.
* **Unreadable jobs.json read as "every job deleted":** a corrupt or unreadable `cron/jobs.json` returned an empty job list, so every recorded job was marked "Deleted job". A missing file still means no jobs; an unreadable one is logged, `/runs` returns an `error` the Recent runs card shows as a failure note, and no job is marked deleted.

## 1.9.7

Second blind review: wrong numbers, hidden failures, write safety, accessibility and copy.

### Fixes
* **Wrong slow-run duration:** the Heartbeat's "slowest run" note read its duration from a list that had the runs without a duration removed, with an index taken from the full list — one run with no duration shifted it onto the wrong run. It now reads the run itself.
* **Median:** the Slowest run KPI used the upper middle value as the median; it now uses the same true median as the Heartbeat strip.
* **No roles is not healthy:** with no job roles (or no readable jobs) the Jobs chip and the Jobs live KPI read `0/0` in green. They now read as needing attention; the KPI chips no longer say `0 missing` / `0 failed` when nothing is wrong.
* **Config-only job ids:** `/runs` and the Scheduled jobs list still credited a job id that only the wiki config mapped, so a job was shown live with Pause/Delete buttons the act route always refused. Only ids the panel recorded itself are read or shown.
* **A failed /jobs read:** it came back as `{ok:false}` with no roles and the panel drew an empty list, `0 of 0 jobs live`. It now returns an empty role list with "the scheduled jobs could not be read: …" and the card shows that error.
* **A failed refresh was invisible:** a refresh that failed kept the previous reading without a word. Each card now keeps the last reading and says "the last refresh failed — showing the previous reading" with the error.
* **Checker errors dropped:** saving a scan root and the pre-save validation dropped the checker's stderr; both now carry it like every other checker call. A cancelled pick is a note, not a refusal.
* **Write safety:** `/automation/candidates?root=` and `/automation/scan_root` refuse a path that is not absolute or not an existing folder before the checker runs.
* **Profiles:** the backend resolved the Hermes home from `HERMES_HOME` only; it now asks the core (`hermes_constants.get_hermes_home`), so the active profile's state and jobs are the ones read.
* **One surface at a time:** a refusal closes the copy/mirror confirmation, so the Watched root card no longer shows "Why this was refused" beside "Yes, take it" for the same path; the help card's action reads "Pick another file…" instead of a second "Choose folder…".
* **Layout:** the header chips drop below the title at 760 px instead of 560 px; the job action columns size to their labels.
* Removed ~50 lines of CSS the dashboard block overrode (`.wa-top`, `.wa-head`, duplicate `.wa-job-confirm` / quiet-pill rules) and the unused `SectionHead`; the mono stack is the app's `--dt-font-mono`.

### Accessibility
* The page title is an `h1` and each panel title an `h2` (sections are labelled by them).
* Status dots carry a text label (`role="img"`), the ring gauge is labelled "N% — x of y completed", the heartbeat bars are focusable with their reading as a label, and the KPI sub-line tooltips are focusable.
* The Root / Install / Jobs / Runs chips are buttons that jump to their section, with their state in the label.
* Result messages sit in a polite live region and the busy card is marked `aria-busy`; the small caps labels use `--ui-text-secondary`.

### Copy
* "4 heartbeat · …" is now "4 runs · …"; the gauge's "the store has held runs since" (it was the oldest run shown) reads "oldest run shown".
* `x of y`, `ms`, `s` and the day-month stamp go through the bundle; plurals use `Intl.PluralRules`; "STORE holds - saving" uses an em dash.
* The manifest no longer claims the panel is read-only.

## 1.9.6

Correctness fixes from a blind review; the panel's layout is unchanged.

* **Fix (server freeze):** every backend route was `async def` while running the automation checker as a blocking subprocess (timeouts up to 60 s), which stalled the whole dashboard server for everyone until it returned. The routes are plain `def` now, so FastAPI runs them in its threadpool; the static audit refuses an async route that runs a subprocess, and the selftest refuses any async route.
* **Fix (acting on someone else's job):** with no job id recorded, Pause, Resume, Delete and Save schedule fell back to finding a job by its display name, and Recent runs credited any job with a matching name to the panel. The panel now refuses with "the panel has no record of creating this job" and only reads runs for ids it recorded itself. An unrelated job with the same name is never paused, removed or shown.
* **Fix (errors hidden):** a checker call that failed (non-zero exit, a traceback, no JSON) was reported as "automation settings unreadable". The error now carries the exit code and the checker's stderr through to the panel's `as written` block.
* **Fix (silent failures):** an unreadable panel settings file, an unreadable job catalogue, a failed settings write and a failed read of `executions.db` now each log a `WARNING`; a remove whose id could not be forgotten reports that instead of "job deleted".
* **Fix (half-saved root):** saving a root wrote the path and the project id in two separate calls and never checked the second. Both now go in one write, and a failure is reported with the checker's own error.
* **Fix:** Refresh re-reads the scheduled jobs as well as the install state and the runs.
* **Fix:** the Scripts card says "Task Scheduler state unknown" instead of "Registered" when the state could not be read; the Root header chip is green only when the saved root is verified.
* **Fix:** the Verified/Not verified badge beside the root path now describes what is shown: a typed draft carries no badge until it is verified, then its own result — it no longer borrows the saved root's.
* **Fix:** the Heartbeat with no runs shows "—" and "nothing recorded yet" instead of "0% · 0 of 0 completed"; the Slowest run card drops its always-full green bar and turns orange when the slowest run is at least twice the median.
* Carried over from the review PR:
  * **Fix (torn settings file):** the panel's job map (`state/wiki-automation/settings.json`) was rewritten in place, so a write that died half-way left a truncated file and every recorded job id with it. It is now written to `settings.json.tmp` and swapped in with one rename; a failed write keeps the previous file and removes the temporary one. The selftest kills a write half-way and fails when the settings changed or a temporary file was left.

## 1.9.5

Repository and release hardening; no change to what the panel shows beyond the fixes named here.

* **Fix (silent failures):** six backend paths swallowed an error and returned an empty answer — the cron store failing to import, the scheduler not being notified of a job change, a job read failing, the duplicate-job check failing, an unreadable `location.json` and a failed `schtasks` query. Each now writes a `WARNING` line to the Hermes log (`hermes.plugins.wiki-automation`) and keeps its previous fallback.
* **Fix:** the heartbeat pill painted `#0d1216` text on a solid tone. It now uses the theme's reading ink on a 24 % tone wash with a tone edge, so the colour is a surface and the text a theme token.
* **Accessibility:** the "Runs shown" segmented control carries an `aria-label`.
* **Contract gate:** `tests/contract_core.py` checks every `cron.jobs` / `cron.scheduler` name and call signature the backend uses against the core sources.
* **Release gate:** `tests/release_gate.py` — the static audit now also fails when `CHANGELOG.md`'s top heading disagrees with `plugin.yaml`, or when the installed desktop copy (`$HERMES_HOME/desktop-plugins/<id>/plugin.js`) differs from `desktop/plugin.js`; `python release_gate.py` proves each rule can fire.
* **Portability:** `tests/env.py` / `tests/env.mjs` resolve `HERMES_HOME` and the core checkout (`HERMES_AGENT_DIR`) env-first; the audit's CSS-token check and the preview's app stylesheet no longer depend on the plugin sitting three folders under the install.
* **Repository:** git, `.gitignore`, `.gitattributes` (LF), README, this changelog, MIT license and a CI workflow (Ubuntu + Windows).

## 1.9.4

The state this repository was created from. Every earlier decision, with its reason, is written up in
[`Docs/wiki-automation-notes.md`](Docs/wiki-automation-notes.md); the versions it names:

* Earlier versions are recorded only in `Docs/wiki-automation-notes.md`.
