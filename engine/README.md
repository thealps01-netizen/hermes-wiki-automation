# LLM Wiki automation engine

The engine behind a personal LLM Wiki (the nashsu/llm_wiki desktop app). It keeps the wiki backed
up and audited, protects the evidence behind its decisions, and turns decisions from finished agent
conversations into source candidates that the owner approves. Panels and agents are views over
this engine: they call these scripts and never keep their own copy of the logic.

## What runs, and when

| Hermes cron job | Script | What it does |
|---|---|---|
| Wiki Auto-Commit | `wiki_autocommit.py` | Commits what the app generated (`wiki/`, `raw/sources/`, `raw/evidence/`, `.llm-wiki/project.json`) once the app is idle, then checks that each mirror advanced: every git remote of the wiki, or only the remotes listed in `settings.json` → `mirrors` (`[]` turns the check off). |
| Wiki Ingest Watch | `wiki_ingest_watch.py` | Checks that every source dropped into `raw/sources/` was actually ingested. |
| Watch Dog | `watchdog.py` | Audits structure: page loss, broken links, duplicate names, isolated pages, project identity, broken skill references. Also checks the evidence store (hashes, passages, manifests, which source cites which folder) and flags decisions whose pinned LLM Wiki / Hermes code changed in the installed version. The agent-setup check (`drift_check.py`) describes one installation's own setup and runs only when `settings.json` declares `drift.expect`; `drift.agents` lists the agent setups installed on the machine, and a tool left out of it is not expected to have the shared components. Reports only. |
| Wiki Harvest | `harvest_night.py` (`harvest_pipeline.py`, `harvest_extract.py`, `harvest_merge.py`, `harvest_ledger.py`) | Script-only, installed paused. Reads every conversation changed since its last run one by one into `harvest-ledger.sqlite` (Hermes `tool` sessions skipped), then merges the new items into at most one draft per wiki page in `inbox/<night>/candidates/`. Cost cap and time limit per night from `settings.json` → `harvest_pipeline` (`cap_usd` 10, `minutes` 45); what a night does not reach waits for the next. The night's report (`report.json` from merging, `night.json` for the whole night with its cost) and model replies: `harvest-nights/<night>/`. `harvest_night.py --status` (read only) is what the panel's Harvest card shows. Never writes to the wiki. |

Missed runs (PC off, gateway down) catch up once when Hermes starts again. Wiki Harvest reads the
conversations through `wiki_session_harvest.py`'s readers (the file keeps the name of the Wiki Session
Harvest agent job, retired in 2.13.3). An agent that is not installed is skipped and the others still
run; an agent whose history cannot be read is named `UNREADABLE` in the night's report. Each model
call's cost is Hermes' own figure from the profile's `state.db`.

## Tools an owner or agent calls

- `wiki_candidates.py list | show | approve | reject`: the only way a candidate enters the wiki.
  `list` re-derives an update draft whose page changed since it was written (`source_merge.py`; see the
  module docstring of `wiki_candidates.py`); the derived draft needs its own approval.
- `evidence_capture.py`: the only way an evidence folder in `raw/evidence/` is made. It downloads
  the file, pins it to a commit, hashes it and checks the passages. `--verify`, `--recheck` and
  `--normalise` maintain the whole store (logic in `evidence_store.py`).
- `wiki_audit.py`, `app_graph_isolated.py`, `drift_check.py`: read-only checks.
- `source_cleanup.py`: one-off, run by hand. Reads every existing source once and drafts into Review a
  removal-only update (entries that do not count under `harvest_prompt.md` "What counts", such as which
  theme or skin is in use), a retirement, or nothing. The model names lines, sentences, clauses after
  a semicolon or whole decisions by number and the code removes them, so no kept word can change;
  a draft removing more than half of the text says so in its `why`. Cost cap
  and time limit from `settings.json` -> `source_cleanup` (`cap_usd` 8, `minutes` 45); a source already
  read at the same content is not read again (`source-cleanup/state.json`). A removal justified by
  the owner's rule must quote a sentence of it that code finds there. `--shadow <folder>` writes
  drafts and the report only into that folder.
