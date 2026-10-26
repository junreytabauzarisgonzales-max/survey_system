# Acceptance evidence and outstanding work

This document deliberately separates implemented source from executed verification.

## Executed in this workspace

- Python API/model/database/CSV tests: `python -m unittest discover -s backend/tests -v` — **43 passed**.
- React form and question-parser tests: `npm test` in `web/` — **7 passed**.
- Production public-site compilation: `npm run build` in `web/` — **passed**.
- Independent survey-interface compilation: `npm run build:app` in `web/` — **passed**.
- Public documentation/tutorial/download Chrome tests: `npm run test:site` — **3 passed**, using only a static preview with no backend.
- Chrome browser workflows: `npm run test:e2e` in `web/` against a separate temporary database — **3 passed**.
- Desktop SQLite/restart/backup/origin-isolation integration check: `python -m unittest discover -s desktop/tests -v` — **1 passed**.
- Native Windows Edge WebView2 window and device-storage bridge: `.venv/Scripts/python.exe -m desktop.smoke` — **passed**, using an isolated temporary database.
- Single-file Windows executable packaging: `desktop/build.ps1` with PyInstaller — **passed**, output `dist/StudentSurveyCreator-Windows.exe`. Inno Setup is not installed locally, so the setup-installer recipe has not been compiled here.
- Single-file packaged Windows executable launch and clean window shutdown — **passed**, using a temporary `LOCALAPPDATA` directory.
- Dart syntax parsing of changed mobile files and the new local-workspace tests (`dart format --output=none`) — **passed**. This does not verify Flutter types or runtime behavior.

### Device-local operation

The Windows desktop host bundles the existing interface and local Python/SQLite engine, binds only to a random loopback port, and stores the database outside the installation directory. Native CSV/summary/manifest save dialogs and verified database backups are supplied. The integration check verifies account/survey writes, backup integrity, preservation after reopening and rejection of unrelated Host/Origin headers. The native smoke check verifies that the desktop interface renders and the only exposed native methods are the file save, backup and storage-info methods.

Android now supplies an independent no-account local workspace, questionnaire creation, offline response collection/corrections, local CSV export, and self-contained local recovery archives. `mobile/test/local_workspace_test.dart` adds SQLite reopen/correction/export and empty-device recovery scenarios. These Flutter tests and APK compilation remain **unexecuted**: a temporary SDK bootstrap did not complete. Dart was recovered and parsed the sources successfully, but Flutter initialization timed out and dependency resolution was blocked by missing engine packages (`sky_engine`). A working Flutter SDK and Android SDK/device verification are still required. See [device installation](DEVICE_INSTALLATION.md) for build and storage details.

### Public documentation website

The default public website provides overview, documentation, platform-specific tutorials and download pages. Static-site browser checks cover navigation, tutorial platform/lesson deep links, absence of survey API requests, an actual Windows EXE download with its matching SHA-256 checksum, disabled missing-package controls, download-manifest error/retry and no horizontal overflow at a 390px viewport. Desktop and mobile screenshots were inspected. Vercel deployment configuration and a package-staging script are supplied; no live deployment was performed.

The real single-file Windows EXE is included in the local static build under `web/dist/releases/`. The Android APK has not been built/supplied, so Android correctly appears as **Build pending**. The manual device-build workflow now produces both native downloads and a combined static website artifact once both builds pass. No CI run or release publication was performed here. See [website build/deployment](WEBSITE.md) for how to provide binaries on a fresh deployment.

### Public survey link verification

The public-link feature adds a data-preserving migration, link management, unauthenticated questionnaire/submission endpoints, and a separate mobile-friendly respondent page. Backend tests cover immutable version pinning, consent and field validation, staff/project scoping, protected-sharing permissions and revocation, link disabling/expiry/archival, retry receipts including after retention, transactional bound attachments, CSV/analytics inclusion, preservation of existing interview/correction/media/sync records, and rollback on migration integrity failure.

The public-link Chrome workflow signs in, selects the survey, creates a share link through **Share**, and opens it in a separate 390px browser context without an account. It collects UTF-8, multiple choices, a protected contact answer and a PDF; exercises conditional hiding and consent; simulates a lost server acknowledgement and retries the exact payload; verifies one public response, private-field exclusion in CSV, receipt recovery after reload, original questions after a newer publication, no mobile horizontal overflow, and link disabling.

The main Chrome workflow creates a survey through the UI, pastes a plain-text question list, reviews the three detected questions, publishes v1, collects UTF-8 text with commas/quotes/newlines plus multiple and numeric answers, verifies response counts, timeline charts, averages, summary CSV, long export, publishes changed labels as v2, confirms that the original response still exports with v1 labels, and permanently deletes the survey with typed-title confirmation. A separate Chrome workflow self-registers a new account, creates and publishes a survey immediately, and signs out. Both check for uncaught browser exceptions.

