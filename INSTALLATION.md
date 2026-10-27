# Install or move the offline Wiki Automation package

This is a local reviewed package, not a published catalog release. It reuses Hermes Desktop's
existing plugin installer and the panel's engine installer; it does not install another service,
panel or control application. Keep the extracted package in a durable folder, not a temporary
or download-cache directory.

## Desktop plugin

1. Extract the delivery ZIP. The `wiki-automation.git` directory is a self-contained Git source.
   `source/` is the readable committed plugin source; `RELEASE.json` records the exact plugin
   commit and bundled engine checksum. Neither directory contains installed user state.
2. In Hermes Desktop open **Capabilities → Plugins** and its existing install dialog. Select the
   intended profile. Use the local Git source's file URL as the repository: on Windows,
   `file://<drive>:/<extracted-folder>/wiki-automation.git`; on other platforms,
   `file:///<extracted-folder>/wiki-automation.git`. Use forward slashes, keep spaces literal,
   and set the plugin commit from `RELEASE.json` as the commit pin. The local-source
   warning is expected; inspect the manifest and source before approving it.
3. Keep both agent/backend and desktop components selected. Enable them explicitly. For an update,
   use the dialog's existing reinstall/replace option only after reviewing the source. Do not
   hand-copy files into installed plugin or materialized desktop directories.
4. Let the existing host installer materialize the desktop half. A backend change requires an
   explicitly approved application restart before the new Python routes are active. An accepted
   local package is not evidence that your running application has loaded it.

No terminal commands are required. If an assistant performs installation, it must use this same
supported host path, preserve existing state and read back the exact installed revision; it must
not approve a user-controlled trust or installation decision on your behalf.

## Engine and interrupted installation

Open **Wiki Automation → Project settings → Install**. Choose your real project folder, request
an install/update preview and inspect its exact root, project, revision, directories and job plan.
Confirm that displayed plan separately. Installation preserves existing task IDs/custom schedules
and creates new jobs paused. It does not configure content-owner authority or activate collection.

An engine installed earlier with `install.py` shows as an existing, not-yet-verified installation.
Use **Preview update**: the plan keeps its data folder and lists each job as adopted in place
(script jobs keep schedule and on/off state) or new and paused. A job of a retired role (Wiki
Session Harvest, replaced by Wiki Harvest) that the installation created is listed for removal.
A customized job is refused at preview. Nothing changes until you confirm that plan.

## Owner approval

Approving a candidate needs an owner bound to this profile. Open **Wiki Automation → Folio**:
while no owner is bound it shows **Owner approval is off** with what turning it on changes. Click
**Turn on owner approval**, then **Confirm and turn on**; no restart is needed. The owner is
this computer's Hermes session (or the signed-in account when the dashboard requires sign-in);
it is never taken from the request. An owner turned on before 2.13.3 stays on after the update.

After an approved interruption, the same verified administrator may open the original unfinished
operation, review its original plan in the new application session and explicitly confirm the
single-use recovery review. The review lasts 300 seconds. Legacy, changed-release, unsupported WAL
or drifted records are refused rather than adopted, repaired or upgraded silently. Keep original
recovery data for inspection; never remove it to turn a refusal into an apparently fresh install.

## Moving to another PC

Copy the extracted offline package and your separately backed-up wiki/user data. Install Hermes
and this pinned plugin through the target machine's normal graphical interface. Select that
machine's real wiki folder in the panel; do not reuse another machine's absolute paths. Local
profile identity and old unfinished approvals are not transferable administrator proof. A moved
old location, unfinished operation or identity mismatch must remain refused until explicitly
resolved; this package does not promise automatic data migration or cross-machine approval reuse.

## Boundaries

- Create, Pause, Resume, Schedule and Delete in this panel are disabled until Hermes supports
  atomic expected-record ownership validation. Verified task listing remains available. No task
  is secretly modified by a disabled button.
- Content-owner decisions, collection activation and application restart remain separate explicit
  operations. Never treat an install preview, a successful test or a retrieved search candidate as
  permission to publish wiki content.
- Existing WAL journals are refused during nonmutating inspection; there is no automatic checkpoint,
  conversion or immutable-reader fallback. External-writer/CAS, power-loss and manually deleted
  archive limits remain described in the engine recovery documentation.
- `Docs/installation-session-recovery.md` and `Docs/install-session-recovery-ui.md` describe the
  tested contracts. Verification reports distinguish source/fixture evidence from live activation,
  external OAuth, semantic answer quality, embedding gain and cost claims.
