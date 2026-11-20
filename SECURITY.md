# Security policy

## Scope

Dataverse Docent is a single-process desktop application (Windows-first,
PySide6) with no server component, no telemetry and no update channel. It
talks only to the Dataverse instance you configure, and keeps its state on
your disk. It handles exactly one secret: your Dataverse API token.

## Reporting a vulnerability

Email **Isaac Pratt (pratti@mcmaster.ca)** with subject line
`Docent security report`. Please include:

- what you found and how to reproduce it,
- the version/build facts from the About pane (support copy),
- whether the report includes a real token (it should not — please describe, don't attach).

Expect an acknowledgment within **7 days** and a triage verdict within
**30 days**. We aim to coordinate disclosure with you and fix before any
public details appear; if you do not receive an acknowledgment within
14 days, re-send or call the McMaster library/DS office to escalate.

## How your token is stored

- **Default**: the OS credential store (Windows Credential Manager via
  `keyring`, service `Dataverse Docent`, keyed by the instance base URL).
  `config.json` keeps `api_token_source: "keyring"` and a blank token.
- **Fallback**: if the credential store is unavailable, the token stays
  in `config.json` with owner-only permissions (`0600` on POSIX, user-only
  ACL on Windows) and the app logs a warning saying so.
- **Environment override**: `DATAVERSE_API_TOKEN` wins over both
  (intended for CI); it is never written to disk by the app.
- **Legacy configs**: plaintext tokens found in older `config.json` files
  are migrated into the credential store on the first save.
- **Clearing the token** in Settings deletes the credential store entry
  as well.
- **Diagnostics**: the in-memory request log redacts `key=` / `token=` /
  `api_token=`-style and header-shaped credentials (and their URL query
  equivalents) before display; the app never logs your token, stores it in
  the SQLite state file, or includes it in support copies.
- **SQLite state** (inventory/caches/actions) never contains credentials.

## Rotation

Rotate tokens per your institution's API token policy (McMaster/Alliance
guidance: short-lived scoped tokens where supported). If you suspect a
leak, revoke the token at Dataverse immediately (admin can delete tokens),
reissue, and update the app via Settings.

## Dependency & CVE policy

- Everything is pinned by `uv.lock` (hashes included).
- CI (every push/PR) audits the locked set against OSV with `pip-audit`;
  any known advisory fails the build.
- Dependabot proposes weekly updates (grouped minor/patch); a high or
  critical advisory in a shipped library gets a patch release, not a
  backlog item.
- We do not patch transitive dependencies locally without upstream fixes;
  we either upgrade or, when blocked, document the risk here.
- Third-party licenses are inventoried per release (`uv run poe
  license-report`); a dependency whose license is incompatible with the
  app's distribution is rejected.
- The engine ports MIT-licensed `CUR_Res_CurationTools` (© 2026 Curation
  Services Team, Digital Research Alliance of Canada); attribution lives
  in `LICENSE`.

## Signing

**Decision (2026-11-17): distributed Windows builds are signed through a
managed signing service — SignPath Foundation.** SignPath Foundation
signs open-source Windows software for free; the publisher name Windows
shows is *SignPath Foundation*, not an individual maintainer. The
signing step is implemented and wired in `dv-4t6.6`, and it is gated on
the `SIGNPATH_*` repository secrets: when they are absent the release
workflow logs "signing skipped" and publishes unsigned artefacts, so
forks and local builds are unaffected.

- **Cert source:** SignPath Foundation (managed). There is no
  institutional certificate to buy or hold, and no key material in this
  repository — the service holds the signing key and signs on request.
- **Renewal:** nothing to renew. SignPath's published signing policy
  governs what may be signed; each release is approved manually in the
  SignPath dashboard before it is signed, so a release cannot be signed
  without a deliberate human action.
- **Scope:** the built `curation-app-full` executable and the packed
  installer are signed. The update package is not (the feed hashes the
  package, not the installer).

**Until the first signed release, the builds are unsigned.** Every
release publishes a `SHA256SUMS.txt` next to its artefacts, and Windows
SmartScreen or institutional AV tools may flag an unsigned build as an
unknown publisher. That is expected for the first release; the
click-through and the checksum check are documented in the
[user guide](https://isaacpratt.github.io/dataverse-curation-app/user-guide/) (First run). Verify an
artefact before running it:

```powershell
Get-FileHash -Algorithm SHA256 .\curation-app-lite.zip
```

and compare the digest with the matching line in `SHA256SUMS.txt`.

The release workflow (`.github/workflows/release.yml`) links this
decision and publishes the checksums.

## Threat model

In scope:

- Token theft via hostile websites/plugins is mitigated by never placing
  the token in files, SQLite, logs, screenshots, or support bundles.
- Token theft via malicious dependencies is covered by the pinned lock,
  CI OSV audit and Dependabot.
- Tampering with the installed exes is mitigated by checksum comparison
  (and by the Authenticode signature once signing goes live).

Out of scope / accepted risks:

- A compromised machine (malware as the user) can read anything the user
  can read; no local app can defend against that.
- `workspace/` SQLite files are readable by the user and any process
  running as the user; do not store API tokens or personal data you are
  not entitled to see in them — they are a curator's operational state,
  not a secrets store.
- The app trusts the filesystem and the configured Dataverse instance;
  a hostile Dataverse endpoint can serve malicious files, which the
  format checks will report but cannot neutralize.
- No update mechanism: new versions are distributed through the same
  channels as the installer you received; outdated installs keep their
  audit state.

## What does not happen

- The app never contacts any service other than the configured Dataverse
  instance (and, incidentally, the OS credential store).
- No telemetry, crash reporting, analytics, or automatic update check.
- No API-token hints, previews or fingerprints are written to disk.
