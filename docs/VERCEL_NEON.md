# Deploy the hosted survey backend on Vercel with Neon

The root Vercel configuration now deploys both the public documentation website and a PostgreSQL-backed online survey system on the same domain:

| URL | Purpose |
|---|---|
| `/` | Documentation/download website with an online-workspace link |
| `/documentation`, `/tutorials`, `/downloads` | Public information pages |
| `/app/` | Online account and survey-management interface |
| `/survey/<token>` | Public respondent questionnaire |
| `/api/*` | Python Vercel Function backed by Neon PostgreSQL |
| `/api/health` | Database, Auth, object-storage and Realtime readiness |
| `/api/projects/<id>/live` | Server-checked, sealed Neon Realtime capability |

The installed Windows and Android local workspaces still use their own on-device SQLite databases. Their local accounts/data are independent from the hosted database.

## 1. Provision the Neon services

The fastest path is the Neon CLI, which links the repository and writes a `neon.ts` service policy:

```powershell
npm install -g neon@latest
neon login
neon init --name survey_system --no-agent-setup `
  --services postgres --services auth --services object-storage --services realtime
neon deploy -y
```

`neon init` writes `.neon`, `neon.ts`, a root `package.json` and `.env.local`. The CLI's comma-separated `--services` form is not accepted in every version; repeat the flag as shown.

The `neon.ts` policy must include the local and deployed browser origins:

```ts
preview: { realtime: { allowedOrigins: ["http://localhost:8765"] } },
auth: true,
buckets: { assets: { access: "private" } },
```

Add the production Vercel origin to `preview.realtime.allowedOrigins` and to the Auth trusted domains before deploying. `neon deploy -y` enables the services and pulls the values into `.env.local`; never commit that file.

| Service | Variable(s) |
|---|---|
| PostgreSQL | `DATABASE_URL`, `DATABASE_URL_UNPOOLED`, `NEON_BRANCH` |
| Neon Auth | `NEON_AUTH_BASE_URL`, `NEON_AUTH_JWKS_URL` |
| Object Storage | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL_S3`, `AWS_REGION` |
| Realtime | `NEON_REALTIME_URL`, `NEON_REALTIME_SECRET` |

The database role must be able to create tables, indexes, triggers and functions during migrations. The owner role for a fresh Neon database is suitable. Use a dedicated application database rather than an unrelated schema.

Only the server reads connection URLs, storage credentials and the Realtime secret. The browser bundle contains only `NEON_REALTIME_URL`; the secret is used by the Node sealing function. `.env` files are ignored by Git and Vercel uploads; `.env.example` contains placeholders only.

## 2. Configure Vercel

Import the GitHub repository into Vercel, or use the existing Vercel project:

- **Root Directory:** repository root.
- **Framework Preset:** Other / use the root `vercel.json` configuration.
- **Build Command:** supplied by the repository (`npm --prefix web ci && npm --prefix web run build:vercel`). Remove a dashboard override that still runs the old static-only build.
- **Output Directory:** `web/dist`.
- **Python:** 3.12, selected by `.python-version`.

Add these server-side environment variables (copy names from `.env.example`):

| Variable | Value |
|---|---|
| `DATABASE_URL` | Neon pooled PostgreSQL URL |
| `DATABASE_URL_UNPOOLED` | Neon direct PostgreSQL URL, used for migrations |
| `AUTO_MIGRATE` | `1` |
| `NEON_AUTH_BASE_URL` | Managed Auth base URL from `neon deploy` |
| `NEON_AUTH_JWKS_URL` | Managed Auth JWKS URL |
| `NEON_AUTH_ORIGIN` | Canonical app origin, e.g. `https://your-project.vercel.app` |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Object Storage credentials |
| `AWS_ENDPOINT_URL_S3` / `AWS_REGION` | Object Storage endpoint and region |
| `NEON_STORAGE_BUCKET` | `assets` (private bucket) |
| `NEON_REALTIME_URL` | Realtime WebSocket URL (also embedded in the browser bundle) |
| `NEON_REALTIME_SECRET` | Realtime signing secret (server-only) |

Set production variables for the production deployment. If using preview deployments, give previews their own Neon test branch/database and their own allowed origins.

No SQLite volume, administrator bootstrap password, public database credential, CORS URL or separately running HTTP server is needed. Users create ordinary accounts through `/app/`; Neon Auth owns the passwords while the app keeps its existing local sessions and project permissions.

The existing optional `WINDOWS_DOWNLOAD_URL` and `ANDROID_DOWNLOAD_URL` variables still configure downloadable app packages. Those are independent of the backend database settings.

## 3. Deploy and initialize

Deploy after the new source and environment variables are available in Vercel. Changing environment variables requires a new deployment.

Builds do not connect to the database. On the first API request, the function applies the PostgreSQL migration files under `backend/postgres_migrations/` using `DATABASE_URL_UNPOOLED` when present. A transaction-scoped PostgreSQL advisory lock serializes initialization across concurrent function instances. The migration ledger prevents replaying completed migrations.

Open:

```text
https://YOUR-PROJECT.vercel.app/api/health
```

Expected response:

```json
{
  "status": "ok",
  "database": "postgresql",
  "services": {"auth": true, "object_storage": true, "realtime": true},
  "limits": {
    "request_bytes": 4194304,
    "attachment_bytes": 2097152,
    "response_bytes": 4194304
  }
}
```

Then open `/app/`, create an account, create a survey, publish a questionnaire version and create a share link. Share links point to `/survey/<token>` on the same domain.

An unset/invalid `DATABASE_URL` returns a configuration error with HTTP 503. There is no hosted fallback to a temporary SQLite file.

### Explicit migrations

