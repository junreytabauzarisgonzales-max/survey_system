$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
if (!(Test-Path -LiteralPath "$root\web\app-dist\index.html")) {
    throw 'Run npm ci and npm run build:app in web/ first.'
}
python -m PyInstaller --noconfirm --clean --windowed --onefile --name StudentSurveyCreator-Windows --paths "$root" --distpath "$root\dist" --workpath "$root\build" --specpath "$root\build" --collect-all webview --add-data "$root\web\app-dist;web/app-dist" --add-data "$root\backend\migrations;backend/migrations" --add-data "$root\backend\templates.json;backend" "$PSScriptRoot\launcher.py"
if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed.' }
$compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($compiler) {
    & $compiler.Source "$PSScriptRoot\installer.iss"
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
} else {
    Write-Host "Single-file desktop app built at $root\dist\StudentSurveyCreator-Windows.exe. Install Inno Setup 6 and run ISCC desktop\installer.iss to create the installer."
}
