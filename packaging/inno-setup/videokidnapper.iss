; SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
; SPDX-License-Identifier: Apache-2.0
;
; Inno Setup script for the "real" Windows installer.
;
; Wraps the standalone PyInstaller .exe in a proper Setup wizard that
; registers in Programs & Features, creates a Start Menu shortcut, adds
; an optional desktop shortcut, and handles uninstall cleanly. This is
; the 90%-of-Windows-users install path — the portable .exe is still
; offered as a secondary "no install needed" option on the release page.
;
; Compiled by the installer.yml workflow after PyInstaller produces
; dist\VideoKidnapper.exe. To compile locally:
;
;   iscc.exe packaging\inno-setup\videokidnapper.iss
;
; Output lands at dist\VideoKidnapper-Setup-<version>.exe.
;
; The #define for MyAppVersion is passed by the CI runner so we don't
; have to maintain a version string in two places. When compiling
; locally, override it with /DMyAppVersion=1.2.0 on the iscc.exe
; command line.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif

#define MyAppName       "VideoKidnapper"
#define MyAppPublisher  "AES256Afro"
#define MyAppURL        "https://github.com/AES256Afro/VideoKidnapper"
#define MyAppExeName    "VideoKidnapper.exe"

[Setup]
; AppId is a permanent identity for this app — Inno uses it to find
; previous installs on upgrade. Keep stable across versions FOREVER.
AppId={{8C8E1A2F-5D4B-4E6A-9F32-7C1A5B2D6E84}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\..\LICENSE
; OutputDir is relative to the .iss file location; the workflow runs
; the compiler from the repo root so this resolves to repo\dist\.
OutputDir=..\..\dist
OutputBaseFilename=VideoKidnapper-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

; Brand icon: the Setup wizard's own .exe icon, and the icon shown in
; Programs & Features next to the uninstall entry.
SetupIconFile=..\..\videokidnapper\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; Install per-user by default (no admin prompt on modern Windows). A
; user with admin privileges can still choose machine-wide install via
; the "Install for all users" question in the wizard.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Windows 10 is our floor — PyInstaller + modern Tk won't run on 7/8.
MinVersion=10.0

; Architecture: the PyInstaller binary is built on x64 runner, so
; restrict install to x64 Windows.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The PyInstaller one-file .exe. The workflow drops it at dist\VideoKidnapper.exe
; before invoking iscc; this path is relative to the .iss file.
Source: "..\..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu entry — appears in "VideoKidnapper" submenu.
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
; Optional desktop shortcut (off by default; user opts in via [Tasks]).
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; In-app updates (videokidnapper/utils/self_update.py) run this installer
; with /SILENT /RELAUNCH=1 after the app has closed itself: reopen it as
; the user who started the update, even when the install was elevated.
Filename: "{app}\{#MyAppExeName}"; Flags: nowait runasoriginaluser; Check: RelaunchRequested
; Offer to launch after install — unchecked by default since the user
; may have closed the wizard intending to launch later.
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent unchecked

[UninstallDelete]
; The app writes settings to %USERPROFILE%\.videokidnapper_settings.json.
; We DON'T delete user settings on uninstall — leaving them lets a
; subsequent reinstall pick up where the user left off. Users who
; really want a clean wipe can delete the JSON by hand.

[Code]
// True when the in-app updater asked for the app to be reopened.
function RelaunchRequested: Boolean;
begin
  Result := ExpandConstant('{param:relaunch|0}') = '1';
end;

// How many copies of the app are running from where it is installed.
// With Ask, each is asked to close (a window close, as clicking X does);
// with Force, each is ended.
function RunningCopies(Ask, Force: Boolean): Integer;
var
  Locator, Service, Processes, Process: Variant;
  Target, Args: String;
  I, Pid, ResultCode: Integer;
begin
  Result := 0;
  Target := ExpandConstant('{app}\{#MyAppExeName}');
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Service := Locator.ConnectServer('.', 'root\CIMV2');
    Processes := Service.ExecQuery('SELECT ProcessId, ExecutablePath FROM Win32_Process ' +
                                   'WHERE Name = ''{#MyAppExeName}''');
    for I := 0 to Processes.Count - 1 do
    begin
      Process := Processes.ItemIndex(I);
      if VarIsNull(Process.ExecutablePath) then
        Continue;
      if CompareText(Process.ExecutablePath, Target) <> 0 then
        Continue;
      Result := Result + 1;
      Pid := Process.ProcessId;
      Args := '/PID ' + IntToStr(Pid);
      if Force then
        Args := '/F ' + Args;
      if Ask or Force then
        Exec(ExpandConstant('{sys}\taskkill.exe'), Args, '', SW_HIDE,
             ewWaitUntilTerminated, ResultCode);
    end;
  except
    Log('Could not list running copies: ' + GetExceptionMessage);
  end;
end;

// Wait up to Ms milliseconds for every running copy to be gone.
function AllClosed(Ms: Integer): Boolean;
var
  Waited: Integer;
begin
  Waited := 0;
  while (RunningCopies(False, False) > 0) and (Waited < Ms) do
  begin
    Sleep(250);
    Waited := Waited + 250;
  end;
  Result := RunningCopies(False, False) = 0;
end;

// The in-app updater starts this installer and then closes the app, so it
// can still be closing. Wait for it, then ask it to close, then end it.
// Restart Manager (/CLOSEAPPLICATIONS) could not do this on its own: the
// one-file .exe runs as a windowless launcher plus the app, the launcher
// can't be asked to close, the .exe stayed in use, and the silent upgrade
// stopped with exit code 5, leaving the app closed and not updated.
// Installs started by hand are left to Setup's usual "close applications".
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not RelaunchRequested then
    Exit;
  if AllClosed(8000) then
    Exit;
  Log('The app is still running; asking it to close.');
  RunningCopies(True, False);
  if AllClosed(8000) then
    Exit;
  Log('The app did not close; ending it.');
  RunningCopies(False, True);
  AllClosed(5000);
end;
