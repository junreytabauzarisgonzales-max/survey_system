[Setup]
AppId=org.agal.StudentSurveyCreator
AppName=Student Survey Creator
AppVersion=1.0.0
DefaultDirName={localappdata}\Programs\StudentSurveyCreator
DefaultGroupName=Student Survey Creator
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=StudentSurveyCreator-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\StudentSurveyCreator.exe

[Files]
Source: "..\dist\StudentSurveyCreator-Windows.exe"; DestDir: "{app}"; DestName: "StudentSurveyCreator.exe"; Flags: ignoreversion

[Icons]
Name: "{group}\Student Survey Creator"; Filename: "{app}\StudentSurveyCreator.exe"
Name: "{autodesktop}\Student Survey Creator"; Filename: "{app}\StudentSurveyCreator.exe"

[Run]
Filename: "{app}\StudentSurveyCreator.exe"; Description: "Open Student Survey Creator"; Flags: nowait postinstall skipifsilent
