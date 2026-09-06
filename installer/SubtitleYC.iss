#define AppName "SubtitleYC"
#ifdef WebInstaller
#include WebPayloadInclude
#endif
#ifndef AppVersion
#define AppVersion "0.6.0"
#endif
#ifndef AppDisplayVersion
#define AppDisplayVersion "0.6.0"
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
#define OutputBaseFilename "SubtitleYC-0.6.0-windows-setup"
#endif
#ifndef IconFile
#define IconFile "..\assets\SubtitleYC.ico"
#endif

[Setup]
AppId={{B5080F3A-8E40-4D62-845A-0B6254B2FD0F}
AppName={#AppName}
AppVersion={#AppDisplayVersion}
AppVerName={#AppName} {#AppDisplayVersion} - {#AppEdition}
AppPublisher=BambooYC123
AppPublisherURL=https://github.com/BambooYC123/SubtitleYC
AppSupportURL=https://github.com/BambooYC123/SubtitleYC/issues
AppUpdatesURL=https://github.com/BambooYC123/SubtitleYC/releases
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
#ifdef WebInstaller
ArchiveExtraction=full
#endif
#ifdef SplitPayload
; Keep the executable small so Windows can finish checking it before showing Setup.
DiskSpanning=yes
DiskSliceSize=1000000000
SlicesPerDisk=1
#endif
WizardStyle=modern
ShowLanguageDialog=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
CloseApplications=yes
SetupLogging=yes
UninstallDisplayIcon={app}\SubtitleYC.exe
UninstallDisplayName={#AppName}
VersionInfoVersion={#AppVersion}
VersionInfoCompany=BambooYC123
VersionInfoDescription=SubtitleYC desktop subtitle extraction and editing app - {#AppEdition}
VersionInfoProductName=SubtitleYC
VersionInfoCopyright=Copyright (C) 2026 BambooYC123
LicenseFile=..\LICENSE
InfoBeforeFile=before-install.txt
SetupIconFile={#IconFile}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"; InfoBeforeFile: "before-install.txt"
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"; InfoBeforeFile: "before-install.zh-CN.txt"

[Messages]
english.SelectDirDesc=Choose where SubtitleYC's application files should be installed.
english.SelectDirLabel3=Program Files is recommended. To use another drive, choose its Program Files folder. Desktop and Start Menu shortcuts are created automatically.
english.ReadyMemoDir=Install folder:
english.ReadyMemoGroup=Start Menu folder:
chinesesimplified.SelectDirDesc=选择 SubtitleYC 应用文件的安装位置。
chinesesimplified.SelectDirLabel3=建议安装到 Program Files。若要使用其他驱动器，请选择该驱动器的 Program Files 文件夹。安装程序会自动创建桌面和开始菜单快捷方式。
chinesesimplified.ReadyMemoDir=安装文件夹：
chinesesimplified.ReadyMemoGroup=开始菜单文件夹：

[CustomMessages]
english.LaunchSubtitleYC=Launch SubtitleYC
chinesesimplified.LaunchSubtitleYC=启动 SubtitleYC

[InstallDelete]
Type: filesandordirs; Name: "{app}\tools"

[Files]
#ifdef WebInstaller
Source: "{tmp}\{#WebAppFile}"; DestDir: "{app}"; ExternalSize: {#WebAppInstalled}; Hash: "{#WebAppHash}"; Flags: external extractarchive ignoreversion recursesubdirs createallsubdirs
Source: "{tmp}\{#WebCpuFile}"; DestDir: "{app}\tools\VideOCR"; ExternalSize: {#WebCpuInstalled}; Hash: "{#WebCpuHash}"; Flags: external extractarchive ignoreversion recursesubdirs createallsubdirs
#else
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#endif

[Icons]
Name: "{group}\SubtitleYC"; Filename: "{app}\SubtitleYC.exe"; WorkingDir: "{app}"
Name: "{group}\Uninstall SubtitleYC"; Filename: "{uninstallexe}"
Name: "{autodesktop}\SubtitleYC"; Filename: "{app}\SubtitleYC.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\SubtitleYC.exe"; Description: "{cm:LaunchSubtitleYC}"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKLM; Subkey: "Software\SubtitleYC"; ValueType: string; ValueName: "InstallerUILanguage"; ValueData: "{language}"; Flags: uninsdeletevalue
Root: HKLM; Subkey: "Software\SubtitleYC"; ValueType: string; ValueName: "InstallerVersion"; ValueData: "{#AppVersion}"; Flags: uninsdeletevalue

[Code]
#ifdef WebInstaller
var
  DownloadPage: TDownloadWizardPage;
  PayloadReady: Boolean;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage('Download SubtitleYC {#AppVersion} and CPU OCR',
    'Internet is required. CPU OCR is included in setup; GPU OCR is optional in the app.', nil);
  DownloadPage.ShowBaseNameInsteadOfUrl := True;
  WizardForm.ReadyLabel.Caption := 'Setup will download {#WebDownloadMiB} MiB and install SubtitleYC {#AppVersion} with CPU OCR ({#WebInstalledGiB} GiB). Internet is required. GPU OCR is optional afterward.';
  if ActiveLanguage = 'chinesesimplified' then
    WizardForm.ReadyLabel.Caption := '安装程序将下载 {#WebDownloadMiB} MiB，并安装 SubtitleYC {#AppVersion} 和 CPU OCR（{#WebInstalledGiB} GiB）。需要联网。GPU OCR 可稍后选装。';
end;

function DownloadPayload: String;
var
  FreeBytes, TotalBytes: Int64;
begin
  Result := '';
  if PayloadReady then Exit;
  if GetSpaceOnDisk64(ExpandConstant('{tmp}'), FreeBytes, TotalBytes) then
    if FreeBytes < {#WebDownloadBytes} + 268435456 then begin
      Result := 'Not enough temporary disk space for the downloads. Free space and retry.';
      Exit;
    end;
  DownloadPage.Clear;
  DownloadPage.Add('{#WebAppUrl}', '{#WebAppFile}', '{#WebAppHash}');
  DownloadPage.Add('{#WebCpuUrl}', '{#WebCpuFile}', '{#WebCpuHash}');
  DownloadPage.Show;
  try
    try
      DownloadPage.Download;
      PayloadReady := True;
    except
      Result := 'Download did not complete. Your existing installation has not been removed. Retry setup when ready. ' + GetExceptionMessage;
    end;
  finally
    DownloadPage.Hide;
  end;
end;
#endif

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
#ifdef WebInstaller
  FreeBytes, TotalBytes: Int64;
#endif
begin
  Result := '';
#ifdef WebInstaller
  Result := DownloadPayload;
  if Result <> '' then Exit;
  { Recheck target space after downloads consume temporary space, before uninstalling. }
  if not GetSpaceOnDisk64(AddBackslash(ExtractFileDrive(WizardDirValue)), FreeBytes, TotalBytes) then begin
    Result := 'Could not check free space on the installation drive. Choose another location and retry.';
    Exit;
  end;
  if FreeBytes - {#WebAppInstalled} < {#WebCpuInstalled} + 268435456 then begin
    Result := 'Not enough free space on the installation drive. Setup needs {#WebInstalledGiB} GiB plus 256 MiB while the downloaded archives are held temporarily. Your existing installation has not been removed.';
    Exit;
  end;
#endif
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
