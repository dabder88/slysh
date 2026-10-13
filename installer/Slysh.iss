; Slysh per-user installer. Unsigned. Output is not committed.
; Build: ISCC.exe installer\Slysh.iss
; Payload is dist\payload next to this repo: light .venv, no weights.
; Paths are relative to this .iss file.

#define Payload "..\dist\payload"
#ifndef AppVersion
#define AppVersion "1.0.0"
#endif
#ifndef VersionInfoVersion
#define VersionInfoVersion "1.0.0.0"
#endif
#ifndef SetupSegment
#define SetupSegment "ru"
#endif
#if SetupSegment == "en"
#define MyOutputBase "Slysh-Setup-" + AppVersion + "-en"
#define MyLicenseFile "LICENSE-EN.txt"
#else
#define MyOutputBase "Slysh-Setup-" + AppVersion + "-ru"
#define MyLicenseFile "LICENSE-RU.txt"
#endif
#define MyAppUserModelId "Slysh.DesktopApp"

[Setup]
AppId={{B7E4C1A8-2F63-4D90-8A15-6C3E9B0D47F2}
AppName=Slysh
AppVersion={#AppVersion}
AppPublisher=Сергачев Антон Константинович
DefaultDirName={localappdata}\Programs\Slysh
DefaultGroupName=Slysh
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename={#MyOutputBase}
SetupIconFile={#Payload}\slysh.ico
UninstallDisplayIcon={app}\slysh.ico
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
LicenseFile={#MyLicenseFile}
CloseApplications=no
VersionInfoProductName=Slysh
VersionInfoVersion={#VersionInfoVersion}

[Languages]
#if SetupSegment == "en"
Name: "english"; MessagesFile: "compiler:Default.isl"
#else
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; models/ — отдельная строка; при удалении по умолчанию сносится (см. InitializeUninstall).
Source: "{#Payload}\*"; DestDir: "{app}"; Excludes: "models,models\*,models\*,.venv,.venv\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Payload}\models\*"; DestDir: "{app}\models"; Flags: ignoreversion recursesubdirs createallsubdirs
#ifexist "redist\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
Source: "redist\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: not WebView2Installed
Source: "redist\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; DestDir: "{app}\redist"; Flags: ignoreversion; Check: not WebView2Installed
#else
Source: "redist\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: not WebView2Installed
#endif

[Dirs]

; Явная папка «Slysh» в меню Пуск (между Skype и Steam в «Все приложения»).
Name: "{group}";

[Icons]
Name: "{group}\Slysh"; Filename: "{app}\Slysh.exe"; IconFilename: "{app}\slysh.ico"; WorkingDir: "{app}"; AppUserModelID: "{#MyAppUserModelId}"
Name: "{group}\{cm:UninstallProgram,Slysh}"; Filename: "{uninstallexe}"; IconFilename: "{app}\slysh.ico"
Name: "{autodesktop}\Slysh"; Filename: "{app}\Slysh.exe"; IconFilename: "{app}\slysh.ico"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; WebView2 — только InstallWebView2IfNeeded в [Code] (не [Run]: bootstrapper падает «уже установлен»).
Filename: "{app}\Slysh.exe"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,Slysh}"; Flags: nowait postinstall skipifsilent runascurrentuser

[UninstallDelete]
; uv sync after install adds files outside the setup manifest — remove whole venv.
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\.venv-engine"
Type: filesandordirs; Name: "{app}\runtime"
Type: files; Name: "{app}\runtime-env.json"
Type: files; Name: "{app}\launch-last-error.txt"
Type: files; Name: "{app}\venv-check.log"
Type: files; Name: "{app}\.install-ui-locale"
Type: files; Name: "{app}\.payload-sync-pending"
Type: files; Name: "{app}\.venv-payload-sync"
Type: files; Name: "{app}\.fresh-install"
Type: dirifempty; Name: "{app}"

[Code]
const
  SHCNE_ASSOCCHANGED = $08000000;
  SHCNF_IDLIST = $0000;
  WebView2ClientId = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function SHChangeNotify(lEventId, uFlags: Integer; dwItem1, dwItem2: Integer): Integer;
  external 'SHChangeNotify@shell32.dll stdcall';

var
  UiLocalePage: TWizardPage;
  UiLocaleCombo: TNewComboBox;
  SelectedUiLocale: String;
  KeepModelsOnUninstall: Boolean;
  IsAppUpgrade: Boolean;

procedure RemoveLegacyStartMenuShortcut;
var
  LegacyLnk: String;
begin
  { Старый Setup клал один ярлык в корень Programs — мешает папке в «Все приложения». }
  LegacyLnk := ExpandConstant('{autoprograms}\Slysh.lnk');
  if FileExists(LegacyLnk) then
    DeleteFile(LegacyLnk);
end;

procedure RefreshStartMenuCache;
begin
  SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, 0, 0);
end;

procedure RemoveEngineVenvSlots;
var
  FindRec: TFindRec;
  AppDir: String;
  SlotPath: String;
begin
  AppDir := ExpandConstant('{app}');
  if FindFirst(AppDir + '\.venv-engine-*', FindRec) then
  begin
    try
      repeat
        if (FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
        begin
          SlotPath := AppDir + '\' + FindRec.Name;
          DelTree(SlotPath, True, True, True);
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

function DefaultInstallDir: String;
begin
  { Must match [Setup] DefaultDirName; app constant is not valid in InitializeSetup. }
  Result := ExpandConstant('{localappdata}\Programs\Slysh');
end;

procedure WriteStartMenuFolderDesktopIni;
var
  IniPath: String;
begin
  IniPath := ExpandConstant('{group}\desktop.ini');
  SaveStringToFile(
    IniPath,
    '[.ShellClassInfo]' + #13#10 +
    'LocalizedResourceName=Slysh' + #13#10 +
    'ConfirmFileOp=0' + #13#10,
    False);
end;

function WebView2RegistryHasPv(RootKey: Integer; const SubKey: String): Boolean;
var
  Ver: String;
begin
  Result :=
    RegQueryStringValue(RootKey, SubKey, 'pv', Ver) and
    (Ver <> '') and (Ver <> '0.0.0.0');
end;

function WebView2ExeOnDisk: Boolean;
var
  FindRec: TFindRec;
  BasePath: String;
begin
  BasePath := ExpandConstant('{pf32}\Microsoft\EdgeWebView\Application');
  if FindFirst(BasePath + '\*', FindRec) then
  try
    repeat
      if (FindRec.Name <> '.') and (FindRec.Name <> '..') and
         ((FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0) then
        if FileExists(BasePath + '\' + FindRec.Name + '\msedgewebview2.exe') then
        begin
          Result := True;
          exit;
        end;
    until not FindNext(FindRec);
  finally
    FindClose(FindRec);
  end;
  Result := False;
end;

function WebView2Installed: Boolean;
begin
  if WebView2RegistryHasPv(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + WebView2ClientId) then
  begin
    Result := True;
    exit;
  end;
  if WebView2RegistryHasPv(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WebView2ClientId) then
  begin
    Result := True;
    exit;
  end;
  if WebView2RegistryHasPv(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\ClientState\' + WebView2ClientId) then
  begin
    Result := True;
    exit;
  end;
  if WebView2RegistryHasPv(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\ClientState\' + WebView2ClientId) then
  begin
    Result := True;
    exit;
  end;
  if WebView2RegistryHasPv(HKCU, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + WebView2ClientId) then
  begin
    Result := True;
    exit;
  end;
  if WebView2RegistryHasPv(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WebView2ClientId) then
  begin
    Result := True;
    exit;
  end;
  if WebView2RegistryHasPv(HKCU, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\ClientState\' + WebView2ClientId) then
  begin
    Result := True;
    exit;
  end;
  if WebView2RegistryHasPv(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\ClientState\' + WebView2ClientId) then
  begin
    Result := True;
    exit;
  end;
  Result := WebView2ExeOnDisk;
end;

procedure InstallWebView2IfNeeded;
var
  ResultCode: Integer;
  Installer: String;
begin
  if WebView2Installed then
    exit;
  Installer := ExpandConstant('{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe');
  if not FileExists(Installer) then
    Installer := ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe');
  if not FileExists(Installer) then
    exit;
  WizardForm.StatusLabel.Caption := 'Microsoft Edge WebView2 Runtime…';
  WizardForm.Update;
  Exec(Installer, '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  { Не прерывать Setup: официальный bootstrapper возвращает ошибку, если runtime уже есть. }
end;

function InitializeSetup(): Boolean;
begin
  { Обновление поверх существующей копии — не сбрасывать first-run через .fresh-install. }
  IsAppUpgrade :=
    FileExists(DefaultInstallDir + '\Slysh.exe') or
    FileExists(DefaultInstallDir + '\.venv\Scripts\python.exe');
  Result := True;
end;

procedure InitializeWizard;
begin
#if SetupSegment == "en"
  UiLocalePage := CreateCustomPage(
    wpWelcome,
    'Interface language',
    'Choose the Slysh interface language. You can change it later in Settings.' + #13#10 +
    'Русский: выберите «Russian» ниже.');

  UiLocaleCombo := TNewComboBox.Create(UiLocalePage);
  UiLocaleCombo.Parent := UiLocalePage.Surface;
  UiLocaleCombo.Left := ScaleX(0);
  UiLocaleCombo.Top := ScaleY(24);
  UiLocaleCombo.Width := UiLocalePage.SurfaceWidth;
  UiLocaleCombo.Style := csDropDownList;
  UiLocaleCombo.Items.Add('English');
  UiLocaleCombo.Items.Add('Russian');
  UiLocaleCombo.ItemIndex := 0;
  SelectedUiLocale := 'en';
#else
  UiLocalePage := CreateCustomPage(
    wpWelcome,
    'Язык интерфейса / Interface language',
    'Выберите язык программы Slysh. Его можно сменить в «Настройках».' + #13#10 +
    'Choose the Slysh interface language. You can change it later in Settings.');

  UiLocaleCombo := TNewComboBox.Create(UiLocalePage);
  UiLocaleCombo.Parent := UiLocalePage.Surface;
  UiLocaleCombo.Left := ScaleX(0);
  UiLocaleCombo.Top := ScaleY(24);
  UiLocaleCombo.Width := UiLocalePage.SurfaceWidth;
  UiLocaleCombo.Style := csDropDownList;
  UiLocaleCombo.Items.Add('Русский / Russian');
  UiLocaleCombo.Items.Add('English');
  UiLocaleCombo.ItemIndex := 0;
  SelectedUiLocale := 'ru';
#endif
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (UiLocalePage <> nil) and (CurPageID = UiLocalePage.ID) then
  begin
#if SetupSegment == "en"
    if UiLocaleCombo.ItemIndex = 0 then
      SelectedUiLocale := 'en'
    else
      SelectedUiLocale := 'ru';
#else
    if UiLocaleCombo.ItemIndex = 1 then
      SelectedUiLocale := 'en'
    else
      SelectedUiLocale := 'ru';
#endif
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  LocalePath: String;
begin
  if CurStep = ssInstall then
    RemoveLegacyStartMenuShortcut;
  if CurStep = ssPostInstall then
  begin
    InstallWebView2IfNeeded;
#if SetupSegment == "en"
    if UiLocaleCombo.ItemIndex = 0 then
      SelectedUiLocale := 'en'
    else
      SelectedUiLocale := 'ru';
#else
    if UiLocaleCombo.ItemIndex = 1 then
      SelectedUiLocale := 'en'
    else
      SelectedUiLocale := 'ru';
#endif
    LocalePath := ExpandConstant('{app}\.install-ui-locale');
    SaveStringToFile(LocalePath, SelectedUiLocale, False);
    if not IsAppUpgrade then
      SaveStringToFile(ExpandConstant('{app}\.fresh-install'), '1', False);
    if IsAppUpgrade then
      SaveStringToFile(ExpandConstant('{app}\.payload-sync-pending'), '1', False);
    WriteStartMenuFolderDesktopIni;
    RefreshStartMenuCache;
  end;
end;

function InitializeUninstall(): Boolean;
begin
  { CreateInputOptionPage is install-only; use MsgBox during uninstall. }
  if UninstallSilent then
    KeepModelsOnUninstall := False
  else
#if SetupSegment == "en"
    KeepModelsOnUninstall :=
      MsgBox(
        'Remove the models folder with the program?' + #13#10 + #13#10 +
        'Yes — delete models (downloaded GigaAM/Whisper weights).' + #13#10 +
        'No — keep models on disk.',
        mbConfirmation,
        MB_YESNO or MB_DEFBUTTON1) = IDNO;
#else
    KeepModelsOnUninstall :=
      MsgBox(
        'Удалить папку models вместе с программой?' + #13#10 + #13#10 +
        '«Да» — удалить models (скачанные веса GigaAM/Whisper).' + #13#10 +
        '«Нет» — оставить models на диске.',
        mbConfirmation,
        MB_YESNO or MB_DEFBUTTON1) = IDNO;
#endif
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    RemoveEngineVenvSlots;
  if CurUninstallStep = usPostUninstall then
  begin
    if not KeepModelsOnUninstall then
      DelTree(ExpandConstant('{app}\models'), True, True, True);
  end;
end;
