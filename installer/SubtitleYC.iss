#define AppName "SubtitleYC"
#ifdef WebInstaller
#include WebPayloadInclude
#endif
#ifndef AppVersion
#define AppVersion "0.7.1"
#endif
#ifndef AppDisplayVersion
#define AppDisplayVersion "0.7.1"
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
#define OutputBaseFilename "SubtitleYC-0.7.1-windows-setup"
#endif
; Sizes shown for the optional GPU OCR package. The web build passes the catalog's real values.
#ifndef GpuDownloadGiB
#define GpuDownloadGiB "1.57"
#endif
#ifndef GpuInstalledGiB
#define GpuInstalledGiB "3.58"
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
english.OcrPageTitle=OCR engines
english.OcrPageDescription=Choose how SubtitleYC reads subtitles from video.
english.OcrCpuCaption=CPU OCR (required)
english.OcrCpuDetail=Works on every PC. Always installed with the app.
english.OcrCpuLocked=CPU OCR is required and can't be turned off. GPU OCR uses it as a fallback.
english.OcrGpuCaption=Nvidia GPU OCR
english.OcrGpuDetail=Several times faster on a supported Nvidia card. %1 GiB download, %2 GiB installed. SubtitleYC downloads it the first time it opens, and you can pause it.
english.OcrGpuFound=Supported card found: %1, driver %2.
english.OcrGpuOldDriver=%1 found, but driver %2 is too old. Update the Nvidia driver to 576.57 or newer.
english.OcrGpuNone=No supported Nvidia card was found on this PC.
english.OcrRecheck=Check again
english.OcrTotalWithGpu=SubtitleYC downloads a further %1 GiB the first time it opens.
english.OcrTotalCpuOnly=Nothing more is downloaded after setup. GPU OCR stays available later in the app.
english.OcrReadyGpu=GPU OCR (%1 GiB) will download the first time SubtitleYC opens.
chinesesimplified.OcrPageTitle=OCR 引擎
chinesesimplified.OcrPageDescription=选择 SubtitleYC 从视频读取字幕的方式。
chinesesimplified.OcrCpuCaption=CPU OCR（必需）
chinesesimplified.OcrCpuDetail=适用于所有电脑，始终随应用一起安装。
chinesesimplified.OcrCpuLocked=CPU OCR 为必需组件，无法取消。GPU OCR 不可用时会改用它。
chinesesimplified.OcrGpuCaption=Nvidia GPU OCR
chinesesimplified.OcrGpuDetail=在受支持的 Nvidia 显卡上速度快数倍。下载 %1 GiB，安装后占用 %2 GiB。SubtitleYC 首次打开时会自动下载，可随时暂停。
chinesesimplified.OcrGpuFound=已找到受支持的显卡：%1，驱动 %2。
chinesesimplified.OcrGpuOldDriver=已找到 %1，但驱动 %2 版本过旧。请将 Nvidia 驱动更新到 576.57 或更高版本。
chinesesimplified.OcrGpuNone=此电脑上未找到受支持的 Nvidia 显卡。
chinesesimplified.OcrRecheck=重新检查
chinesesimplified.OcrTotalWithGpu=SubtitleYC 首次打开时还会下载 %1 GiB。
chinesesimplified.OcrTotalCpuOnly=安装完成后不会再下载其他内容。之后仍可在应用中安装 GPU OCR。
chinesesimplified.OcrReadyGpu=SubtitleYC 首次打开时将下载 GPU OCR（%1 GiB）。

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
; "1" asks the app to download GPU OCR on first launch; "0" means the user declined or the PC is not supported.
Root: HKLM; Subkey: "Software\SubtitleYC"; ValueType: string; ValueName: "InstallerGpuOcr"; ValueData: "{code:GpuOcrChoice}"; Flags: uninsdeletevalue

[Code]
{ ---- OCR engines page: CPU is always installed; GPU is offered when the PC supports it.
       Setup only records the choice. The app downloads GPU OCR itself on first launch,
       where an interrupted download can resume. ---- }
var
  OcrPage: TWizardPage;
  OcrCpuCheck, OcrGpuCheck: TNewCheckBox;
  OcrCpuNote, OcrGpuStatus, OcrTotalLabel: TNewStaticText;
  OcrRecheckButton: TNewButton;
  OcrGpuCompatible: Boolean;
  BaseReadyCaption: String;

function IsDigitAt(const Text: String; Index: Integer): Boolean;
begin
  Result := (Index >= 1) and (Index <= Length(Text)) and (Text[Index] >= '0') and (Text[Index] <= '9');
end;

function HasSeries(const CompactName, Prefix: String): Boolean;
var
  Position: Integer;
begin
  Position := Pos(Prefix, CompactName);
  Result := (Position > 0) and IsDigitAt(CompactName, Position + Length(Prefix)) and
    IsDigitAt(CompactName, Position + Length(Prefix) + 1);
end;

{ Same rule as the app: GeForce GTX 16xx, or RTX 20xx to 50xx. }
function IsSupportedCard(const Name: String): Boolean;
var
  Compact: String;
