# Approved installation recovery across application sessions

The integrated implementation is shipped in the local 2.3.4 package with committed engine
revision `a51c0b310f3c35d2491ec25870cbe92373a6ebc6`. Native and actual host-source SDK/HTTP
verification use disposable profiles and the real pinned archive. No live application, real
profile, jobs, settings, wiki, core source or remote release was changed by these tests.

## Authority and transport

- Original `/engine/prepare` captures a stable administrator hash separately from the session
  principal and content-owner authority. Remote identity uses host-verified provider/user/org;
  local identity uses the selected native profile home. Access tokens never establish stable
  ownership. The remote session principal also includes the host process session incarnation.
- Original explicit `/engine/apply` durably writes `approved: true` before engine mutation.
  Only original `applying`/`recovery_required` records with that flag and the original stable
  administrator may be recovered. Missing/legacy/unapproved records are never retrofitted.
- `/engine/recovery/prepare` accepts exactly `{install_id}` and returns the original bounded
  preview, `state: recovery_prepared`, a 64-hex review ID/digest, numeric `review_expires_at`,
  `operation_state`, and `native_operation_state`. It writes only a separate server review.
  Review validity is 300 seconds. No original settings, access tokens or owner binding are emitted.
- `/engine/recovery/apply` accepts exactly `{install_id, plan_digest, recovery_review_id,
  recovery_review_digest, confirm: true}`. It rechecks stable administrator, fresh session,
  original immutable record/plan, manifest/artifact/code, native current-state digest and expiry.
  A separate confirmed review authorizes execution; it never rewrites the original principal,
  administrator, plan or installation ID. Consumed reviews cannot be replayed.
- Business refusals use `{ok:false,state:refused,reason}` and HTTP 409. Existing host authentication
  and exact-field HTTP 400/401/403 validation remain in force. Service, cron and host-isolation
  callers cannot review/confirm installation. No routes automatically prepare or apply on mount.
- GET `/engine/status` preserves readable unfinished operation state, ID and plan digest even
  when active location, launchers, settings, jobs or another installation record are unreadable.
  `active_state: null` and `active_verification: unverified` do not claim installed health.
  `read_only_diagnostic` contains a bounded native inspection state/reason, never settings.
  Supported installed/prepared response fields remain unchanged; installed job inspection is
  strict and read-only, rather than calling native repair-capable cron loaders.

## Engine-owned read-only validation

The captured engine did not expose read-only inspection of a previously approved installation.
`build_plan` previews new state; `apply_plan` mutates; `_check_capture` may restore files. None is
an appropriate read-only recovery review API.

The approved engine exposes `validate_installation_recovery(plan, expected_digest)` and
`--validate-recovery-plan`. It reuses `build_plan`, `code_fingerprints`, `verify_job_role`,
`WorkflowStore(read_only=True)`, `checked_path`, `unlinked_path`, and `_retained_captures`.
It checks primary and **all secondary recaptures** in every native state, including unstarted
operations and no-op projections, without repairs. Incomplete recapture prefixes and missing
primary before-images refuse. Valid capture facts participate in the current-state digest.
`parse_native_jobs` is the single strict nonrepairing parser used by preview capture,
`existing_job_snapshot`, recovery validation, apply comparison and final panel readback. Pure
native display/skills/state normalization does not rewrite raw jobs. Unsupported JSON shapes,
duplicate IDs/fields, malformed repeat/schedule records and unsupported/corrupt journals refuse
with bounded JSON, without native auto-repair or traceback output.
The original plan binds the selected interpreter. Shared native role verification checks script
interpreter, workdir, agent prompt/toolsets and exact engine origin. Newly created marked jobs
must retain the original paused creation fields and exact journaled snapshot; pre-existing
approved jobs retain custom schedules, enabled state and delivery. Unsupported custom script
executables are refused, never silently replaced.
It also checks original captured/recorded native job presence before resume, instead of creating
replacement jobs for missing owner records. Native current facts are returned as a digest plus a
bounded operation state, not settings or owner data.

`apply_plan(..., expected_recovery_state=...)` checks that digest under existing native operation
locks **before opening the writable journal or performing engine mutations**. Native validation
runs again after apply for recovery readback. Projection construction is shared with the existing
installer; the panel does not implement projection, capture, scheduler or settings business rules.

Earlier pre-commit development used explicitly labelled test-only snapshots; release acceptance
now executes the actual pinned Git archive. The old helperless committed archive is retained only
under `tests/fixtures` as a negative capability fixture, never selected as runtime fallback. It
refuses recovery without staging or upgrading anything. Existing original-session apply/retry
remains supported. A changed release also refuses: this feature does not upgrade an old approved
half-install. Read-only journal inspection supports SQLite rollback mode; existing WAL journals
are refused without checkpoints, conversion, sidecar creation or immutable-reader fallback.

## Evidence and integration boundary

Tests exercise actual FastAPI routes and the native host authentication gate. Remote tests register
a disposable provider through the native registry; they do not mock the route auth predicate.
Service/cron contexts and fake profiles are disposable native fixtures. No external identity
provider or live application was contacted.

The first red log reproduces real `engine_applied` process death, the original new-session 409,
and missing recovery routes (404). Subsequent vertical implementation cycles cover the read-only
native helper/CLI and locked digest, immutable admin identity, unfinished status, native journal,
secondary-capture readback, and captured/recorded job loss. Additional acceptance tests characterize
guards already established by those slices. Real process deaths also cover original approval before
engine mutation and native job save before journal registration. Jobs/settings/content/owner files
are checked for preservation; existing enabled jobs and custom schedules remain unchanged.

The staged proposal was integrated selectively into the latest original isolated worktrees,
retaining the independently approved generic primary/all-secondary capture fixes. Exact pre-edit
backups, incremental diffs and red/green native logs are in the scratch integration evidence.
The local package now includes the actual reviewed committed engine archive. Parent and
independent full-suite gates passed for the engine, extracted archive and integrated panel.
Live deployment, external OAuth and physical-click ownership remain outside fixture acceptance.
Older pinned engines lacking the strict read-only helper fail closed; this implementation does
not retrofit or upgrade them.
