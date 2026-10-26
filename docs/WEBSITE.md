# Public website: documentation, tutorials and downloads

The default `web/` build is a static public information site. It has four routes:

- `/` — system overview and links to resources.
- `/documentation` — setup, questionnaire types, storage/backups, sharing and platform comparison.
- `/tutorials` — Windows/Android tutorials for creating surveys, collecting/resuming responses, CSV export and backup/restore. Platform and lesson selections are preserved in the URL.
- `/downloads` — Windows EXE and Android APK cards, package availability, file size, SHA-256 checksums and installation guidance.

The public site makes no survey API calls and requires no Python backend or database. Its static release manifest is generated at build time. The actual survey interface is separately built for the installed Windows app and optional hosted survey backend.

## Run locally

From `web/`:

```powershell
npm ci
npm run dev
```

For a production build and preview:

```powershell
npm run build
npm run preview
```

The static output is `web/dist/`. The independent survey-interface commands are `npm run dev:app` and `npm run build:app`; that output is `web/app-dist/`. The Python engine, Dockerfile and desktop packager use `app-dist`, so the installed system never opens the documentation homepage instead of the survey UI.

## Supply the actual download files

### Bundle files with the website

1. Build the survey interface with `npm run build:app` in `web/`.
2. On Windows, run `desktop/build.ps1` with its Python dependencies installed. It creates **`dist/StudentSurveyCreator-Windows.exe`**, a self-contained single-file executable. The old folder-based executable is not suitable for a direct single-file download.
3. With Flutter, Android SDK and JDK 17 installed, build `mobile/build/app/outputs/flutter-apk/app-debug.apk` using the [device installation guide](DEVICE_INSTALLATION.md).
4. Run `npm run build` in `web/`. `scripts/prepare-downloads.mjs` copies the EXE/APK into `web/public/releases/`, checks their binary signatures, calculates file sizes/SHA-256 hashes and generates `downloads.json`. Vite copies those releases into `web/dist/releases/`.

Packages can also be supplied directly in `web/public/releases/` as `StudentSurveyCreator-Windows.exe` and `StudentSurveyCreator-Android.apk`. The Android package is labeled as development-signed to match the supplied debug APK build process.

The website enables a download only if its file or an explicit external URL was supplied. A missing Android package is displayed as **Build pending**, not linked to an empty file or the source code. No APK was available in the local workspace when this page was implemented; Android SDK/JDK and a complete working Flutter toolchain were unavailable.

### Use external file hosting

For repository-based static deployments, upload the real EXE/APK to your chosen file host and configure these environment variables before the website build:

```text
WINDOWS_DOWNLOAD_URL=https://your-download-host.example/StudentSurveyCreator-Windows.exe
ANDROID_DOWNLOAD_URL=https://your-download-host.example/StudentSurveyCreator-Android.apk
```

Use public HTTPS URLs to the actual files, with `.exe` / `.apk` path extensions. These values are optional and take precedence over bundled files. External-host links do not display a computed checksum/size because the website build does not download those files. External servers control their own download headers.

Set `REQUIRE_DOWNLOADS=1` to reject a website build if either package is missing. By default the site still builds and clearly reports unavailable packages.

Generated packages and manifests are ignored by Git. Their presence in a developer’s working directory does not make them available to a fresh GitHub/Vercel checkout. Supply external URLs, stage the files in CI, or deploy from a local directory that contains the staged packages.

## Deploy the public website on Vercel

The root `vercel.json` installs/builds the website and publishes `web/dist`. It includes rewrites for the three documentation routes and download headers for bundled EXE/APK files.

**Git integration:** import this repository, keep the root directory at the repository root, and use the supplied configuration. Configure the external download URL environment variables if the files are hosted separately. No backend deployment, API variables, SQLite volume or Python runtime is needed.

**Local CLI deployment:** build/stage your packages first, then run `vercel --prod` from the repository root. `.vercelignore` excludes the backend, native build environments and intermediate outputs while including `web/public/releases/` for upload. The Vercel build runs again using the staged files.

The deployment must be initiated separately; adding configuration does not publish the website or packages automatically.

## Build both platforms in GitHub Actions

Run the manual **Device builds** workflow after pushing the changes. It produces:

- `Windows-download` — standalone Windows EXE.
- `Windows-setup` — optional Windows setup installer, compiled with Inno Setup on the runner.
- `Android-development-APK` — development-signed APK.
- `Website-with-downloads` — static site files containing both packages and the generated manifest. This final job requires both native builds to pass and sets `REQUIRE_DOWNLOADS=1`.

Download artifacts are CI build outputs; they are not public release URLs and are not automatically visible to Vercel’s Git integration. Deploy the website output or stage the files as described above.

## Verification

From `web/`:

```powershell
npm run build
npm run test:site
npm run build:app
npm run test:e2e
```

Public-site browser tests run against a static preview without a backend. They verify tutorial navigation/deep links, no survey API requests, real bundled downloads and checksums, honest unavailable states, manifest failure/retry, and mobile layouts. The separate existing application browser suite continues to test the survey system against an isolated temporary Python API/database.
