# Drafting security integration (development, not an installed release)

The native entry point of the existing Wiki Automation plugin registers the `wiki_draft`
toolset and a host `pre_tool_call` veto. No separate plugin, scheduler or model provider is added.

## Contract

- The configured `draft_job_id` is profile-owned plugin configuration, not a tool argument.
- Each constrained handler obtains job and execution identity from `ctx.current_cron_execution()`.
  An ordinary chat, delegated child, wrong job or missing identity cannot use the handler.
- The host collector must persist `execution_id`, `job_id` and `project_id` in the run manifest.
  Old/unbound run folders fail closed; do not let the model generate their binding.
- Job activation must explicitly use `enabled_toolsets: [wiki_draft, no_mcp]`. The host must
  have loaded the native registration before any such job is enabled. Empty/inherited settings
  or schema-only selection are not an enforcement claim.
- The host veto blocks other tools in the bound drafting execution, including general terminal,
  file writes, Python, browser execution, delegation and connection management. Scoped Tool Search
  is handled by the host's own catalog filter; no second catalog is implemented.
- `wiki_draft_read` can read run metadata, the source index, conversation Markdown and selected
  source files only. It reports text clipping and the exact file digest; range limits are explicit.
- `wiki_draft_submit` delegates validation and immutable inbox persistence to the engine. The
  native wrapper owns no source-domain rules, target paths or publication logic. Tool arguments
  are JSON stdin, never command fragments; job/execution/profile/settings argv are host-owned.
- New external evidence capture is not yet exposed. Unsupported externally grounded decisions
  must be omitted, not relabelled as owner decisions or execution proof.
- Completion is built from what the host saw, never from the model's account of it. The candidate
  list is every `wiki_draft_submit` the engine accepted in the bound run (refused ones never appear),
  and the status is `drafted` exactly when that list is non-empty. The model's final reply only has
  to be one JSON object: `owner_report` becomes the owner's notification, `missing_evidence` (its
  strings) is recorded, and any other field, `status` and `candidate_refs` included, is ignored. On
  2026-10-19 a reply with a misspelled key and a listed candidate the engine had refused left a fully
  read run uncommitted, so its conversations were read again the next night. Every captured input
  still has to be read completely, and the engine still checks the list against the candidate
  folders, their format and the input hashes.

## Human approval

The draft tools cannot issue an owner approval or write a live source. Public unbound non-dry
approval still refuses caller confirmation/actor claims. The protected broker can invoke the
engine's shared recoverable application only with explicit `owner_publication_enabled: true`,
owner/profile binding and fresh native readiness. Disposable fixtures opt in; installed settings
were not changed. This is development integration, not an activated human-review workflow.

The owner-approved broker foundation is in `dashboard/owner_broker.py`, with exact-review signed
once-only records implemented in the engine's `owner_decisions.py`. The trusted principal is the
host-authenticated owner-controlled UI session. The HTTP facade invokes the host's actual session
verifier and rejects noninteractive principals/current cron contexts; body labels and a correlated
callback are not authority. This is not biometric attestation of a click. It excludes the constrained
drafting job's channels, not arbitrary other privileged same-OS-user programs or general-purpose agents.

`approval_runtime_ready()` verifies a loaded local guard and the stored agent job's exact
`[wiki_draft, no_mcp]` selection; `no_agent` jobs are refused. The production owner router is mounted
and the panel carries the displayed digest and prepared request ID. Explicit owner binding is
mandatory: local-owner opt-in or an exact interactive provider/user/organization match, in the same
profile. Principal fields use canonical framing, not ambiguous delimiter concatenation.

The production readiness gate also challenges the real native dispatcher with an inert canary,
checks the loaded release identity and bound read/submit handlers, and identifies the built-in
gateway through its existing local control channel. Same-process readiness uses the local native
proof. A different gateway PID requires an explicitly opted-in, authenticated, fresh peer proof
with the same profile, job, release and a successful native veto; a disk descriptor alone is not
proof. External/scoped workers, external cron providers, isolated plugin hosts, missing release
identity, missing handlers/veto or a reached canary deny. This supports the request process plus an
identified built-in, in-process-cron gateway; it is NOT attestation of every running Hermes process.

`runtime_probe_enabled` defaults OFF. When explicitly enabled for development/activation, the
existing plugin owns one temporary loopback listener in each loaded process and closes it through
`ctx.on_unload`. No standalone daemon or additional drafting tool is installed. Its private
profile-cache descriptor carries ephemeral authentication material, not UI settings; never include
it in model inputs, API responses, exported logs or portable packages. The endpoint accepts only a
bounded, signed, short-lived nonce challenge. Approval/publication commands, wrong authentication,
expired/repeated nonces, oversized frames, unknown proof schemas and wrong PID/profile/job/release
are refused. An expired reply is refused even if its signature is valid. The OS-user access boundary
and privileged-code exclusion still apply; no biometric/human-click proof is claimed.

