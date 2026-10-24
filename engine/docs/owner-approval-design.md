# Owner-decision broker design

## Approved boundary and limitations

The owner approved development of the additional authorization mechanism inside the existing plugin.
No host-core edit, installation, settings/cron mutation, host restart or live wiki write is authorized.

The trusted principal is the owner-controlled authenticated Desktop/dashboard session. The broker
uses the host's actual session verifier; caller `actor`, `confirm`, receipt-shaped JSON and transport
callbacks are not independent authority. This is a scoped agent-access boundary, not biometric
attestation of a physical click or a sandbox against arbitrary code with the same OS account.
The machine's other privileged programs/agents must not be represented as isolated by this mechanism.

## Flow

1. Existing read-only candidate show returns exact source/current text and a canonical review digest.
2. The first explicit Approve action sends the **displayed** digest to a protected owner broker.
   The broker validates host authentication, profile ownership, capability readiness and the fresh
   engine snapshot. Missing/stale digests never get silently replaced.
3. The engine-owned authority records a random pending request bound to snapshot, authenticated
   principal and a maximum five-minute expiry. No receipt is returned on a read-only show.
4. The second explicit UI confirmation sends that request ID and the same displayed digest.
   The authenticated broker confirms only the same pending snapshot and principal. A general
   approval callback is not consulted and no cached/session/permanent grant is accepted.
5. A signed engine-owned receipt records request, issuer, principal, exact snapshot and once-only
   choice. It stays between broker and engine; the UI does not receive the issuer secret or receipt.
6. Application verifies both signature and durable approved record, preserves the operation before
   consuming, and binds consumption to one operation. Retries are the same operation, not a new
   authorization. A fresh operation cannot reuse a consumed decision. Recovery can continue only
   the already-authorized prepared operation and must recheck actual progress.

## Enforcement prerequisites

- The host-bound drafting job exposes exactly `wiki_draft` plus `no_mcp` and loads the native veto.
- Draft handlers permit only explicit bounded data reads and immutable inbox submission; they expose
  no authority, terminal, general file, browser, UI control, RPC, REST or delegation capability.
- Authority records and signing material are in the configured mutable data root, never inbox inputs,
  source files, release code, model context or responses. Initialization is an explicit installation/
  owner setup step, not a side effect of verifying an arbitrary receipt.
- Profile-owned engine settings, loaded guard and active-job capability checks are release gates.
  Unconfirmed cross-process guard liveness cannot be replaced with a disk version/status flag.
- An unreadable authority, unavailable host authentication, linked path, stale project/base/review,
  expired/wrong-session request or changed issuer denies rather than falls back.
- `owner_publication_enabled` defaults off and must be exactly `true` before broker publication or
  recovery. Isolated fixtures opt in; installed settings remain unchanged. Public unbound approve/
  recover still fail closed. Live activation and the final security review are separate gates.

## New-session recovery

An original pending decision remains bound to its exact session, review and expiry. A separate
owner-authenticated recovery action may finish only a previously approved request with a signed
durable owner binding. The host derives that binding from profile and configured owner identity,
never from a request body. A fresh session cannot confirm a pending decision using this path.
Legacy receipts lacking this binding are not migrated or reinterpreted as transferable authority.
Recovery repeats the original operation ID and verified prepared bytes; it never signs a new
review. Expired unconsumed approval, different configured owner/profile, signature tampering,
changed inputs or conflicting target content deny. Status responses expose no receipt or key.

## Portability

The standard-library authority database is mutable data, not part of immutable releases. Moving the
product retains data separately; copied authority records must not silently bind another profile or
project. Profile/data ownership must be explicitly revalidated on installation. No new service,
scheduler, plugin package or second domain implementation is introduced.

## Evidence classification

Fixture HTTP requests prove authentication/denial mechanics, not that the real owner clicked a live
button. Actual host-dispatch tests prove the scoped drafting execution cannot invoke its forbidden
surfaces. Only a separately approved deployment and owner-operated UI exercise can prove the live
human path. No simulated callback is called human-origin proof.
