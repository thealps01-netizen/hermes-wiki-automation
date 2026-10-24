# Candidate evidence attribution and citation admission

This describes development-only recovery mechanics. Public approval remains disabled; no installed
settings, owner-authority schema or signature format changes are required.

## Lossless inner manifest publication

Candidate attribution uses the shared `candidate_apply.publish_file` publisher. It hashes the exact
bytes parsed by `sync_used_by`, before computing the wanted `used_by`; it never re-reads newer live
bytes to authorize a stale metadata update. The shared writer requires that expected hash explicitly.

The operation records `attribution-base:<evidence-id>` with that before-image hash before capture.
Publication flushes and file-fsyncs `.llm-wiki/evidence-attribution/<operation-id>/<evidence-id>/publication.bin`,
then exclusively renames the canonical manifest to `captured.bin`. It verifies the retained bytes,
exclusively publishes into the absent canonical name, and checks retained captures again before the
application marker. Owner edits at capture/publication boundaries cause refusal, retaining their bytes.
A held native owner handle can continue editing the retained object; partial JSON is not a completion
signal. Captured drift observed after completion is reported as `later_drift`, without repair.

Capture leaves an observable canonical-name gap. For a prepared owner-authorized operation, resume
may restore the exact hash-bound retained before-image into an absent canonical name **before**
validating evidence. It cannot use another operation's capture, invent a missing manifest, recreate a
missing evidence directory, or ignore missing/extra canonical payload files. Restoration retains the
archive and never overwrites an independently recreated owner entry. Validation still compares the
complete canonical payload set and reviewed manifest metadata, excluding only derived `used_by`.

If validation required restoration, publication exclusively re-captures the identical old bytes into
a fresh `recapture-<unique>/captured.bin` under the same operation's recovery directory. All old and
re-captured objects remain retained and are checked; an owner racing re-capture is preserved and
requires review. No old capture is renamed away or deleted to make room for another attempt.
Standalone maintenance uses a unique same-volume `.evidence-attribution-*` directory outside
canonical evidence; it has no candidate journal recovery authorization.

Canonical payload validation remains exact. Extra files, including a manually inserted
`raw/evidence/<id>/manifest.json.tmp`, are preserved and cause refusal; their names do not grant
staging ownership. Citation admission and prior base-citation removal/retirement rules below are
unchanged; recovery does not expand the signed evidence snapshot.

The five source matrices exercise every checkpoint for new/update/retire and update/removal and
retirement with empty proposed evidence IDs. Native inner-manifest tests also use `os._exit(91)`
at actual fsync and no-overwrite rename boundaries: before/after file fsync, after capture, immediately
before exclusive publication, and after exclusive publication. Each of those five phases is tested
for all five operation configurations (25 deaths). Recovery completes the exact signed operation,
retains exact before-images outside canonical evidence, does not republish the source, and a second
retry reports no staging-induced evidence drift. A repeated-death test interrupts restoration and
re-capture six times for each of three operation configurations (18 additional native deaths), then
verifies every retained before-image and completes the same journal operation.

## Proposed citations (RR-LOGIC-4)

New/update source citations must match `evidence_ids` exactly before a review snapshot or approval
preview is admitted. Both free-text `Evidence:` values and the first column of `## Evidence` tables
use the evidence store's citation parser. `Evidence: none (...)` is an explicit no-evidence
annotation; identifiers such as `none-code` remain citations.

Every declared citation needs a readable schema-1 identity-matching manifest in candidate or
retained evidence. Those files and payloads remain bound in the existing snapshot fields; no
citation union is added after approval. Missing, duplicate, inconsistent or unsupported citation
metadata is refused. Previously prepared unfinished operations also revalidate proposed citation
metadata on resume and refuse mismatches without changing the signed snapshot or expanding it.

The constrained draft adapter admits evidence citations only as retained evidence of an update:
every declared ID must already be cited by the exact current target (the submitted base hash
must match the live file) and have a retained identity-matching manifest. A new source, a
retirement, a stale base or any evidence the target does not already cite is refused before any
draft file is created. The drafting step therefore cannot introduce evidence; it can only keep the
citations of decisions it leaves unchanged. This is a capability limit, not permission to remove
required evidence and submit the unsupported decision anyway. Prior base-citation
removal/retirement reconciliation is unchanged.

These tests establish process-interruption recovery on Windows. Linux's `renameat2(RENAME_NOREPLACE)`
path is implemented but not exercised by this Windows run; other platforms refuse without a supported
no-overwrite rename. This is lossless retention, not linearizable compare-and-swap or sudden-power-loss
durability. Independent writers can observe the capture gap, and a same-user writer can alter a
retained object after the last check. The engine operation lock does not constrain those writers.
No directory-fsync or owner-lock assumption is added; review and retained-byte inspection are required
when drift is detected.
