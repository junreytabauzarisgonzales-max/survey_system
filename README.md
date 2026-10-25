# Student Survey & Questionnaire Creator

A simple survey platform for students: create an account, build or paste questions, share a public link, collect answers, and see charts and averages. It includes a React web app, a standard-library Python/SQLite API, and a Flutter Android client for offline collection.

Anyone can register and immediately create surveys. Each account owns its own workspace; surveys are private unless the owner invites teammates by email.

## What it does

- **Self-service accounts.** Register with a name, email and password (8+ characters). No approval or administrator setup is needed after the server starts.
- **Private surveys.** Every survey belongs to the account that created it. Owners can edit details, duplicate, archive, configure consent, share, delete old responses, or permanently delete a survey and all of its data.
- **Fast question builder.** Add questions one at a time, or paste a plain-text list from Word, Docs, a message or notes. The importer detects questions, choices, answer types, required markers and sections, then lets you review and correct everything before adding it.
- **Question types.** Short text, long text, single choice, multiple choice, yes/no, rating, number, currency, date, time and media.
- **Share by link.** Publish an immutable version and create a public link. Respondents answer in a mobile-friendly page with no account or sign-in. Links can expire or be disabled.
- **Responses and corrections.** Review completed responses and drafts, add a response yourself, and keep an auditable correction history instead of overwriting completed answers.
- **Graphical results.** See total/completed/draft counts, a response timeline, category bars and donut charts, numeric averages/medians/modes/standard deviations, and histograms. Download a summary CSV or print the page.
- **CSV export.** Wide, long, raw and analysis-ready files with filters, column previews, dictionaries, manifests and optional de-identification.
- **Offline Android source.** Cached published forms, local SQLite autosaves, a durable sync outbox, attachment upload and local CSV export.

The optional starter templates are editable examples. Their domain-specific roles live only in template configuration, not in application logic or database tables.

## Run the web app

Requirements: Python 3.12+, Node.js 22.12+ and npm. The backend uses the Python standard library; no Python packages are required.

From the repository root:

```powershell
python -m backend.server --bootstrap-email admin@example.org
```

Enter an administrator password of at least 8 characters when prompted. No default accounts or passwords are installed. Running the command again with the same email does not replace that account. This bootstrap administrator is only needed for account management or cross-project support; ordinary users can self-register.

From `web/`:

```powershell
npm ci
npm run build
```

Then, from the repository root:

```powershell
python -m backend.server --db data/agal.sqlite --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. The server serves both the built web app and `/api`. The default database filename keeps its original internal name for compatibility with existing installations.

For web development, run the API on port 8000 and run `npm run dev` in `web/`. Vite proxies API requests to the backend.

### Deploy on Railway (free plan)

The included `Dockerfile` builds the web app and packages it with the API in one service. `railway.json` selects that Dockerfile and checks `/api/health`.

1. In Railway, create a project from this GitHub repository. Railway detects `railway.json` and builds the Docker image.
2. Add a volume to the service and mount it at **`/data`**. The server stores `/data/agal.sqlite` there, so surveys survive redeploys and restarts.
3. Generate a public domain under **Settings → Networking**. Open it and create an account through the normal sign-up form.

Railway's Free plan currently includes 0.5 GB of volume storage, 0.5 GB of RAM and $1 of monthly usage credit. That is enough for a small survey deployment, but attachments and large response sets can exceed the storage limit. If Railway cannot verify the account or the credit is exhausted, use an always-free VM such as Oracle Cloud Always Free and run the same Docker image with a persistent volume.

Back up the database from the Railway CLI with:

```powershell
railway run python -m backend.server --db /data/agal.sqlite --backup /data/agal-backup.sqlite
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
```

From `web/`:

```powershell
npm test
npm run build
npm run test:e2e
```

The browser tests use installed Google Chrome by default. Set `PLAYWRIGHT_CHANNEL=msedge` to use Edge. They start an isolated temporary API/database with test-only credentials and never touch `data/agal.sqlite`. Coverage includes self-registration, creating a survey from pasted questions, collecting a response, charts/averages, summary and long CSV export, immutable labels after a new version, public-link sharing on a 390px viewport, retry receipts and link disabling.

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
web/       React survey app, question importer, public respondent page, charts, acceptance tests
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