An opted-in registration initializes the inert native dispatcher before exposing its listener;
this avoids a first-request import delay at the one-second transport deadline. The initialization
proof is never cached or reused as owner readiness. Every readiness call uses fresh challenges.
A disposable real host-discovery fixture verifies native load and host unload, and a separate-process
fixture checks the real control server, fresh peer veto, removed-guard refusal and dead-peer refusal.
This is not evidence that the user's installed Desktop/gateway have been updated or activated.
The filesystem protection of the profile/cache is part of the authentication boundary; Windows ACL
checks at installation are still pending. Hard-linked descriptor files and Windows reparse/junction
paths are refused, including on the host's Python 3.11 where `Path.is_junction` is unavailable. A load
whose host declines the cleanup registration closes its listener instead of leaving an orphan.
Native callback failures deny that request, log only their exception type and leave the channel
available for a fresh proof after recovery; they must not silently kill its worker thread.

Engine initialization is explicit and opt-in; missing authority is never created by verification.
No issuer secret or signed receipt is returned to the UI, including nested response fields. The
mounted route/native-veto fixture now confirms and applies exact bytes in a disposable project.
Public unbound approve/recovery stays disabled; live activation/final release verification is pending.

Original pending confirmation stays session-bound. Remote principals now include a hash of the
host-verified access token as well as the configured account/profile; token replacement or refresh
invalidates an unfinished confirmation and requires review again. A real engine authority fixture
verifies that a replacement remote session cannot consume the original pending request. The durable
configured-owner binding deliberately excludes that session incarnation, so the already-approved
receipt remains recoverable by the same owner. Response fields and primitive types are allowlisted
per owner operation; unknown nested classes such as runtime descriptors are refused rather than
filtered by a small secret-key blacklist. This is a schema boundary, not a promise to detect any
secret deliberately embedded inside an allowed source-preview string by privileged code.

Separate protected `/owner/recoverable` and
`/owner/recover` routes allow a newly authenticated session of the same configured owner to finish
only an already approved request with a signed durable owner binding. The host supplies this
binding; client owner/ref/principal claims are refused. Legacy unbound and pending requests cannot
use recovery. Session replacement, real broker-process interruption, exact-source readback, removed
guard refusal and no authority exposure are verified in fixtures. The existing Review view now
has a server-owned Interrupted approvals list and explicit Resume controls. It never resumes on
mount, sends only the approved request ID, retains a refused operation for retry and refreshes after
completion. No new panel/plugin/client storage was added. The owner's subsequent `bitene kadar durma`
instruction authorized proceeding with the proposed existing-Review controls, not live deployment.
Installed Desktop restart and actual owner-operated UI interaction are still separate acceptance gates.

## Native task management: compare, then act, under the store lock

The panel's `/jobs` response declares `mutation_available: true` when the Hermes cron store offers
its cross-process jobs lock (`cron.jobs._jobs_lock`), otherwise `false` with a `management_reason`.
`/jobs/act` takes the role, the action and `expected` — the `{id, state, schedule}` the page showed.

Pause, Resume, Schedule and Delete run in this order: verify ownership of the mapped job (engine
policy source, installation provenance, exact-ID readback, same as the role listing); take the store
lock; re-read the role mapping, the binding files and the native record and refuse unless all equal
what was verified and the record's `{id, state, schedule}` equals `expected`; call Hermes' own
`pause_job` / `resume_job` / `update_job` / `remove_job`; read the record back inside the lock and
refuse to report success unless it shows the change. A writer holding the lock (scheduler tick, CLI,
gateway) is waited for, and its change makes the panel's request stale. Hermes degrades the lock to
in-process only when the file lock times out; the panel inherits that limit and does not add a
second locking scheme. Without the lock function the panel refuses every change.

Delete is limited to script jobs, needs `confirm`, and removes the role from the engine and panel
mappings only when they still point at the deleted ID. The panel never creates a native job:
Create opens the reviewed engine installation, whose plan lists the missing role as
`create_paused` and records its provenance. The drafting job (Session Harvest) can be paused,
resumed and rescheduled; it is created and removed only by the engine installer, and a change
never touches its prompt or toolsets. `/jobs/preview` remains read-only.

## Executable proof and limits

`tests/test_draft_security.py` uses the actual host `PluginContext`, execution identity and
`model_tools.handle_function_call`, including scoped Tool Describe, against temporary profile/data
fixtures. It tests both forbidden dispatch and a real engine subprocess read. `WIKI_ENGINE_TEST_DIR`
selects the engine source checkout for that cross-repository integration; it is a test-only variable.
Run using the interpreter and core path resolved by `tests/env.py`; `TMPDIR` must name the host scratch
root. The engine separately tests immutable draft submissions and unchanged fixture wiki bytes.

This is not a sandbox against arbitrary Python or another privileged same-OS-user process. It is not
proof of live cron activation, an owner-operated installed UI/restart, all-process enforcement or
a model-provider run. Those require their own integration gates. The installed plugin, engine, jobs and wiki remain
untouched during this development stage.
