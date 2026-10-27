# Owner approval and native task management

How Review approvals and the panel's job controls are protected. Read this before changing
`dashboard/owner_broker.py`, `engine/owner_decisions.py` or `/jobs/act`.

## Where drafts come from

Wiki Harvest (`harvest_night`) is a script job. It calls the model through `hermes chat` with only
the to-do tool, and the engine's own code writes every draft into the inbox. No drafting agent job,
plugin tool or tool veto is involved. Releases up to 2.13.2 had one (Wiki Session Harvest with a
`wiki_draft` toolset, a native veto and a runtime check that Review required before any approval);
2.13.3 removed it, and the installer removes that job (see `retired` in `engine/jobs.json`).

## Human approval

The trusted principal is the host-authenticated, owner-controlled UI session. The HTTP facade
(`dashboard/owner_broker.py`) invokes the host's session verifier and refuses non-interactive
principals and every current cron execution; body labels and correlated callbacks are not authority.
This is not biometric attestation of a click, and it does not protect against another privileged
program running as the same OS user.

Approval needs, in the selected profile's engine settings: `owner_approval_enabled: true`,
`owner_publication_enabled: true` and an explicit owner binding (`owner_approval_owner`: local owner,
or an exact interactive provider/user/organization match in the same profile). Turning it on is the
owner's explicit action in Review (`/owner/activation`): the page shows the plan, the second click
sends only that plan's digest, and the engine writes these keys. No restart is needed. Re-running it
keeps the existing signing authority. Readiness also requires a readable engine code identity.

Records are exact-review, signed and once-only (`engine/owner_decisions.py`). Principal fields use
canonical framing. Remote principals include a hash of the host-verified access token, so a replaced
or refreshed token invalidates an unfinished confirmation; the durable owner binding excludes that
session incarnation, so an already-approved receipt stays recoverable by the same owner through
`/owner/recoverable` and `/owner/recover`. Legacy unbound and pending requests cannot use recovery.
Response fields are allowlisted per operation; no issuer secret or signed receipt reaches the UI.
Review never resumes an interrupted approval on mount and sends only the approved request ID.

## Native task management: compare, then act, under the store lock

The panel's `/jobs` response declares `mutation_available: true` when the Hermes cron store offers
its cross-process jobs lock (`cron.jobs._jobs_lock`), otherwise `false` with a `management_reason`.
`/jobs/act` takes the role, the action and `expected`: the `{id, state, schedule}` the page showed.

Pause, Resume, Schedule and Delete run in this order: verify ownership of the mapped job (engine
policy source, installation provenance, exact-ID readback, same as the role listing); take the store
lock; re-read the role mapping, the binding files and the native record and refuse unless all equal
what was verified and the record's `{id, state, schedule}` equals `expected`; call Hermes' own
`pause_job` / `resume_job` / `update_job` / `remove_job`; read the record back inside the lock and
refuse to report success unless it shows the change. A writer holding the lock (scheduler tick, CLI,
gateway) is waited for, and its change makes the panel's request stale. Hermes degrades the lock to
in-process only when the file lock times out; the panel inherits that limit and does not add a
second locking scheme. Without the lock function the panel refuses every change.

Delete needs `confirm` and removes the role from the engine and panel mappings only when they still
point at the deleted ID. The panel never creates a native job: Create opens the reviewed engine
installation, whose plan lists the missing role as `create_paused` and records its provenance.
`/jobs/preview` remains read-only.

## Limits

This is not a sandbox against arbitrary Python or another privileged same-OS-user process, and the
fixtures are not proof of an owner-operated installed UI.