To run migrations before accepting traffic, install dependencies and set `DATABASE_URL_UNPOOLED` (or `DATABASE_URL`) in your shell:

```powershell
python -m pip install -r requirements.txt
# Set DATABASE_URL_UNPOOLED in your shell to your direct connection URL.
python -m backend.migrate
```

This command reads the URL from the environment and does not print it. Set `AUTO_MIGRATE=0` only after explicitly applying the migrations. Plain `python` does not automatically load a local `.env` file; set the environment variable in the shell or use Vercel's environment-variable injection.

## Storage and consistency

- Accounts, sessions, surveys, immutable questionnaire versions, answers, corrections, history, receipts, exports and attachment metadata are stored in PostgreSQL.
- Hosted attachment bytes use Neon Object Storage in the private `assets` bucket under `attachments/<interview>/<attachment>`. The database keeps the `storage_key`; no upload is stored on the function's filesystem. Project deletion and retention remove the corresponding objects.
- Offline SQLite installations keep attachment bytes in the local database.
- Neon Auth stores hosted passwords. The app maps the verified Auth user ID to its local user row and keeps issuing its existing session tokens, so project roles and researcher scoping are unchanged. Existing local password accounts fall back to the legacy verifier only when Auth is not configured.
- The local SQLite backup command is not used for Neon. Use Neon recovery/branching features or PostgreSQL `pg_dump` for hosted backups.
- Existing SQLite databases are not automatically imported into Neon. The new hosted database begins as a separate workspace; local files are preserved.
- Write transactions that previously used SQLite `BEGIN IMMEDIATE` use a transaction-scoped PostgreSQL advisory lock to preserve revision/idempotency checks across function instances. This retains the existing single-writer consistency model rather than silently allowing conflicting updates.
- Correction order uses a generated database sequence rather than timestamps or random UUID ordering.
- CSV exports read through a server-side cursor and a repeatable-read snapshot. Hosted exports are staged in a bounded temporary spool solely to validate their final size before returning a file. This spool is not durable application storage.
- Login, registration and public-submission request limits use atomic PostgreSQL records shared across Vercel instances. Hosted limits use 60-second windows; stored client keys are hashed.
- Connections are closed after each database operation/transaction. Use Neon's pooled URL; server-side prepared-statement caching is disabled for compatibility with transaction pooling.

## Live response counts

The Results page shows a live response count. The browser requests `/api/projects/<id>/live`; on Vercel this is rewritten to the Node function `api/live.js`, which:

1. Reads the app session token and validates it against `sessions`/`users` in PostgreSQL.
2. Rechecks that the caller is a member of the project.
3. Seals a parameterized `interviews` count query with `NEON_REALTIME_SECRET`.

The browser subscribes with `@neon/realtime/client` using `NEON_REALTIME_URL`. The secret never enters the frontend bundle. Capabilities are renewed from the same endpoint when they expire.

Locally, `npm start` runs the same Node function on port 8790 and sets `REALTIME_SEAL_URL` so the Python server proxies `/api/projects/<id>/live` to it. `neon.ts` must trust the local origins:

```ts
preview: {
  realtime: {
    allowedOrigins: ["http://localhost:8765", "http://127.0.0.1:8765"],
  },
}
```

Add the exact production origin (for example `https://your-project.vercel.app`) before deploying. A missing or unlisted origin produces a Realtime connection error; Auth also rejects sign-in from an untrusted origin.

## Hosted payload limits

The Vercel entry point caps JSON requests and responses/CSV files at **4 MiB**, below the platform payload ceiling. Hosted attachment uploads are capped at **2 MiB** per staff upload or in total per public response, leaving space for base64 encoding and questionnaire answers. The public questionnaire reports this limit and the hosted browser interface checks it before reading files.

Oversized exports return HTTP 413 before CSV headers rather than producing a partial download; narrow the version/date/location/answer filters and export smaller datasets. The function duration is configured for 60 seconds. Very long operations remain subject to Vercel execution limits.

Desktop/local server mode retains its existing 10 MiB attachment limit and streaming-export behavior. Android's server-connected mode receives the hosted API's size errors if a local attachment is larger than the hosted limit.

## Local verification

SQLite/local regression suite:

```powershell
python -m unittest discover -s backend/tests -v
```

PostgreSQL integration suite, using a **dedicated test database** with schema-creation permission:

```powershell
python -m pip install -r requirements.txt
# Set TEST_POSTGRES_URL to the dedicated test database URL.
python -m unittest discover -s backend/postgres_tests -v
```

The integration suite creates a random isolated schema per test, then drops it. It reuses the existing platform/public-survey scenarios and adds cross-instance request limits, concurrent retries/revision checks and hosted payload checks. These tests use a normal unpooled PostgreSQL test connection so per-test `search_path` startup options are available.

To run the combined portal and app against the real Neon project on this machine:

```powershell
npm run build:vercel
npm start
```

`npm start` loads `.env.local`, applies pending migrations, serves `web/dist` at `http://127.0.0.1:8765` and starts the Realtime sealing sidecar on port 8790. `GET /api/health` should report `auth`, `object_storage` and `realtime` as `true`.

From `web/`, with the same test environment and Python dependencies available:

```powershell
npm run build:vercel
npm run test:hosted
```

Set `HOSTED_TEST_PYTHON` if the Python interpreter with psycopg is not the default `python`. The browser test verifies the documentation homepage, `/app/` assets/login, a real public survey submission and the saved PostgreSQL answer. Local verification is not a substitute for checking the deployed URL with your actual Neon connection.

References: [Vercel Python functions](https://vercel.com/docs/functions/runtimes/python/api-directory) · [Neon connection pooling](https://neon.tech/docs/connect/connection-pooling).
