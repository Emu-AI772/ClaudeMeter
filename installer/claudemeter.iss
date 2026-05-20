; ClaudeMeter Installer Script
; Requires Inno Setup 6+ from https://jrsoftware.org/isinfo.php
; Build: Run build_installer.bat or open this in Inno Setup IDE

#define AppName "ClaudeMeter"
#define AppVersion "2.0.0"
#define AppPublisher "Wayne O"
#define AppExeName "ClaudeMeter.exe"
#define AppDescription "Claude API Usage Monitor - Based on usage-monitor-for-claude by jens-duttke"
#define SourceDir "..\dist"
#define IconFile "..\claudemeter.ico"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://github.com/jens-duttke/usage-monitor-for-claude
AppSupportURL=https://github.com/jens-duttke/usage-monitor-for-claude
AppUpdatesURL=https://github.com/jens-duttke/usage-monitor-for-claude
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
LicenseFile=
OutputDir=..\installer_output
OutputBaseFilename=ClaudeMeterSetup_v{#AppVersion}
SetupIconFile={#IconFile}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=110
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppDescription}
VersionInfoProductName={#AppName}

; Minimum Windows 10
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked
Name: "startupicon"; Description: "Start {#AppName} automatically when Windows starts"; GroupDescription: "Startup:"; Flags: checkedonce

[Files]
Source: "{#SourceDir}\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; Include icon for uninstaller
Source: "{#IconFile}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\claudemeter.ico"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
; Desktop (optional)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\claudemeter.ico"; Tasks: desktopicon

[Registry]
; Start with Windows (optional task)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "{#AppName}"; \
  ValueData: """{app}\{#AppExeName}"""; \
  Flags: uninsdeletevalue; Tasks: startupicon

[Run]
; Launch after install
Filename: "{app}\{#AppExeName}"; \
  Description: "Launch {#AppName} now"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
; Stop the app before uninstalling
Filename: "taskkill"; Parameters: "/f /im {#AppExeName}"; \
  Flags: runhidden; RunOnceId: "StopApp"

[UninstallDelete]
; Clean up log files if user wants (optional — commented out to preserve data)
; Type: filesandordirs; Name: "{userdocs}\ClaudeMeter"

[Code]
// Check if .NET WebView2 runtime is available (required by pywebview)
function IsWebView2Installed(): Boolean;
var
  Version: String;
begin
  Result := RegQueryStringValue(
    HKLM,
    'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'pv', Version
  ) and (Version <> '') and (Version <> '0.0.0.0');

  if not Result then
    Result := RegQueryStringValue(
      HKCU,
      'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
      'pv', Version
    ) and (Version <> '') and (Version <> '0.0.0.0');
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if not IsWebView2Installed() then begin
    if MsgBox(
      'ClaudeMeter requires Microsoft Edge WebView2 Runtime, which does not appear to be installed.' + #13#10 + #13#10 +
      'Most Windows 10/11 systems already have it via Windows Update.' + #13#10 +
      'If ClaudeMeter does not start after install, download it from:' + #13#10 +
      'https://developer.microsoft.com/microsoft-edge/webview2/' + #13#10 + #13#10 +
      'Continue with installation?',
      mbConfirmation, MB_YESNO
    ) = IDNO then
      Result := False;
  end;
end;
