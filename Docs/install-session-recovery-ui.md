# Interrupted installation recovery UI

The Engine install card exposes recovery only for a readable `applying` or
`recovery_required` record with the original lowercase 64-character install ID and plan digest.
It never adopts a legacy record, binds an administrator, rolls back, or posts on mount.
The backend verifies administrator and durable installation ownership; a backend refusal remains
visible and is not replaced by a client-side ownership claim.

## Fresh review and confirmation

An explicit review posts only `{install_id}` to `/engine/recovery/prepare`. The returned
`recovery_prepared` plan must include the original revision, canonical and requested absolute roots,
project ID, engine and audit directories, activation text, all role/name/schedule rows, and lowercase
64-character review ID/digest. The expiry must be finite, still in the future, and at most 300 seconds
away. Different requested/canonical roots appear separately, exactly as supplied, as escaped text.
No identifiers or roots are case-normalized or rewritten.

The user separately confirms `/engine/recovery/apply` with exactly five fields:
`install_id`, `plan_digest`, `recovery_review_id`, `recovery_review_digest`, and `confirm: true`.
Confirmation consumes the local review even if the request fails. A new explicit review is needed
before another attempt. Success requires a matching install ID/revision, an installed state, and
`activation_required: true`; it never activates jobs or publishes sources.

## Context and refresh

Each displayed action retains its SDK connection/profile/cwd epoch, status-read ticket and exact
review identity. Guards read the current SDK atoms before requests and check the captured epoch
again before publishing async results. Old Preview, picker, input, Retry status, Discard, review and
confirmation callbacks cannot recapture a new SDK scope or clear a newer review. A-B-A identity
changes remain a different epoch. Explicit root edits and real saved-root/project-ID drift retire
old authorization and require a fresh status read.

The inherited 60-second automation interval refreshes automation only. Its busy transitions do not
poll engine status or discard local root drafts/reviews. Unchanged manual automation refresh also
preserves ordinary install and recovery approvals. A read error disables recovery confirmation
without pretending that identity changed. Expiry is enforced both by the local timer and immediately
before dispatch. Unmount removes timers/listeners and ignores deferred results.

Host connection/profile atoms accept null or string values, including an empty string. Undefined or
non-string values disable install/recovery with a visible reason and no perpetual loader. The actual
host initializes the profile to `default` and the detached cwd to `''`; connection identity is a
computed projection of the published descriptor and is null before a descriptor is published.
Both null and empty cwd mean no selected workspace, not an inferred administrator. An explicit
absolute install root remains usable after a fresh backend status read. Other cwd values must be
absolute. Raw atom values and epochs remain captured: null/default or empty/default transitions
invalidate an old review even when `backendScopeKey` returns the same canonical key.

`ctx.rest` delegates to `pluginRest`, then `profileScoped` and `hermesApi` in the real host. Null or
empty request tags are omitted. They identify the ambient/primary routing path, not proof that the
backend is physically local: legacy per-profile remote overrides can still own that path. This panel
does not synthesize a `local` tag, choose a remote source, normalize captured atoms, or persist scope.
An explicit remote connection stays explicit. Stable administrator verification remains server-side.

## Native job management

JobsCard requires the top-level `mutation_available` value to be exactly `true`. Missing, false,
null or string values disable Pause, Resume, Schedule, Delete and Create, and block retained
callback requests/confirmation dialogs. The backend's `management_reason` remains visible, with the
fallback:

> This Hermes version does not offer the cron store lock, so job changes stay off.

Every change posts the `{id, state, schedule}` the row showed; the backend refuses a stale page.
Create does not post: it unfolds Project settings and scrolls to the engine installation, whose
reviewed plan creates the job paused. Revoked capability closes/hides old mutation reviews and
prevents retained intents from posting.

## Evidence and scope

`tests/render_check.mjs` exercises the real mounted React UI and actual captured automation interval.
Red/green logs cover UI-01, UI-03, UI-04, retained local/read callbacks, malformed SDK identity,
300-second TTL, exact requested-root display and lowercase tokens. UI-02 shares UI-01's busy-key fix;
its separate negative control restores the original defect on the real source, observes the named
failure, restores bytes in `finally`, and then reruns green. This is not a second independent
production fix. Existing Root/Jobs scope and Folio guards remain exercised.

The harness keeps the existing HTTP lifecycle branch before fixture-only cases. All render-check
exit paths return through cleanup; no forced process exit hides interval/timer leaks. Health and
static previews are run serially because their generated SDK/plugin modules share paths.

Fixture checks do not prove native pixels. `tests/test_install_recovery_http.py` adds a real loopback
HTTP acceptance path: mounted React actions call the real host `pluginRest` and client scope helpers,
then FastAPI and the actual digest-verified committed engine folder selected by `engine-release.json`. Host nanostores execute declarations
extracted from the actual connection/profile/cwd producers and actual SDK state projections. Only the
desktop IPC bridge, persisted-cwd storage and descriptor inputs are disposable harness boundaries;
the REST routing functions and native engine operations are not mocked. This measures host source,
not a live Electron window or its complete boot state machine.

The acceptance gate proves first install from the actual null/default/empty-cwd producer state,
approved child-process death at `engine_applied`, a fresh session's status and original-plan review,
separate five-field confirmation, one resume, single-use replay refusal, and a host-verified different
administrator's refusal. The verified-session provider is a disposable auth fixture, not an external
OAuth service. Jobs stay paused and wiki bytes/administrator/plan bindings are preserved.

Earlier pre-commit fixtures were explicitly marked `TEST-SNAPSHOT-NOT-A-RELEASE.json` and never
claimed to be Git releases. The release HTTP acceptance gate now uses the actual committed engine
archive. Complete live Electron routing, external identity-provider behavior, deployment and restart
remain separate operations; a local accepted package is not proof of live activation. No live wiki,
cron, settings or core files are changed by these tests. All Node generators run serially and return
naturally through root/timer cleanup.
