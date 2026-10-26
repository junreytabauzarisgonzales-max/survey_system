# Student Survey & Questionnaire Creator

A survey system for students with a standalone Windows desktop application, an Android local workspace, and a public documentation/tutorial/download website. Installed apps store surveys and responses directly on the device. The Windows app includes the React interface and Python/SQLite engine; Android uses Flutter and local SQLite. A hosted survey-server mode is also available.

Anyone can register and immediately create surveys. Each account owns its own workspace; surveys are private unless the owner invites teammates by email.

## Public website — documentation, tutorials and downloads

The default website is an information site with **Overview**, **Documentation**, **Tutorials** and **Downloads** pages. It can be hosted on Vercel without a backend. It includes Windows/Android walkthroughs, local-storage guidance, and real-package download availability.

From `web/`:

```powershell
npm ci
npm run dev
```

Use `npm run build` to produce a static-only `web/dist/`. The root Vercel configuration uses `npm run build:vercel` to include both the documentation site and the online workspace described below. The Windows EXE is staged automatically when built; the Android APK must be built/supplied before its download becomes available. See **[website deployment and download packaging](docs/WEBSITE.md)** for bundling files, external download URLs and CI artifacts.

## Hosted backend — Vercel + Neon PostgreSQL

The backend supports a hosted PostgreSQL database and a Vercel Python Function, with Neon Auth, Neon Object Storage and Neon Realtime wired into the hosted app. Set the variables from `.env.example` in Vercel's server-side environment variables, then deploy from the repository root. `DATABASE_URL_UNPOOLED` is used for migrations; the pooled `DATABASE_URL` serves application queries.

- `/` remains the documentation/download website.
- `/app/` opens the hosted survey workspace.
- `/survey/<token>` opens a public respondent questionnaire.
- `/api/*` uses Neon; `/api/health` checks database, Auth, storage and Realtime readiness.
- `/api/projects/<id>/live` returns a sealed Realtime capability after a server-side access check.

PostgreSQL migrations run on first API use, serialized across instances. Account/survey data persists in Neon; hosted attachment bytes are stored in the private `assets` bucket and deleted with their project. The Windows/Android device-local apps continue to use their own SQLite storage. No Neon credentials are required to build the frontend; only the Realtime WebSocket URL is embedded in the hosted bundle.

To run the combined portal and app locally against Neon:

```powershell
npm install
npm --prefix web ci
npm start
```

`npm start` runs the combined `build:vercel` build first, then starts the Python hosted server at `http://127.0.0.1:8765` and the local Realtime sealing sidecar. It reads `.env.local`, applies pending Neon migrations and serves `web/dist`. The Auth trusted origin and Realtime allowed origins must include `http://localhost:8765`.

See **[complete Vercel + Neon setup](docs/VERCEL_NEON.md)** for environment variables, payload limits, migrations, testing and backup behavior. Root `requirements.txt` installs the PostgreSQL driver; SQLite-only source operation still uses the Python standard library.

## Install on PC or mobile — device-local storage

- **Windows:** build/run `desktop/` to open the system in its own desktop window. Its database is `%LOCALAPPDATA%\StudentSurveyCreator\surveys.sqlite`. No hosted server or internet is required. Accounts are local to this PC. CSV and recovery backups save through native file dialogs.
- **Android:** choose **Use device storage — no account needed**. Create surveys, collect/autosave responses, export CSV and save/restore recovery backups without an initial download or connection. Records live in app-private device storage. Export a recovery backup before uninstalling or clearing app data.
- **Installation packages:** the Windows build script produces a standalone application and, with Inno Setup, a setup installer. Flutter produces an installable Android APK. A manual GitHub Actions workflow builds both packages.

See **[device installation, build commands and storage locations](docs/DEVICE_INSTALLATION.md)**. Each device has a separate database; there is no automatic upload or cross-device synchronization in local mode. Native targets supplied here are Windows and Android.

## What it does