begin
  Compact := Uppercase(Name);
  StringChangeEx(Compact, ' ', '', True);
  Result := (Pos('GEFORCE', Compact) > 0) and (HasSeries(Compact, 'GTX16') or HasSeries(Compact, 'RTX20') or
    HasSeries(Compact, 'RTX30') or HasSeries(Compact, 'RTX40') or HasSeries(Compact, 'RTX50'));
end;

{ Driver 576.57 or newer, compared as two whole numbers like the app does. }
function IsSupportedDriver(const Driver: String): Boolean;
var
  Dot, Major, Minor: Integer;
begin
  Result := False;
  Dot := Pos('.', Driver);
  if Dot < 2 then Exit;
  Major := StrToIntDef(Copy(Driver, 1, Dot - 1), -1);
  Minor := StrToIntDef(Copy(Driver, Dot + 1, Length(Driver)), -1);
  if (Major < 0) or (Minor < 0) then Exit;
  Result := (Major > 576) or ((Major = 576) and (Minor >= 57));
end;

function FindNvidiaSmi: String;
begin
  Result := ExpandConstant('{sysnative}\nvidia-smi.exe');
  if not FileExists(Result) then
    Result := ExpandConstant('{commonpf64}\NVIDIA Corporation\NVSMI\nvidia-smi.exe');
  if not FileExists(Result) then
    Result := '';
end;

procedure DetectGpu(var Compatible: Boolean; var StatusText: String);
var
  Smi, Line, Name, Driver, OldName, OldDriver: String;
  Captured: TExecOutput;
  Lines: TArrayOfString;
  ResultCode, Index, Comma: Integer;
begin
  Compatible := False;
  StatusText := CustomMessage('OcrGpuNone');
  OldName := '';
  Smi := FindNvidiaSmi;
  if Smi = '' then Exit;
  try
    if not ExecAndCaptureOutput(Smi, '--query-gpu=name,driver_version --format=csv,noheader,nounits', '',
      SW_HIDE, ewWaitUntilTerminated, ResultCode, Captured) then Exit;
  except
    Exit;
  end;
  if ResultCode <> 0 then Exit;
  Lines := Captured.StdOut;
  for Index := 0 to GetArrayLength(Lines) - 1 do begin
    Line := Trim(Lines[Index]);
    Comma := Length(Line);
    while (Comma > 0) and (Line[Comma] <> ',') do Comma := Comma - 1;
    if Comma < 2 then Continue;
    Name := Trim(Copy(Line, 1, Comma - 1));
    Driver := Trim(Copy(Line, Comma + 1, Length(Line)));
    if not IsSupportedCard(Name) then Continue;
    if IsSupportedDriver(Driver) then begin
      Compatible := True;
      StatusText := FmtMessage(CustomMessage('OcrGpuFound'), [Name, Driver]);
      Exit;
    end;
    if OldName = '' then begin
      OldName := Name;
      OldDriver := Driver;
    end;
  end;
  if OldName <> '' then
    StatusText := FmtMessage(CustomMessage('OcrGpuOldDriver'), [OldName, OldDriver]);
end;

procedure UpdateOcrTotal;
begin
  if OcrGpuCheck.Checked then
    OcrTotalLabel.Caption := FmtMessage(CustomMessage('OcrTotalWithGpu'), ['{#GpuDownloadGiB}'])
  else
    OcrTotalLabel.Caption := CustomMessage('OcrTotalCpuOnly');
end;

procedure RefreshGpuState(TickWhenSupported: Boolean);
var
  StatusText: String;
begin
  DetectGpu(OcrGpuCompatible, StatusText);
  OcrGpuStatus.Caption := StatusText;
  OcrGpuCheck.Enabled := OcrGpuCompatible;
  if not OcrGpuCompatible then
    OcrGpuCheck.Checked := False
  else if TickWhenSupported then
    OcrGpuCheck.Checked := True;
  if OcrGpuCompatible then
    OcrGpuStatus.Font.Color := $003B6A0B
  else
    OcrGpuStatus.Font.Color := $00005A8A;
  { A card that is present but unsupported today may be fixed by a driver update. }
  OcrRecheckButton.Visible := (not OcrGpuCompatible) and (FindNvidiaSmi <> '');
  UpdateOcrTotal;
end;

procedure OcrCpuCheckClick(Sender: TObject);
begin
  { Looks like any other ticked option, but stays ticked and says why. }
  if not OcrCpuCheck.Checked then begin
    OcrCpuCheck.Checked := True;
    OcrCpuNote.Visible := True;
  end;
end;

procedure OcrGpuCheckClick(Sender: TObject);
begin
  UpdateOcrTotal;
end;

procedure OcrRecheckClick(Sender: TObject);
begin
  RefreshGpuState(True);
end;

function NewOcrText(const Caption: String; Top, Left: Integer; Muted: Boolean): TNewStaticText;
begin
  Result := TNewStaticText.Create(OcrPage);
  Result.Parent := OcrPage.Surface;
  Result.AutoSize := False;
  Result.WordWrap := True;
  Result.Left := Left;
  Result.Top := Top;
  Result.Width := OcrPage.SurfaceWidth - Left;
  Result.Height := ScaleY(30);
  Result.Caption := Caption;
  if Muted then Result.Font.Color := clGrayText;
