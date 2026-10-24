# Recoverable candidate application (development integration)

## What exists and what is still gated

`candidate_apply.py` is the engine's shared recovery implementation. It is exercised with disposable
wiki/data roots and signed synthetic owner decisions. The mounted authenticated broker now invokes
this shared implementation only when `owner_publication_enabled` is exactly `true`, in addition to
explicit owner activation/profile binding and fresh native runtime verification. No installed
settings were changed. Public `approve` remains disabled; public `recover` and `reconcile` still
allow only read-only `--dry-run` inspection. Default broker confirmation only records authorization.
Do not infer release readiness or live enforcement from these mechanics.

## State and ordering

- `operation.lock` is a persistent lock file, held exclusively by the OS. Another writer waits or
  reports a busy lock without deleting it. Process death releases the lock; the pathname is retained.
- An operation ID binds issuer, owner request and exact review digest. The selected data root owns
  its workflow journal and authority; a different journal root is refused.
- Source, expected base and evidence bytes are privately prepared with verified hashes before an
  operation is journaled. The base copy is retained for inspection, never an automatic rollback.
- A durable operation exists before once-only authorization is consumed. Both journals survive
  independent process restarts. Recovery verifies the stored decision and operation binding.
- Existing project/candidate/evidence identities are checked before continuation. Evidence folders
  are fully prepared on the destination volume and placed before the source becomes visible.
- Source publication uses a guarded no-overwrite protocol, not a hash pre-read followed by replacement.
  New sources are prepared, flushed and file-fsynced on the destination volume, then renamed exclusively.
  Updates/retirements first rename the current entry into
  `.llm-wiki/source-recovery/<operation-id>/captured.bin`, without replacing an existing capture.
  Captured bytes must match the signed expected base; an update then publishes only into an absent
  target. A retirement retains the captured object instead of unlinking it. Every capture is retained,
  including the object reachable through any independently held owner handle. Drift is refused;
  restoration of captured owner bytes uses a separate copy and exclusive rename, never replacement.
  When another owner has already recreated the target, both target and capture survive.
- Windows `os.rename` provides destination-exists refusal. Linux requires `renameat2(RENAME_NOREPLACE)`;
  unsupported platforms/filesystems and cross-volume renames fail closed. No fallback to overwrite,
  advisory writer cooperation or exclusive ownership is assumed. The target may temporarily be absent
  between capture and publication; the durable operation and retained capture allow process recovery.
- Attribution uses `evidence_store.sync_used_by` for both proposed evidence and citations found in the
  prepared base after verifying its signed hash. Removing evidence from an update, or retiring a source
  with empty candidate evidence IDs, clears obsolete `used_by` entries without changing the reviewed
  snapshot, signatures, payloads or unrelated manifest fields.
- The backward-compatible application marker is written last. Journaled steps are immutable;
  completing an already published step does not rewrite its source. A completed operation reports
  later source/evidence-payload drift without repairing it.
- Conflicting target content or a deletion after journaled publication is preserved and requires
  review. No rollback overwrites somebody else's newer source.

## Authenticated broker retries

The broker never returns receipt/signature/key material. A retry resolves the durable approved
request using its original principal, ref and displayed digest. It does not obtain a new review
or authorize a different operation. This permits update/retirement recovery even after publication
has changed the target base. Expired unconsumed requests are refused; consumed decisions can finish
only their original operation. Target drift is reported without overwrite; later drift is explained
without repair. CLI application/journal refusals are structured errors, not tracebacks.

The panel retains the exact confirmation handle after an engine timeout or transport exception,
provided selection/review identity has not changed. Cancellation, selection changes and refreshed
reviews still invalidate it. Fixture tests cover reusing the same request across broker-process
death. A separate protected recovery path now accepts only an already approved request bound to
the same configured owner, even from a freshly authenticated session. The host derives a stable
owner-binding digest from the selected profile/mode and interactive provider/user/organization,
not client claims. It is signed into the receipt; ordinary pending confirmation stays session-bound.
Legacy receipts without this binding cannot be silently transferred. The existing version-1
authority schema is retained: bound session/owner identity is canonically framed in its opaque
principal field. No schema migration or installed database edit was performed.

Protected `GET /owner/recoverable` lists eligible same-owner unfinished approvals only, reading an
existing workflow journal without creating one. Protected `POST /owner/recover` accepts only the
request identity; original reviewed bytes and receipt remain engine-owned. It cannot sign pending
decisions, change the approved operation or consume an expired unconsumed receipt. Body owner/ref/
principal claims are rejected. All authority material is refused recursively in host responses.