- **Self-service accounts.** Register with a name, email and password (8+ characters). No approval or administrator setup is needed after the server starts.
- **Private surveys.** Every survey belongs to the account that created it. Owners can edit details, duplicate, archive, configure consent, share, delete old responses, or permanently delete a survey and all of its data.
- **Fast question builder.** Add questions one at a time, or paste a plain-text list from Word, Docs, a message or notes. The importer detects questions, choices, answer types, required markers and sections, then lets you review and correct everything before adding it.
- **Question types.** Short text, long text, single choice, multiple choice, yes/no, rating, number, currency, date, time and media.
- **Share by link.** Publish an immutable version and create a public link. Respondents answer in a mobile-friendly page with no account or sign-in. Links can expire or be disabled.
- **Responses and corrections.** Review completed responses and drafts, add a response yourself, and keep an auditable correction history instead of overwriting completed answers.
- **Graphical results.** See total/completed/draft counts, a response timeline, category bars and donut charts, numeric averages/medians/modes/standard deviations, and histograms. Download a summary CSV or print the page.
- **CSV export.** Wide, long, raw and analysis-ready files with filters, column previews, dictionaries, manifests and optional de-identification.
- **Device-local applications.** Standalone Windows window/engine with persistent SQLite and native exports/backups; Android local questionnaire creation, SQLite autosaves, attachment storage, CSV export and recovery. Optional server-connected Android mode also supports cached published forms and a durable sync outbox.

The optional starter templates are editable examples. Their domain-specific roles live only in template configuration, not in application logic or database tables.

## Run the survey interface / optional hosted backend

Requirements: Python 3.12+, Node.js 22.12+ and npm. SQLite-only operation uses the Python standard library. PostgreSQL operation additionally requires `python -m pip install -r requirements.txt` and a `DATABASE_URL` environment variable.

From the repository root:

```powershell
python -m backend.server --bootstrap-email admin@example.org
```

Enter an administrator password of at least 8 characters when prompted. No default accounts or passwords are installed. Running the command again with the same email does not replace that account. This bootstrap administrator is only needed for account management or cross-project support; ordinary users can self-register.

From `web/`:

```powershell
npm ci
npm run build:app
```

Then, from the repository root:

```powershell
python -m backend.server --db data/agal.sqlite --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. The server serves the survey interface from `web/app-dist/` and `/api`. The public documentation website uses the independent `web/dist/` build. The default database filename keeps its original internal name for compatibility with existing installations.

For survey-interface development, run the API on port 8000 and run `npm run dev:app` in `web/`. This mode proxies API requests to the backend.

### Deploy on Railway (free plan)

The included `Dockerfile` builds the web app and packages it with the API in one service. `railway.json` selects that Dockerfile and checks `/api/health`.

1. In Railway, create a project from this GitHub repository. Railway detects `railway.json` and builds the Docker image.
2. Add a volume to the service and mount it at **`/data`**. The server stores `/data/agal.sqlite` there, so surveys survive redeploys and restarts.
3. Generate a public domain under **Settings → Networking**. Open it and create an account through the normal sign-up form.

Railway's Free plan currently includes 0.5 GB of volume storage, 0.5 GB of RAM and $1 of monthly usage credit. That is enough for a small survey deployment, but attachments and large response sets can exceed the storage limit. If Railway cannot verify the account or the credit is exhausted, use an always-free VM such as Oracle Cloud Always Free and run the same Docker image with a persistent volume.

Back up the database with the Railway CLI. Run `railway login` and `railway link` once, then create the verified backup inside the running service and download it:

```powershell
railway ssh -- python -m backend.server --db /data/agal.sqlite --backup /data/agal-backup.sqlite
railway volume files download /agal-backup.sqlite ./agal-backup.sqlite
```

### Your first survey

1. Open the site and choose **New here? Create a free account**.
2. Open **My Surveys**, enter a title and optional description, and choose **Create survey**.
3. In **Questions**, add questions manually or choose **Paste questions** and paste a list such as:

   ```text
   Student life survey

   1. What is your year of study?
   - First year
   - Second year
   - Third year

   2. Which support services have you used? (select all that apply)
   - Library
   - Counseling
   - Career center

   3. Hours studied this week
   ```

4. Review the detected questions and answer types, then choose **Add questions**.
5. Publish a version, open **Share**, create a link and send it to respondents.
6. Open **Responses** to review answers, or **Results** for charts and averages.

Workspace owners can invite teammates by email under **Settings → Team access**. Roles control who can view, collect, correct or manage the survey. Identifiable-data access is a separate permission and is required for protected questions, media and coordinates.

## Share a survey link

1. Publish a version under **Questions**.
2. Open **Share**, select the published version, name the link, and optionally set an expiration.
3. Choose **Create link** and copy the shareable URL.
4. Respondents open `/survey/<unique-token>`, read the consent message, answer, and submit. They do not need an account.
5. Responses appear under **Responses** with source **Public link**. The link creator's account is not attributed to the respondent.

The share link uses the address currently open in the browser. To share outside your computer, deploy the app at a publicly reachable HTTPS address. A `localhost` link only works on that computer.

Links are pinned to the published version and consent statement. Create a new link to share a newer version. **Disable link** stops new responses immediately. Expiration, survey/questionnaire archival, or loss of the creator's required access also stops collection. Link changes are recorded in configuration history.

No account does not automatically mean anonymous. A survey can ask for contact information. Forms containing protected questions, media or coordinates require identifiable-data permission to share, and the creator must retain that permission. Public visitors receive only the shared questionnaire and declared location choices, never existing responses, respondent profiles, team details or private settings.

Public answers need a connection to submit. Unsent answers stay in page memory. A success receipt is stored so a reload does not resubmit accidentally; uncertain failures keep the exact payload for an idempotent retry. There is no identity-based one-response limit. Public attachments are submitted atomically with answers, up to 10 MiB total. Requests are rate-limited per client IP.

### Upgrading an existing database

Create a verified backup before restarting. Migration `002_public_surveys.sql` rebuilds the interview table to allow public responses without a fictitious researcher account. It preserves existing IDs, answers, timestamps, revisions, corrections, attachments and sync records, restores completed-record immutability, and validates all foreign keys before committing. Existing records become `source=researcher`. Failed integrity validation rolls back the migration.

Migration `003_project_deletion.sql` adds a project-deletion marker used by the confirmed permanent-delete operation. Published versions remain protected by the immutability trigger for all other deletes.

## Android setup

Requirements: Flutter stable with Dart >=3.5, Android SDK, JDK 17, and an emulator or device (API 23+). **Flutter is not installed in this workspace, so the Android source has not been compiled or device-tested here.**

From `mobile/`:

```powershell
flutter create --platforms=android --org org.agal --project-name agal_research .
flutter pub get
flutter analyze
flutter test
flutter run --debug
```

The `flutter create` step generates SDK-local metadata and the Gradle wrapper binary/scripts that are not included in this source-only workspace. Keep the supplied Android source/configuration files; do not pass `--overwrite`. Internal package identifiers (`agal_research`, `org.agal.research`) are retained for compatibility; the displayed app name is the Student Survey Creator.

For the Android emulator, use the server URL `http://10.0.2.2:8000`. For a physical device, use an HTTPS deployment URL. Cleartext access is limited to local development hosts.

### Offline fieldwork

- For fully local operation, choose **Use device storage — no account needed**, create a local survey and start collecting. See the [local-device guide](docs/DEVICE_INSTALLATION.md).
- For optional server-connected operation:
- Sign in and download published surveys before leaving connectivity.
- Open a survey to create a response. Draft changes are saved to local SQLite. Resume through **Responses**.
- Record informed consent before completion. Coordinates require explicit consent and an Android runtime location grant.
- Completed local originals cannot be edited. Save a reasoned correction instead. When a correction conflicts with server history, review and reconcile; local proposals remain visible as superseded history.
- Use **Sync** to upload pending responses, media and corrections. The persisted event payload retries with the same idempotency key.
- Export the current version, selected responses, or all authorized local responses. Choose whether drafts are included and preview the count before saving.
- A local CSV export is not synchronization. It creates a file without uploading responses or marking them synced.

Offline access uses the last successfully downloaded permission grant. Revocations take effect on the next successful online refresh. Sign-out clears credentials and leaves account-isolated local records for that account's next sign-in.

## Verification

From the root:

