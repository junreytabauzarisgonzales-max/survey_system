# Website download files

`npm run build` generates `downloads.json` and stages real packages here. Generated files are ignored by Git.

- Windows: build `dist/StudentSurveyCreator-Windows.exe` using `desktop/build.ps1`, or place that single-file executable here.
- Android: build `mobile/build/app/outputs/flutter-apk/app-debug.apk`, or place a development APK here as `StudentSurveyCreator-Android.apk`.
- For externally hosted files, set `WINDOWS_DOWNLOAD_URL` and `ANDROID_DOWNLOAD_URL` to public HTTPS URLs ending in `.exe` and `.apk`.

Run `npm run prepare:downloads` after changing packages. The build records file sizes and SHA-256 checksums for bundled files. Missing packages are visibly unavailable, never linked to placeholder files. Set `REQUIRE_DOWNLOADS=1` to fail the website build if either package is missing.

The Android package is labeled as a development build; use the development APK produced by the supplied workflow. A future signed production release should update its labeling and build configuration together.