- Contradictions between sources: no script yet. The app's Lint → "Semantic (LLM)" option is only a
  hint (the model sees the first 500 characters of each page). Never press its Fix buttons: they
  write `## Related` blocks with folder-form links and placeholder pages straight into `wiki/`, which
  the wiki's AGENTS.md forbids.
- `wikiconfig.py`: the single settings resolver. Every path comes from `settings.json`. Nothing is
  hard-coded to one machine.

## Install on a PC

This folder is part of the Wiki Automation panel repository. The normal install is the panel's
**Project settings → Install** (preview a plan, then confirm it): the panel copies this folder to
`<HERMES_HOME>/state/wiki-automation/releases/<revision>` and runs `install.py --no-plugin` from there.
The steps below are the standalone install, without the panel.

1. Install Python 3.11+, git, the LLM Wiki app and Hermes Agent.
2. Copy this folder to `~/.llmwiki-audit`.
3. Run `python install.py --dry-run`, then `python install.py`. The installer finds the wiki
   project, writes `settings.json`, installs the cron jobs and the panels, and verifies them by
   running them.
4. Put the LLM Wiki API token in `~/.llmwiki-audit/llm-wiki-token.txt` (one line). It is never
   committed.
5. Run `python portability_check.py`. It must report no machine-specific paths.

## Panels

The panels are separate repositories. `panels.json` names each one and the exact commit this engine
was verified with, and `install.py` has Hermes install it as a pinned Git install
(`hermes plugins install <repo> --ref <commit>`); the engine keeps no copy of a panel. Run
`install.py` with Hermes' own Python, because it calls the Hermes CLI. A panel that is already pinned
at another commit is reported and left alone. `python install.py --force` moves it to the engine's
commit, but never over a checkout with uncommitted changes. To ship a panel release, update its
commit in `panels.json`.

## Developing the engine

Change the engine in a clone of the panel repository and run its tests from this folder
(`python -m unittest discover -s tests`). After any change, regenerate the panel's pinned manifest
with `python tools/engine_release.py` from the repository root; the panel's CI fails until it matches.
The data folder (`~/.llmwiki-audit` or the panel's data folder) holds this PC's state, inbox and token,
never engine code.

## Development recovery and backup safety

This branch is an isolated release candidate, not the installed runtime. Signed owner publication
and same-owner new-session recovery are opt-in; see `docs/recovery-design.md`. Public unbound
approval remains disabled. Scheduler completion, notification delivery and wiki domain completion
are different outcomes. The private helpers are privileged cooperative host implementation,
not authentication of arbitrary same-user programs or a sandbox. Live activation is not performed
by developing or testing this branch.

Automatic backup refuses pre-existing staged work, unreadable workflow state and any applying or
recovery-required source operation. It shares the source application's persistent OS lock, not an
age-based PID-file lock. A failed commit cleans only this attempt's scoped staging if both the
recorded index and HEAD still agree; otherwise it reports recovery required without cleanup.
Pre-commit, prepare-commit-msg and commit-msg hooks are preserved but block automatic commits,
because Git's native scoped commit still allowed an index-mutating hook to sweep unrelated work
into the commit in a real disposable-repository test. Manual/user-controlled Git remains available;
the automation does not disable hooks or install another index-management layer. Post-commit
mirror hooks are not removed or replaced.

Mirrors are checked against actual configured remote `refs/heads/main`, not stale tracking refs.
Exact HEAD equality is fresh, a verified ancestor is behind, and inaccessible/diverged/unverifiable
state is unknown. Retry uses existing configured targets, never adds a remote or force-pushes, and
rechecks the target after push even when there is no new commit. Unknown must not be reported as
fresh. These behaviors are tested with local disposable bare remotes; live network mirrors are not
verified or changed by the development run.

## Not in this repository

The following are listed in `.gitignore`: secrets, `settings.json` and other state files, logs,
`inbox/`, `backups/`, `rebuild-staging/` and one-off probes.
