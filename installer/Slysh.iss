; Slysh per-user installer. Unsigned. Output is not committed.
; Build: ISCC.exe installer\Slysh.iss
; Payload is dist\payload next to this repo: light .venv, no weights.
; Paths are relative to this .iss file.

#define Payload "..\dist\payload"
#ifndef AppVersion
#define AppVersion "0.1.0"
#endif
#ifndef VersionInfoVersion
#define VersionInfoVersion "0.1.0.0"
#endif
#define MyAppUserModelId "Slysh.DesktopApp"

[Setup]
AppId={{B7E4C1A8-2F63-4D90-8A15-6C3E9B0D47F2}
AppName=Slysh
AppVersion={#AppVersion}
AppPublisher=Slysh
DefaultDirName={localappdata}\Programs\Slysh
DefaultGroupName=Slysh
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=Slysh-Setup
SetupIconFile={#Payload}\slysh.ico
UninstallDisplayIcon={app}\slysh.ico
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
VersionInfoProductName=Slysh
VersionInfoVersion={#VersionInfoVersion}

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; models/ — отдельная строка; при удалении по умолчанию сносится (см. InitializeUninstall).
Source: "{#Payload}\*"; DestDir: "{app}"; Excludes: "models,models\*,models\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Payload}\models\*"; DestDir: "{app}\models"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "redist\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: not WebView2Installed

[Dirs]
; Явная папка «Slysh» в меню Пуск (между Skype и Steam в «Все приложения»).
Name: "{group}";

[Icons]
Name: "{group}\Slysh"; Filename: "{app}\Slysh.exe"; IconFilename: "{app}\slysh.ico"; WorkingDir: "{app}"; AppUserModelID: "{#MyAppUserModelId}"
Name: "{group}\{cm:UninstallProgram,Slysh}"; Filename: "{uninstallexe}"; IconFilename: "{app}\slysh.ico"
Name: "{autodesktop}\Slysh"; Filename: "{app}\Slysh.exe"; IconFilename: "{app}\slysh.ico"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Microsoft Edge WebView2 Runtime…"; Check: not WebView2Installed; Flags: waituntilterminated
Filename: "{app}\Slysh.exe"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,Slysh}"; Flags: nowait postinstall skipifsilent runascurrentuser

[UninstallDelete]
; uv sync after install adds files outside the setup manifest — remove whole venv.
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\runtime"
Type: files; Name: "{app}\launch-last-error.txt"
Type: files; Name: "{app}\.install-ui-locale"
Type: files; Name: "{app}\.fresh-install"
Type: dirifempty; Name: "{app}"

[Code]
const
  SHCNE_ASSOCCHANGED = $08000000;
  SHCNF_IDLIST = $0000;

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

function WebView2Installed: Boolean;
var
  Ver: String;
const
  ClientKey = 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  ClientKey32 = 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
begin
  if RegQueryStringValue(HKLM, ClientKey, 'pv', Ver) and (Ver <> '') and (Ver <> '0.0.0.0') then
  begin
    Result := True;
    exit;
  end;
  if RegQueryStringValue(HKLM, ClientKey32, 'pv', Ver) and (Ver <> '') and (Ver <> '0.0.0.0') then
  begin
    Result := True;
    exit;
  end;
  if RegQueryStringValue(HKCU, ClientKey32, 'pv', Ver) and (Ver <> '') and (Ver <> '0.0.0.0') then
    Result := True
  else
    Result := False;
end;

function InitializeSetup(): Boolean;
begin
  { Обновление поверх существующей копии — не сбрасывать first-run через .fresh-install. }
  IsAppUpgrade :=
    FileExists(ExpandConstant('{app}\Slysh.exe')) or
    FileExists(ExpandConstant('{app}\.venv\Scripts\python.exe'));
  Result := True;
end;

procedure InitializeWizard;
begin
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
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (UiLocalePage <> nil) and (CurPageID = UiLocalePage.ID) then
  begin
    if UiLocaleCombo.ItemIndex = 1 then
      SelectedUiLocale := 'en'
    else
      SelectedUiLocale := 'ru';
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
    if UiLocaleCombo.ItemIndex = 1 then
      SelectedUiLocale := 'en'
    else
      SelectedUiLocale := 'ru';
    LocalePath := ExpandConstant('{app}\.install-ui-locale');
    SaveStringToFile(LocalePath, SelectedUiLocale, False);
    if not IsAppUpgrade then
      SaveStringToFile(ExpandConstant('{app}\.fresh-install'), '1', False);
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
    KeepModelsOnUninstall :=
      MsgBox(
        'Удалить папку models вместе с программой?' + #13#10 + #13#10 +
        '«Да» — удалить models (скачанные веса GigaAM/Whisper).' + #13#10 +
        '«Нет» — оставить models на диске.',
        mbConfirmation,
        MB_YESNO or MB_DEFBUTTON1) = IDNO;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if not KeepModelsOnUninstall then
      DelTree(ExpandConstant('{app}\models'), True, True, True);
  end;
end;
