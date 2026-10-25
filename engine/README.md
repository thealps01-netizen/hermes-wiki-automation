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
| Wiki Session Harvest | `wiki_session_harvest.py` + `harvest_prompt.md` | Collects conversations finished since the last harvest (Hermes, Codex incl. archived, Claude Code, Antigravity) and drafts source candidates into `inbox/`. The morning report is written in the language the owner uses in those conversations. Never writes to the wiki. |

Missed runs (PC off, gateway down) catch up once when Hermes starts again. The harvest uses one
cursor per agent, so nothing is lost or harvested twice. An agent that is not installed is skipped and
the others still run; an agent whose history cannot be read keeps its cursor, so its conversations
wait for a later run while the others are collected. `--last-run` prints the newest host-bound run and
whether it was completed, read-only; it also names why an unfinished run stopped (`stop_reason`) and
what its drafting session cost (`usage`, Hermes' own figures from the profile's `state.db`).
`--runs` lists every host-bound run the same way (`--json` for machine output). The native plugin
records each run's drafting session and turn end in `inbox/<run>/attempt.json` (`--record-attempt`);
`harvest_attempts.py` lists the stop codes.

## Tools an owner or agent calls

- `wiki_candidates.py list | show | approve | reject`: the only way a candidate enters the wiki.
  `list` re-derives an update draft whose page changed since it was written (`source_merge.py`; see the
  module docstring of `wiki_candidates.py`); the derived draft needs its own approval.
- `evidence_capture.py`: the only way an evidence folder in `raw/evidence/` is made. It downloads
  the file, pins it to a commit, hashes it and checks the passages. `--verify`, `--recheck` and
  `--normalise` maintain the whole store (logic in `evidence_store.py`).
- `wiki_audit.py`, `app_graph_isolated.py`, `drift_check.py`: read-only checks.
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
are different outcomes. Native harvest requires strict `harvest_workflow_enabled: true` in both
plugin and selected engine settings, current-profile ownership and the actual configured native
cron execution. Every bounded input read must match the captured hash and cover the whole file;
a later restored file cannot disguise a read of different bytes. Only native completed/nonfailed/
noninterrupted flags plus an explicit drafted/no-candidates outcome can record processing. The
owner report is rendered separately; neither the report nor SILENT is evidence of completion.
Legacy agent-side commit is refused. Captured input, drafted artifacts and cursor projections
survive tested real worker death; retry reuses one journal operation and cannot rewind a cursor.
The CLI native-outcome bridge and private helpers are privileged cooperative host implementation,
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