The mounted native/control-server fixture proves token replacement followed by recovery of an
interrupted broker process. It does not restart the installed Desktop. The existing Review view now
lists interrupted approvals and offers an explicit Resume control using server-owned request IDs,
without persistent client storage. A full owner-operated installed application-restart workflow
is still an acceptance gate.

## Rejection and legacy records

Public rejection delegates to this engine implementation. The reason is in both durable operation
identity and `rejected.json` before the candidate is moved. A retry with the same reason finishes the
same move; a conflicting destination/decision is refused without replacing either copy.
Any prepared candidate application for the same ref blocks rejection before a rejection record,
reason marker or move is written. This includes unfinished recovery and completed applications:
reconcile the original authorized operation, or review a separate update/retirement instead.
`reject --expected-review-digest <displayed-digest>` passes the selected wiki into the engine.
Under the same `operation_lock`, the engine compares the current `review_snapshot` digest before
writing any rejection record/marker or moving the candidate. The supplied digest is bound into
rejection identity; a moved-candidate retry must match that durable record and cannot invent a
review from a nonexistent candidate. Omitting the flag retains explicit legacy CLI behavior;
review-bound panel callers must supply it.

Legacy reconciliation is read-only by default. A marker alone is insufficient: source bytes,
evidence payload and attribution must agree. An absent retired source is ambiguous, because absence
does not prove the recorded deletion. Invalid candidates are reported as ambiguity, not skipped.
Internal explicit import records content agreement only; it does not manufacture an owner approval
and cannot be recovered as an authorized candidate operation. Public import is still gated.

## Read-only journal inspection

`WorkflowStore(..., read_only=True)` supports only ordinary SQLite rollback-mode journals.
It reads the SQLite header before opening a database connection and refuses WAL or unsupported
file formats without creating WAL/SHM sidecars. Existing WAL files, pending records and journal
mode are preserved: there is no checkpoint, conversion, migration or `immutable=1` fallback.
This restriction applies to both source and installation recovery inspection. A refusal is not
an empty journal or proof that no operation is pending; recovery stays blocked and reports an
unsupported journal. Normal engine-created journals use rollback mode.

The format preflight is not an atomic guarantee against an unrelated process changing journal
mode after the check. The existing operation locks bind cooperating engine writers; the documented
external-writer and power-loss limitations remain. The header fields are defined by the
[SQLite database file format](https://www.sqlite.org/fileformat.html#the_database_header).

## Verification and limitations

The subprocess interruption matrix terminates execution before/after preparation writes, fsync,
atomic replacements, authority consumption, journal transitions, evidence placement, attribution,
and the final marker. A fresh process reopens the operation and finishes it. New, update and retire
fixtures include actual evidence. Separate-process lock contention, lock-owner death, concurrent
same-operation application, stale candidate input, forged authority, later drift and read-only
preview byte preservation are also tested.
Additional update/retire matrices cover removal of all candidate evidence. Independent subprocess
writers exercise in-place edits, atomic owner replacement immediately at the OS rename seam, and
creation inside the capture gap. A Windows share-delete owner handle also edits the captured object
after the rename; owner bytes remain in the archive and are restored without overwrite when possible.

Windows execution is verified; the POSIX fcntl and Linux renameat2 branches have not been run on POSIX. These are process
interruption tests, not a sudden-power-loss/filesystem-controller simulation. A file fsync does not
promise multi-file or directory-entry durability on every filesystem. Independent app/user writers
do not honor the engine lock: source mutation never overwrites/deletes their racing bytes, but this
is not linearizable CAS or an atomic multi-file transaction. A capture-and-publish gap is observable
to readers/watchers. A held handle can edit the retained capture even after successful publication;
subsequent retries report capture drift without repairing it. Writes after the last verification
and edits that change away and back to identical bytes are not claimed immediately detectable.
Archives are retained without automatic cleanup; manual deletion of an archive, owner edits to
operation-private staging, and concurrent directory/reparse substitution are not protected by this
source protocol. The separate path-guard work owns directory/reparse guarantees. Interrupted
same-volume temporary files/folders may remain for inspection; they are not completion markers.

All-process guard attestation, live owner UI use, installation, harvest-cursor safety, backup Git
preservation, retrieval measurement and the final whole-branch review are separate acceptance gates.
