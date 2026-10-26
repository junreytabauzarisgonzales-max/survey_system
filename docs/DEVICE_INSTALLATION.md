# Install on a device and keep data local

## Windows PC

The desktop application bundles the interface and Python/SQLite engine. It opens its own native window and starts a private engine on a random loopback port for that window. Users do not need Python, Node.js, a hosted server, or an internet connection after installation. Windows 10/11 with the Microsoft Edge WebView2 Runtime is required (normally already present on current Windows installations).

### Build and install

Build requirements: 64-bit Windows, Python 3.12+, Node.js 22.12+, and optionally [Inno Setup 6](https://jrsoftware.org/isinfo.php) to produce a setup installer.

From `web/`:

```powershell
npm ci
npm run build:app
```

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r desktop/requirements.txt
.\.venv\Scripts\Activate.ps1
.\desktop\build.ps1
```

- Run `dist/StudentSurveyCreator-Windows.exe` for the standalone application. This is a single-file executable suitable for the public download page; no companion directory is required.
- With Inno Setup's `ISCC.exe` on PATH, the build also creates `dist/StudentSurveyCreator-Setup.exe`. Otherwise compile `desktop/installer.iss` with Inno Setup after building. Run the setup file to install the app and its Start menu/desktop shortcuts for the current Windows user.
- For source development, use `python -m desktop.app` after installing dependencies and building the interface.

On first launch, select **Create a free account**. This creates an account in this PC's database; it does not register with an online service. Existing online accounts/data are not automatically downloaded. Create surveys, publish versions, add responses and view results normally.

### Where Windows data goes

```text
%LOCALAPPDATA%\StudentSurveyCreator\surveys.sqlite
```

The database includes accounts, surveys, responses, corrections, and attachment bytes. It is separate from the executable and installer directory. Restarting, updating, moving the portable program, or uninstalling the program does not delete this data directory. Each Windows user has a separate database. **Settings → Device storage** shows its exact path.

CSV, summary CSV, dictionaries and export manifests use the native **Save** dialog. Choose a folder on your device. **Settings → Save local recovery backup** creates an integrity-checked SQLite backup containing committed writes.

To restore a Windows backup, close all instances of the desktop app, preserve the current data directory separately, remove the old database and its matching `surveys.sqlite-wal` / `surveys.sqlite-shm` files if present, and place the verified backup at the database path above as `surveys.sqlite`. Reopen the app. Never replace the database while the app is running.

Existing `data/agal.sqlite` installations can be transferred by creating a verified backup with the existing backend backup command, then following the same restore steps. The desktop launcher does not silently move or overwrite existing data.

## Android phone or tablet

The Flutter app offers **Use device storage — no account needed** on its first screen. This opens a local workspace with no server connection:

1. Choose **Create local survey**, enter a title, consent statement and questions, then save.
2. Open the survey, collect a response, and save a draft or complete it. Changes autosave to SQLite.
3. Resume drafts from **Responses** after restarting the app. Completed originals remain immutable; reasoned corrections are saved locally and can be repeated without synchronization.
4. Export CSV through Android's document picker. Select **Downloads** or another local folder to save directly to device storage. The Share option only sends a file when explicitly chosen.
5. Under **Settings**, save a recovery backup to a chosen folder. A local-workspace recovery archive includes survey definitions, responses, corrections and attachment bytes, so it can restore an empty local workspace on another Android installation.

Question types include text, number, currency, rating, single/multiple choice, yes/no, date/time, media and coordinates. Saved local questionnaires are fixed snapshots; create another survey for a different questionnaire. The desktop app provides the fuller versioned builder and charts.

Android stores its SQLite database and attachments inside the app's private on-device storage. No broad storage permission is needed. **Uninstalling the Android app or clearing its app data deletes those private records.** Export a recovery backup to retain them. CSV alone is not a recovery backup. Automatic Android cloud backups are disabled. A document provider chosen by the user may itself be cloud-backed; select a local folder for device-only files.

### Build an APK

Requirements: Flutter stable / Dart >=3.5, Android SDK, JDK 17, Android API 23+ device.

From `mobile/`:

```powershell
flutter create --platforms=android --org org.agal --project-name agal_research .
flutter pub get
flutter analyze
flutter test
flutter build apk --debug
```

Keep existing source/configuration when generating the wrapper; do not pass `--overwrite`. Install `mobile/build/app/outputs/flutter-apk/app-debug.apk` on the device. This is a development-signed installable APK. Distribution releases need your own Android release-signing configuration.

A working Flutter/Android SDK toolchain is not available in the current workspace. Temporary Flutter initialization could not complete; Dart syntax parsing succeeded, but Android compilation, Flutter tests, picker behavior, airplane-mode operation and physical-device persistence still need to be verified using those commands and a device.

## Build downloads using GitHub Actions

The **Device builds** workflow (`.github/workflows/device-builds.yml`) can be started manually in GitHub Actions. It builds a standalone Windows EXE, a Windows setup installer and a development Android APK, runs the automated checks, and uploads them as downloadable artifacts. A final job builds the public website with both EXE/APK downloads included. Download and extract the artifact you need. It requires the repository and this workflow to be pushed first. See [website packaging and deployment](WEBSITE.md).

## Sharing and separate devices

Each installation has its own data. Saving on a phone does not automatically copy records to a PC or another phone. Transfer CSV for analysis or a same-platform recovery backup for recovery. Windows SQLite backups and Android JSON archives are different formats.

Public links created in the Windows local installation work only on that PC while its app is running. A local-only installation cannot accept internet responses from other devices. The optional hosted-server workflow and the Android **Connect to an existing server** mode remain available when online collaboration is required; choosing the local workspace does not upload data to them.

The supplied native targets are Windows and Android. iOS and macOS installers are not supplied.