Backend coverage includes self-registration and isolated workspaces, email-based team invitations, project isolation, researcher row scopes, protected-field exclusion, identifiable export denial, metadata selection, declarative condition/validation handling, required empties, draft revision conflicts, idempotent submissions/corrections, immutable publication/originals, preserved correction chains, UTF-8/escaping/formula protection, original/raw data types, numeric/choice encoding, state-aware analytics, mean/median/mode/standard deviation/histograms, overview counts and timeline, answer/date/version/location filters, de-identified export IDs, starter duplication, export audits/interrupted streams, bounded-memory streaming, backups/repeated migrations, retention, and transactional confirmed survey deletion across all related records.

## User acceptance scenarios

| Scenario | Evidence | Status |
|---|---|---|
| 1. Custom questionnaire reaches native app and web/CSV | Web/API flow executed. Generic Flutter cache and renderer supplied. | **Partial**: native download/collection not executed. |
| 2. Offline collection and local Android CSV | SQLite store, offline renderer/exporter and FFI test source supplied. | **Unverified**: needs Flutter tests plus airplane-mode device run. |
| 3. Questionnaire changes retain original labels/data | Database immutability tests and real browser v1/v2 export workflow. | **Web/API verified**; Android version-cache compatibility unverified. |
| 4. Multiple-choice values preserved | Wide indicators and raw JSON tested; both choices selected in browser export. | **Web/API verified**; native exporter test not run. |
| 5. Commas, quotes, newlines, Filipino/UTF-8 | Tested round-trip CSV parsing plus actual browser-download content. | **Web/API verified**; Android test source supplied but not run. |
| 6. Privacy | API denies protected inclusion; default exports redact fields, own-row scoping and project isolation tested. | **Backend verified**; native document/share access not device-tested. |
| 7. Large server export | 3,000 interviews streamed without materializing response dataset; <2 MB traced Python peak. | **Representative automated test passed**; larger deployment benchmark outstanding. |
| 8. Counts/mappings/missing/answers match records | Parsed CSV compared to stored submissions/corrections; metadata/state/indicator/audit counts tested. | **Representative web/API tests passed**; full mobile end-to-end comparison outstanding. |

## Android verification procedure

Flutter/Dart are absent from this environment. After the README setup, run `flutter analyze` and `flutter test` before building an APK. Resolve any SDK/plugin compatibility or compile issues before describing the native client as working.

On an Android device/emulator:

1. Sign in to a test survey, publish a new non-starter questionnaire containing every supported type, and download it.
2. Enable airplane mode and make the API unavailable. Open the questionnaire, exercise conditional chains/defaults/bounds, complete two responses, leave another as a draft, kill/restart the app, and resume it.
3. Preview/export current version, selected responses, and all local responses, with and without drafts. Confirm UTF-8 CSV and dictionary/manifest against local SQLite records. Test save cancellation and at least Downloads and another document provider.
4. Share via an installed spreadsheet/mail app. Verify the URI is readable only with the granted permission. Check the manifest requests no broad storage access. Exercise location-denial and consent-denial flows.
5. Publish v2 with changed labels/options, reconnect, download, disconnect again, and export v1/v2 local responses. Confirm original schema labels and version qualification.
6. Interrupt sync after server acceptance but before client acknowledgement. Retry and verify exactly one response/correction. Try draft revision and correction-base conflicts. Explicitly reconcile server history and verify superseded local proposals remain visible.
7. Change protected-data/project grants while connected, refresh, and verify local listings/exports honor the new cache. Sign out/in as a different user and verify local data isolation.
8. Add media, interrupt upload, retry, verify protected references/downloads, and test recovery archive save/restore with pending sync/media. A different account or conflicting existing record must fail restoration without overwrite.

## Remaining functional limits

- No automatic semantic cross-version merge/coalescing; explicit version groups and version-qualified columns are implemented.
- No arbitrary report designer, custom role-definition designer, bulk protected attachment ZIP export, server collection of local export audits, or automatic background synchronization service. Synchronization is explicit from Android Sync.
- Hosted browser mode requires connectivity. The Windows desktop bundle runs its own local engine without internet; Android local operation is implemented in native source. No browser PWA is supplied.
- The Android Gradle wrapper binary and local SDK metadata must be generated with `flutter create` as documented; no APK or release signing has been produced.
- Instantaneous offline permission revocation and automatic anonymization of unclassified identifying free text are not guarantees the implementation makes.

These limits and unexecuted native checks mean the entire original requirements document is **not yet fully accepted**.
