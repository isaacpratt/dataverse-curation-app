# ADR 0005 — The Dataverse API token lives in the OS credential store

- **Status:** Accepted
- **Date:** 2026-11-13 (decision), 2026-11-16 (landed)

## Context

The Dataverse API token is the only secret the application handles. It was
stored as plaintext in `config.json`, in the user's home or working directory.
The audit rated this as the highest-severity finding: a plaintext token on
disk is copied by backups, synced by cloud drives, and leaks through support
zip files.

The application is a single-process desktop program on Windows, where the
platform already provides a credential store (Credential Manager). There is
no server, so there is no need for an application-level secrets service.

## Decision

- **The token is stored in the OS credential store** via the `keyring` package
  (Windows Credential Manager on the supported platform), under the service
  name `Dataverse Docent`, keyed by the instance base URL. `config.json`
  keeps `api_token_source: "keyring"` and a blank token.
- **Load precedence is env > keyring > plaintext file.** The environment
  variable `DATAVERSE_API_TOKEN` exists for CI and one-off headless runs and
  is never written to disk by the app.
- **Plaintext is a documented fallback, not the default.** If the credential
  store is unavailable, the token stays in `config.json` with owner-only
  permissions (`0600` on POSIX, a user-only ACL via `icacls` on Windows) and
  the app logs a warning saying that the file could not be locked down.
- **Legacy plaintext configs migrate on first save**; clearing the token in
  Settings deletes the credential-store entry as well.
- **Diagnostics never carry the token.** The in-memory request log redacts
  `key=`/`token=`/`api_token=`-style secrets, header-shaped credentials
  (`X-Dataverse-key`, `Authorization: Bearer`, `Api-Key`), `password=`/`secret=`
  and the URL query equivalents. The About-pane support copy carries version,
  environment and provenance facts only.
- **The SQLite state file never contains credentials.**

## Consequences

- A curator's token is protected by the same credential store they already
  trust for other desktop apps; a stolen config.json no longer leaks it.
- The first save of an existing installation migrates the token — curators
  should be told that the app now uses the credential store.
- Headless/CI runs use `DATAVERSE_API_TOKEN`; a machine with no credential
  store (some Linux CI images, minimal containers) falls back to the
  environment or to the plaintext file, and the fallback is loud.
- The Windows exes are unsigned in the first releases (see `SECURITY.md`);
  credential storage does not change that. The signing policy was decided
  on 2026-11-17 (SignPath Foundation, wired in `dv-4t6.6`), and the
  decision bead was `dv-hcg.39`.

## Links

- Beads: `dv-hcg` (audit), `dv-hcg.9` (keyring storage), `dv-hcg.10`
  (config schema), `dv-hcg.11` (env overrides), `dv-hcg.17` (log redaction),
  `dv-hcg.18` (ACL failure reporting), `dv-hcg.19` (SECURITY.md).
- `SECURITY.md` — token handling, reporting channel, threat model.
- `curation/config.py` — `KEYRING_SERVICE`, load precedence, save fallback.
- `curation/applog.py` — redaction patterns.
- `engine/tests/test_config.py` — keyring contract tests.