end;

procedure CreateOcrPage;
var
  Indent, Top: Integer;
  Detail: TNewStaticText;
begin
  OcrPage := CreateCustomPage(wpSelectDir, CustomMessage('OcrPageTitle'), CustomMessage('OcrPageDescription'));
  Indent := ScaleX(20);
  Top := 0;

  OcrCpuCheck := TNewCheckBox.Create(OcrPage);
  OcrCpuCheck.Parent := OcrPage.Surface;
  OcrCpuCheck.SetBounds(0, Top, OcrPage.SurfaceWidth, ScaleY(20));
  OcrCpuCheck.Caption := CustomMessage('OcrCpuCaption');
  OcrCpuCheck.Font.Style := [fsBold];
  OcrCpuCheck.Checked := True;
  OcrCpuCheck.OnClick := @OcrCpuCheckClick;
  Top := Top + ScaleY(22);
  Detail := NewOcrText(CustomMessage('OcrCpuDetail'), Top, Indent, True);
  Detail.Height := ScaleY(16);
  Top := Top + ScaleY(18);
  OcrCpuNote := NewOcrText(CustomMessage('OcrCpuLocked'), Top, Indent, False);
  OcrCpuNote.Font.Color := $00005A8A;
  OcrCpuNote.Height := ScaleY(30);
  OcrCpuNote.Visible := False;
  Top := Top + ScaleY(38);

  OcrGpuCheck := TNewCheckBox.Create(OcrPage);
  OcrGpuCheck.Parent := OcrPage.Surface;
  OcrGpuCheck.SetBounds(0, Top, OcrPage.SurfaceWidth, ScaleY(20));
  OcrGpuCheck.Caption := CustomMessage('OcrGpuCaption');
  OcrGpuCheck.Font.Style := [fsBold];
  OcrGpuCheck.OnClick := @OcrGpuCheckClick;
  Top := Top + ScaleY(22);
  Detail := NewOcrText(FmtMessage(CustomMessage('OcrGpuDetail'), ['{#GpuDownloadGiB}', '{#GpuInstalledGiB}']), Top, Indent, True);
  Detail.Height := ScaleY(44);
  Top := Top + ScaleY(48);
  OcrGpuStatus := NewOcrText('', Top, Indent, False);
  OcrGpuStatus.Font.Style := [fsBold];
  OcrGpuStatus.Height := ScaleY(30);
  Top := Top + ScaleY(34);
  OcrRecheckButton := TNewButton.Create(OcrPage);
  OcrRecheckButton.Parent := OcrPage.Surface;
  OcrRecheckButton.SetBounds(Indent, Top, ScaleX(110), ScaleY(23));
  OcrRecheckButton.Caption := CustomMessage('OcrRecheck');
  OcrRecheckButton.OnClick := @OcrRecheckClick;
  Top := Top + ScaleY(34);

  OcrTotalLabel := NewOcrText('', Top, 0, True);
  OcrTotalLabel.Height := ScaleY(30);
  RefreshGpuState(True);
end;

{ Value handed to the app through the registry. Unattended installs never opt in. }
function GpuOcrChoice(Param: String): String;
begin
  if (not WizardSilent) and OcrGpuCompatible and OcrGpuCheck.Checked then
    Result := '1'
  else
    Result := '0';
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID <> wpReady then Exit;
  if BaseReadyCaption = '' then
    BaseReadyCaption := WizardForm.ReadyLabel.Caption;
  if OcrGpuCompatible and OcrGpuCheck.Checked then
    WizardForm.ReadyLabel.Caption := BaseReadyCaption + ' ' + FmtMessage(CustomMessage('OcrReadyGpu'), ['{#GpuDownloadGiB}'])
  else
    WizardForm.ReadyLabel.Caption := BaseReadyCaption;
end;

#ifdef WebInstaller
var
  DownloadPage: TDownloadWizardPage;
  PayloadReady: Boolean;
#endif

procedure InitializeWizard;
begin
  CreateOcrPage;
#ifdef WebInstaller
  DownloadPage := CreateDownloadPage('Download SubtitleYC {#AppVersion} and CPU OCR',
    'Internet is required. CPU OCR is included in setup.', nil);
  DownloadPage.ShowBaseNameInsteadOfUrl := True;
  WizardForm.ReadyLabel.Caption := 'Setup will download {#WebDownloadMiB} MiB and install SubtitleYC {#AppVersion} with CPU OCR ({#WebInstalledGiB} GiB). Internet is required.';
  if ActiveLanguage = 'chinesesimplified' then
    WizardForm.ReadyLabel.Caption := '安装程序将下载 {#WebDownloadMiB} MiB，并安装 SubtitleYC {#AppVersion} 和 CPU OCR（{#WebInstalledGiB} GiB）。需要联网。';
#endif
end;

#ifdef WebInstaller
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
