#define AppName "SubtitleYC"
#ifndef AppVersion
#define AppVersion "0.5.2"
#endif
#ifndef AppDisplayVersion
#define AppDisplayVersion "0.5.2"
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
#define OutputBaseFilename "SubtitleYC-0.5.2-windows-setup"
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
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

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