```powershell
python -m unittest discover -s backend/tests -v
python -m unittest discover -s desktop/tests -v
```

With desktop dependencies installed, `.venv/Scripts/python.exe -m desktop.smoke` opens and automatically closes an isolated native Windows test window to verify rendering and the local-storage bridge.

From `web/`:

```powershell
npm test
npm run build
npm run test:site
npm run build:app
npm run test:e2e
```

The browser tests use installed Google Chrome by default. Set `PLAYWRIGHT_CHANNEL=msedge` to use Edge. Website tests use a static preview with no backend. The survey application tests start an isolated temporary API/database with test-only credentials and never touch `data/agal.sqlite`. Coverage includes self-registration, creating a survey from pasted questions, collecting a response, charts/averages, summary and long CSV export, immutable labels after a new version, public-link sharing on a 390px viewport, retry receipts and link disabling.

Flutter tests are in `mobile/test/`. They include schema/CSV tests and an SQLite FFI offline completion/export/privacy test; none has been run here.

## Backups, deletion and retention

Create a verified server backup from the root:

```powershell
python -m backend.server --db data/agal.sqlite --backup data/backups/agal-backup.sqlite
```

This uses SQLite's online backup API, includes committed WAL data, and runs an integrity check. To restore, stop the server and restore the verified backup as the database file. Preserve the current database separately. Migrations run on startup and are recorded in `migrations`. Never replace a live SQLite file or copy only the `.sqlite` file while WAL writes are active.

Android **Settings** can save/restore an app-format JSON recovery archive, including original versions, responses, corrections, pending sync events and attachment bytes. It excludes login tokens. Restore requires the same account and already-downloaded, currently authorized original versions. Conflicting existing responses cause a transaction rollback rather than an overwrite. Archives are limited to 100 MiB; CSV is not a recovery backup. Automatic Android cloud backups are disabled.

Workspace owners can configure a retention period and explicitly apply it under **Settings**. Expired responses, attachments and corrections, and unreferenced expired respondent profiles/history are removed transactionally with a retention event. Retention does not erase separately downloaded files or older backups.

To permanently delete a survey, open **My Surveys**, expand **Survey options**, choose **Delete survey**, and type the survey title exactly. This transactionally removes the survey, its questionnaires and versions, share links and receipts, responses, corrections, attachments, respondents, team assignments, audits, sync results and project history. Downloaded files and older backups are not erased. Deletion is separate from **Archive**, which keeps the survey readable but stops collection.

## Architecture and limits

```text
backend/   migrations, authorization, validation, sync, exports, analytics, HTTP API
desktop/   native Windows window, bundled local engine, file dialogs, installer build
web/       public docs/tutorial/download site; separate local survey interface and tests
mobile/    Flutter collection app, local SQLite store, Android document/share bridge
docs/      API contract, CSV encoding, acceptance status
```

- No survey-specific tables. Answers reference immutable version schemas with UUID question identifiers. Respondent field definitions are snapshotted with each profile.
- Conditions are declarative comparisons against earlier questions; no author JavaScript, SQL, Dart or Python is executed.
- Form limits: 100 sections, 2,000 questions, 1,000 choices per question. Response listings are paginated. Attachments are limited to 10 MiB each.
- Server CSV generation streams one response at a time. Browser downloads buffer the received file into a Blob; extremely large downloads may hit browser memory limits.
- Version-qualified columns preserve original labels. Automatic semantic mapping of changed questions and a general custom report designer are not implemented.
- Personal-field exclusion and optional per-export pseudonyms are de-identification controls, not automatic detection of identifying information in free text. Authors must mark identifying questions as protected. CSV attachments are references, not embedded files.
- Android compilation, native document-provider/share behavior, process-restart recovery and airplane-mode acceptance still require verification. No APK or release-signing configuration is supplied.

For deployment, run behind an HTTPS reverse proxy with request/time limits and restricted database/backup file access. The included standard-library HTTP server is a functional single-node service, not a horizontally scaled deployment stack.

Further details: [API and schema](docs/API.md) · [CSV contract](docs/CSV.md) · [acceptance status](docs/ACCEPTANCE.md).
