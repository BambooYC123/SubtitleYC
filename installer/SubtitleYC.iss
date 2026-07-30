#define AppName "SubtitleYC"
#ifndef AppVersion
#define AppVersion "0.3.0"
#endif
#ifndef AppDisplayVersion
#define AppDisplayVersion "0.3.0"
#endif

#ifndef AppEdition
#define AppEdition "External Tools Edition"
#endif
#ifndef SourceDir
#define SourceDir "..\dist\SubtitleYC"
#endif
#ifndef OutputDir
#define OutputDir "..\release"
#endif
#ifndef OutputBaseFilename
#define OutputBaseFilename "SubtitleYC-0.3.0-windows-setup"
#endif
#ifndef IconFile
#define IconFile "..\assets\SubtitleYC.ico"
#endif

[Setup]
AppId={{B5080F3A-8E40-4D62-845A-0B6254B2FD0F}
AppName={#AppName}
AppVersion={#AppDisplayVersion}
AppVerName={#AppName} {#AppDisplayVersion} - {#AppEdition}
AppPublisher=EricYC123
AppPublisherURL=https://github.com/EricYC123/SubtitleYC
AppSupportURL=https://github.com/EricYC123/SubtitleYC/issues
AppUpdatesURL=https://github.com/EricYC123/SubtitleYC/releases
DefaultDirName={code:GetDefaultDirName}
DefaultGroupName=SubtitleYC
DisableDirPage=no
DisableProgramGroupPage=yes
AllowNoIcons=no
UsePreviousAppDir=no
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBaseFilename}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
CloseApplications=yes
SetupLogging=yes
UninstallDisplayIcon={app}\SubtitleYC.exe
UninstallDisplayName={#AppName}
VersionInfoVersion={#AppVersion}
VersionInfoCompany=EricYC123
VersionInfoDescription=SubtitleYC desktop subtitle extraction and editing app - {#AppEdition}
VersionInfoProductName=SubtitleYC
VersionInfoCopyright=Copyright (C) 2026 EricYC123
LicenseFile=..\LICENSE
InfoBeforeFile=before-install.txt
SetupIconFile={#IconFile}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
SelectDirDesc=Choose where SubtitleYC's application files should be installed.
SelectDirLabel3=Program Files is recommended. To use another drive, choose its Program Files folder. Desktop and Start Menu shortcuts are created automatically.
ReadyMemoDir=Install folder:
ReadyMemoGroup=Start Menu folder:

[InstallDelete]
Type: filesandordirs; Name: "{app}\tools"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SubtitleYC"; Filename: "{app}\SubtitleYC.exe"; WorkingDir: "{app}"
Name: "{group}\Uninstall SubtitleYC"; Filename: "{uninstallexe}"
Name: "{autodesktop}\SubtitleYC"; Filename: "{app}\SubtitleYC.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\SubtitleYC.exe"; Description: "Launch SubtitleYC"; Flags: nowait postinstall skipifsilent

[Code]
const
  SubtitleYCUninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B5080F3A-8E40-4D62-845A-0B6254B2FD0F}_is1';

function QueryPreviousInstallValue(const ValueName: String; var Value: String): Boolean;
begin
  Result := RegQueryStringValue(HKCU, SubtitleYCUninstallKey, ValueName, Value);
  if not Result then
    Result := RegQueryStringValue(HKLM64, SubtitleYCUninstallKey, ValueName, Value);
  if not Result then
    Result := RegQueryStringValue(HKLM32, SubtitleYCUninstallKey, ValueName, Value);
end;

function IsProgramFilesInstall(const Path: String): Boolean;
var
  NormalizedPath: String;
begin
  NormalizedPath := Uppercase(AddBackslash(RemoveBackslashUnlessRoot(Path)));
  Result := Pos(':\PROGRAM FILES\', NormalizedPath) = 2;
end;

function GetDefaultDirName(Param: String): String;
var
  PreviousPath: String;
begin
  if QueryPreviousInstallValue('InstallLocation', PreviousPath) and
     IsProgramFilesInstall(PreviousPath) then
    Result := RemoveBackslashUnlessRoot(PreviousPath)
  else
    Result := ExpandConstant('{autopf}\SubtitleYC');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  PreviousUninstallString: String;
  PreviousUninstaller: String;
  ResultCode: Integer;
begin
  Result := '';
  if not QueryPreviousInstallValue('UninstallString', PreviousUninstallString) then
    Exit;

  PreviousUninstaller := RemoveQuotes(PreviousUninstallString);
  if not FileExists(PreviousUninstaller) then
    Exit;

  if not Exec(PreviousUninstaller, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '',
    SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    Result := 'SubtitleYC Setup could not remove the previous application version.'
  else if ResultCode <> 0 then
    Result := Format('The previous SubtitleYC uninstaller returned error code %d.', [ResultCode]);
end;
